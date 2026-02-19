"""データ取得タスク"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from airflow.models import TaskInstance
from github import GithubException

from nagare.constants import FetchConfig, SourceType, TaskIds, XComKeys
from nagare.utils.protocols import (
    BitriseClientProtocol,
    DatabaseClientProtocol,
    GitHubClientProtocol,
    XcodeCloudClientProtocol,
)
from nagare.utils.xcom_utils import check_xcom_size

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Rate limit回避のため期間分割してバッチ取得
INITIAL_FETCH_DAYS = 30
INITIAL_PERIOD_DAYS = 6
INITIAL_PERIODS = 5
INCREMENTAL_PERIOD_DAYS = 7


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
            # その他の予期しないエラー（初回のみスタックトレースを出力）
            error_msg = (
                f"Unexpected error while {operation_name.lower()} for {item_desc}: "
                f"{type(e).__name__}: {e}"
            )
            logger.error(error_msg, exc_info=(error_stats["failed"] == 0))
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
    db: DatabaseClientProtocol, source: str | None = None, batch_size: int | None = None, **context: Any
) -> list[dict[str, Any]]:
    """監視対象のリポジトリリストを取得し、期間別バッチに分割する

    PostgreSQLから監視対象リポジトリを取得し、Dynamic Task Mapping用にバッチに分割する。
    前回取得時を起点に7日ごとの期間でも分割することで、データ量を削減する。

    Args:
        db: DatabaseClientインスタンス（必須、外部から注入される）
        source: ソースタイプでフィルタ（オプション）。例: "github_actions", "bitrise"
        batch_size: バッチサイズ（省略時はFetchConfig.BATCH_SIZEを使用）
        **context: Airflowのコンテキスト

    Returns:
        op_kwargsの辞書リスト（Dynamic Task Mappingで展開される）
        GitHubの場合: [{"batch_repos": [...], "since": "...", "until": "..."}, ...]
        Bitriseの場合: [{"batch_apps": [...], "since": "...", "until": "..."}, ...]
    """
    # データベースから取得
    repositories = db.get_repositories(source=source)

    source_msg = f" for source '{source}'" if source else ""
    logger.info(f"Found {len(repositories)} repositories to monitor{source_msg}")

    # バッチサイズのデフォルト値
    if batch_size is None:
        batch_size = FetchConfig.BATCH_SIZE

    # Rate limit回避のため期間分割
    now = datetime.now(UTC)

    try:
        oldest_timestamp = db.get_oldest_run_timestamp(source=source)
    except Exception as e:
        logger.warning(
            f"Failed to get oldest run timestamp for source '{source}': {e}. "
            f"Assuming initial fetch."
        )
        oldest_timestamp = None

    # 初回は過去30日、それ以降は前回取得時から現在まで
    if oldest_timestamp is None:
        logger.info(
            f"Initial fetch detected. Splitting {INITIAL_FETCH_DAYS} days into "
            f"{INITIAL_PERIODS} periods ({INITIAL_PERIOD_DAYS} days each)"
        )
        start_date = now - timedelta(days=INITIAL_FETCH_DAYS)
        periods = []
        for i in range(INITIAL_PERIODS):
            period_start = start_date + timedelta(days=i * INITIAL_PERIOD_DAYS)
            # 最後の期間は残り日数を全て含む
            if i < INITIAL_PERIODS - 1:
                period_end = start_date + timedelta(days=(i + 1) * INITIAL_PERIOD_DAYS)
            else:
                period_end = now
            # 空の期間をスキップ
            if period_start < now:
                periods.append({
                    "since": period_start.isoformat(),
                    "until": period_end.isoformat()
                })
    else:
        # 2回目以降: 前回取得時から現在まで7日ごとに分割
        days_since_last = (now - oldest_timestamp).days
        logger.info(f"Incremental fetch detected. Last fetch was {days_since_last} days ago")

        if days_since_last <= INCREMENTAL_PERIOD_DAYS:
            # 期間内なら1期間のみ
            periods = [{
                "since": oldest_timestamp.isoformat(),
                "until": now.isoformat()
            }]
        else:
            # 指定日数ごとに分割
            periods = []
            current_start = oldest_timestamp
            while current_start < now:
                current_end = min(current_start + timedelta(days=INCREMENTAL_PERIOD_DAYS), now)
                periods.append({
                    "since": current_start.isoformat(),
                    "until": current_end.isoformat()
                })
                current_start = current_end

    logger.info(f"Generated {len(periods)} time periods for data fetching")

    # リポジトリをバッチに分割してop_kwargs形式に変換
    # GitHubとBitriseでパラメータ名が異なるため、sourceで判定
    param_name = "batch_repos" if source == SourceType.GITHUB_ACTIONS else "batch_apps"

    batch_op_kwargs = []
    for i in range(0, len(repositories), batch_size):
        repo_batch = repositories[i:i + batch_size]
        # 各リポジトリバッチ × 各期間の組み合わせを生成
        for period in periods:
            batch_op_kwargs.append({
                param_name: repo_batch,
                "since": period["since"],
                "until": period["until"]
            })

    logger.info(
        f"Split into {len(batch_op_kwargs)} batches "
        f"({len(range(0, len(repositories), batch_size))} repo batches × {len(periods)} periods)"
    )

    # XComで次のタスクに渡す（後方互換性のため元のリストも保持）
    ti: TaskInstance = context["ti"]
    ti.xcom_push(key=XComKeys.REPOSITORIES, value=repositories)

    return batch_op_kwargs


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

    _fetch_workflow_runs_impl(repositories, github_client, db, ti, context)


def fetch_workflow_runs_batch(
    github_client: GitHubClientProtocol,
    db: DatabaseClientProtocol,
    batch_repos: list[dict[str, str]],
    since: str | None = None,
    until: str | None = None,
    **context: Any
) -> None:
    """リポジトリのバッチでワークフロー実行データを取得する（並列処理用）

    Dynamic Task Mappingで使用される。各タスクは1つのバッチ（リポジトリのリスト）と期間を処理する。

    Args:
        github_client: GitHubClientインスタンス
        db: DatabaseClientインスタンス
        batch_repos: 処理対象のリポジトリリスト
        since: 取得開始日時（ISO8601形式）
        until: 取得終了日時（ISO8601形式）
        **context: Airflowのコンテキスト
    """
    ti: TaskInstance = context["ti"]

    if not batch_repos:
        logger.warning("No repositories in this batch")
        return

    # map_indexを取得してログに使用（Dynamic Task Mappingで自動設定される）
    map_index = context.get("task_instance").map_index
    period_info = f" (period: {since} to {until})" if since and until else ""
    logger.info(
        f"Processing batch {map_index}: {len(batch_repos)} repositories{period_info}"
    )

    _fetch_workflow_runs_impl(
        batch_repos, github_client, db, ti, context,
        xcom_suffix=f"_batch_{map_index}",
        since=since,
        until=until
    )


def _collect_workflow_runs_from_xcom(ti: TaskInstance) -> list[dict[str, Any]]:
    """複数のバッチタスクからワークフロー実行データを収集する

    Args:
        ti: TaskInstanceインスタンス

    Returns:
        全バッチからのワークフロー実行リスト
    """
    # まず通常のXComキーを試す
    workflow_runs = ti.xcom_pull(
        task_ids=TaskIds.FETCH_WORKFLOW_RUNS, key=XComKeys.WORKFLOW_RUNS
    )

    if workflow_runs:
        logger.info(f"Found {len(workflow_runs)} workflow runs from single task")
        return workflow_runs

    # バッチタスクからの収集を試みる
    all_runs = []
    batch_index = 0

    while True:
        task_id = f"fetch_workflow_runs_batch_{batch_index}"
        xcom_key = f"{XComKeys.WORKFLOW_RUNS}_batch_{batch_index}"

        batch_runs = ti.xcom_pull(task_ids=task_id, key=xcom_key)

        if batch_runs is None:
            break

        logger.info(f"Found {len(batch_runs)} workflow runs from batch {batch_index}")
        all_runs.extend(batch_runs)
        batch_index += 1

    if all_runs:
        logger.info(f"Collected total {len(all_runs)} workflow runs from {batch_index} batches")

    return all_runs


def _fetch_workflow_runs_impl(
    repositories: list[dict[str, str]],
    github_client: GitHubClientProtocol,
    db: DatabaseClientProtocol,
    ti: TaskInstance,
    context: dict[str, Any],
    xcom_suffix: str = "",
    since: str | None = None,
    until: str | None = None
) -> None:
    """ワークフロー実行データ取得の実装（共通処理）

    Args:
        repositories: 処理対象のリポジトリリスト
        github_client: GitHubClientインスタンス
        db: DatabaseClientインスタンス
        ti: TaskInstanceインスタンス
        context: Airflowのコンテキスト
        xcom_suffix: XComキーに付加するサフィックス（バッチ処理用）
        since: 取得開始日時（ISO8601形式、優先使用）
        until: 取得終了日時（ISO8601形式）
    """

    if not repositories:
        logger.warning("No repositories to process")
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

        # バッチ処理時は指定期間、それ以外は差分取得
        if since is not None:
            created_after = datetime.fromisoformat(since)
            logger.info(
                f"Fetching {owner}/{repo_name} for period {since} to {until}"
            )
        else:
            # DBから最新タイムスタンプを取得して差分取得
            latest_timestamp = db.get_latest_run_timestamp(owner, repo_name)

            if latest_timestamp is None:
                logger.info(f"Initial fetch for {owner}/{repo_name} (fetching all runs)")
                created_after = None
            else:
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

    # ADR-006: 一時テーブルにデータを保存（XComは統計のみ）
    run_id = context.get("run_id", ti.run_id)
    task_id = ti.task_id

    # 一時テーブルに保存
    db.insert_temp_workflow_runs(all_workflow_runs, task_id=task_id, run_id=run_id)

    # XComには統計情報のみ保存（軽量）
    ti.xcom_push(
        key=f"batch_stats{xcom_suffix}",
        value={
            "count": len(all_workflow_runs),
            "task_id": task_id,
            "run_id": run_id,
            "error_stats": error_stats,
        }
    )

    logger.info(
        f"Saved {len(all_workflow_runs)} workflow runs to temp table "
        f"(task_id={task_id}, run_id={run_id})"
    )

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

    # 前のタスクからワークフロー実行リストを取得（バッチ対応）
    workflow_runs = _collect_workflow_runs_from_xcom(ti)

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


def _fetch_bitrise_builds_impl(
    bitrise_apps: list[dict[str, Any]],
    bitrise_client: BitriseClientProtocol,
    db: DatabaseClientProtocol,
    ti: TaskInstance,
    context: dict[str, Any],
    xcom_suffix: str = "",
    since: str | None = None,
    until: str | None = None,
) -> None:
    """Bitriseビルドデータを取得する内部実装（バッチ処理対応）

    Args:
        bitrise_apps: Bitriseアプリのリスト
        bitrise_client: BitriseClientインスタンス
        db: DatabaseClientインスタンス
        ti: TaskInstanceインスタンス
        context: Airflowのコンテキスト
        xcom_suffix: XComキーのサフィックス（バッチ処理時に使用）
        since: 取得開始日時（ISO8601形式、オプショナル）
        until: 取得終了日時（ISO8601形式、オプショナル）
    """
    all_builds = []
    error_stats = {
        "total_items": len(bitrise_apps),
        "successful": 0,
        "failed": 0,
        "errors": [],
    }

    for app in bitrise_apps:
        # source_repository_idがBitriseのapp_slug（UUID）
        app_slug = app["source_repository_id"]
        repository_name = app["repository_name"]  # GitHub repo名（表示用）
        try:
            # repository_nameを"owner/repo"形式に分割
            owner, repo = repository_name.split("/", 1) if "/" in repository_name else (repository_name, repository_name)

            # 期間パラメータが指定されている場合はそれを使用、なければ既存のロジック
            if since is not None:
                # 期間指定あり: バッチの期間を使用
                after_date = datetime.fromisoformat(since)
                logger.info(
                    f"Fetching builds for {repository_name} for period {since} to {until}"
                )
            else:
                # 期間指定なし: 既存の差分取得ロジック
                logger.info(f"Fetching builds for Bitrise app: {repository_name} (app_slug: {app_slug})")
                after_date = None
                try:
                    latest_timestamp = db.get_latest_run_timestamp(owner, repo)
                    if latest_timestamp:
                        after_date = latest_timestamp
                        logger.info(f"Fetching builds after {latest_timestamp} for {app_slug}")
                    else:
                        logger.info(f"Fetching initial builds for {repository_name}")
                except Exception as e:
                    logger.warning(
                        f"Failed to get timestamp for {owner}/{repo}: {e}. "
                        f"Fetching all recent builds."
                    )

            # ビルドを取得
            builds = bitrise_client.get_builds(app_slug, limit=50)

            # after_dateが指定されている場合はフィルタ
            if after_date:
                builds = [
                    b for b in builds
                    if datetime.fromisoformat(b["triggered_at"].replace("Z", "+00:00")) > after_date
                ]

            logger.info(f"Fetched {len(builds)} builds from {repository_name}")

            # リポジトリ情報を追加（transform_dataで必要）
            # owner/repo は上で解析済みの変数を再利用
            for build in builds:
                build["repository_id"] = app["id"]
                build["app_slug"] = app_slug
                build["_repository_owner"] = owner
                build["_repository_name"] = repo
                build["_source"] = "bitrise"  # ソース識別子
                # BitriseのビルドIDはslugフィールドにある。idフィールドとして複製
                if "slug" in build and "id" not in build:
                    build["id"] = build["slug"]

            all_builds.extend(builds)
            error_stats["successful"] += 1

        except Exception as e:
            error_msg = f"Error fetching builds for {repository_name}: {type(e).__name__}: {e}"
            # 初回のみスタックトレースを出力（大量失敗時のログ肥大化を防ぐ）
            logger.error(error_msg, exc_info=(error_stats["failed"] == 0))
            error_stats["failed"] += 1
            error_stats["errors"].append({
                "item": repository_name,
                "error_type": type(e).__name__,
                "message": str(e),
            })
            continue

    # サマリーログ
    success_rate = (error_stats["successful"] / error_stats["total_items"] * 100) if error_stats["total_items"] > 0 else 0
    logger.info(
        f"Bitrise builds fetch summary: {error_stats['successful']}/{error_stats['total_items']} successful "
        f"({success_rate:.1f}%), {error_stats['failed']} failed"
    )

    logger.info(f"Total builds fetched: {len(all_builds)}")

    # ADR-006: 一時テーブルにデータを保存（XComは統計のみ）
    run_id = context.get("run_id", ti.run_id)
    task_id = ti.task_id

    # 一時テーブルに保存
    db.insert_temp_workflow_runs(all_builds, task_id=task_id, run_id=run_id)

    # XComには統計情報のみ保存（軽量）
    ti.xcom_push(
        key=f"batch_stats{xcom_suffix}",
        value={
            "count": len(all_builds),
            "task_id": task_id,
            "run_id": run_id,
            "error_stats": error_stats,
        }
    )

    logger.info(
        f"Saved {len(all_builds)} Bitrise builds to temp table "
        f"(task_id={task_id}, run_id={run_id})"
    )

    if error_stats["successful"] == 0 and error_stats["total_items"] > 0:
        logger.error(
            f"All {error_stats['total_items']} Bitrise apps failed to fetch builds. "
            f"However, continuing with empty builds list."
        )


def fetch_bitrise_builds(
    bitrise_client: BitriseClientProtocol,
    db: DatabaseClientProtocol,
    **context: Any,
) -> None:
    """Bitriseビルドデータを取得する

    Args:
        bitrise_client: BitriseClientインスタンス
        db: DatabaseClientインスタンス
        **context: Airflowコンテキスト（tiを含む）
    """
    ti: TaskInstance = context["ti"]

    bitrise_apps = ti.xcom_pull(
        task_ids=TaskIds.FETCH_REPOSITORIES, key=XComKeys.REPOSITORIES
    )

    if not bitrise_apps:
        logger.warning("No Bitrise apps found in XCom")
        return

    _fetch_bitrise_builds_impl(bitrise_apps, bitrise_client, db, ti, context)


def fetch_bitrise_builds_batch(
    bitrise_client: BitriseClientProtocol,
    db: DatabaseClientProtocol,
    batch_apps: list[dict[str, Any]],
    since: str | None = None,
    until: str | None = None,
    **context: Any,
) -> None:
    """Bitriseビルドデータをバッチ単位で取得する

    Dynamic Task Mappingで使用される。各タスクは1つのバッチ（アプリのリスト）と期間を処理する。

    Args:
        bitrise_client: BitriseClientインスタンス
        db: DatabaseClientインスタンス
        batch_apps: 処理対象のアプリリスト
        since: 取得開始日時（ISO8601形式、オプショナル）
        until: 取得終了日時（ISO8601形式、オプショナル）
        **context: Airflowコンテキスト（tiを含む）
    """
    ti: TaskInstance = context["ti"]

    if not batch_apps:
        logger.warning("No Bitrise apps in this batch")
        return

    # map_indexを取得してログに使用（Dynamic Task Mappingで自動設定される）
    map_index = context.get("task_instance").map_index
    period_info = f" (period: {since} to {until})" if since and until else ""
    logger.info(
        f"Processing batch {map_index}: {len(batch_apps)} apps{period_info}"
    )

    _fetch_bitrise_builds_impl(
        batch_apps, bitrise_client, db, ti, context,
        xcom_suffix=f"_batch_{map_index}",
        since=since,
        until=until
    )


def _fetch_xcode_cloud_builds_impl(
    xcode_cloud_apps: list[dict[str, Any]],
    xcode_cloud_client: XcodeCloudClientProtocol,
    db: DatabaseClientProtocol,
    ti: TaskInstance,
    context: dict[str, Any],
    xcom_suffix: str = "",
    since: str | None = None,
    until: str | None = None,
) -> None:
    """Xcode Cloudビルドデータを取得する内部実装（バッチ処理対応）

    Args:
        xcode_cloud_apps: Xcode Cloudアプリのリスト
        xcode_cloud_client: XcodeCloudClientインスタンス
        db: DatabaseClientインスタンス
        ti: TaskInstanceインスタンス
        context: Airflowのコンテキスト
        xcom_suffix: XComキーのサフィックス（バッチ処理時に使用）
        since: 取得開始日時（ISO8601形式、オプショナル）
        until: 取得終了日時（ISO8601形式、オプショナル）
    """
    all_builds = []
    error_stats = {
        "total_items": len(xcode_cloud_apps),
        "successful": 0,
        "failed": 0,
        "errors": [],
    }

    for app in xcode_cloud_apps:
        # source_repository_idがApp Store ConnectのApp ID
        app_id = app["source_repository_id"]
        repository_name = app["repository_name"]  # アプリ名（表示用）
        try:
            # repository_nameを"owner/repo"形式に分割（アプリ名をそのまま使用）
            owner, repo = repository_name.split("/", 1) if "/" in repository_name else (repository_name, repository_name)

            # 期間パラメータが指定されている場合はそれを使用、なければ既存のロジック
            filter_start = None
            filter_end = None
            if since is not None:
                # 期間指定あり: バッチの期間を使用
                filter_start = since
                filter_end = until
                logger.info(
                    f"Fetching builds for {repository_name} for period {since} to {until}"
                )
            else:
                # 期間指定なし: 既存の差分取得ロジック
                logger.info(f"Fetching builds for Xcode Cloud app: {repository_name} (app_id: {app_id})")
                try:
                    latest_timestamp = db.get_latest_run_timestamp(owner, repo)
                    if latest_timestamp:
                        # ISO8601形式に変換
                        filter_start = latest_timestamp.isoformat()
                        logger.info(f"Fetching builds after {latest_timestamp} for {app_id}")
                    else:
                        logger.info(f"Fetching initial builds for {repository_name}")
                except Exception as e:
                    logger.warning(
                        f"Failed to get timestamp for {owner}/{repo}: {e}. "
                        f"Fetching all recent builds."
                    )

            # ビルドを取得
            builds = xcode_cloud_client.list_ci_builds_for_app(
                app_id=app_id,
                limit=200,
                filter_created_date_start=filter_start,
                filter_created_date_end=filter_end,
            )

            logger.info(f"Fetched {len(builds)} builds from {repository_name}")

            # リポジトリ情報を追加（transform_dataで必要）
            owner, repo = repository_name.split("/", 1) if "/" in repository_name else (repository_name, repository_name)
            for build in builds:
                build["repository_id"] = app["id"]
                build["app_id"] = app_id
                build["_repository_owner"] = owner
                build["_repository_name"] = repo
                build["_source"] = "xcode_cloud"  # ソース識別子

            all_builds.extend(builds)
            error_stats["successful"] += 1

        except Exception as e:
            error_msg = f"Error fetching builds for {repository_name}: {type(e).__name__}: {e}"
            # 初回のみスタックトレースを出力（大量失敗時のログ肥大化を防ぐ）
            logger.error(error_msg, exc_info=(error_stats["failed"] == 0))
            error_stats["failed"] += 1
            error_stats["errors"].append({
                "item": repository_name,
                "error_type": type(e).__name__,
                "message": str(e),
            })
            continue

    # サマリーログ
    success_rate = (error_stats["successful"] / error_stats["total_items"] * 100) if error_stats["total_items"] > 0 else 0
    logger.info(
        f"Xcode Cloud builds fetch summary: {error_stats['successful']}/{error_stats['total_items']} successful "
        f"({success_rate:.1f}%), {error_stats['failed']} failed"
    )

    logger.info(f"Total builds fetched: {len(all_builds)}")

    # ADR-006: 一時テーブルにデータを保存（XComは統計のみ）
    run_id = context.get("run_id", ti.run_id)
    task_id = ti.task_id

    # 一時テーブルに保存
    db.insert_temp_workflow_runs(all_builds, task_id=task_id, run_id=run_id)

    # XComには統計情報のみ保存（軽量）
    ti.xcom_push(
        key=f"batch_stats{xcom_suffix}",
        value={
            "count": len(all_builds),
            "task_id": task_id,
            "run_id": run_id,
            "error_stats": error_stats,
        }
    )

    logger.info(
        f"Saved {len(all_builds)} Xcode Cloud builds to temp table "
        f"(task_id={task_id}, run_id={run_id})"
    )

    if error_stats["successful"] == 0 and error_stats["total_items"] > 0:
        logger.error(
            f"All {error_stats['total_items']} Xcode Cloud apps failed to fetch builds. "
            f"However, continuing with empty builds list."
        )


def fetch_xcode_cloud_builds_batch(
    xcode_cloud_client: XcodeCloudClientProtocol,
    db: DatabaseClientProtocol,
    batch_apps: list[dict[str, Any]],
    since: str | None = None,
    until: str | None = None,
    **context: Any,
) -> None:
    """Xcode Cloudビルドデータをバッチ単位で取得する

    Dynamic Task Mappingで使用される。各タスクは1つのバッチ（アプリのリスト）と期間を処理する。

    Args:
        xcode_cloud_client: XcodeCloudClientインスタンス
        db: DatabaseClientインスタンス
        batch_apps: 処理対象のアプリリスト
        since: 取得開始日時（ISO8601形式、オプショナル）
        until: 取得終了日時（ISO8601形式、オプショナル）
        **context: Airflowコンテキスト（tiを含む）
    """
    ti: TaskInstance = context["ti"]

    if not batch_apps:
        logger.warning("No Xcode Cloud apps in this batch")
        return

    # map_indexを取得してログに使用（Dynamic Task Mappingで自動設定される）
    map_index = context.get("task_instance").map_index
    period_info = f" (period: {since} to {until})" if since and until else ""
    logger.info(
        f"Processing batch {map_index}: {len(batch_apps)} apps{period_info}"
    )

    _fetch_xcode_cloud_builds_impl(
        xcode_cloud_apps=batch_apps,
        xcode_cloud_client=xcode_cloud_client,
        db=db,
        ti=ti,
        context=context,
        xcom_suffix=f"_batch_{map_index}",
        since=since,
        until=until
    )
