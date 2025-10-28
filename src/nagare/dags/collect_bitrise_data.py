"""Bitriseデータ収集DAG

このDAGは1時間に1回実行され、監視対象アプリのCI/CDビルドデータを
Bitrise APIから取得し、PostgreSQLに保存する。

Bitrise認証設定:
  connections.ymlでBitrise APIトークンを設定
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

from nagare.constants import TaskIds
from nagare.tasks.fetch import fetch_bitrise_builds, fetch_repositories
from nagare.utils.connections import ConnectionRegistry
from nagare.utils.dag_helpers import (
    with_bitrise_and_database_clients,
    with_database_client,
)

# Connection設定ファイルの読み込み
connections_file = os.getenv("NAGARE_CONNECTIONS_FILE")
if connections_file and Path(connections_file).exists():
    ConnectionRegistry.from_file(connections_file)

# デフォルト引数
default_args = {
    "owner": "nagare",
    "depends_on_past": False,
    "email": os.getenv("AIRFLOW_ALERT_EMAIL", "admin@example.com"),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
}

# DAG定義
with DAG(
    dag_id="collect_bitrise_data",
    default_args=default_args,
    description="Bitriseのビルドデータを収集する",
    schedule_interval="0 * * * *",  # 毎時0分に実行
    start_date=datetime(2024, 1, 1),
    catchup=False,  # 過去の実行をスキップ
    tags=["bitrise", "data-collection"],
) as dag:
    # タスク1: 監視対象リポジトリ（アプリ）の取得
    task_fetch_repositories = PythonOperator(
        task_id=TaskIds.FETCH_REPOSITORIES,
        python_callable=with_database_client(fetch_repositories),
    )

    # タスク2: ビルドデータの取得
    task_fetch_bitrise_builds = PythonOperator(
        task_id="fetch_bitrise_builds",
        python_callable=with_bitrise_and_database_clients(fetch_bitrise_builds),
    )

    # タスクの依存関係を定義
    task_fetch_repositories >> task_fetch_bitrise_builds  # type: ignore[expression-value]
