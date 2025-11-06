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

    # 検証: 期間バッチングにより、リポジトリは複数のバッチに分割される
    assert mock_db_client.get_repositories_called
    # 結果は [{"batch_apps": [...], "since": "...", "until": "..."}, ...] 形式
    assert len(result) > 0
    assert all("batch_apps" in batch for batch in result)

    # 各バッチに2つのリポジトリが含まれることを確認
    for batch in result:
        assert len(batch["batch_apps"]) == 2
        assert batch["batch_apps"][0]["owner"] == "test-org"
        assert batch["batch_apps"][0]["repo"] == "test-repo-1"

    # XComには元のリポジトリリストが保存される（期間バッチング前）
    ti = mock_airflow_context["ti"]
    xcom_data = ti.xcom_data.get("repositories")
    assert xcom_data is not None
    assert len(xcom_data) == 2
    assert xcom_data[0]["owner"] == "test-org"
    assert xcom_data[0]["repo"] == "test-repo-1"


def test_fetch_workflow_runs_with_mock(
    mock_github_client: MockGitHubClient, mock_airflow_context: dict[str, Any]
) -> None:
    """fetch_workflow_runs関数がモックGitHubClientで動作することを確認

    ADR-006: データは一時テーブルに保存され、XComには統計情報のみ保存
    """
    from nagare.tasks.fetch import fetch_workflow_runs
    from tests.conftest import MockDatabaseClient

    # 前のタスクのデータを設定
    ti = mock_airflow_context["ti"]
    ti.xcom_data["repositories"] = [
        {"owner": "test-org", "repo": "test-repo-1"},
    ]

    # MockDatabaseClientを作成
    mock_db_client = MockDatabaseClient()

    # モックを注入して実行
    fetch_workflow_runs(
        github_client=mock_github_client, db=mock_db_client, **mock_airflow_context
    )

    # 検証
    assert mock_github_client.get_workflow_runs_called

    # 一時テーブルに保存されたか確認（ADR-006準拠）
    run_id = ti.run_id
    workflow_runs = mock_db_client.temp_workflow_runs.get(run_id, [])
    assert len(workflow_runs) == 1
    assert workflow_runs[0]["id"] == 123456

    # リポジトリ情報が追加されていることを確認
    assert workflow_runs[0]["_repository_owner"] == "test-org"
    assert workflow_runs[0]["_repository_name"] == "test-repo-1"


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
