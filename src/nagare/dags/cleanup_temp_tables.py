"""一時テーブルクリーンアップDAG

ADR-006: 一時テーブル方式によるDAG間データ転送

このDAGは毎日実行され、7日より古い一時テーブルデータを削除する。
通常は各DAG実行後にクリーンアップされるが、失敗時の残骸を定期的に削除する。
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from airflow import DAG
from airflow.operators.python import PythonOperator

from nagare.utils.dag_helpers import with_database_client
from nagare.utils.protocols import DatabaseClientProtocol

logger = logging.getLogger(__name__)


def cleanup_old_temp_data(db: DatabaseClientProtocol, **context: Any) -> None:
    """7日より古い一時テーブルデータを削除する

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    days = 7  # 保持日数
    logger.info(f"Starting cleanup of temp tables (older than {days} days)")

    try:
        # 古いデータを削除
        deleted_count = db.cleanup_temp_tables(run_id=None, days=days)

        logger.info(
            f"Successfully cleaned up {deleted_count} old records from temp tables "
            f"(older than {days} days)"
        )

        # 統計情報をログに出力
        if deleted_count > 0:
            logger.warning(
                f"Deleted {deleted_count} orphaned records. "
                f"This may indicate failed DAG runs that didn't clean up properly."
            )
        else:
            logger.info("No old records found. Temp tables are clean.")

    except Exception as e:
        logger.error(
            f"Failed to cleanup temp tables: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise


# デフォルト引数
default_args = {
    "owner": "nagare",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
}

# DAG定義
with DAG(
    dag_id="cleanup_temp_tables",
    description="一時テーブルの古いデータを定期的にクリーンアップする",
    tags=["maintenance", "cleanup"],
    default_args=default_args,
    schedule_interval="0 2 * * *",  # 毎日2:00 UTC（日本時間11:00）
    start_date=datetime(2024, 1, 1),
    catchup=False,  # 過去の実行をスキップ
    max_active_runs=1,  # 同時実行は1つのみ
) as dag:
    # クリーンアップタスク
    cleanup_task = PythonOperator(
        task_id="cleanup_old_temp_data",
        python_callable=with_database_client(cleanup_old_temp_data),
    )

    cleanup_task
