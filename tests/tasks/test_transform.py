"""transform.pyのユニットテスト"""

from typing import Any


def test_transform_data_with_workflow_runs(
    mock_airflow_context: dict[str, Any],
) -> None:
    """ワークフロー実行データが正常に変換されることを確認"""
    from nagare.tasks.transform import transform_data

    ti = mock_airflow_context["ti"]

    # XComにワークフロー実行データをセット
    ti.xcom_data["workflow_runs"] = [
        {
            "id": 123456,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "event": "push",
            "head_branch": "main",
            "head_sha": "abc123",
            "created_at": "2024-01-01T00:00:00Z",
            "run_started_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:10:00Z",
            "html_url": "https://github.com/test-org/test-repo/actions/runs/123456",
            "_repository_owner": "test-org",
            "_repository_name": "test-repo",
        }
    ]

    # 変換実行
    transform_data(**mock_airflow_context)

    # 変換結果を確認
    transformed_runs = ti.xcom_data["transformed_runs"]
    assert len(transformed_runs) == 1

    run = transformed_runs[0]
    assert run["source_run_id"] == "123456"
    assert run["source"] == "github_actions"
    assert run["pipeline_name"] == "CI"
    assert run["status"] == "SUCCESS"
    assert run["trigger_event"] == "push"
    assert run["repository_owner"] == "test-org"
    assert run["repository_name"] == "test-repo"
    assert run["branch_name"] == "main"
    assert run["commit_sha"] == "abc123"
    assert run["url"] == "https://github.com/test-org/test-repo/actions/runs/123456"

    # 実行時間の確認（10分 = 600,000ミリ秒）
    assert run["duration_ms"] == 600000


def test_transform_data_with_empty_workflow_runs(
    mock_airflow_context: dict[str, Any],
) -> None:
    """空のワークフローリストの場合、空リストがpushされることを確認"""
    from nagare.tasks.transform import transform_data

    ti = mock_airflow_context["ti"]
    ti.xcom_data["workflow_runs"] = []

    # 変換実行
    transform_data(**mock_airflow_context)

    # transformed_runsが空リストとしてpushされることを確認
    assert ti.xcom_data["transformed_runs"] == []
    assert ti.xcom_data["transformed_jobs"] == []


def test_transform_data_with_no_workflow_runs(
    mock_airflow_context: dict[str, Any],
) -> None:
    """workflow_runsがNoneの場合、空リストがpushされることを確認"""
    from nagare.tasks.transform import transform_data

    # XComにデータをセットしない（Noneが返される）
    transform_data(**mock_airflow_context)

    # transformed_runsが空リストとしてpushされることを確認
    ti = mock_airflow_context["ti"]
    assert ti.xcom_data["transformed_runs"] == []
    assert ti.xcom_data["transformed_jobs"] == []


def test_transform_workflow_run_status_mapping() -> None:
    """ステータスマッピングが正しく行われることを確認"""
    from nagare.tasks.transform import (
        _transform_workflow_run,  # type: ignore[reportPrivateUsage]
    )

    # completed + success -> SUCCESS
    run = {
        "id": 1,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    result = _transform_workflow_run(run)
    assert result["status"] == "SUCCESS"

    # completed + failure -> FAILURE
    run["conclusion"] = "failure"
    result = _transform_workflow_run(run)
    assert result["status"] == "FAILURE"

    # completed + cancelled -> CANCELLED
    run["conclusion"] = "cancelled"
    result = _transform_workflow_run(run)
    assert result["status"] == "CANCELLED"

    # in_progress -> IN_PROGRESS
    run = {
        "id": 2,
        "status": "in_progress",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    result = _transform_workflow_run(run)
    assert result["status"] == "IN_PROGRESS"

    # queued -> QUEUED
    run["status"] = "queued"
    result = _transform_workflow_run(run)
    assert result["status"] == "QUEUED"

    # unknown status -> UNKNOWN
    run["status"] = "some_unknown_status"
    result = _transform_workflow_run(run)
    assert result["status"] == "UNKNOWN"


def test_transform_workflow_run_duration_calculation() -> None:
    """実行時間の計算が正しく行われることを確認"""
    from nagare.tasks.transform import (
        _transform_workflow_run,  # type: ignore[reportPrivateUsage]
    )

    # run_started_atとupdated_atから計算
    run = {
        "id": 1,
        "status": "completed",
        "conclusion": "success",
        "run_started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:05:30Z",  # 5分30秒後
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    result = _transform_workflow_run(run)
    assert result["duration_ms"] == 330000  # 5分30秒 = 330秒 = 330,000ミリ秒

    # run_started_atがない場合、created_atを使用
    run = {
        "id": 2,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:02:00Z",  # 2分後
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    result = _transform_workflow_run(run)
    assert result["duration_ms"] == 120000  # 2分 = 120秒 = 120,000ミリ秒

    # 時刻情報がない場合はNone
    run = {
        "id": 3,
        "status": "queued",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    result = _transform_workflow_run(run)
    assert result["duration_ms"] is None


def test_transform_workflow_run_handles_missing_fields() -> None:
    """必須フィールド以外が欠けている場合でも変換できることを確認"""
    from nagare.tasks.transform import (
        _transform_workflow_run,  # type: ignore[reportPrivateUsage]
    )

    # 最小限のフィールドのみ（必須フィールド: id, _repository_owner, _repository_name）
    run = {
        "id": 999,
        "status": "completed",
        "conclusion": "success",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }

    result = _transform_workflow_run(run)

    assert result["source_run_id"] == "999"
    assert result["source"] == "github_actions"
    assert result["pipeline_name"] == "Unknown"
    assert result["status"] == "SUCCESS"
    assert result["trigger_event"] == "UNKNOWN"
    assert result["repository_owner"] == "test-org"
    assert result["repository_name"] == "test-repo"
    assert result["branch_name"] is None
    assert result["commit_sha"] is None
    assert result["started_at"] is None
    assert result["completed_at"] is None
    assert result["duration_ms"] is None
    assert result["url"] is None


def test_map_conclusion_to_status() -> None:
    """conclusion値のマッピングが正しく行われることを確認"""
    from nagare.tasks.transform import (
        _map_conclusion_to_status,  # type: ignore[reportPrivateUsage]
    )

    assert _map_conclusion_to_status("success") == "SUCCESS"
    assert _map_conclusion_to_status("failure") == "FAILURE"
    assert _map_conclusion_to_status("cancelled") == "CANCELLED"
    assert _map_conclusion_to_status("skipped") == "SKIPPED"
    assert _map_conclusion_to_status("timed_out") == "TIMEOUT"
    assert _map_conclusion_to_status("unknown_value") == "UNKNOWN"
    assert _map_conclusion_to_status(None) == "UNKNOWN"
    assert _map_conclusion_to_status("") == "UNKNOWN"


def test_transform_data_continues_on_error(
    mock_airflow_context: dict[str, Any],
) -> None:
    """一部のrunの変換が失敗しても、他のrunは処理されることを確認"""
    from nagare.tasks.transform import transform_data

    ti = mock_airflow_context["ti"]

    # 3つのrun: 2つは正常、1つはidフィールドがない（KeyError発生）
    ti.xcom_data["workflow_runs"] = [
        {
            "id": 123,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:01:00Z",
            "_repository_owner": "test-org",
            "_repository_name": "test-repo",
        },
        {
            # idフィールドがない -> KeyError
            "status": "completed",
            "conclusion": "success",
            "_repository_owner": "test-org",
            "_repository_name": "test-repo",
        },
        {
            "id": 456,
            "status": "completed",
            "conclusion": "failure",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:02:00Z",
            "_repository_owner": "test-org",
            "_repository_name": "test-repo",
        },
    ]

    # 変換実行
    transform_data(**mock_airflow_context)

    # エラーがあっても、正常なrunは変換される
    transformed_runs = ti.xcom_data["transformed_runs"]
    assert len(transformed_runs) == 2
    assert transformed_runs[0]["source_run_id"] == "123"
    assert transformed_runs[1]["source_run_id"] == "456"


def test_transform_workflow_run_missing_required_fields() -> None:
    """必須フィールドが欠落している場合にKeyErrorが発生することを確認"""
    import pytest

    from nagare.tasks.transform import (
        _transform_workflow_run,  # type: ignore[reportPrivateUsage]
    )

    # idフィールドが欠落
    run_missing_id = {
        "status": "completed",
        "conclusion": "success",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    with pytest.raises(KeyError, match="Missing required fields"):
        _transform_workflow_run(run_missing_id)

    # _repository_ownerフィールドが欠落
    run_missing_owner = {
        "id": 123,
        "status": "completed",
        "conclusion": "success",
        "_repository_name": "test-repo",
    }
    with pytest.raises(KeyError, match="Missing required fields"):
        _transform_workflow_run(run_missing_owner)

    # _repository_nameフィールドが欠落
    run_missing_name = {
        "id": 123,
        "status": "completed",
        "conclusion": "success",
        "_repository_owner": "test-org",
    }
    with pytest.raises(KeyError, match="Missing required fields"):
        _transform_workflow_run(run_missing_name)


def test_transform_job_missing_required_fields() -> None:
    """ジョブデータで必須フィールドが欠落している場合にKeyErrorが発生することを確認"""
    import pytest

    from nagare.tasks.transform import (
        _transform_workflow_run_job,  # type: ignore[reportPrivateUsage]
    )

    # idフィールドが欠落
    job_missing_id = {
        "run_id": 123,
        "status": "completed",
        "conclusion": "success",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    with pytest.raises(KeyError, match="Missing required fields"):
        _transform_workflow_run_job(job_missing_id)

    # run_idフィールドが欠落
    job_missing_run_id = {
        "id": 789,
        "status": "completed",
        "conclusion": "success",
        "_repository_owner": "test-org",
        "_repository_name": "test-repo",
    }
    with pytest.raises(KeyError, match="Missing required fields"):
        _transform_workflow_run_job(job_missing_run_id)


def test_transform_data_with_jobs(
    mock_airflow_context: dict[str, Any],
) -> None:
    """ジョブデータが正常に変換されることを確認"""
    from nagare.tasks.transform import transform_data

    ti = mock_airflow_context["ti"]

    # XComにジョブデータをセット
    ti.xcom_data["workflow_run_jobs"] = [
        {
            "id": 789,
            "run_id": 123456,
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:05:00Z",
            "html_url": "https://github.com/test-org/test-repo/actions/runs/123456/jobs/789",
            "_repository_owner": "test-org",
            "_repository_name": "test-repo",
        }
    ]

    # 変換実行
    transform_data(**mock_airflow_context)

    # 変換結果を確認
    transformed_jobs = ti.xcom_data["transformed_jobs"]
    assert len(transformed_jobs) == 1

    job = transformed_jobs[0]
    assert job["source_job_id"] == "789"
    assert job["source_run_id"] == "123456"
    assert job["source"] == "github_actions"
    assert job["job_name"] == "build"
    assert job["status"] == "SUCCESS"
    assert job["repository_owner"] == "test-org"
    assert job["repository_name"] == "test-repo"
    assert job["url"] == "https://github.com/test-org/test-repo/actions/runs/123456/jobs/789"

    # 実行時間の確認（5分 = 300,000ミリ秒）
    assert job["duration_ms"] == 300000
