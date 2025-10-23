"""データ読み込みタスク"""

import logging
from typing import Any

from airflow.models import TaskInstance

from nagare.utils.protocols import DatabaseClientProtocol

logger = logging.getLogger(__name__)


def load_to_database(db: DatabaseClientProtocol, **context: Any) -> None:
    """変換されたデータをPostgreSQLに保存する

    ワークフロー実行データとジョブデータの両方を保存する。

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    # ワークフロー実行データの保存
    transformed_runs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="transform_data", key="transformed_runs"
    )

    if transformed_runs:
        db.upsert_pipeline_runs(transformed_runs)
        logger.info(f"Successfully loaded {len(transformed_runs)} runs to database")
    else:
        logger.warning("No transformed runs to load")

    # ジョブデータの保存
    transformed_jobs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="transform_data", key="transformed_jobs"
    )

    if transformed_jobs:
        db.upsert_jobs(transformed_jobs)
        logger.info(f"Successfully loaded {len(transformed_jobs)} jobs to database")
    else:
        logger.warning("No transformed jobs to load")
