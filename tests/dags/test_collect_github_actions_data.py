"""collect_github_actions_data.py DAGのユニットテスト"""

from typing import Any


def test_dag_imports() -> None:
    """DAGファイルがインポートできることを確認"""
    from nagare.dags import collect_github_actions_data

    assert collect_github_actions_data.dag is not None


def test_with_database_client_wrapper(mock_airflow_context: dict[str, Any]) -> None:
    """with_database_clientヘルパー関数が動作することを確認"""
    from nagare.tasks.fetch import fetch_repositories
    from nagare.utils.dag_helpers import with_database_client
    from nagare.utils.factory import ClientFactory, set_factory
    from tests.conftest import MockDatabaseClient

    # モック用のFactoryを作成
    class MockFactory(ClientFactory):
        @staticmethod
        def create_database_client() -> MockDatabaseClient:
            return MockDatabaseClient()

    # Factoryを差し替え
    original_factory = ClientFactory()
    set_factory(MockFactory())

    try:
        # ヘルパー関数でラップして実行
        wrapped_func = with_database_client(fetch_repositories)
        result = wrapped_func(**mock_airflow_context)

        # 結果を検証（期間バッチングにより、リポジトリは複数のバッチに分割される）
        assert len(result) > 0
        assert all("batch_apps" in batch for batch in result)
        # 各バッチに2つのリポジトリが含まれることを確認
        for batch in result:
            assert len(batch["batch_apps"]) == 2
            assert batch["batch_apps"][0]["owner"] == "test-org"
            assert batch["batch_apps"][0]["repo"] == "test-repo-1"

    finally:
        # 元に戻す
        set_factory(original_factory)


def test_with_github_client_wrapper(mock_airflow_context: dict[str, Any]) -> None:
    """with_github_and_database_clientsヘルパー関数が動作することを確認"""
    from nagare.tasks.fetch import fetch_workflow_runs
    from nagare.utils.dag_helpers import with_github_and_database_clients
    from nagare.utils.factory import ClientFactory, set_factory
    from tests.conftest import MockDatabaseClient, MockGitHubClient

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["repositories"] = [
        {"owner": "test-org", "repo": "test-repo-1"},
    ]

    # モック用のFactoryを作成（同一インスタンスを返すように）
    mock_db = MockDatabaseClient()

    class MockFactory(ClientFactory):
        @staticmethod
        def create_github_client(conn_id: str | None = None) -> MockGitHubClient:
            return MockGitHubClient()

        @staticmethod
        def create_database_client(conn_id: str | None = None) -> MockDatabaseClient:
            return mock_db

    # Factoryを差し替え
    original_factory = ClientFactory()
    set_factory(MockFactory())

    try:
        # ヘルパー関数でラップして実行
        wrapped_func = with_github_and_database_clients(fetch_workflow_runs)
        wrapped_func(**mock_airflow_context)

        # 一時テーブルに保存されたか確認（ADR-006準拠）
        run_id = ti.run_id
        workflow_runs = mock_db.temp_workflow_runs.get(run_id, [])
        assert len(workflow_runs) == 1
        assert workflow_runs[0]["id"] == 123456

    finally:
        # 元に戻す
        set_factory(original_factory)


def test_with_database_client_load_wrapper(mock_airflow_context: dict[str, Any]) -> None:
    """with_database_clientヘルパー関数がload_to_databaseで動作することを確認"""
    from nagare.tasks.load import load_to_database
    from nagare.utils.dag_helpers import with_database_client
    from nagare.utils.factory import ClientFactory, set_factory
    from tests.conftest import MockDatabaseClient

    # 前のタスクのデータを設定（ADR-006準拠で一時テーブルを使用）
    ti = mock_airflow_context["ti"]
    run_id = ti.run_id

    # モック用のFactoryを作成
    mock_db = MockDatabaseClient()
    mock_db.temp_transformed_runs[run_id] = [
        {
            "source_run_id": "123456",
            "source": "github_actions",
            "pipeline_name": "CI",
            "status": "SUCCESS",
        }
    ]

    class MockFactory(ClientFactory):
        @staticmethod
        def create_database_client() -> MockDatabaseClient:
            return mock_db

    # Factoryを差し替え
    original_factory = ClientFactory()
    set_factory(MockFactory())

    try:
        # ヘルパー関数でラップして実行
        wrapped_func = with_database_client(load_to_database)
        wrapped_func(**mock_airflow_context)

        # upsert_pipeline_runsが呼ばれたことを確認
        assert mock_db.upsert_pipeline_runs_called
        assert len(mock_db.upserted_runs) == 1

    finally:
        # 元に戻す
        set_factory(original_factory)
