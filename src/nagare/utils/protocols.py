"""依存性注入用のProtocol定義

テストやモック作成を容易にするため、各クライアントのインターフェースを定義する。

## モック戦略について

このプロジェクトでは以下のモック機能を提供している:

1. **本番環境**: ConnectionRegistryからDatabaseConnection/GitHubConnectionを取得
   - 環境変数から接続情報を読み込む
   - 実際のPostgreSQL/GitHub APIに接続

2. **テスト環境**: MockFactory経由でMock*Clientを注入
   - ユニットテスト時に依存性注入で使用
   - 呼び出し履歴とパラメータを記録
   - テスト内でアサーションが可能
"""

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseClientProtocol(Protocol):
    """DatabaseClientのインターフェース

    このProtocolを実装するクラス:
    - DatabaseClient (src/nagare/utils/database.py)
    - MockDatabaseClient (tests/conftest.py) - テスト用
    """

    def get_repositories(self, source: str | None = None) -> list[dict[str, str]]:
        """監視対象リポジトリのリストを取得する

        Args:
            source: ソースタイプでフィルタ（オプション）。例: "github_actions", "bitrise"
        """
        ...

    def get_latest_run_timestamp(self, owner: str, repo: str) -> datetime | None:
        """指定リポジトリの最新パイプライン実行タイムスタンプを取得する

        Args:
            owner: リポジトリオーナー
            repo: リポジトリ名

        Returns:
            最新の started_at タイムスタンプ。データがない場合はNone
        """
        ...

    def upsert_pipeline_runs(self, runs: list[dict[str, Any]]) -> None:
        """pipeline_runsテーブルにデータをUPSERTする"""
        ...

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """jobsテーブルにデータをUPSERTする"""
        ...

    def get_oldest_run_timestamp(self, source: str | None = None) -> datetime | None:
        """全リポジトリの最も古いパイプライン実行タイムスタンプを取得する

        Args:
            source: ソースタイプでフィルタ（オプション）

        Returns:
            最も古い started_at タイムスタンプ。データがない場合はNone
        """
        ...

    # 一時テーブル関連メソッド（ADR-006: XCom削減のため）

    def insert_temp_workflow_runs(
        self, runs: list[dict[str, Any]], task_id: str, run_id: str
    ) -> None:
        """一時テーブルにワークフロー実行データを保存する

        Args:
            runs: ワークフロー実行データのリスト（GitHub/Bitrise APIレスポンス）
            task_id: バッチタスクID（例: fetch_github_batch_0）
            run_id: DAG run ID（Airflow生成、例: manual__2025-11-04T10:00:00）
        """
        ...

    def get_temp_workflow_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから全ワークフロー実行データを取得する

        Args:
            run_id: DAG run ID

        Returns:
            ワークフロー実行データのリスト
        """
        ...

    def insert_temp_transformed_runs(
        self, runs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルに変換済みデータを保存する

        Args:
            runs: 変換済みワークフロー実行データのリスト（汎用データモデル形式）
            run_id: DAG run ID
        """
        ...

    def get_temp_transformed_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから変換済みデータを取得する

        Args:
            run_id: DAG run ID

        Returns:
            変換済みワークフロー実行データのリスト
        """
        ...

    def insert_temp_workflow_jobs(
        self, jobs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルにジョブデータを保存する

        Args:
            jobs: ジョブデータのリスト
            run_id: DAG run ID
        """
        ...

    def get_temp_workflow_jobs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルからジョブデータを取得する

        Args:
            run_id: DAG run ID

        Returns:
            ジョブデータのリスト
        """
        ...

    def move_temp_to_production(self, run_id: str) -> None:
        """一時テーブルから本番テーブルへデータを移動する

        トランザクション内で呼び出すこと。
        temp_transformed_runs → pipeline_runs
        temp_workflow_jobs → jobs

        Args:
            run_id: DAG run ID
        """
        ...

    def cleanup_temp_tables(self, run_id: str | None = None, days: int = 7) -> int:
        """一時テーブルをクリーンアップする

        Args:
            run_id: 特定のDAG runのデータを削除（Noneの場合は古いデータを削除）
            days: 保持日数（run_idがNoneの場合のみ有効）

        Returns:
            削除されたレコード数の合計
        """
        ...

    def transaction(self) -> AbstractContextManager[None]:
        """トランザクションを開始する

        Context managerとして使用し、正常終了時はコミット、例外発生時はロールバック。

        Yields:
            None

        Example:
            with db.transaction():
                db.upsert_pipeline_runs(runs)
                db.upsert_jobs(jobs)
                # 両方成功した場合のみコミット
        """
        ...

    def close(self) -> None:
        """データベース接続をクローズする"""
        ...

    def __enter__(self) -> "DatabaseClientProtocol":
        """Context manager: with文でのエントリーポイント"""
        ...

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理"""
        ...


@runtime_checkable
class GitHubClientProtocol(Protocol):
    """GitHubClientのインターフェース

    このProtocolを実装するクラス:
    - GitHubClient (src/nagare/utils/github_client.py)
    - MockGitHubClient (tests/conftest.py) - テスト用
    """

    def get_platform(self) -> str:
        """プラットフォーム識別子を返す

        Returns:
            str: Platform.GITHUB
        """
        ...

    def get_workflow_runs(
        self,
        owner: str,
        repo: str,
        created_after: datetime | None = None,
        max_results: int = 1000,
    ) -> list[dict[str, Any]]:
        """ワークフロー実行データを取得する"""
        ...

    def get_workflow_run_jobs(
        self, owner: str, repo: str, run_id: int, max_results: int = 1000
    ) -> list[dict[str, Any]]:
        """ワークフロー実行のジョブ情報を取得する"""
        ...

    def close(self) -> None:
        """クライアントをクローズする"""
        ...

    def __enter__(self) -> "GitHubClientProtocol":
        """Context manager: with文でのエントリーポイント"""
        ...

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理"""
        ...


@runtime_checkable
class BitriseClientProtocol(Protocol):
    """BitriseClientのインターフェース

    このProtocolを実装するクラス:
    - BitriseClient (src/nagare/utils/bitrise_client.py)
    - MockBitriseClient (tests/conftest.py) - テスト用（将来追加予定）
    """

    def get_platform(self) -> str:
        """プラットフォーム識別子を返す

        Returns:
            str: Platform.BITRISE
        """
        ...

    def get_apps(self, limit: int = 50) -> list[dict[str, Any]]:
        """アプリ一覧を取得する"""
        ...

    def get_builds(
        self,
        app_slug: str,
        branch: str | None = None,
        workflow: str | None = None,
        created_after: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """アプリのビルド一覧を取得する"""
        ...

    def get_build(self, app_slug: str, build_slug: str) -> dict[str, Any]:
        """特定のビルドの詳細情報を取得する"""
        ...

    def get_build_log(self, app_slug: str, build_slug: str) -> str:
        """ビルドのログを取得する"""
        ...

    def close(self) -> None:
        """クライアントをクローズする"""
        ...

    def __enter__(self) -> "BitriseClientProtocol":
        """Context manager: with文でのエントリーポイント"""
        ...

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理"""
        ...


@runtime_checkable
class XcodeCloudClientProtocol(Protocol):
    """XcodeCloudClientのインターフェース

    このProtocolを実装するクラス:
    - XcodeCloudClient (src/nagare/utils/xcode_cloud_client.py)
    - MockXcodeCloudClient (tests/conftest.py) - テスト用（将来追加予定）
    """

    def get_platform(self) -> str:
        """プラットフォーム識別子を返す

        Returns:
            str: Platform.XCODE_CLOUD
        """
        ...

    def list_apps(self, limit: int = 200) -> list[dict[str, Any]]:
        """アプリ一覧を取得する

        Args:
            limit: 1リクエストあたりの取得件数（最大200）

        Returns:
            アプリ情報のリスト
        """
        ...

    def list_ci_builds_for_app(
        self,
        app_id: str,
        limit: int = 200,
        filter_created_date_start: str | None = None,
        filter_created_date_end: str | None = None,
    ) -> list[dict[str, Any]]:
        """特定アプリのCI/CDビルド一覧を取得する

        Args:
            app_id: アプリID
            limit: 1リクエストあたりの取得件数（最大200）
            filter_created_date_start: 開始日時フィルタ（ISO8601形式）
            filter_created_date_end: 終了日時フィルタ（ISO8601形式）

        Returns:
            ビルド情報のリスト
        """
        ...

    def get_build(self, build_id: str) -> dict[str, Any]:
        """特定ビルドの詳細情報を取得する

        Args:
            build_id: ビルドID

        Returns:
            ビルド詳細情報
        """
        ...

    def close(self) -> None:
        """クライアントをクローズする"""
        ...

    def __enter__(self) -> "XcodeCloudClientProtocol":
        """Context manager: with文でのエントリーポイント"""
        ...

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理"""
        ...
