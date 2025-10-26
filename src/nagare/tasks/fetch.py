"""データ取得タスク"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

from airflow.models import TaskInstance
from github import GithubException

from nagare.constants import FetchConfig, TaskIds, XComKeys
from nagare.utils.protocols import DatabaseClientProtocol, GitHubClientProtocol
from nagare.utils.xcom_utils import check_xcom_size

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _process_items_with_error_handling(
    items: list[T],
    process_func: Callable[[T], list[dict[str, Any]]],
    item_descriptor: Callable[[T], str],
    operation_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """各アイテムを処理し、エラーハンドリングを行う共通ヘルパー

    Args:
        items: 処理対象のアイテムリスト
        process_func: 各アイテムを処理する関数
        item_descriptor: アイテムを説明する文字列を返す関数
        operation_name: 操作名（ログ用）

    Returns:
        タプル: (処理結果の集約リスト, エラー統計情報)
    """
    results: list[dict[str, Any]] = []
    error_stats = {
        "total_items": len(items),
        "successful": 0,
        "failed": 0,
        "errors": [],
    }

    for item in items:
        item_desc = item_descriptor(item)
        try:
            logger.info(f"{operation_name} for {item_desc}...")
            item_results = process_func(item)
            results.extend(item_results)
            logger.info(f"Fetched {len(item_results)} items from {item_desc}")
            error_stats["successful"] += 1
        except GithubException as e:
            # GitHub API固有のエラー（レート制限、認証エラーなど）
            error_msg = (
                f"GitHub API error while {operation_name.lower()} for {item_desc}: "
                f"Status {e.status}, Message: {e.data.get('message', str(e)) if isinstance(e.data, dict) else e.data}"
            )
            logger.error(error_msg)
            error_stats["failed"] += 1
            error_stats["errors"].append({
                "item": item_desc,
                "error_type": "GithubException",
                "status": e.status,
                "message": str(e.data),
            })
            continue
        except (KeyError, ValueError, TypeError) as e:
            # データ処理エラー（予期しないレスポンス形式など）
            error_msg = (
                f"Data processing error while {operation_name.lower()} for "
                f"{item_desc}: {type(e).__name__}: {e}"
            )
            logger.error(error_msg)
            error_stats["failed"] += 1
            error_stats["errors"].append({
                "item": item_desc,
                "error_type": type(e).__name__,
                "message": str(e),
            })
            continue
        except Exception as e:
            # その他の予期しないエラー
            error_msg = (
                f"Unexpected error while {operation_name.lower()} for {item_desc}: "
                f"{type(e).__name__}: {e}"
            )
            logger.error(error_msg, exc_info=True)
            error_stats["failed"] += 1
            error_stats["errors"].append({
                "item": item_desc,
                "error_type": type(e).__name__,
                "message": str(e),
            })
            continue

    # サマリーログ
    success_rate = (error_stats["successful"] / error_stats["total_items"] * 100) if error_stats["total_items"] > 0 else 0
    logger.info(
        f"{operation_name} summary: {error_stats['successful']}/{error_stats['total_items']} successful "
        f"({success_rate:.1f}%), {error_stats['failed']} failed"
    )

    if error_stats["failed"] > 0:
        logger.warning(
            f"{operation_name} completed with {error_stats['failed']} failures. "
            f"Check logs for details."
        )

    return results, error_stats


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
    ti.xcom_push(key=XComKeys.REPOSITORIES, value=repositories)

    return repositories


def fetch_workflow_runs(
    github_client: GitHubClientProtocol, db: DatabaseClientProtocol, **context: Any
) -> None:
    """各リポジトリのワークフロー実行データを取得する

    初回実行時は全件取得、2回目以降は最新タイムスタンプからの差分取得を行う。

    Args:
        github_client: GitHubClientインスタンス（必須、外部から注入される）
        db: DatabaseClientインスタンス（必須、外部から注入される）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    # 前のタスクからリポジトリリストを取得
    repositories: list[dict[str, str]] = ti.xcom_pull(
        task_ids=TaskIds.FETCH_REPOSITORIES, key=XComKeys.REPOSITORIES
    )

    if not repositories:
        logger.warning("No repositories found to fetch workflow runs")
        return

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

        # リポジトリの最新実行タイムスタンプを取得
        latest_timestamp = db.get_latest_run_timestamp(owner, repo_name)

        if latest_timestamp is None:
            # 初回実行: 全件取得
            logger.info(f"Initial fetch for {owner}/{repo_name} (fetching all runs)")
            created_after = None
        else:
            # 2回目以降: 差分取得
            logger.info(
                f"Incremental fetch for {owner}/{repo_name} "
                f"(fetching runs after {latest_timestamp.isoformat()})"
            )
            created_after = latest_timestamp

        runs = github_client.get_workflow_runs(
            owner=owner, repo=repo_name, created_after=created_after
        )

        # リポジトリ情報を各runに追加
        for run in runs:
            run["_repository_owner"] = owner
            run["_repository_name"] = repo_name

        return runs

    all_workflow_runs, error_stats = _process_items_with_error_handling(
        items=repositories,
        process_func=process_repository,
        item_descriptor=lambda r: f"{r['owner']}/{r['repo']}",
        operation_name="Fetching workflow runs",
    )

    logger.info(f"Total workflow runs fetched: {len(all_workflow_runs)}")

    # エラー統計をXComに保存（モニタリング用）
    ti.xcom_push(key=f"{XComKeys.WORKFLOW_RUNS}_error_stats", value=error_stats)

    # XComサイズチェック
    check_xcom_size(all_workflow_runs, XComKeys.WORKFLOW_RUNS)

    # XComで次のタスクに渡す
    ti.xcom_push(key=XComKeys.WORKFLOW_RUNS, value=all_workflow_runs)

    # 全てのリポジトリで失敗した場合はエラーを投げる
    if error_stats["successful"] == 0 and error_stats["total_items"] > 0:
        raise RuntimeError(
            f"All {error_stats['total_items']} repositories failed to fetch workflow runs. "
            f"Check logs for details."
        )


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
        task_ids=TaskIds.FETCH_WORKFLOW_RUNS, key=XComKeys.WORKFLOW_RUNS
    )

    if not workflow_runs:
        logger.warning("No workflow runs found to fetch jobs")
        ti.xcom_push(key=XComKeys.WORKFLOW_RUN_JOBS, value=[])
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

    all_jobs, error_stats = _process_items_with_error_handling(
        items=workflow_runs,
        process_func=process_workflow_run,
        item_descriptor=lambda r: (
            f"workflow run {r['id']} "
            f"({r['_repository_owner']}/{r['_repository_name']})"
        ),
        operation_name="Fetching jobs",
    )

    logger.info(f"Total jobs fetched: {len(all_jobs)}")

    # エラー統計をXComに保存（モニタリング用）
    ti.xcom_push(key=f"{XComKeys.WORKFLOW_RUN_JOBS}_error_stats", value=error_stats)

    # XComサイズチェック
    check_xcom_size(all_jobs, XComKeys.WORKFLOW_RUN_JOBS)

    # XComで次のタスクに渡す
    ti.xcom_push(key=XComKeys.WORKFLOW_RUN_JOBS, value=all_jobs)

    # 全てのワークフロー実行で失敗した場合でも、部分的な成功があれば継続
    if error_stats["successful"] == 0 and error_stats["total_items"] > 0:
        logger.error(
            f"All {error_stats['total_items']} workflow runs failed to fetch jobs. "
            f"However, continuing with empty jobs list."
        )
