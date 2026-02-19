"""データ変換タスク"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from airflow.models import TaskInstance

from nagare.constants import (
    GITHUB_CONCLUSION_TO_STATUS,
    GitHubStatus,
    PipelineStatus,
    TaskIds,
    XComKeys,
)
from nagare.utils.datetime_utils import calculate_duration_ms, parse_iso_datetime
from nagare.utils.protocols import DatabaseClientProtocol

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _validate_required_fields(
    data: dict[str, Any], required_fields: list[str], data_type: str
) -> None:
    """必須フィールドの存在を検証する

    Args:
        data: 検証対象のデータ
        required_fields: 必須フィールドのリスト
        data_type: データの種類（エラーメッセージ用）

    Raises:
        KeyError: 必須フィールドが欠落している場合
    """
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        raise KeyError(
            f"Missing required fields in {data_type}: {missing_fields}. "
            f"Available fields: {list(data.keys())}"
        )


def _transform_items_with_error_handling(
    items: list[dict[str, Any]],
    transform_func: Callable[[dict[str, Any]], dict[str, Any]],
    item_descriptor: Callable[[dict[str, Any]], str],
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
            # その他の予期しないエラー（初回のみスタックトレースを出力）
            logger.error(
                f"Unexpected error transforming {item_type} {item_desc}: "
                f"{type(e).__name__}: {e}",
                exc_info=(len(results) == 0),
            )
            continue

    return results


def transform_data(db: DatabaseClientProtocol, **context: Any) -> None:
    """GitHub/Bitrise/Xcode Cloud APIから取得したデータを汎用データモデルに変換する

    ADR-006: 一時テーブルからデータを取得し、変換後も一時テーブルに保存。
    XComは統計情報のみ保存する。

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]
    run_id = context.get("run_id", ti.run_id)

    logger.info(f"Starting data transformation (run_id={run_id})")

    # ADR-006: 一時テーブルから全ワークフロー実行データを取得
    all_workflow_runs = db.get_temp_workflow_runs(run_id)
    logger.info(f"Retrieved {len(all_workflow_runs)} workflow runs from temp table")

    if all_workflow_runs:
        logger.debug(f"Sample workflow run keys: {list(all_workflow_runs[0].keys())[:10]}")

        transformed_runs = _transform_items_with_error_handling(
            items=all_workflow_runs,
            transform_func=_transform_workflow_run,
            item_descriptor=lambda r: f"{r.get('id', 'unknown')}",
            item_type="workflow run",
        )
        logger.info(f"Transformed {len(transformed_runs)} workflow runs from {len(all_workflow_runs)} total")
    else:
        logger.warning("No workflow runs to transform")
        transformed_runs = []

    # ジョブデータの変換（既存の詳細取得タスクから、まだ一時テーブル化していない）
    # TODO: fetch_workflow_run_jobsも一時テーブル化する
    workflow_run_jobs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids=TaskIds.FETCH_WORKFLOW_RUN_JOBS, key=XComKeys.WORKFLOW_RUN_JOBS
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

    # ADR-006: 変換済みデータを一時テーブルに保存
    db.insert_temp_transformed_runs(transformed_runs, run_id)
    db.insert_temp_workflow_jobs(transformed_jobs, run_id)

    # XComには統計情報のみ保存（軽量）
    ti.xcom_push(
        key="transform_stats",
        value={
            "input_count": len(all_workflow_runs),
            "transformed_runs_count": len(transformed_runs),
            "transformed_jobs_count": len(transformed_jobs),
            "run_id": run_id,
        }
    )

    logger.info(
        f"Saved {len(transformed_runs)} transformed runs and {len(transformed_jobs)} jobs "
        f"to temp tables (run_id={run_id})"
    )


def _transform_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
    """個別のワークフロー実行データを変換する

    Args:
        run: GitHub APIから取得したワークフロー実行データ

    Returns:
        汎用データモデル形式に変換されたデータ

    Raises:
        KeyError: 必須フィールドが欠落している場合
    """
    # 必須フィールドの検証
    _validate_required_fields(
        run,
        required_fields=["id", "_repository_owner", "_repository_name"],
        data_type="workflow run",
    )

    # ステータスをマッピング（GitHub Actions, Bitrise, Xcode Cloud）
    run_status = run.get("status", "unknown")
    source = run.get("_source", "github_actions")

    # Xcode Cloud: processingState field (VALID, PROCESSING, FAILED, INVALID)
    if source == "xcode_cloud":
        processing_state = run.get("attributes", {}).get("processingState", "unknown")
        if processing_state == "VALID":
            status = PipelineStatus.SUCCESS
        elif processing_state == "PROCESSING":
            status = PipelineStatus.IN_PROGRESS
        elif processing_state == "FAILED":
            status = PipelineStatus.FAILURE
        elif processing_state == "INVALID":
            status = PipelineStatus.FAILURE
        else:
            status = PipelineStatus.UNKNOWN
    # Bitriseは整数ステータス: 0=in_progress, 1=success, 2=failed, 3/4=aborted
    elif isinstance(run_status, int):
        if run_status == 0:
            status = PipelineStatus.IN_PROGRESS
        elif run_status == 1:
            status = PipelineStatus.SUCCESS
        elif run_status == 2:
            status = PipelineStatus.FAILURE
        elif run_status in (3, 4):
            status = PipelineStatus.CANCELLED
        else:
            status = PipelineStatus.UNKNOWN
    # GitHub Actionsは文字列ステータス
    elif run_status == GitHubStatus.COMPLETED:
        status = _map_conclusion_to_status(run.get("conclusion"))
    elif run_status == GitHubStatus.IN_PROGRESS:
        status = PipelineStatus.IN_PROGRESS
    elif run_status == GitHubStatus.QUEUED:
        status = PipelineStatus.QUEUED
    else:
        status = PipelineStatus.UNKNOWN

    # 実行時間を計算（ミリ秒）
    # GitHub: run_started_at/created_at, updated_at
    # Bitrise: triggered_at, started_on_worker_at, finished_at
    # Xcode Cloud: attributes.uploadedDate
    if source == "xcode_cloud":
        # Xcode Cloudはupload日時を使用
        attributes = run.get("attributes", {})
        started_at_str = attributes.get("uploadedDate")
        completed_at_str = attributes.get("uploadedDate")
    else:
        started_at_str = (run.get("run_started_at") or run.get("created_at") or
                         run.get("triggered_at") or run.get("started_on_worker_at"))
        completed_at_str = run.get("updated_at") or run.get("finished_at")

    started_at = parse_iso_datetime(started_at_str)
    completed_at = parse_iso_datetime(completed_at_str)
    duration_ms = calculate_duration_ms(started_at, completed_at)

    # ソース識別（GitHub Actions, Bitrise, Xcode Cloud）
    # Already extracted above for status mapping

    # 汎用データモデルに変換
    # 必須フィールドは既にバリデーション済みなので安全にアクセス可能

    # Xcode Cloud用の特殊処理
    if source == "xcode_cloud":
        attributes = run.get("attributes", {})
        pipeline_name = attributes.get("name", "Unknown")
        branch_name = attributes.get("sourceBranchOrTag")
        commit_sha = attributes.get("sourceCommit", {}).get("commitSha") if isinstance(attributes.get("sourceCommit"), dict) else None
        url = None  # Xcode CloudにはWeb URLがない
    else:
        pipeline_name = run.get("name") or run.get("triggered_workflow", "Unknown")
        branch_name = run.get("head_branch") or run.get("branch")
        commit_sha = run.get("head_sha") or run.get("commit_hash")
        url = run.get("html_url") or run.get("commit_view_url")

    return {
        "source_run_id": str(run["id"]),
        "source": source,
        "pipeline_name": pipeline_name,
        "status": status,
        "trigger_event": run.get("event") or run.get("triggered_by", "UNKNOWN"),
        "repository_owner": run["_repository_owner"],
        "repository_name": run["_repository_name"],
        "branch_name": branch_name,
        "commit_sha": commit_sha,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "url": url,
    }


def _transform_workflow_run_job(job: dict[str, Any]) -> dict[str, Any]:
    """個別のジョブデータを変換する

    Args:
        job: GitHub APIから取得したジョブデータ

    Returns:
        汎用データモデル形式に変換されたデータ

    Raises:
        KeyError: 必須フィールドが欠落している場合
    """
    # 必須フィールドの検証
    _validate_required_fields(
        job,
        required_fields=["id", "run_id", "_repository_owner", "_repository_name"],
        data_type="job",
    )

    # ステータスをマッピング
    job_status = job.get("status", "unknown")
    if job_status == GitHubStatus.COMPLETED:
        status = _map_conclusion_to_status(job.get("conclusion"))
    elif job_status == GitHubStatus.IN_PROGRESS:
        status = PipelineStatus.IN_PROGRESS
    elif job_status == GitHubStatus.QUEUED:
        status = PipelineStatus.QUEUED
    else:
        status = PipelineStatus.UNKNOWN

    # 実行時間を計算（ミリ秒）
    started_at_str = job.get("started_at")
    completed_at_str = job.get("completed_at")

    started_at = parse_iso_datetime(started_at_str)
    completed_at = parse_iso_datetime(completed_at_str)
    duration_ms = calculate_duration_ms(started_at, completed_at)

    # 汎用データモデルに変換
    # 必須フィールドは既にバリデーション済みなので安全にアクセス可能
    return {
        "source_job_id": str(job["id"]),
        "source_run_id": str(job["run_id"]),
        "source": "github_actions",
        "job_name": job.get("name", "Unknown"),
        "status": status,
        "repository_owner": job["_repository_owner"],
        "repository_name": job["_repository_name"],
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "url": job.get("html_url"),
    }


def _map_conclusion_to_status(conclusion: str | None) -> PipelineStatus:
    """GitHub Actionsのconclusionをステータスにマッピングする

    Args:
        conclusion: GitHub Actionsのconclusion値

    Returns:
        汎用ステータス
    """
    if not conclusion:
        return PipelineStatus.UNKNOWN

    # 辞書のキーとして使用するため、conclusionをそのまま使う
    # GitHubConclusionのenumはstr型を継承しているため、
    # 文字列として直接使用可能
    return GITHUB_CONCLUSION_TO_STATUS.get(conclusion, PipelineStatus.UNKNOWN)  # type: ignore[arg-type]
