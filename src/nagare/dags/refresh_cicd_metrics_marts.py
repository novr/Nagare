"""メトリクスマート v2 の日次（または随時）リフレッシュ DAG。

collect_* DAG で取り込んだ pipeline_runs / jobs を
fact_pipeline_run / agg_daily_repo_metrics 等へ同期する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

from nagare.tasks.metrics_mart_refresh import run_metrics_mart_refresh

logger = logging.getLogger(__name__)

default_args = {
    "owner": "nagare",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
}


def _refresh_task() -> None:
    run_metrics_mart_refresh()


with DAG(
    dag_id="refresh_cicd_metrics_marts",
    default_args=default_args,
    description="CI/CD メトリクスマート v2 を PostgreSQL 上で更新する",
    schedule="@hourly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["metrics", "nagare"],
) as dag:
    # 増分同期は TEMP テーブルと単一トランザクション前提のため、DB 呼び出しは 1 タスクにまとめる。
    # 処理フェーズの分割は SQL 側の _metrics_mart_* / refresh_cicd_metrics_marts を参照。
    with TaskGroup(
        group_id="cicd_metrics_mart_sync",
        tooltip=(
            "refresh_cicd_metrics_marts(FALSE) を 1 トランザクションで実行。"
            "SQL 内: advisory xact lock → seed → full|incremental → watermark"
        ),
    ):
        PythonOperator(
            task_id="refresh_marts",
            python_callable=_refresh_task,
        )
