"""GitHub Actionsデータ収集DAG

このDAGは1時間に1回実行され、監視対象リポジトリのCI/CD実行データを
GitHub APIから取得し、PostgreSQLに保存する。

GitHub認証設定:
  推奨: Airflow Connectionを使用（Streamlit管理画面で設定可能）
  - Streamlit管理画面の「Connections管理」でConnection IDを作成
  - デフォルトでは 'github_default' を使用
  - 環境変数 GITHUB_CONNECTION_ID で変更可能

  後方互換: 環境変数 GITHUB_TOKEN でも動作（非推奨）
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

from nagare.constants import TaskIds
from nagare.tasks.fetch import (
    fetch_repositories,
    fetch_workflow_run_jobs,
    fetch_workflow_runs_batch,
)
from nagare.tasks.load import load_to_database
from nagare.tasks.transform import transform_data
from nagare.utils.connections import ConnectionRegistry
from nagare.utils.dag_helpers import (
    with_database_client,
    with_github_and_database_clients,
    with_github_client,
)

# Connection設定ファイルの読み込み
connections_file = os.getenv("NAGARE_CONNECTIONS_FILE")
if connections_file and Path(connections_file).exists():
    ConnectionRegistry.from_file(connections_file)

# GitHub Connection ID（Streamlit管理画面で設定）
# 環境変数 GITHUB_CONNECTION_ID で上書き可能
GITHUB_CONNECTION_ID = os.getenv("GITHUB_CONNECTION_ID", "github_default")

# バッチ処理設定
NUM_BATCHES = 10  # 並列処理するバッチ数
BATCH_SIZE = 17  # 各バッチで処理するリポジトリ数（161 / 10 ≈ 16-17）

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
    dag_id="collect_github_actions_data",
    default_args=default_args,
    description="GitHub Actionsのワークフロー実行データを収集する",
    schedule_interval="0 * * * *",  # 毎時0分に実行
    start_date=datetime(2024, 1, 1),
    catchup=False,  # 過去の実行をスキップ
    max_active_tasks=20,  # 並列バッチ処理用に増やす（デフォルト16から20へ）
    max_active_runs=1,  # 同時実行DAG runは1つのみ
    tags=["github", "data-collection"],
) as dag:
    # タスク1: 監視対象リポジトリの取得
    task_fetch_repositories = PythonOperator(
        task_id=TaskIds.FETCH_REPOSITORIES,
        python_callable=with_database_client(fetch_repositories),
    )

    # タスク2: ワークフロー実行データの取得（バッチ並列処理）
    batch_tasks = []
    for batch_index in range(NUM_BATCHES):
        task = PythonOperator(
            task_id=f"fetch_workflow_runs_batch_{batch_index}",
            python_callable=with_github_and_database_clients(
                fetch_workflow_runs_batch, conn_id=GITHUB_CONNECTION_ID
            ),
            op_kwargs={
                "batch_index": batch_index,
                "batch_size": BATCH_SIZE,
            },
        )
        batch_tasks.append(task)

    # タスク3: ジョブデータの取得
    task_fetch_workflow_run_jobs = PythonOperator(
        task_id=TaskIds.FETCH_WORKFLOW_RUN_JOBS,
        python_callable=with_github_client(
            fetch_workflow_run_jobs, conn_id=GITHUB_CONNECTION_ID
        ),
    )

    # タスク4: データ変換
    task_transform_data = PythonOperator(
        task_id=TaskIds.TRANSFORM_DATA,
        python_callable=transform_data,
    )

    # タスク5: データベースへの保存
    task_load_to_database = PythonOperator(
        task_id=TaskIds.LOAD_TO_DATABASE,
        python_callable=with_database_client(load_to_database),
    )

    # タスクの依存関係を定義
    # リポジトリ取得 → 10個のバッチ並列処理 → ジョブ取得 → 変換 → 保存
    task_fetch_repositories >> batch_tasks  # type: ignore[expression-value]
    batch_tasks >> task_fetch_workflow_run_jobs  # type: ignore[expression-value]
    (
        task_fetch_workflow_run_jobs
        >> task_transform_data
        >> task_load_to_database
    )  # type: ignore[expression-value]
