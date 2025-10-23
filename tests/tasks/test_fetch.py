"""fetch.pyのユニットテスト"""

from typing import Any

from tests.conftest import MockDatabaseClient, MockGitHubClient


def test_fetch_repositories_with_mock(
    mock_db_client: MockDatabaseClient, mock_airflow_context: dict[str, Any]
) -> None:
    """fetch_repositories関数がモックDBClientで動作することを確認"""
    from nagare.tasks.fetch import fetch_repositories

    # モックを注入して実行
    result = fetch_repositories(db=mock_db_client, **mock_airflow_context)

    # 検証
    assert mock_db_client.get_repositories_called
    assert len(result) == 2
    assert result[0]["owner"] == "test-org"
    assert result[0]["repo"] == "test-repo-1"

    # XComに保存されたか確認
    ti = mock_airflow_context["ti"]
    xcom_data = ti.xcom_data.get("repositories")
    assert xcom_data == result


def test_fetch_workflow_runs_with_mock(
    mock_github_client: MockGitHubClient, mock_airflow_context: dict[str, Any]
) -> None:
    """fetch_workflow_runs関数がモックGitHubClientで動作することを確認"""
    from nagare.tasks.fetch import fetch_workflow_runs

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["repositories"] = [
        {"owner": "test-org", "repo": "test-repo-1"},
    ]

    # モックを注入して実行
    fetch_workflow_runs(github_client=mock_github_client, **mock_airflow_context)

    # 検証
    assert mock_github_client.get_workflow_runs_called

    # XComに保存されたか確認
    workflow_runs = ti.xcom_data.get("workflow_runs")
    assert workflow_runs is not None
    assert len(workflow_runs) == 1
    assert workflow_runs[0]["id"] == 123456


def test_fetch_workflow_run_jobs_with_mock(
    mock_github_client: MockGitHubClient, mock_airflow_context: dict[str, Any]
) -> None:
    """fetch_workflow_run_jobs関数がモックGitHubClientで動作することを確認"""
    from nagare.tasks.fetch import fetch_workflow_run_jobs

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["workflow_runs"] = [
        {
            "id": 123456,
            "_repository_owner": "test-org",
            "_repository_name": "test-repo-1",
        },
    ]

    # モックを注入して実行
    fetch_workflow_run_jobs(github_client=mock_github_client, **mock_airflow_context)

    # 検証
    assert mock_github_client.get_workflow_run_jobs_called
    assert mock_github_client.get_workflow_run_jobs_call_count == 1

    # XComに保存されたか確認
    workflow_run_jobs = ti.xcom_data.get("workflow_run_jobs")
    assert workflow_run_jobs is not None
    assert len(workflow_run_jobs) == 1
    assert workflow_run_jobs[0]["id"] == 789
    assert workflow_run_jobs[0]["run_id"] == 123456
