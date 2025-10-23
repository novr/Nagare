"""データ取得タスク"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, TypeVar

from airflow.models import TaskInstance
from github import GithubException

from nagare.utils.protocols import DatabaseClientProtocol, GitHubClientProtocol
from nagare.utils.xcom_utils import check_xcom_size

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _process_items_with_error_handling(
    items: list[T],
    process_func: Callable[[T], list[dict[str, Any]]],
    item_descriptor: Callable[[T], str],
    operation_name: str,
) -> list[dict[str, Any]]:
    """各アイテムを処理し、エラーハンドリングを行う共通ヘルパー

    Args:
        items: 処理対象のアイテムリスト
        process_func: 各アイテムを処理する関数
        item_descriptor: アイテムを説明する文字列を返す関数
        operation_name: 操作名（ログ用）

    Returns:
        処理結果の集約リスト
    """
    results: list[dict[str, Any]] = []

    for item in items:
        item_desc = item_descriptor(item)
        try:
            logger.info(f"{operation_name} for {item_desc}...")
            item_results = process_func(item)
            results.extend(item_results)
            logger.info(f"Fetched {len(item_results)} items from {item_desc}")
        except GithubException as e:
            # GitHub API固有のエラー（レート制限、認証エラーなど）
            logger.error(
                f"GitHub API error while {operation_name.lower()} for {item_desc}: "
                f"Status {e.status}, Message: {e.data.get('message', str(e))}"
            )
            continue
        except (KeyError, ValueError, TypeError) as e:
            # データ処理エラー（予期しないレスポンス形式など）
            logger.error(
                f"Data processing error while {operation_name.lower()} for {item_desc}: "
                f"{type(e).__name__}: {e}"
            )
            continue
        except Exception as e:
            # その他の予期しないエラー
            logger.error(
                f"Unexpected error while {operation_name.lower()} for {item_desc}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            continue

    return results


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

    def process_repository(repo: dict[str, str]) -> list[dict[str, Any]]:
        """リポジトリからワークフロー実行データを取得

        Raises:
            KeyError: 必須フィールド(owner, repo)が欠落している場合
        """
        # 必須フィールドの検証
        if "owner" not in repo or "repo" not in repo:
            raise KeyError(
                f"Repository data missing required fields. "
                f"Expected: ['owner', 'repo'], Found: {list(repo.keys())}"
            )

        owner = repo["owner"]
        repo_name = repo["repo"]

        runs = github_client.get_workflow_runs(
            owner=owner, repo=repo_name, created_after=created_after
        )

        # リポジトリ情報を各runに追加
        for run in runs:
            run["_repository_owner"] = owner
            run["_repository_name"] = repo_name

        return runs

    all_workflow_runs = _process_items_with_error_handling(
        items=repositories,
        process_func=process_repository,
        item_descriptor=lambda r: f"{r['owner']}/{r['repo']}",
        operation_name="Fetching workflow runs",
    )

    logger.info(f"Total workflow runs fetched: {len(all_workflow_runs)}")

    # XComサイズチェック
    check_xcom_size(all_workflow_runs, "workflow_runs")

    # XComで次のタスクに渡す
    ti.xcom_push(key="workflow_runs", value=all_workflow_runs)


def fetch_workflow_run_jobs(
    github_client: GitHubClientProtocol, **context: Any
) -> None:
    """各ワークフロー実行のジョブデータを取得する

    Args:
        github_client: GitHubClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    # 前のタスクからワークフロー実行リストを取得
    workflow_runs: list[dict[str, Any]] = ti.xcom_pull(
        task_ids="fetch_workflow_runs", key="workflow_runs"
    )

    if not workflow_runs:
        logger.warning("No workflow runs found to fetch jobs")
        ti.xcom_push(key="workflow_run_jobs", value=[])
        return

    def process_workflow_run(run: dict[str, Any]) -> list[dict[str, Any]]:
        """ワークフロー実行からジョブデータを取得

        Raises:
            KeyError: 必須フィールドが欠落している場合
        """
        # 必須フィールドの検証
        required_fields = ["id", "_repository_owner", "_repository_name"]
        missing_fields = [f for f in required_fields if f not in run]
        if missing_fields:
            raise KeyError(
                f"Workflow run data missing required fields: {missing_fields}. "
                f"Available fields: {list(run.keys())}"
            )

        owner = run["_repository_owner"]
        repo_name = run["_repository_name"]
        run_id = run["id"]

        jobs = github_client.get_workflow_run_jobs(
            owner=owner, repo=repo_name, run_id=run_id
        )

        # リポジトリ情報を各jobに追加
        for job in jobs:
            job["_repository_owner"] = owner
            job["_repository_name"] = repo_name

        return jobs

    all_jobs = _process_items_with_error_handling(
        items=workflow_runs,
        process_func=process_workflow_run,
        item_descriptor=lambda r: f"workflow run {r['id']} ({r['_repository_owner']}/{r['_repository_name']})",
        operation_name="Fetching jobs",
    )

    logger.info(f"Total jobs fetched: {len(all_jobs)}")

    # XComサイズチェック
    check_xcom_size(all_jobs, "workflow_run_jobs")

    # XComで次のタスクに渡す
    ti.xcom_push(key="workflow_run_jobs", value=all_jobs)
