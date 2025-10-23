"""GitHub API Clientモジュール

PyGithubを使用したGitHub APIクライアント
"""

import logging
import os
from datetime import datetime
from typing import Any

from github import Auth, Github, GithubException, GithubRetry

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

        try:
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

        except GithubException as e:
            # 共通関数を使ってエラーメッセージを生成
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

        try:
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

        except GithubException as e:
            # 共通関数を使ってエラーメッセージを生成
            error_msg = _format_github_error_message(
                e, context="fetching jobs", owner=owner, repo=repo, run_id=run_id
            )
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
