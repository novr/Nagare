"""依存性注入用のProtocol定義

テストやモック作成を容易にするため、各クライアントのインターフェースを定義する。

## モック戦略について

このプロジェクトでは2レベルのモック機能を提供している:

1. **環境変数ベースのモック** (database.py の USE_DB_MOCK)
   - 開発環境でPostgreSQL未接続時に使用
   - 実際のファイル (YAML/JSON) から設定を読み込む
   - ログ出力により動作を確認可能

2. **テスト注入モック** (conftest.py の Mock*Client)
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

    def get_repositories(self) -> list[dict[str, str]]:
        """監視対象リポジトリのリストを取得する"""
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
