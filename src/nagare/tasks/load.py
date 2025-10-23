"""データ読み込みタスク"""

import logging
from typing import Any

from airflow.models import TaskInstance

from nagare.utils.protocols import DatabaseClientProtocol

logger = logging.getLogger(__name__)


def load_to_database(db: DatabaseClientProtocol, **context: Any) -> None:
    """変換されたデータをPostgreSQLに保存する

    ワークフロー実行データとジョブデータの両方を保存する。
    トランザクションを使用して、両方のデータが正常に保存されることを保証する。

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト

    Raises:
        Exception: データベース保存に失敗した場合（ロールバックされる）
    """
    ti: TaskInstance = context["ti"]

    # ワークフロー実行データの取得
    transformed_runs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="transform_data", key="transformed_runs"
    )

    # ジョブデータの取得
    transformed_jobs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="transform_data", key="transformed_jobs"
    )

    # データがない場合は早期リターン
    if not transformed_runs and not transformed_jobs:
        logger.warning("No data to load (both runs and jobs are empty)")
        return

    # トランザクション内で両方のデータを保存
    # 片方が失敗した場合は両方ロールバックされる
    try:
        with db.transaction():
            if transformed_runs:
                db.upsert_pipeline_runs(transformed_runs)
                logger.info(
                    f"Successfully loaded {len(transformed_runs)} runs to database"
                )
            else:
                logger.warning("No transformed runs to load")

            if transformed_jobs:
                db.upsert_jobs(transformed_jobs)
                logger.info(
                    f"Successfully loaded {len(transformed_jobs)} jobs to database"
                )
            else:
                logger.warning("No transformed jobs to load")

            # トランザクション正常終了
            runs_count = len(transformed_runs) if transformed_runs else 0
            jobs_count = len(transformed_jobs) if transformed_jobs else 0
            logger.info(
                "Transaction completed successfully: "
                f"{runs_count} runs, {jobs_count} jobs"
            )
    except Exception as e:
        logger.error(f"Failed to load data to database (transaction rolled back): {e}")
        raise
