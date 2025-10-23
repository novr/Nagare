"""load.pyのユニットテスト"""

from typing import Any

from tests.conftest import MockDatabaseClient


def test_load_to_database_with_mock(
    mock_db_client: MockDatabaseClient, mock_airflow_context: dict[str, Any]
) -> None:
    """load_to_database関数がモックDBClientで動作することを確認"""
    from nagare.tasks.load import load_to_database

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["transformed_runs"] = [
        {
            "source_run_id": "123456",
            "source": "github_actions",
            "pipeline_name": "CI",
            "status": "SUCCESS",
            "trigger_event": "push",
            "repository_owner": "test-org",
            "repository_name": "test-repo",
            "branch_name": "main",
            "commit_sha": "abc123",
            "started_at": "2024-01-01T00:00:00+00:00",
            "completed_at": "2024-01-01T00:10:00+00:00",
            "duration_ms": 600000,
            "url": "https://github.com/test-org/test-repo/actions/runs/123456",
        }
    ]

    # モックを注入して実行
    load_to_database(db=mock_db_client, **mock_airflow_context)

    # 検証
    assert mock_db_client.upsert_pipeline_runs_called
    assert len(mock_db_client.upserted_runs) == 1
    assert mock_db_client.upserted_runs[0]["source_run_id"] == "123456"


def test_load_to_database_with_jobs(
    mock_db_client: MockDatabaseClient, mock_airflow_context: dict[str, Any]
) -> None:
    """load_to_database関数がジョブデータもロードできることを確認"""
    from nagare.tasks.load import load_to_database

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["transformed_runs"] = [
        {
            "source_run_id": "123456",
            "source": "github_actions",
            "status": "SUCCESS",
        }
    ]
    ti.xcom_data["transformed_jobs"] = [
        {
            "source_job_id": "789",
            "source_run_id": "123456",
            "source": "github_actions",
            "job_name": "build",
            "status": "SUCCESS",
        }
    ]

    # モックを注入して実行
    load_to_database(db=mock_db_client, **mock_airflow_context)

    # 検証: runsとjobsの両方が保存される
    assert mock_db_client.upsert_pipeline_runs_called
    assert len(mock_db_client.upserted_runs) == 1
    assert mock_db_client.upserted_runs[0]["source_run_id"] == "123456"

    assert mock_db_client.upsert_jobs_called
    assert len(mock_db_client.upserted_jobs) == 1
    assert mock_db_client.upserted_jobs[0]["source_job_id"] == "789"


def test_load_to_database_uses_transaction(
    mock_db_client: MockDatabaseClient, mock_airflow_context: dict[str, Any]
) -> None:
    """load_to_database関数がトランザクションを使用することを確認"""
    from nagare.tasks.load import load_to_database

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["transformed_runs"] = [
        {"source_run_id": "123", "status": "SUCCESS"}
    ]
    ti.xcom_data["transformed_jobs"] = [
        {"source_job_id": "456", "source_run_id": "123", "status": "SUCCESS"}
    ]

    # モックを注入して実行
    load_to_database(db=mock_db_client, **mock_airflow_context)

    # トランザクションが使用されたことを確認
    assert mock_db_client.transaction_called
    assert mock_db_client.transaction_call_count == 1
    assert mock_db_client.transaction_committed
    assert not mock_db_client.transaction_rolled_back
