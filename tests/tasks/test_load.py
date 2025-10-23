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
