"""Bitriseデータ収集DAG

このDAGは1時間に1回実行され、監視対象アプリのCI/CDビルドデータを
Bitrise APIから取得し、PostgreSQLに保存する。

Bitrise認証設定:
  推奨: Airflow Connectionを使用（Streamlit管理画面で設定可能）
  - Streamlit管理画面の「Connections管理」でConnection IDを作成
  - デフォルトでは 'bitrise_default' を使用
  - 環境変数 BITRISE_CONNECTION_ID で変更可能

  後方互換: 環境変数 BITRISE_TOKEN でも動作（非推奨）
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from nagare.constants import Platform
from nagare.dags.cicd_dag_factory import PlatformConfig, create_cicd_collection_dag
from nagare.tasks.fetch import fetch_bitrise_builds_batch
from nagare.utils.connections import ConnectionRegistry
from nagare.utils.dag_helpers import (
    with_bitrise_and_database_clients,
    with_bitrise_client,
)

# Connection設定ファイルの読み込み
connections_file = os.getenv("NAGARE_CONNECTIONS_FILE")
if connections_file and Path(connections_file).exists():
    ConnectionRegistry.from_file(connections_file)

# Bitrise Connection ID（Streamlit管理画面で設定）
# 環境変数 BITRISE_CONNECTION_ID で上書き可能
BITRISE_CONNECTION_ID = os.getenv("BITRISE_CONNECTION_ID", "bitrise_default")

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

# Bitrise用のプラットフォーム設定
# バッチサイズはFetchConfig.BATCH_SIZE（デフォルト: 10）を使用
# Dynamic Task Mappingによりアプリ数に応じてバッチ数が自動決定される
bitrise_config = PlatformConfig(
    name=Platform.BITRISE,
    display_name="Bitrise",
    connection_id=BITRISE_CONNECTION_ID,
    fetch_runs_batch=fetch_bitrise_builds_batch,
    fetch_details=None,  # Bitriseはジョブ詳細の取得をサポートしない
    with_client_wrapper=with_bitrise_client,
    with_client_and_db_wrapper=with_bitrise_and_database_clients,
)

# DAG生成
dag = create_cicd_collection_dag(
    platform_config=bitrise_config,
    dag_id="collect_bitrise_data",
    description="Bitriseのビルドデータを収集する",
    tags=["bitrise", "data-collection"],
    default_args=default_args,
    schedule_interval="0 * * * *",  # 毎時0分に実行
    start_date=datetime(2024, 1, 1),
    catchup=False,  # 過去の実行をスキップ
    max_active_tasks=8,  # メモリ不足対策で並列数を制限
    max_active_runs=1,  # 同時実行DAG runは1つのみ
)
