"""データ読み込みタスク"""

import logging
from typing import Any

from airflow.models import TaskInstance

from nagare.utils.protocols import DatabaseClientProtocol

logger = logging.getLogger(__name__)


def load_to_database(db: DatabaseClientProtocol, **context: Any) -> None:
    """変換されたデータをPostgreSQLに保存する

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    # 前のタスクから変換済みデータを取得
    transformed_runs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="transform_data", key="transformed_runs"
    )

    if not transformed_runs:
        logger.warning("No transformed runs to load")
        return

    # データベースにUPSERT
    db.upsert_pipeline_runs(transformed_runs)

    logger.info(f"Successfully loaded {len(transformed_runs)} runs to database")
