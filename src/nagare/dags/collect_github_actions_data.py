"""GitHub Actionsデータ収集DAG

このDAGは1時間に1回実行され、監視対象リポジトリのCI/CD実行データを
GitHub APIから取得し、PostgreSQLに保存する。
"""

import os
from datetime import datetime, timedelta
from typing import Any

from airflow import DAG
from airflow.operators.python import PythonOperator

from nagare.tasks.fetch import fetch_repositories, fetch_workflow_runs
from nagare.tasks.load import load_to_database
from nagare.tasks.transform import transform_data
from nagare.utils.factory import get_factory


# タスクラッパー関数（依存性注入 + リソース管理）
def fetch_repositories_with_di(**context: Any) -> list[dict[str, str]]:
    """fetch_repositoriesのラッパー関数（依存性注入）

    Args:
        **context: Airflowのコンテキスト

    Returns:
        リポジトリ情報のリスト
    """
    factory = get_factory()
    with factory.create_database_client() as db:
        return fetch_repositories(db=db, **context)


def fetch_workflow_runs_with_di(**context: Any) -> None:
    """fetch_workflow_runsのラッパー関数（依存性注入）

    Args:
        **context: Airflowのコンテキスト
    """
    factory = get_factory()
    with factory.create_github_client() as github_client:
        fetch_workflow_runs(github_client=github_client, **context)


def load_to_database_with_di(**context: Any) -> None:
    """load_to_databaseのラッパー関数（依存性注入）

    Args:
        **context: Airflowのコンテキスト
    """
    factory = get_factory()
    with factory.create_database_client() as db:
        load_to_database(db=db, **context)


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
    tags=["github", "data-collection"],
) as dag:
    # タスク1: 監視対象リポジトリの取得
    task_fetch_repositories = PythonOperator(
        task_id="fetch_repositories",
        python_callable=fetch_repositories_with_di,
    )

    # タスク2: ワークフロー実行データの取得
    task_fetch_workflow_runs = PythonOperator(
        task_id="fetch_workflow_runs",
        python_callable=fetch_workflow_runs_with_di,
    )

    # タスク3: データ変換
    task_transform_data = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    # タスク4: データベースへの保存
    task_load_to_database = PythonOperator(
        task_id="load_to_database",
        python_callable=load_to_database_with_di,
    )

    # タスクの依存関係を定義
    (
        task_fetch_repositories
        >> task_fetch_workflow_runs
        >> task_transform_data
        >> task_load_to_database
    )  # type: ignore[expression-value]
