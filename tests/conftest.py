"""Pytest設定とテスト用フィクスチャ

このモジュールはユニットテスト用のモッククラスとフィクスチャを提供する。

## モック戦略

- **MockDatabaseClient**: DatabaseClientProtocolの実装
  - メソッド呼び出しをトラッキング
  - 渡されたデータを保存してアサーション可能

- **MockGitHubClient**: GitHubClientProtocolの実装
  - メソッド呼び出しと引数をトラッキング
  - 固定のテストデータを返却

- **mock_airflow_context**: Airflowのタスクコンテキストをモック
  - XCom機能をメモリ内で再現
  - TaskInstanceとexecution_dateを提供
"""

from datetime import datetime
from typing import Any

import pytest


class MockDatabaseClient:
    """テスト用のモックDatabaseClient

    DatabaseClientProtocolを実装し、ユニットテストで使用する。
    メソッド呼び出しを追跡し、渡されたデータを保存する。

    注意: 実際の開発環境では src/nagare/utils/database_mock.py の
    MockDatabaseClient を使用すること。

    Attributes:
        get_repositories_called: get_repositories()が呼ばれたかどうか
        get_repositories_call_count: get_repositories()の呼び出し回数
        upsert_pipeline_runs_called: upsert_pipeline_runs()が呼ばれたかどうか
        upsert_pipeline_runs_call_count: upsert_pipeline_runs()の呼び出し回数
        upserted_runs: upsert_pipeline_runs()に渡されたデータ
        upsert_jobs_called: upsert_jobs()が呼ばれたかどうか
        upsert_jobs_call_count: upsert_jobs()の呼び出し回数
        upserted_jobs: upsert_jobs()に渡されたデータ
        close_called: close()が呼ばれたかどうか
    """

    def __init__(self) -> None:
        # get_repositories tracking
        self.get_repositories_called = False
        self.get_repositories_call_count = 0

        # upsert_pipeline_runs tracking
        self.upsert_pipeline_runs_called = False
        self.upsert_pipeline_runs_call_count = 0
        self.upserted_runs: list[dict[str, Any]] = []

        # upsert_jobs tracking
        self.upsert_jobs_called = False
        self.upsert_jobs_call_count = 0
        self.upserted_jobs: list[dict[str, Any]] = []

        # close tracking
        self.close_called = False

    def get_repositories(self) -> list[dict[str, str]]:
        """モックのリポジトリリストを返す"""
        self.get_repositories_called = True
        self.get_repositories_call_count += 1
        return [
            {"owner": "test-org", "repo": "test-repo-1"},
            {"owner": "test-org", "repo": "test-repo-2"},
        ]

    def upsert_pipeline_runs(self, runs: list[dict[str, Any]]) -> None:
        """モックのUPSERT処理

        Args:
            runs: UPSERTするパイプライン実行データのリスト
        """
        self.upsert_pipeline_runs_called = True
        self.upsert_pipeline_runs_call_count += 1
        self.upserted_runs = runs

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """モックのUPSERT処理（ジョブ）

        Args:
            jobs: UPSERTするジョブデータのリスト
        """
        self.upsert_jobs_called = True
        self.upsert_jobs_call_count += 1
        self.upserted_jobs = jobs

    def close(self) -> None:
        """モックのクローズ処理"""
        self.close_called = True

    def __enter__(self) -> "MockDatabaseClient":
        """Context manager: with文でのエントリーポイント"""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理"""
        self.close()


class MockGitHubClient:
    """テスト用のモックGitHubClient

    GitHubClientProtocolを実装し、ユニットテストで使用する。
    メソッド呼び出しと引数を追跡し、固定のテストデータを返却する。

    Attributes:
        get_workflow_runs_called: get_workflow_runs()が呼ばれたかどうか
        get_workflow_runs_call_count: get_workflow_runs()の呼び出し回数
        get_workflow_runs_calls: get_workflow_runs()の呼び出し履歴
        get_workflow_run_jobs_called: get_workflow_run_jobs()が呼ばれたかどうか
        get_workflow_run_jobs_call_count: get_workflow_run_jobs()の呼び出し回数
        get_workflow_run_jobs_calls: get_workflow_run_jobs()の呼び出し履歴
        close_called: close()が呼ばれたかどうか
    """

    def __init__(self) -> None:
        # get_workflow_runs tracking
        self.get_workflow_runs_called = False
        self.get_workflow_runs_call_count = 0
        self.get_workflow_runs_calls: list[dict[str, Any]] = []

        # get_workflow_run_jobs tracking
        self.get_workflow_run_jobs_called = False
        self.get_workflow_run_jobs_call_count = 0
        self.get_workflow_run_jobs_calls: list[dict[str, Any]] = []

        # close tracking
        self.close_called = False

    def get_workflow_runs(
        self,
        owner: str,
        repo: str,
        created_after: datetime | None = None,
        max_results: int = 1000,
    ) -> list[dict[str, Any]]:
        """モックのワークフロー実行データを返す

        Args:
            owner: リポジトリのオーナー
            repo: リポジトリ名
            created_after: この日時以降に作成されたrunを取得
            max_results: 取得する最大件数

        Returns:
            ワークフロー実行データのリスト
        """
        self.get_workflow_runs_called = True
        self.get_workflow_runs_call_count += 1
        self.get_workflow_runs_calls.append(
            {
                "owner": owner,
                "repo": repo,
                "created_after": created_after,
                "max_results": max_results,
            }
        )
        return [
            {
                "id": 123456,
                "name": "CI",
                "head_branch": "main",
                "head_sha": "abc123",
                "status": "completed",
                "conclusion": "success",
                "event": "push",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:10:00Z",
                "run_started_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test-org/test-repo/actions/runs/123456",
            }
        ]

    def get_workflow_run_jobs(
        self, owner: str, repo: str, run_id: int, max_results: int = 1000
    ) -> list[dict[str, Any]]:
        """モックのジョブデータを返す

        Args:
            owner: リポジトリのオーナー
            repo: リポジトリ名
            run_id: ワークフロー実行ID
            max_results: 取得する最大件数

        Returns:
            ジョブデータのリスト
        """
        self.get_workflow_run_jobs_called = True
        self.get_workflow_run_jobs_call_count += 1
        self.get_workflow_run_jobs_calls.append(
            {"owner": owner, "repo": repo, "run_id": run_id, "max_results": max_results}
        )
        return [
            {
                "id": 789,
                "run_id": run_id,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:05:00Z",
                "html_url": f"https://github.com/test-org/test-repo/actions/runs/{run_id}/jobs/789",
            }
        ]

    def close(self) -> None:
        """モックのクローズ処理"""
        self.close_called = True

    def __enter__(self) -> "MockGitHubClient":
        """Context manager: with文でのエントリーポイント"""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理"""
        self.close()


@pytest.fixture
def mock_db_client() -> MockDatabaseClient:
    """テスト用のモックDatabaseClientフィクスチャ"""
    return MockDatabaseClient()


@pytest.fixture
def mock_github_client() -> MockGitHubClient:
    """テスト用のモックGitHubClientフィクスチャ"""
    return MockGitHubClient()


@pytest.fixture
def mock_airflow_context() -> dict[str, Any]:
    """テスト用のモックAirflowコンテキスト

    Airflowのタスクコンテキストをメモリ内で再現する。
    XCom機能（タスク間データ受け渡し）を辞書で実装。

    Returns:
        以下のキーを含む辞書:
        - ti (MockTaskInstance): タスクインスタンスのモック
        - execution_date (datetime): 実行日時
    """

    class MockTaskInstance:
        """Airflow TaskInstanceのモック

        Attributes:
            xcom_data: XComデータを保存する辞書
        """

        def __init__(self) -> None:
            self.xcom_data: dict[str, Any] = {}

        def xcom_push(self, key: str, value: Any) -> None:
            """XComにデータを保存する

            Args:
                key: データのキー
                value: 保存する値
            """
            self.xcom_data[key] = value

        def xcom_pull(self, task_ids: str, key: str) -> Any:
            """XComからデータを取得する

            Args:
                task_ids: タスクID（このモックでは未使用）
                key: データのキー

            Returns:
                保存されたデータ、存在しない場合はNone
            """
            return self.xcom_data.get(key)

    return {
        "ti": MockTaskInstance(),
        "execution_date": datetime(2024, 1, 1, 0, 0, 0),
    }
