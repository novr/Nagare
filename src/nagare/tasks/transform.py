"""データ変換タスク"""

import logging
from datetime import datetime
from typing import Any

from airflow.models import TaskInstance

from nagare.utils.xcom_utils import check_xcom_size

logger = logging.getLogger(__name__)


def transform_data(**context: Any) -> None:
    """GitHub APIから取得したデータを汎用データモデルに変換する

    ワークフロー実行データとジョブデータの両方を変換する。

    Args:
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    # ワークフロー実行データの変換
    workflow_runs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="fetch_workflow_runs", key="workflow_runs"
    )

    transformed_runs: list[dict[str, Any]] = []

    if workflow_runs:
        for run in workflow_runs:
            try:
                transformed_run = _transform_workflow_run(run)
                transformed_runs.append(transformed_run)
            except Exception as e:
                logger.error(f"Failed to transform workflow run {run.get('id')}: {e}")
                continue
        logger.info(f"Transformed {len(transformed_runs)} workflow runs")
    else:
        logger.warning("No workflow runs to transform")

    # ジョブデータの変換
    workflow_run_jobs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="fetch_workflow_run_jobs", key="workflow_run_jobs"
    )

    transformed_jobs: list[dict[str, Any]] = []

    if workflow_run_jobs:
        for job in workflow_run_jobs:
            try:
                transformed_job = _transform_workflow_run_job(job)
                transformed_jobs.append(transformed_job)
            except Exception as e:
                logger.error(f"Failed to transform job {job.get('id')}: {e}")
                continue
        logger.info(f"Transformed {len(transformed_jobs)} jobs")
    else:
        logger.warning("No jobs to transform")

    # XComサイズチェック
    check_xcom_size(transformed_runs, "transformed_runs")
    check_xcom_size(transformed_jobs, "transformed_jobs")

    # XComで次のタスクに渡す
    ti.xcom_push(key="transformed_runs", value=transformed_runs)
    ti.xcom_push(key="transformed_jobs", value=transformed_jobs)


def _transform_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
    """個別のワークフロー実行データを変換する

    Args:
        run: GitHub APIから取得したワークフロー実行データ

    Returns:
        汎用データモデル形式に変換されたデータ
    """
    # ステータスをマッピング
    status_mapping = {
        "completed": _map_conclusion_to_status(run.get("conclusion")),
        "in_progress": "IN_PROGRESS",
        "queued": "QUEUED",
    }
    run_status = run.get("status", "unknown")
    status = status_mapping.get(run_status, "UNKNOWN")

    # 実行時間を計算（ミリ秒）
    started_at_str = run.get("run_started_at") or run.get("created_at")
    completed_at_str = run.get("updated_at")

    started_at = (
        datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        if started_at_str
        else None
    )
    completed_at = (
        datetime.fromisoformat(completed_at_str.replace("Z", "+00:00"))
        if completed_at_str
        else None
    )

    duration_ms = None
    if started_at and completed_at:
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    # 汎用データモデルに変換
    return {
        "source_run_id": str(run["id"]),
        "source": "github_actions",
        "pipeline_name": run.get("name", "Unknown"),
        "status": status,
        "trigger_event": run.get("event", "UNKNOWN"),
        "repository_owner": run.get("_repository_owner"),
        "repository_name": run.get("_repository_name"),
        "branch_name": run.get("head_branch"),
        "commit_sha": run.get("head_sha"),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "url": run.get("html_url"),
    }


def _transform_workflow_run_job(job: dict[str, Any]) -> dict[str, Any]:
    """個別のジョブデータを変換する

    Args:
        job: GitHub APIから取得したジョブデータ

    Returns:
        汎用データモデル形式に変換されたデータ
    """
    # ステータスをマッピング
    status_mapping = {
        "completed": _map_conclusion_to_status(job.get("conclusion")),
        "in_progress": "IN_PROGRESS",
        "queued": "QUEUED",
    }
    job_status = job.get("status", "unknown")
    status = status_mapping.get(job_status, "UNKNOWN")

    # 実行時間を計算（ミリ秒）
    started_at_str = job.get("started_at")
    completed_at_str = job.get("completed_at")

    started_at = (
        datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        if started_at_str
        else None
    )
    completed_at = (
        datetime.fromisoformat(completed_at_str.replace("Z", "+00:00"))
        if completed_at_str
        else None
    )

    duration_ms = None
    if started_at and completed_at:
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    # 汎用データモデルに変換
    return {
        "source_job_id": str(job["id"]),
        "source_run_id": str(job["run_id"]),
        "source": "github_actions",
        "job_name": job.get("name", "Unknown"),
        "status": status,
        "repository_owner": job.get("_repository_owner"),
        "repository_name": job.get("_repository_name"),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "url": job.get("html_url"),
    }


def _map_conclusion_to_status(conclusion: str | None) -> str:
    """GitHub Actionsのconclusionをステータスにマッピングする

    Args:
        conclusion: GitHub Actionsのconclusion値

    Returns:
        汎用ステータス
    """
    mapping = {
        "success": "SUCCESS",
        "failure": "FAILURE",
        "cancelled": "CANCELLED",
        "skipped": "SKIPPED",
        "timed_out": "TIMEOUT",
    }
    return mapping.get(conclusion or "", "UNKNOWN")
