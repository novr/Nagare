"""CI/CDデータ収集DAGファクトリー

GitHub Actions、Bitrise等の複数のCI/CDプラットフォームに対応した
データ収集DAGを生成する汎用ファクトリー関数を提供する。

Usage:
    >>> from nagare.dags.cicd_dag_factory import create_cicd_collection_dag, PlatformConfig
    >>>
    >>> config = PlatformConfig(
    ...     name="github",
    ...     display_name="GitHub Actions",
    ...     connection_id="github_default",
    ...     fetch_runs_batch=fetch_workflow_runs_batch,
    ...     fetch_details=fetch_workflow_run_jobs,
    ...     with_client_wrapper=with_github_client,
    ...     with_client_and_db_wrapper=with_github_and_database_clients,
    ... )
    >>>
    >>> dag = create_cicd_collection_dag(
    ...     platform_config=config,
    ...     dag_id="collect_github_actions_data",
    ...     description="GitHub Actionsのワークフロー実行データを収集する",
    ...     tags=["github", "data-collection"],
    ...     default_args=default_args,
    ...     schedule_interval="0 * * * *",
    ...     start_date=datetime(2024, 1, 1),
    ...     catchup=False,
    ... )
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from airflow import DAG
from airflow.operators.python import PythonOperator

from nagare.constants import Platform, SourceType, TaskIds
from nagare.tasks.fetch import fetch_repositories
from nagare.tasks.load import load_to_database
from nagare.tasks.transform import transform_data
from nagare.utils.dag_helpers import with_database_client


@dataclass
class PlatformConfig:
    """CI/CDプラットフォーム固有の設定

    Attributes:
        name: プラットフォーム名（小文字、例: "github", "bitrise"）
        display_name: 表示用のプラットフォーム名（例: "GitHub Actions", "Bitrise"）
        connection_id: Airflow Connection ID（例: "github_default", "bitrise_default"）
        fetch_runs_batch: バッチ単位でワークフロー実行/ビルドを取得する関数
        fetch_details: 詳細データ（ジョブ等）を取得する関数（オプショナル、Noneの場合はスキップ）
        with_client_wrapper: クライアント注入用のwrapper関数
        with_client_and_db_wrapper: クライアント＋DB注入用のwrapper関数

    Example:
        >>> github_config = PlatformConfig(
        ...     name="github",
        ...     display_name="GitHub Actions",
        ...     connection_id="github_default",
        ...     fetch_runs_batch=fetch_workflow_runs_batch,
        ...     fetch_details=fetch_workflow_run_jobs,
        ...     with_client_wrapper=with_github_client,
        ...     with_client_and_db_wrapper=with_github_and_database_clients,
        ... )
    """

    name: str
    display_name: str
    connection_id: str
    fetch_runs_batch: Callable[..., Any]
    fetch_details: Callable[..., Any] | None
    with_client_wrapper: Callable[..., Any]
    with_client_and_db_wrapper: Callable[..., Any]


def create_cicd_collection_dag(
    platform_config: PlatformConfig,
    dag_id: str,
    description: str,
    tags: list[str],
    **dag_kwargs: Any,
) -> DAG:
    """CI/CDデータ収集DAGを生成するファクトリー関数

    GitHub Actions、Bitrise等の複数のCI/CDプラットフォームに対応した
    データ収集DAGを生成する。以下の共通タスク構造を持つ：

    1. fetch_repositories: 監視対象リポジトリ/アプリの取得
    2. fetch_*_runs_batch (並列): ワークフロー実行/ビルドデータの取得（バッチ処理）
    3. fetch_*_details (オプショナル): 詳細データ（ジョブ等）の取得
    4. transform_data: データ変換
    5. load_to_database: データベースへの保存

    Args:
        platform_config: プラットフォーム固有の設定
        dag_id: DAG ID（例: "collect_github_actions_data"）
        description: DAGの説明
        tags: タグリスト（例: ["github", "data-collection"]）
        **dag_kwargs: その他のDAGパラメータ（default_args, schedule_interval等）

    Returns:
        生成されたDAG

    Example:
        >>> config = PlatformConfig(...)
        >>> dag = create_cicd_collection_dag(
        ...     platform_config=config,
        ...     dag_id="collect_github_actions_data",
        ...     description="GitHub Actionsのワークフロー実行データを収集する",
        ...     tags=["github", "data-collection"],
        ...     default_args=default_args,
        ...     schedule_interval="0 * * * *",
        ...     start_date=datetime(2024, 1, 1),
        ...     catchup=False,
        ... )
    """
    with DAG(
        dag_id=dag_id,
        description=description,
        tags=tags,
        **dag_kwargs,
    ) as dag:
        # タスク1: 監視対象リポジトリ/アプリの取得（プラットフォームでフィルタ）
        # ソースタイプを決定（github -> github_actions, bitrise -> bitrise, xcode_cloud -> xcode_cloud）
        if platform_config.name == Platform.GITHUB:
            source_type = SourceType.GITHUB_ACTIONS
        elif platform_config.name == Platform.BITRISE:
            source_type = SourceType.BITRISE
        elif platform_config.name == Platform.XCODE_CLOUD:
            source_type = SourceType.XCODE_CLOUD
        else:
            raise ValueError(f"Unknown platform: {platform_config.name}")
        task_fetch_repositories = PythonOperator(
            task_id=TaskIds.FETCH_REPOSITORIES,
            python_callable=with_database_client(fetch_repositories),
            op_kwargs={"source": source_type},
        )

        # タスク2: ワークフロー実行/ビルドデータの取得（Dynamic Task Mapping）
        # fetch_repositoriesが返すop_kwargsのリストを使用して動的にタスクを生成
        # expand(op_kwargs=...)は自動的にリストの各要素（辞書）に対してタスクを作成する
        batch_tasks = PythonOperator.partial(
            task_id=f"fetch_{platform_config.name}_batch",
            python_callable=platform_config.with_client_and_db_wrapper(
                platform_config.fetch_runs_batch,
                conn_id=platform_config.connection_id,
            ),
            execution_timeout=timedelta(minutes=30),  # バッチタスク個別タイムアウト（GitHub API制限考慮）
        ).expand(
            op_kwargs=task_fetch_repositories.output
        )

        # タスク3: 詳細データの取得（オプショナル、fetch_detailsがNoneの場合はスキップ）
        previous_tasks = batch_tasks
        if platform_config.fetch_details:
            task_fetch_details = PythonOperator(
                task_id=f"fetch_{platform_config.name}_details",
                python_callable=platform_config.with_client_wrapper(
                    platform_config.fetch_details,
                    conn_id=platform_config.connection_id,
                ),
            )
            previous_tasks = [task_fetch_details]
            batch_tasks >> task_fetch_details  # type: ignore[arg-type]

        # タスク4: データ変換（ADR-006: 一時テーブルからデータ取得）
        task_transform_data = PythonOperator(
            task_id=TaskIds.TRANSFORM_DATA,
            python_callable=with_database_client(transform_data),
        )

        # タスク5: データベースへの保存
        task_load_to_database = PythonOperator(
            task_id=TaskIds.LOAD_TO_DATABASE,
            python_callable=with_database_client(load_to_database),
        )

        # タスクの依存関係を定義
        # リポジトリ取得 → バッチ並列処理 → [詳細取得] → 変換 → 保存
        task_fetch_repositories >> batch_tasks  # type: ignore[arg-type]
        previous_tasks >> task_transform_data >> task_load_to_database  # type: ignore[arg-type]

    return dag
