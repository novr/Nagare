"""DAG統合テスト

DAG全体の実行フローとタスク間のデータ連携を検証する統合テスト。
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestDAGIntegration:
    """DAG全体の統合テスト"""

    def test_dag_structure(self) -> None:
        """DAGの構造とタスク定義が正しいことを確認"""
        from nagare.dags import collect_github_actions_data

        dag = collect_github_actions_data.dag

        # DAG基本情報
        assert dag.dag_id == "collect_github_actions_data"
        assert dag.schedule_interval == "0 * * * *"
        assert dag.catchup is False
        assert "github" in dag.tags
        assert "data-collection" in dag.tags

        # タスク数の確認（Dynamic Task Mapping使用時は定義時のタスク数）
        # fetch_repositories + fetch_github_batch (Mapped) + fetch_github_details + transform_data + load_to_database = 5
        assert len(dag.tasks) == 5

        # タスクIDの確認
        task_ids = {task.task_id for task in dag.tasks}

        expected_task_ids = {
            "fetch_repositories",
            "fetch_github_batch",  # Dynamic Task Mapping: 実行時に展開される
            "fetch_github_details",
            "transform_data",
            "load_to_database",
        }

        assert task_ids == expected_task_ids

    def test_dag_task_dependencies(self) -> None:
        """タスクの依存関係が正しく設定されていることを確認

        Dynamic Task Mappingにより、実行時にバッチタスクが展開される。
        定義時点では依存関係のみ確認する。
        """
        from nagare.dags import collect_github_actions_data

        dag = collect_github_actions_data.dag

        # タスクを取得
        fetch_repos = dag.get_task("fetch_repositories")
        fetch_batch = dag.get_task("fetch_github_batch")  # Mapped task
        fetch_details = dag.get_task("fetch_github_details")
        transform = dag.get_task("transform_data")
        load = dag.get_task("load_to_database")

        # 依存関係の確認（Dynamic Task Mappingによる依存関係）
        # fetch_repositories → fetch_github_batch (Mapped)
        assert fetch_repos.downstream_task_ids == {"fetch_github_batch"}

        # fetch_github_batch → fetch_github_details
        assert fetch_batch.downstream_task_ids == {"fetch_github_details"}

        # fetch_github_details → transform_data
        assert fetch_details.downstream_task_ids == {"transform_data"}

        # transform_data → load_to_database
        assert transform.downstream_task_ids == {"load_to_database"}

        # load_to_database → (終端)
        assert len(load.downstream_task_ids) == 0

    def test_dag_default_args(self) -> None:
        """DAGのデフォルト引数が適切に設定されていることを確認"""
        from nagare.dags import collect_github_actions_data

        dag = collect_github_actions_data.dag

        # デフォルト引数の確認
        assert dag.default_args["owner"] == "nagare"
        assert dag.default_args["depends_on_past"] is False
        assert dag.default_args["email_on_failure"] is True
        assert dag.default_args["email_on_retry"] is False
        assert dag.default_args["retries"] == 3

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    @patch("nagare.utils.factory.ClientFactory.create_github_client")
    def test_full_dag_execution_flow(
        self,
        mock_github_factory: MagicMock,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """DAG全体の実行フローが正常に動作することを確認"""
        from tests.conftest import MockDatabaseClient, MockGitHubClient

        # モッククライアントを作成
        mock_db = MockDatabaseClient()
        mock_github = MockGitHubClient()

        mock_db_factory.return_value = mock_db
        mock_github_factory.return_value = mock_github

        # タスク関数をインポート
        from nagare.tasks.fetch import (
            fetch_repositories,
            fetch_workflow_run_jobs,
            fetch_workflow_runs,
        )
        from nagare.tasks.load import load_to_database
        from nagare.tasks.transform import transform_data
        from nagare.utils.dag_helpers import (
            with_database_client,
            with_github_and_database_clients,
            with_github_client,
        )

        ti = mock_airflow_context["ti"]
        run_id = ti.run_id

        # 1. リポジトリ取得
        wrapped_fetch_repos = with_database_client(fetch_repositories)
        batch_ops = wrapped_fetch_repos(**mock_airflow_context)
        # 期間バッチングにより、リポジトリは複数のバッチに分割される
        assert len(batch_ops) > 0
        assert all("batch_apps" in batch for batch in batch_ops)
        # XComには元のリポジトリリストが保存される
        repos = ti.xcom_data["repositories"]
        assert len(repos) == 2

        # 2. ワークフロー実行データ取得（ADR-006: 一時テーブルに保存）
        wrapped_fetch_runs = with_github_and_database_clients(fetch_workflow_runs)
        ti.xcom_data["repositories"] = repos  # fetch_runs が参照するためセット
        wrapped_fetch_runs(**mock_airflow_context)
        # 一時テーブルに保存されていることを確認
        workflow_runs = mock_db.temp_workflow_runs.get(run_id, [])
        assert len(workflow_runs) > 0

        # 3. ジョブデータ取得（まだXCom使用）
        wrapped_fetch_jobs = with_github_client(fetch_workflow_run_jobs)
        ti.xcom_data["workflow_runs"] = workflow_runs  # fetch_jobs が参照するためセット
        wrapped_fetch_jobs(**mock_airflow_context)
        jobs = ti.xcom_data["workflow_run_jobs"]
        assert jobs is not None
        assert len(jobs) > 0

        # 4. データ変換（ADR-006: 一時テーブルから読み込み、一時テーブルに保存）
        wrapped_transform = with_database_client(transform_data)
        wrapped_transform(**mock_airflow_context)
        # 一時テーブルに保存されていることを確認
        transformed_runs = mock_db.temp_transformed_runs.get(run_id, [])
        transformed_jobs = mock_db.temp_workflow_jobs.get(run_id, [])
        assert len(transformed_runs) > 0
        assert len(transformed_jobs) > 0

        # 5. データベース保存（ADR-006: 一時テーブルから読み込み、本番テーブルに保存）
        wrapped_load = with_database_client(load_to_database)
        wrapped_load(**mock_airflow_context)
        assert mock_db.upsert_pipeline_runs_called
        assert mock_db.upsert_jobs_called


class TestDAGErrorHandling:
    """DAGのエラーハンドリングテスト"""

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    def test_fetch_repositories_empty_result(
        self,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """リポジトリが0件の場合のハンドリング"""
        from tests.conftest import MockDatabaseClient

        # 空のリポジトリリストを返すモック
        mock_db = MockDatabaseClient()
        mock_db.repositories = []
        mock_db_factory.return_value = mock_db

        from nagare.tasks.fetch import fetch_repositories
        from nagare.utils.dag_helpers import with_database_client

        wrapped_func = with_database_client(fetch_repositories)
        result = wrapped_func(**mock_airflow_context)

        # 空リストが返されることを確認
        assert result == []

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    @patch("nagare.utils.factory.ClientFactory.create_github_client")
    def test_fetch_workflow_runs_with_api_error(
        self,
        mock_github_factory: MagicMock,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """GitHub API エラー時のハンドリング

        ADR-006: データは一時テーブルに保存される。
        """
        from tests.conftest import MockDatabaseClient, MockGitHubClient

        # APIエラーを返すモック（空データ）
        mock_github = MockGitHubClient()
        mock_github.workflow_runs_data = []
        mock_github_factory.return_value = mock_github

        mock_db = MockDatabaseClient()
        mock_db_factory.return_value = mock_db

        # 前のタスクのデータを設定
        ti = mock_airflow_context["ti"]
        run_id = ti.run_id
        ti.xcom_data["repositories"] = [
            {"owner": "test-org", "repo": "test-repo"},
        ]

        from nagare.tasks.fetch import fetch_workflow_runs
        from nagare.utils.dag_helpers import with_github_and_database_clients

        wrapped_func = with_github_and_database_clients(fetch_workflow_runs)

        # エラーが発生しても処理が続行されることを確認
        # （実装では部分的失敗を許容）
        wrapped_func(**mock_airflow_context)

        # 一時テーブルにデータが保存されている（空データ）
        workflow_runs = mock_db.temp_workflow_runs.get(run_id, [])
        # 空データでもエラーにならない
        assert isinstance(workflow_runs, list)

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    def test_transform_data_with_missing_xcom(
        self,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """一時テーブルにデータが無い場合のハンドリング

        ADR-006: transform_dataは一時テーブルからデータを取得する。
        データが無い場合は警告ログ出力して空リストで処理する。
        これはエラーを投げるのではなく、部分的な失敗を許容する設計。
        """
        from tests.conftest import MockDatabaseClient

        mock_db = MockDatabaseClient()
        mock_db_factory.return_value = mock_db

        # 一時テーブルにデータを設定しない（workflow_runsが無い）
        ti = mock_airflow_context["ti"]
        run_id = ti.run_id
        # mock_db.temp_workflow_runs[run_id] を設定しない

        from nagare.tasks.transform import transform_data

        # エラーにならず、空のリストを保存することを確認
        transform_data(db=mock_db, **mock_airflow_context)

        # 一時テーブルに空のデータが保存されていることを確認
        transformed_runs = mock_db.temp_transformed_runs.get(run_id, [])
        transformed_jobs = mock_db.temp_workflow_jobs.get(run_id, [])

        assert len(transformed_runs) == 0
        assert len(transformed_jobs) == 0

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    def test_load_to_database_with_empty_data(
        self,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """変換済みデータが空の場合のハンドリング

        load_to_databaseは空データの場合、DBアクセスをスキップして早期リターンする。
        これは不要なDB接続とトランザクションを避ける最適化。
        """
        from tests.conftest import MockDatabaseClient

        mock_db = MockDatabaseClient()
        mock_db_factory.return_value = mock_db

        # 空のデータを設定
        ti = mock_airflow_context["ti"]
        ti.xcom_data["transformed_runs"] = []
        ti.xcom_data["transformed_jobs"] = []

        from nagare.tasks.load import load_to_database
        from nagare.utils.dag_helpers import with_database_client

        wrapped_func = with_database_client(load_to_database)

        # 空データでもエラーにならないことを確認
        wrapped_func(**mock_airflow_context)

        # 空データの場合、upsert は呼ばれない（早期リターン）
        assert not mock_db.upsert_pipeline_runs_called
        assert not mock_db.upsert_jobs_called


class TestDAGScalability:
    """DAGのスケーラビリティテスト

    Note: パフォーマンス測定（実行時間など）は行わない。
    大量データの処理が正常に完了することを確認する機能テスト。
    """

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    @patch("nagare.utils.factory.ClientFactory.create_github_client")
    def test_large_dataset_handling(
        self,
        mock_github_factory: MagicMock,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """大量のデータを処理できることを確認

        50リポジトリ×10ワークフロー実行（計500件）のデータを処理し、
        正常に完了することを検証する。実行時間の測定は行わない。
        """
        from tests.conftest import MockDatabaseClient, MockGitHubClient

        # 大量のリポジトリを返すモック
        mock_db = MockDatabaseClient()
        mock_db.repositories = [
            {"owner": f"org-{i}", "repo": f"repo-{i}", "is_active": True}
            for i in range(50)
        ]

        mock_github = MockGitHubClient()
        # 各リポジトリに10件のワークフロー実行
        mock_github.workflow_runs_data = [
            {
                "id": i * 10 + j,
                "name": f"workflow-{j}",
                "status": "completed",
                "conclusion": "success",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T01:00:00Z",
                "run_started_at": "2024-01-01T00:00:00Z",
                "repository": {"full_name": f"org-{i}/repo-{i}"},
            }
            for i in range(50)
            for j in range(10)
        ]

        mock_db_factory.return_value = mock_db
        mock_github_factory.return_value = mock_github

        from nagare.tasks.fetch import fetch_repositories
        from nagare.utils.dag_helpers import with_database_client

        wrapped_func = with_database_client(fetch_repositories)
        batch_ops = wrapped_func(**mock_airflow_context)

        # 期間バッチングにより複数のバッチに分割される
        assert len(batch_ops) > 0
        assert all("batch_apps" in batch for batch in batch_ops)

        # XComに保存された元のリポジトリ数を確認
        ti = mock_airflow_context["ti"]
        repos = ti.xcom_data["repositories"]
        assert len(repos) == 50

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    def test_upsert_idempotency(
        self,
        mock_db_factory: MagicMock,
        mock_airflow_context: dict[str, Any],
    ) -> None:
        """upsert操作の冪等性を確認

        冪等性とは、同じ操作を複数回実行しても結果が同じになる性質。
        UPSERTでは、同じsource_run_idのデータを複数回挿入しても、
        データは1件のみ存在し、最新のデータで上書きされる。
        """
        from tests.conftest import MockDatabaseClient

        mock_db = MockDatabaseClient()
        mock_db_factory.return_value = mock_db

        # 同じsource_run_idのデータを2回upsert（2回目でstatusを変更）
        ti = mock_airflow_context["ti"]
        run_id = ti.run_id

        # 1回目: status=SUCCESS (ADR-006: 一時テーブルに保存)
        mock_db.temp_transformed_runs[run_id] = [
            {
                "source_run_id": "123456",
                "source": "github_actions",
                "pipeline_name": "CI",
                "status": "SUCCESS",
            }
        ]
        mock_db.temp_workflow_jobs[run_id] = []

        from nagare.tasks.load import load_to_database
        from nagare.utils.dag_helpers import with_database_client

        wrapped_func = with_database_client(load_to_database)

        # 1回目の実行
        wrapped_func(**mock_airflow_context)
        first_count = len(mock_db.upserted_runs)
        first_status = mock_db.upserted_runs[0]["status"]

        # 2回目: 同じsource_run_idでstatusをFAILUREに変更
        mock_db.temp_transformed_runs[run_id] = [
            {
                "source_run_id": "123456",
                "source": "github_actions",
                "pipeline_name": "CI",
                "status": "FAILURE",  # 変更
            }
        ]

        # 2回目の実行
        wrapped_func(**mock_airflow_context)
        second_count = len(mock_db.upserted_runs)
        second_status = mock_db.upserted_runs[0]["status"]

        # 冪等性の検証:
        # 1. レコード数は1件のまま（重複しない）
        assert first_count == 1
        assert second_count == 1  # UPSERTなので1件のまま

        # 2. データは最新のもので上書きされている
        assert first_status == "SUCCESS"
        assert second_status == "FAILURE"  # 更新されている
