"""GitHub API Clientモジュール

PyGithubを使用したGitHub APIクライアント
"""

import logging
import os
import time
from datetime import datetime
from typing import Any

from github import Auth, Github, GithubException, GithubRetry, RateLimitExceededException

from nagare.constants import GitHubConfig

logger = logging.getLogger(__name__)


def _format_github_error_message(
    e: GithubException, context: str, owner: str = "", repo: str = "", run_id: int = 0
) -> str:
    """GitHub APIエラーメッセージをフォーマットする

    Args:
        e: GithubException
        context: エラーコンテキスト（例: "fetching workflow runs"）
        owner: リポジトリのオーナー
        repo: リポジトリ名
        run_id: ワークフロー実行ID（ジョブ取得の場合）

    Returns:
        フォーマットされたエラーメッセージ
    """
    # リポジトリ情報の構築
    repo_info = f"{owner}/{repo}" if owner and repo else ""
    run_info = f" for run {run_id}" if run_id else ""

    # ステータスコード別のメッセージ
    if e.status == 401:
        return (
            f"Authentication failed while {context}{run_info}. "
            f"Check your GitHub credentials (token or app configuration)."
        )
    elif e.status == 403:
        return (
            f"Access forbidden while {context}{run_info}. "
            f"Check repository permissions or rate limits."
        )
    elif e.status == 404:
        resource = f"workflow run {run_id}" if run_id else f"repository {repo_info}"
        check_item = "run ID" if run_id else "repository name"
        return (
            f"{resource.capitalize()} not found while {context}. "
            f"Check the {check_item} or access permissions."
        )
    else:
        # その他のエラー
        error_data = (
            e.data.get("message", str(e.data)) if isinstance(e.data, dict) else e.data
        )
        target = f"{repo_info}{run_info}" if repo_info or run_id else context
        return f"Failed {context} for {target}: HTTP {e.status} - {error_data}"


class GitHubClient:
    """GitHub APIクライアント

    PyGithubライブラリを使用してGitHub APIにアクセスする。
    レート制限とリトライはPyGithubが自動処理する。

    Attributes:
        github: PyGithubのGithubインスタンス
    """

    def __init__(
        self,
        app_id: int | None = None,
        private_key: str | None = None,
        installation_id: int | None = None,
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        """GitHub Clientを初期化する

        引数が指定されない場合、環境変数から認証情報を読み取る。
        GitHub Appsとして認証する場合は app_id, private_key, installation_id を指定。
        Personal Access Tokenで認証する場合は token を指定。

        Args:
            app_id: GitHub App ID (未指定時は環境変数GITHUB_APP_IDから取得)
            private_key: GitHub App Private Key (未指定時は環境変数から取得)
            installation_id: GitHub App Installation ID (未指定時は環境変数から取得)
            token: Personal Access Token (未指定時は環境変数GITHUB_TOKENから取得)
            base_url: GitHub API ベースURL（GitHub Enterpriseの場合に変更可能）

        Raises:
            ValueError: 認証情報が不足している場合
        """
        # 各引数が未指定の場合に環境変数から読み取る
        # GitHub Apps認証
        if app_id is None:
            app_id_str = os.getenv("GITHUB_APP_ID")
            if app_id_str:
                try:
                    app_id = int(app_id_str)
                except ValueError as e:
                    raise ValueError(
                        f"GITHUB_APP_ID must be an integer, got: {app_id_str}"
                    ) from e

        if installation_id is None:
            installation_id_str = os.getenv("GITHUB_APP_INSTALLATION_ID")
            if installation_id_str:
                try:
                    installation_id = int(installation_id_str)
                except ValueError as e:
                    raise ValueError(
                        f"GITHUB_APP_INSTALLATION_ID must be an integer, "
                        f"got: {installation_id_str}"
                    ) from e

        if private_key is None:
            private_key_env = os.getenv("GITHUB_APP_PRIVATE_KEY")
            private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")

            if private_key_path and not private_key_env:
                try:
                    with open(private_key_path) as f:
                        private_key = f.read()
                except FileNotFoundError as e:
                    raise ValueError(
                        f"GitHub App private key file not found: {private_key_path}"
                    ) from e
                except PermissionError as e:
                    raise ValueError(
                        f"Permission denied reading GitHub App private key file: "
                        f"{private_key_path}"
                    ) from e
                except Exception as e:
                    raise ValueError(
                        f"Failed to read GitHub App private key file "
                        f"{private_key_path}: {e}"
                    ) from e
            elif private_key_env:
                private_key = private_key_env

        # Personal Access Token認証（フォールバック）
        if token is None:
            token = os.getenv("GITHUB_TOKEN")

        # 認証設定
        if app_id and private_key and installation_id:
            # GitHub Apps認証
            app_auth = Auth.AppAuth(app_id, private_key)
            auth = Auth.AppInstallationAuth(app_auth, installation_id)
            logger.debug("GitHubClient initialized with GitHub App authentication")
        elif token:
            # Personal Access Token認証
            auth = Auth.Token(token)
            logger.debug("GitHubClient initialized with token authentication")
        else:
            raise ValueError(
                "GitHub authentication not configured. "
                "Set either (GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID, "
                "GITHUB_APP_PRIVATE_KEY/PATH) or GITHUB_TOKEN"
            )

        # リトライ設定（指数バックオフ）
        retry = GithubRetry(
            total=GitHubConfig.RETRY_TOTAL,
            backoff_factor=GitHubConfig.RETRY_BACKOFF_FACTOR,
            status_forcelist=GitHubConfig.RETRY_STATUS_FORCELIST,
        )

        # GitHubクライアントの初期化
        # PyGithubがレート制限を自動的に処理
        self.github = Github(
            auth=auth,
            base_url=base_url,
            retry=retry,
            per_page=GitHubConfig.PER_PAGE,
        )

        # リポジトリオブジェクトのキャッシュ（API呼び出し削減）
        self._repo_cache: dict[str, Any] | None = (
            {} if GitHubConfig.ENABLE_REPO_CACHE else None
        )

    def _get_repository(self, owner: str, repo: str) -> Any:
        """リポジトリオブジェクトを取得（キャッシュ使用）

        Args:
            owner: リポジトリのオーナー
            repo: リポジトリ名

        Returns:
            PyGithubのRepositoryオブジェクト
        """
        repo_key = f"{owner}/{repo}"

        # キャッシュが有効な場合はキャッシュを使用
        if self._repo_cache is not None:
            if repo_key not in self._repo_cache:
                self._repo_cache[repo_key] = self.github.get_repo(repo_key)
            return self._repo_cache[repo_key]

        # キャッシュ無効の場合は毎回取得
        return self.github.get_repo(repo_key)

    def check_rate_limit(self) -> dict[str, Any]:
        """GitHub API rate limitの状態を確認する

        Returns:
            rate limit情報の辞書
            - core: コアAPIの情報
            - search: 検索APIの情報
        """
        rate_limit = self.github.get_rate_limit()

        core = rate_limit.resources.core
        search = rate_limit.resources.search

        rate_info = {
            "core": {
                "limit": core.limit,
                "remaining": core.remaining,
                "reset": core.reset.isoformat() if core.reset else None,
                "used": core.limit - core.remaining,
            },
            "search": {
                "limit": search.limit,
                "remaining": search.remaining,
                "reset": search.reset.isoformat() if search.reset else None,
                "used": search.limit - search.remaining,
            },
        }

        # ログ出力
        logger.info(
            f"GitHub API rate limit - Core: {core.remaining}/{core.limit}, "
            f"Search: {search.remaining}/{search.limit}"
        )

        # 残りが少ない場合は警告
        if core.remaining < core.limit * 0.1:  # 10%未満
            logger.warning(
                f"GitHub API rate limit running low: {core.remaining}/{core.limit} remaining"
            )

        return rate_info

    def wait_for_rate_limit_reset(self, resource: str = "core") -> None:
        """Rate limit resetまで待機する

        Args:
            resource: "core" または "search"
        """
        rate_limit = self.github.get_rate_limit()

        if resource == "core":
            reset_time = rate_limit.resources.core.reset
            remaining = rate_limit.resources.core.remaining
        elif resource == "search":
            reset_time = rate_limit.resources.search.reset
            remaining = rate_limit.resources.search.remaining
        else:
            logger.error(f"Unknown resource type: {resource}")
            return

        if remaining > 0:
            logger.info(f"Rate limit not exceeded for {resource}: {remaining} remaining")
            return

        # リセットまでの待機時間を計算
        wait_seconds = (reset_time - datetime.now(reset_time.tzinfo)).total_seconds()
        wait_seconds = max(wait_seconds, 0) + 5  # 安全のため5秒追加

        logger.warning(
            f"Rate limit exceeded for {resource}. "
            f"Waiting {wait_seconds:.0f} seconds until reset at {reset_time.isoformat()}"
        )

        time.sleep(wait_seconds)

    def get_workflow_runs(
        self,
        owner: str,
        repo: str,
        created_after: datetime | None = None,
        max_results: int = 1000,
    ) -> list[dict[str, Any]]:
        """ワークフロー実行データを取得する

        Args:
            owner: リポジトリのオーナー
            repo: リポジトリ名
            created_after: この日時以降に作成されたものを取得
            max_results: 取得する最大件数（デフォルト: 1000）

        Returns:
            ワークフロー実行データのリスト（辞書形式）

        Raises:
            GithubException: GitHub API呼び出しエラー
            ValueError: max_resultsが不正な値の場合
        """
        if max_results <= 0:
            raise ValueError(f"max_results must be positive, got: {max_results}")

        retry_count = 0
        max_retries = 3

        while retry_count <= max_retries:
            try:
                # Rate limit確認
                rate_info = self.check_rate_limit()
                if rate_info["core"]["remaining"] < 10:
                    logger.warning("Rate limit low, waiting for reset...")
                    self.wait_for_rate_limit_reset("core")

                # リポジトリオブジェクトを取得（キャッシュ使用）
                repository = self._get_repository(owner, repo)

                # ワークフロー実行を取得
                # PyGithubのget_workflow_runsは自動でページネーションを処理
                if created_after:
                    workflow_runs = repository.get_workflow_runs(
                        created=f">={created_after.isoformat()}"
                    )
                else:
                    workflow_runs = repository.get_workflow_runs()

                all_runs: list[dict[str, Any]] = []

                # 各ワークフロー実行を辞書形式に変換（最大件数まで）
                for i, run in enumerate(workflow_runs):
                    if i >= max_results:
                        logger.warning(
                            f"Reached max_results limit ({max_results}) for {owner}/{repo}"
                        )
                        break
                    # PyGithubのWorkflowRunオブジェクトを辞書に変換
                    run_dict = {
                        "id": run.id,
                        "name": run.name,
                        "head_branch": run.head_branch,
                        "head_sha": run.head_sha,
                        "status": run.status,
                        "conclusion": run.conclusion,
                        "event": run.event,
                        "created_at": (
                            run.created_at.isoformat() if run.created_at else None
                        ),
                        "updated_at": (
                            run.updated_at.isoformat() if run.updated_at else None
                        ),
                        "run_started_at": (
                            run.run_started_at.isoformat() if run.run_started_at else None
                        ),
                        "html_url": run.html_url,
                    }
                    all_runs.append(run_dict)

                logger.info(f"Fetched {len(all_runs)} workflow runs for {owner}/{repo}")
                return all_runs

            except RateLimitExceededException:
                logger.warning(f"Rate limit exceeded, waiting for reset (retry {retry_count}/{max_retries})")
                self.wait_for_rate_limit_reset("core")
                retry_count += 1
                if retry_count > max_retries:
                    raise

            except GithubException as e:
                # 一時的なエラー (502, 503, 504) の場合はリトライ
                if e.status in [502, 503, 504] and retry_count < max_retries:
                    wait_time = 2 ** retry_count  # 指数バックオフ
                    logger.warning(
                        f"Temporary error {e.status}, retrying in {wait_time}s "
                        f"(retry {retry_count}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    retry_count += 1
                    continue

                # その他のエラーは即座に例外を投げる
                error_msg = _format_github_error_message(
                    e, context="fetching workflow runs", owner=owner, repo=repo
                )
                logger.error(error_msg)
                raise GithubException(e.status, e.data, e.headers) from e

    def get_workflow_run_jobs(
        self, owner: str, repo: str, run_id: int, max_results: int = 1000
    ) -> list[dict[str, Any]]:
        """特定のワークフロー実行のジョブ情報を取得する

        Args:
            owner: リポジトリのオーナー
            repo: リポジトリ名
            run_id: ワークフロー実行ID
            max_results: 取得する最大件数（デフォルト: 1000）

        Returns:
            ジョブ情報のリスト（辞書形式）

        Raises:
            GithubException: GitHub API呼び出しエラー
            ValueError: max_resultsが不正な値の場合
        """
        if max_results <= 0:
            raise ValueError(f"max_results must be positive, got: {max_results}")

        retry_count = 0
        max_retries = 3

        while retry_count <= max_retries:
            try:
                # Rate limit確認
                rate_info = self.check_rate_limit()
                if rate_info["core"]["remaining"] < 10:
                    logger.warning("Rate limit low, waiting for reset...")
                    self.wait_for_rate_limit_reset("core")

                # リポジトリオブジェクトを取得（キャッシュ使用）
                repository = self._get_repository(owner, repo)

                # ワークフロー実行を取得
                workflow_run = repository.get_workflow_run(run_id)

                # ジョブ一覧を取得
                jobs = workflow_run.jobs()

                all_jobs: list[dict[str, Any]] = []

                for i, job in enumerate(jobs):
                    if i >= max_results:
                        logger.warning(
                            f"Reached max_results limit ({max_results}) "
                            f"for workflow run {run_id}"
                        )
                        break
                    job_dict = {
                        "id": job.id,
                        "run_id": job.run_id,
                        "name": job.name,
                        "status": job.status,
                        "conclusion": job.conclusion,
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        "html_url": job.html_url,
                    }
                    all_jobs.append(job_dict)

                logger.info(f"Fetched {len(all_jobs)} jobs for workflow run {run_id}")
                return all_jobs

            except RateLimitExceededException:
                logger.warning(f"Rate limit exceeded, waiting for reset (retry {retry_count}/{max_retries})")
                self.wait_for_rate_limit_reset("core")
                retry_count += 1
                if retry_count > max_retries:
                    raise

            except GithubException as e:
                # 一時的なエラー (502, 503, 504) の場合はリトライ
                if e.status in [502, 503, 504] and retry_count < max_retries:
                    wait_time = 2 ** retry_count  # 指数バックオフ
                    logger.warning(
                        f"Temporary error {e.status}, retrying in {wait_time}s "
                        f"(retry {retry_count}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    retry_count += 1
                    continue

                # その他のエラーは即座に例外を投げる
                error_msg = _format_github_error_message(
                    e, context="fetching jobs", owner=owner, repo=repo, run_id=run_id
                )
                logger.error(error_msg)
                raise GithubException(e.status, e.data, e.headers) from e

    def get_organization_repositories(
        self, org_name: str, page: int = 1, per_page: int = 30
    ) -> dict[str, Any]:
        """組織のリポジトリ一覧を取得する（ページング対応）

        Args:
            org_name: 組織名
            page: ページ番号（1から開始）
            per_page: 1ページあたりの件数（デフォルト: 30、最大: 100）

        Returns:
            辞書形式:
            - repos: リポジトリ情報のリスト
            - page: 現在のページ番号
            - per_page: 1ページあたりの件数
            - has_next: 次のページがあるか

        Raises:
            GithubException: GitHub API呼び出しエラー
            ValueError: pageまたはper_pageが不正な値の場合
        """
        if page < 1:
            raise ValueError(f"page must be >= 1, got: {page}")
        if per_page < 1 or per_page > 100:
            raise ValueError(f"per_page must be between 1 and 100, got: {per_page}")

        try:
            org = self.github.get_organization(org_name)
            repos_paginated = org.get_repos()

            # ページング処理: PyGithubのPaginatedListを使用
            all_repos: list[dict[str, Any]] = []
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page

            for i, repo in enumerate(repos_paginated):
                if i < start_idx:
                    continue
                if i >= end_idx:
                    break

                repo_dict = {
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "owner": repo.owner.login,
                    "description": repo.description,
                    "private": repo.private,
                    "html_url": repo.html_url,
                    "stargazers_count": repo.stargazers_count,
                    "forks_count": repo.forks_count,
                    "language": repo.language,
                    "updated_at": (
                        repo.updated_at.isoformat() if repo.updated_at else None
                    ),
                    "has_actions": True,
                }
                all_repos.append(repo_dict)

            # 次のページがあるかチェック
            has_next = False
            try:
                # 次のページの最初のアイテムを確認
                for i, _ in enumerate(repos_paginated):
                    if i == end_idx:
                        has_next = True
                        break
            except StopIteration:
                has_next = False

            logger.info(
                f"Fetched {len(all_repos)} repositories for org {org_name} "
                f"(page {page}, per_page {per_page})"
            )

            return {
                "repos": all_repos,
                "page": page,
                "per_page": per_page,
                "has_next": has_next,
            }

        except GithubException as e:
            error_msg = f"Failed to fetch repositories for organization '{org_name}': HTTP {e.status}"
            if e.status == 404:
                error_msg = f"Organization '{org_name}' not found or not accessible"
            logger.error(error_msg)
            raise GithubException(e.status, e.data, e.headers) from e

    def get_user_repositories(
        self, username: str, page: int = 1, per_page: int = 30
    ) -> dict[str, Any]:
        """ユーザーのリポジトリ一覧を取得する（ページング対応）

        Args:
            username: ユーザー名
            page: ページ番号（1から開始）
            per_page: 1ページあたりの件数（デフォルト: 30、最大: 100）

        Returns:
            辞書形式:
            - repos: リポジトリ情報のリスト
            - page: 現在のページ番号
            - per_page: 1ページあたりの件数
            - has_next: 次のページがあるか

        Raises:
            GithubException: GitHub API呼び出しエラー
            ValueError: pageまたはper_pageが不正な値の場合
        """
        if page < 1:
            raise ValueError(f"page must be >= 1, got: {page}")
        if per_page < 1 or per_page > 100:
            raise ValueError(f"per_page must be between 1 and 100, got: {per_page}")

        try:
            user = self.github.get_user(username)
            repos_paginated = user.get_repos()

            # ページング処理
            all_repos: list[dict[str, Any]] = []
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page

            for i, repo in enumerate(repos_paginated):
                if i < start_idx:
                    continue
                if i >= end_idx:
                    break

                repo_dict = {
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "owner": repo.owner.login,
                    "description": repo.description,
                    "private": repo.private,
                    "html_url": repo.html_url,
                    "stargazers_count": repo.stargazers_count,
                    "forks_count": repo.forks_count,
                    "language": repo.language,
                    "updated_at": (
                        repo.updated_at.isoformat() if repo.updated_at else None
                    ),
                    "has_actions": True,
                }
                all_repos.append(repo_dict)

            # 次のページがあるかチェック
            has_next = False
            try:
                for i, _ in enumerate(repos_paginated):
                    if i == end_idx:
                        has_next = True
                        break
            except StopIteration:
                has_next = False

            logger.info(
                f"Fetched {len(all_repos)} repositories for user {username} "
                f"(page {page}, per_page {per_page})"
            )

            return {
                "repos": all_repos,
                "page": page,
                "per_page": per_page,
                "has_next": has_next,
            }

        except GithubException as e:
            error_msg = f"Failed to fetch repositories for user '{username}': HTTP {e.status}"
            if e.status == 404:
                error_msg = f"User '{username}' not found or not accessible"
            logger.error(error_msg)
            raise GithubException(e.status, e.data, e.headers) from e

    def search_repositories(
        self, query: str, page: int = 1, per_page: int = 30
    ) -> dict[str, Any]:
        """リポジトリを検索する（ページング対応）

        Args:
            query: 検索クエリ（例: "org:myorg", "user:username", "language:python"）
            page: ページ番号（1から開始）
            per_page: 1ページあたりの件数（デフォルト: 30、最大: 100）

        Returns:
            辞書形式:
            - repos: リポジトリ情報のリスト
            - page: 現在のページ番号
            - per_page: 1ページあたりの件数
            - total_count: 検索結果総数（GitHub APIから取得）
            - has_next: 次のページがあるか

        Raises:
            GithubException: GitHub API呼び出しエラー
            ValueError: pageまたはper_pageが不正な値の場合
        """
        if page < 1:
            raise ValueError(f"page must be >= 1, got: {page}")
        if per_page < 1 or per_page > 100:
            raise ValueError(f"per_page must be between 1 and 100, got: {per_page}")

        try:
            repos_paginated = self.github.search_repositories(query=query)

            # 総数を取得（GitHubの検索APIは総数を提供）
            total_count = repos_paginated.totalCount

            # ページング処理
            all_repos: list[dict[str, Any]] = []
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page

            for i, repo in enumerate(repos_paginated):
                if i < start_idx:
                    continue
                if i >= end_idx:
                    break

                repo_dict = {
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "owner": repo.owner.login,
                    "description": repo.description,
                    "private": repo.private,
                    "html_url": repo.html_url,
                    "stargazers_count": repo.stargazers_count,
                    "forks_count": repo.forks_count,
                    "language": repo.language,
                    "updated_at": (
                        repo.updated_at.isoformat() if repo.updated_at else None
                    ),
                    "has_actions": True,
                }
                all_repos.append(repo_dict)

            # 次のページがあるかチェック
            has_next = (page * per_page) < total_count

            logger.info(
                f"Found {len(all_repos)} repositories for query '{query}' "
                f"(page {page}/{(total_count + per_page - 1) // per_page}, "
                f"total: {total_count})"
            )

            return {
                "repos": all_repos,
                "page": page,
                "per_page": per_page,
                "total_count": total_count,
                "has_next": has_next,
            }

        except GithubException as e:
            error_msg = f"Failed to search repositories with query '{query}': HTTP {e.status}"
            logger.error(error_msg)
            raise GithubException(e.status, e.data, e.headers) from e

    def close(self) -> None:
        """GitHubクライアントをクローズする"""
        self.github.close()
        logger.debug("GitHubClient closed")

    def __enter__(self) -> "GitHubClient":
        """Context manager: with文でのエントリーポイント

        Returns:
            GitHubClientインスタンス自身
        """
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理

        Args:
            *args: 例外情報（型、値、トレースバック）
        """
        self.close()
