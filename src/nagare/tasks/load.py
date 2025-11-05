"""データ読み込みタスク"""

import logging
from typing import Any

from airflow.models import TaskInstance

from nagare.utils.protocols import DatabaseClientProtocol

logger = logging.getLogger(__name__)


def load_to_database(db: DatabaseClientProtocol, **context: Any) -> None:
    """変換されたデータをPostgreSQLに保存する

    ADR-006: 一時テーブルから本番テーブルへデータを移動する。
    トランザクションを使用して、データ整合性を保証する。

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト

    Raises:
        Exception: データベース保存に失敗した場合（ロールバックされる）
    """
    ti: TaskInstance = context["ti"]
    run_id = context.get("run_id", ti.run_id)

    logger.info(f"Starting data load to production tables (run_id={run_id})")

    # ADR-006: 一時テーブルからデータ取得（確認用）
    transformed_runs = db.get_temp_transformed_runs(run_id)
    transformed_jobs = db.get_temp_workflow_jobs(run_id)

    runs_count = len(transformed_runs)
    jobs_count = len(transformed_jobs)

    logger.info(
        f"Found {runs_count} transformed runs and {jobs_count} jobs in temp tables"
    )

    # データがない場合は早期リターン
    if runs_count == 0 and jobs_count == 0:
        logger.warning("No data to load (both runs and jobs are empty)")
        return

    try:
        # トランザクション内で一時テーブルから本番テーブルへ移動
        with db.transaction():
            db.move_temp_to_production(run_id)

        logger.info(
            f"Successfully moved {runs_count} runs and {jobs_count} jobs "
            f"to production tables (run_id={run_id})"
        )

        # 成功後、一時テーブルをクリーンアップ
        deleted_count = db.cleanup_temp_tables(run_id=run_id)
        logger.info(
            f"Cleaned up {deleted_count} records from temp tables (run_id={run_id})"
        )

    except Exception as e:
        logger.error(
            f"Failed to load data to database (transaction rolled back): "
            f"{type(e).__name__}: {e}. "
            f"Attempted to save {runs_count} runs and {jobs_count} jobs.",
            exc_info=True,
        )
        raise
