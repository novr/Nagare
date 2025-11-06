"""Bitrise API Clientモジュール

Bitrise API v0.1を使用したCI/CDデータ取得クライアント

ADR-002: Connection管理アーキテクチャに準拠し、
BitriseConnectionから接続情報を受け取る。

Reference:
    https://api-docs.bitrise.io/
"""

import logging
from datetime import datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nagare.constants import Platform
from nagare.utils.connections import BitriseConnection

logger = logging.getLogger(__name__)


class BitriseAPIException(Exception):
    """Bitrise API例外"""

    def __init__(self, status_code: int, message: str, response: dict[str, Any] | None = None):
        self.status_code = status_code
        self.message = message
        self.response = response
        super().__init__(f"HTTP {status_code}: {message}")


class BitriseClient:
    """Bitrise APIクライアント

    Bitrise API v0.1を使用してビルドデータを取得する。
    レート制限とリトライを自動処理する。

    Attributes:
        session: requestsセッション
        base_url: APIベースURL
        headers: 認証ヘッダー
    """

    def __init__(
        self,
        connection: BitriseConnection | None = None,
        # 後方互換性のため既存引数も残す（非推奨）
        api_token: str | None = None,
        base_url: str = "https://api.bitrise.io/v0.1",
    ) -> None:
        """Bitrise Clientを初期化する

        Args:
            connection: Bitrise接続設定（推奨）
            api_token: Personal Access Token（非推奨、後方互換性のため残存）
            base_url: Bitrise API ベースURL（非推奨）

        Raises:
            ValueError: 認証情報が不足している場合
        """
        # Connection優先、なければ既存引数から生成、最後に環境変数
        if connection is None:
            # 既存の引数が指定されている場合（後方互換性）
            if api_token or base_url != "https://api.bitrise.io/v0.1":
                connection = BitriseConnection(
                    api_token=api_token,
                    base_url=base_url,
                )
            else:
                # 環境変数から生成
                connection = BitriseConnection.from_env()

        # 認証情報の検証
        if not connection.validate():
            raise ValueError(
                "Bitrise authentication not configured. "
                "Set api_token in BitriseConnection or BITRISE_TOKEN environment variable."
            )

        self.base_url = connection.base_url
        self.headers = {
            "Authorization": f"token {connection.api_token}",
            "Accept": "application/json",
        }

        # セッションの設定（リトライ機能付き）
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,  # 1秒, 2秒, 4秒...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        logger.debug("BitriseClient initialized")

    def get_platform(self) -> str:
        """プラットフォーム識別子を返す

        Returns:
            str: Platform.BITRISE
        """
        return Platform.BITRISE

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: tuple[int, int] | int = (10, 30),
    ) -> dict[str, Any]:
        """APIリクエストを実行する

        Args:
            method: HTTPメソッド（GET, POST, etc.）
            endpoint: APIエンドポイント（/apps など）
            params: クエリパラメータ
            timeout: タイムアウト（接続, 読み取り）または合計秒数
                    デフォルト: (10, 30) = 接続10秒、読み取り30秒

        Returns:
            APIレスポンス（JSON）

        Raises:
            BitriseAPIException: API呼び出しエラー
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 0
            try:
                error_data = e.response.json() if e.response else {}
                error_message = error_data.get("message", str(e))
            except Exception:
                error_message = str(e)

            logger.error(f"Bitrise API error: HTTP {status_code} - {error_message}")
            raise BitriseAPIException(status_code, error_message, error_data) from e

        except requests.exceptions.Timeout as e:
            logger.error(f"Bitrise API timeout: {endpoint}")
            raise BitriseAPIException(0, f"Request timeout: {endpoint}") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"Bitrise API request error: {e}")
            raise BitriseAPIException(0, f"Request failed: {e}") from e

    def get_apps(self, limit: int = 50) -> list[dict[str, Any]]:
        """アプリ一覧を取得する

        Args:
            limit: 取得する最大件数（デフォルト: 50）

        Returns:
            アプリ情報のリスト

        Raises:
            BitriseAPIException: API呼び出しエラー
        """
        all_apps: list[dict[str, Any]] = []
        next_token = None

        while len(all_apps) < limit:
            # ページネーショントークンをクエリパラメータとして渡す
            params = {"next": next_token} if next_token else None
            response = self._request("GET", "/apps", params=params)
            apps = response.get("data", [])
            all_apps.extend(apps)

            # ページネーション
            paging = response.get("paging", {})
            next_token = paging.get("next", None)

            # 次のページがない、またはデータがない場合は終了
            if not next_token or not apps:
                break

            if len(all_apps) >= limit:
                all_apps = all_apps[:limit]
                break

        logger.info(f"Fetched {len(all_apps)} apps from Bitrise")
        return all_apps

    def get_builds(
        self,
        app_slug: str,
        branch: str | None = None,
        workflow: str | None = None,
        created_after: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """アプリのビルド一覧を取得する

        Args:
            app_slug: アプリのSlug（識別子）
            branch: ブランチ名でフィルタ（オプション）
            workflow: ワークフロー名でフィルタ（オプション）
            created_after: この日時以降に作成されたビルドを取得
            limit: 取得する最大件数（デフォルト: 50）

        Returns:
            ビルド情報のリスト

        Raises:
            BitriseAPIException: API呼び出しエラー
        """
        all_builds: list[dict[str, Any]] = []
        next_url = f"/apps/{app_slug}/builds"

        params: dict[str, Any] = {}
        if branch:
            params["branch"] = branch
        if workflow:
            params["workflow"] = workflow
        if limit:
            params["limit"] = min(limit, 50)  # Bitrise APIは最大50件/リクエスト

        while next_url and len(all_builds) < limit:
            response = self._request("GET", next_url, params=params)
            builds = response.get("data", [])

            # created_afterフィルタ
            if created_after:
                builds = [
                    b
                    for b in builds
                    if b.get("triggered_at")
                    and datetime.fromisoformat(
                        b["triggered_at"].replace("Z", "+00:00")
                    )
                    >= created_after
                ]

            all_builds.extend(builds)

            # ページネーション
            paging = response.get("paging", {})
            next_url = paging.get("next", None)
            params = {}  # 次のページは next_url に含まれる

            if len(all_builds) >= limit:
                all_builds = all_builds[:limit]
                break

        logger.info(f"Fetched {len(all_builds)} builds for app {app_slug}")
        return all_builds

    def get_build(self, app_slug: str, build_slug: str) -> dict[str, Any]:
        """特定のビルドの詳細情報を取得する

        Args:
            app_slug: アプリのSlug
            build_slug: ビルドのSlug

        Returns:
            ビルド詳細情報

        Raises:
            BitriseAPIException: API呼び出しエラー
        """
        endpoint = f"/apps/{app_slug}/builds/{build_slug}"
        response = self._request("GET", endpoint)
        build_data = response.get("data", {})

        logger.info(f"Fetched build {build_slug} for app {app_slug}")
        return build_data

    def get_build_log(self, app_slug: str, build_slug: str) -> str:
        """ビルドのログを取得する

        Args:
            app_slug: アプリのSlug
            build_slug: ビルドのSlug

        Returns:
            ビルドログ（テキスト）

        Raises:
            BitriseAPIException: API呼び出しエラー
        """
        # ログURL取得
        endpoint = f"/apps/{app_slug}/builds/{build_slug}/log"
        response = self._request("GET", endpoint)

        log_url = response.get("expiring_raw_log_url")
        if not log_url:
            logger.warning(f"No log available for build {build_slug}")
            return ""

        # ログ本体をダウンロード
        try:
            log_response = self.session.get(log_url, timeout=30)
            log_response.raise_for_status()
            logger.info(f"Fetched log for build {build_slug}")
            return log_response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download build log: {e}")
            raise BitriseAPIException(0, f"Failed to download build log: {e}") from e

    def close(self) -> None:
        """セッションをクローズする"""
        self.session.close()
        logger.debug("BitriseClient closed")

    def __enter__(self) -> "BitriseClient":
        """Context manager: with文でのエントリーポイント

        Returns:
            BitriseClientインスタンス自身
        """
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理

        Args:
            *args: 例外情報（型、値、トレースバック）
        """
        self.close()
