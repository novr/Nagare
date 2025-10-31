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
from nagare.utils.xcom_utils import check_xcom_size

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
            # その他の予期しないエラー
            logger.error(
                f"Unexpected error transforming {item_type} {item_desc}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            continue

    return results


def transform_data(**context: Any) -> None:
    """GitHub/Bitrise APIから取得したデータを汎用データモデルに変換する

    Dynamic Task Mappingで生成されたバッチタスクから全データを集約して変換する。
    ワークフロー実行データとジョブデータの両方を変換する。

    Args:
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]
    dag = context["dag"]

    # DAG内のバッチタスクを検索（Dynamic Task Mapping対応）
    # GitHub: fetch_github_batch, Bitrise: fetch_bitrise_batch
    batch_task_patterns = ["_batch"]
    batch_task_id = None
    for task in dag.tasks:
        if any(pattern in task.task_id for pattern in batch_task_patterns):
            batch_task_id = task.task_id
            break

    logger.info(f"Found batch task ID: {batch_task_id}")
    logger.info(f"Available tasks in DAG: {[t.task_id for t in dag.tasks]}")

    # XComから全バッチのデータを集約
    all_workflow_runs = []

    if batch_task_id:
        # Dynamic Task Mappingの各インスタンスからデータを取得
        # サフィックス付きキーパターン: workflow_runs_batch_0, workflow_runs_batch_1, ...
        batch_count = 0
        for i in range(100):  # 最大100バッチをサポート
            batch_key = f"{XComKeys.WORKFLOW_RUNS}_batch_{i}"
            logger.info(f"Trying to pull XCom: task_id={batch_task_id}, key={batch_key}")
            batch_data = ti.xcom_pull(task_ids=batch_task_id, key=batch_key)
            logger.info(f"XCom pull result: type={type(batch_data)}, is_none={batch_data is None}, length={len(batch_data) if isinstance(batch_data, list) else 'N/A'}")

            if batch_data is None:
                # このバッチ番号のデータが存在しない = 全バッチを取得完了
                logger.info(f"No data found for batch {i}, stopping")
                break

            # Dynamic Task Mappingの場合、LazyXComSelectSequenceが返される
            # これを list() すると、各map_indexの結果を含むリストになる: [[runs_from_map_0]]
            # 通常は1つのmap_indexのデータしか含まれないので、最初の要素を取得
            if hasattr(batch_data, '__iter__') and not isinstance(batch_data, (str, bytes)):
                batch_list = list(batch_data) if not isinstance(batch_data, list) else batch_data
                # LazyXComSelectSequenceの場合、[actual_data]形式なので最初の要素を取得
                if len(batch_list) > 0 and isinstance(batch_list[0], list):
                    batch_list = batch_list[0]
                all_workflow_runs.extend(batch_list)
                batch_count += 1
                logger.info(f"Retrieved {len(batch_list)} runs from {batch_task_id} batch {i}")

        if batch_count > 0:
            logger.info(f"Total: Retrieved {len(all_workflow_runs)} runs from {batch_count} batches (Dynamic Task Mapping)")

    # 後方互換性: 古い固定タスクIDからも取得を試みる
    if not all_workflow_runs:
        legacy_data = ti.xcom_pull(task_ids=TaskIds.FETCH_WORKFLOW_RUNS, key=XComKeys.WORKFLOW_RUNS)
        if legacy_data:
            all_workflow_runs = legacy_data if isinstance(legacy_data, list) else []
            logger.info(f"Retrieved {len(all_workflow_runs)} runs from legacy task ID")

    if all_workflow_runs:
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

    # ジョブデータの変換（既存の詳細取得タスクから）
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

    # XComサイズチェック
    check_xcom_size(transformed_runs, XComKeys.TRANSFORMED_RUNS)
    check_xcom_size(transformed_jobs, XComKeys.TRANSFORMED_JOBS)

    # XComで次のタスクに渡す
    ti.xcom_push(key=XComKeys.TRANSFORMED_RUNS, value=transformed_runs)
    ti.xcom_push(key=XComKeys.TRANSFORMED_JOBS, value=transformed_jobs)


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

    # ステータスをマッピング
    run_status = run.get("status", "unknown")
    if run_status == GitHubStatus.COMPLETED:
        status = _map_conclusion_to_status(run.get("conclusion"))
    elif run_status == GitHubStatus.IN_PROGRESS:
        status = PipelineStatus.IN_PROGRESS
    elif run_status == GitHubStatus.QUEUED:
        status = PipelineStatus.QUEUED
    else:
        status = PipelineStatus.UNKNOWN

    # 実行時間を計算（ミリ秒）
    started_at_str = run.get("run_started_at") or run.get("created_at")
    completed_at_str = run.get("updated_at")

    started_at = parse_iso_datetime(started_at_str)
    completed_at = parse_iso_datetime(completed_at_str)
    duration_ms = calculate_duration_ms(started_at, completed_at)

    # 汎用データモデルに変換
    # 必須フィールドは既にバリデーション済みなので安全にアクセス可能
    return {
        "source_run_id": str(run["id"]),
        "source": "github_actions",
        "pipeline_name": run.get("name", "Unknown"),
        "status": status,
        "trigger_event": run.get("event", "UNKNOWN"),
        "repository_owner": run["_repository_owner"],
        "repository_name": run["_repository_name"],
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
