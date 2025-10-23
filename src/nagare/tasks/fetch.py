"""データ取得タスク"""

import logging
from datetime import datetime, timedelta
from typing import Any

from airflow.models import TaskInstance

from nagare.utils.protocols import DatabaseClientProtocol, GitHubClientProtocol

logger = logging.getLogger(__name__)


def fetch_repositories(
    db: DatabaseClientProtocol, **context: Any
) -> list[dict[str, str]]:
    """監視対象のリポジトリリストを取得する

    PostgreSQLから監視対象リポジトリを取得する。
    開発環境では USE_DB_MOCK=true でモックデータを使用可能。

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト

    Returns:
        リポジトリ情報のリスト（owner, repoを含む辞書）
    """
    # データベースから取得
    repositories = db.get_repositories()

    logger.info(f"Found {len(repositories)} repositories to monitor")

    # XComで次のタスクに渡す
    ti: TaskInstance = context["ti"]
    ti.xcom_push(key="repositories", value=repositories)

    return repositories


def fetch_workflow_runs(github_client: GitHubClientProtocol, **context: Any) -> None:
    """各リポジトリのワークフロー実行データを取得する

    Args:
        github_client: GitHubClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    # 前のタスクからリポジトリリストを取得
    repositories: list[dict[str, str]] = ti.xcom_pull(
        task_ids="fetch_repositories", key="repositories"
    )

    if not repositories:
        logger.warning("No repositories found to fetch workflow runs")
        return

    # 前回実行時刻から今回実行時刻までのデータを取得
    execution_date: datetime = context["execution_date"]
    created_after = execution_date - timedelta(hours=2)  # 余裕を持って2時間前から

    all_workflow_runs: list[dict[str, Any]] = []

    for repo in repositories:
        owner = repo["owner"]
        repo_name = repo["repo"]

        try:
            logger.info(f"Fetching workflow runs for {owner}/{repo_name}...")
            runs = github_client.get_workflow_runs(
                owner=owner, repo=repo_name, created_after=created_after
            )

            # リポジトリ情報を各runに追加
            for run in runs:
                run["_repository_owner"] = owner
                run["_repository_name"] = repo_name

            all_workflow_runs.extend(runs)
            logger.info(f"Fetched {len(runs)} runs from {owner}/{repo_name}")

        except Exception as e:
            # 特定のリポジトリでエラーが発生しても、他のリポジトリの処理は継続
            logger.error(f"Failed to fetch workflow runs for {owner}/{repo_name}: {e}")
            continue

    logger.info(f"Total workflow runs fetched: {len(all_workflow_runs)}")

    # XComで次のタスクに渡す
    ti.xcom_push(key="workflow_runs", value=all_workflow_runs)
