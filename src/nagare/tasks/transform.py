"""データ変換タスク"""

import logging
from datetime import datetime
from typing import Any, Callable, TypeVar

from airflow.models import TaskInstance

from nagare.utils.xcom_utils import check_xcom_size

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _transform_items_with_error_handling(
    items: list[T],
    transform_func: Callable[[T], dict[str, Any]],
    item_descriptor: Callable[[T], str],
    item_type: str,
) -> list[dict[str, Any]]:
    """各アイテムを変換し、エラーハンドリングを行う共通ヘルパー

    Args:
        items: 変換対象のアイテムリスト
        transform_func: 各アイテムを変換する関数
        item_descriptor: アイテムを説明する文字列を返す関数
        item_type: アイテムの種類（ログ用）

    Returns:
        変換結果のリスト
    """
    results: list[dict[str, Any]] = []

    for item in items:
        item_desc = item_descriptor(item)
        try:
            transformed = transform_func(item)
            results.append(transformed)
        except KeyError as e:
            # 必須フィールドの欠落
            logger.error(
                f"Missing required field in {item_type} {item_desc}: {e}. "
                f"Available keys: {list(item.keys())}"
            )
            continue
        except (ValueError, TypeError) as e:
            # データ型や値の変換エラー
            logger.error(
                f"Data conversion error in {item_type} {item_desc}: "
                f"{type(e).__name__}: {e}"
            )
            continue
        except Exception as e:
            # その他の予期しないエラー
            logger.error(
                f"Unexpected error transforming {item_type} {item_desc}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            continue

    return results


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

    if workflow_runs:
        transformed_runs = _transform_items_with_error_handling(
            items=workflow_runs,
            transform_func=_transform_workflow_run,
            item_descriptor=lambda r: f"{r.get('id', 'unknown')}",
            item_type="workflow run",
        )
        logger.info(f"Transformed {len(transformed_runs)} workflow runs")
    else:
        logger.warning("No workflow runs to transform")
        transformed_runs = []

    # ジョブデータの変換
    workflow_run_jobs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="fetch_workflow_run_jobs", key="workflow_run_jobs"
    )

    if workflow_run_jobs:
        transformed_jobs = _transform_items_with_error_handling(
            items=workflow_run_jobs,
            transform_func=_transform_workflow_run_job,
            item_descriptor=lambda j: f"{j.get('id', 'unknown')}",
            item_type="job",
        )
        logger.info(f"Transformed {len(transformed_jobs)} jobs")
    else:
        logger.warning("No jobs to transform")
        transformed_jobs = []

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
