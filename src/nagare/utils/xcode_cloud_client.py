"""Xcode Cloud / App Store Connect API Clientモジュール

App Store Connect APIを使用したCI/CDデータ取得クライアント
JWT (JSON Web Token)認証を使用してXcode Cloudのビルドデータを取得する。

ADR-002: Connection管理アーキテクチャに準拠し、
XcodeCloudConnectionから接続情報を受け取る。

Reference:
    https://developer.apple.com/documentation/appstoreconnectapi
    https://developer.apple.com/documentation/appstoreconnectapi/ci_builds
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import jwt
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nagare.constants import Platform
from nagare.utils.connections import XcodeCloudConnection

logger = logging.getLogger(__name__)


class XcodeCloudAPIException(Exception):
    """Xcode Cloud API例外"""

    def __init__(self, status_code: int, message: str, response: dict[str, Any] | None = None):
        self.status_code = status_code
        self.message = message
        self.response = response
        super().__init__(f"HTTP {status_code}: {message}")


class XcodeCloudClient:
    """Xcode Cloud / App Store Connect APIクライアント

    App Store Connect APIを使用してXcode Cloudのビルドデータを取得する。
    JWT認証とレート制限を自動処理する。

    Attributes:
        session: requestsセッション
        base_url: APIベースURL
        connection: XcodeCloud接続設定
        token_cache: JWTトークンキャッシュ
        token_expires_at: トークン有効期限
    """

    def __init__(
        self,
        connection: XcodeCloudConnection | None = None,
        # 後方互換性のため既存引数も残す（非推奨）
        key_id: str | None = None,
        issuer_id: str | None = None,
        private_key: str | None = None,
        base_url: str = "https://api.appstoreconnect.apple.com/v1",
    ) -> None:
        """Xcode Cloud Clientを初期化する

        Args:
            connection: Xcode Cloud接続設定（推奨）
            key_id: App Store Connect API Key ID（非推奨）
            issuer_id: App Store Connect API Issuer ID（非推奨）
            private_key: Private Key文字列（非推奨）
            base_url: App Store Connect API ベースURL（非推奨）

        Raises:
            ValueError: 認証情報が不足している場合
        """
        # Connection優先、なければ既存引数から生成、最後に環境変数
        if connection is None:
            # 既存の引数が指定されている場合（後方互換性）
            if any([key_id, issuer_id, private_key]):
                connection = XcodeCloudConnection(
                    key_id=key_id,
                    issuer_id=issuer_id,
                    private_key=private_key,
                    base_url=base_url,
                )
            else:
                # 環境変数から生成
                connection = XcodeCloudConnection.from_env()

        # 認証情報の検証
        if not connection.validate():
            raise ValueError(
                "Xcode Cloud authentication not configured. "
                "Set key_id, issuer_id, and private_key in XcodeCloudConnection "
                "or APPSTORE_KEY_ID, APPSTORE_ISSUER_ID, and APPSTORE_PRIVATE_KEY "
                "environment variables."
            )

        self.connection = connection
        self.base_url = connection.base_url

        # Private Keyを読み込み
        if not connection.private_key:
            raise ValueError("Private key is required")
        self.private_key = connection.private_key

        # JWTトークンキャッシュ
        self.token_cache: str | None = None
        self.token_expires_at: datetime | None = None

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

        logger.info(f"XcodeCloudClient initialized for {self.base_url}")

    def get_platform(self) -> str:
        """プラットフォーム識別子を返す

        Returns:
            str: Platform.XCODE_CLOUD
        """
        return Platform.XCODE_CLOUD

    def _generate_jwt_token(self) -> str:
        """JWT認証トークンを生成する

        App Store Connect APIはJWT認証を使用する。
        トークンは20分間有効（有効期限は最大20分）

        Returns:
            str: JWTトークン

        Reference:
            https://developer.apple.com/documentation/appstoreconnectapi/generating_tokens_for_api_requests
        """
        now = datetime.utcnow()

        # トークンをキャッシュして再利用（期限切れの5分前に更新）
        if self.token_cache and self.token_expires_at:
            if now < self.token_expires_at - timedelta(minutes=5):
                return self.token_cache

        # JWTペイロード
        expiration = now + timedelta(minutes=20)  # 最大20分
        payload = {
            "iss": self.connection.issuer_id,
            "iat": int(now.timestamp()),
            "exp": int(expiration.timestamp()),
            "aud": "appstoreconnect-v1",
        }

        # JWTヘッダー
        headers = {
            "kid": self.connection.key_id,
            "typ": "JWT",
            "alg": "ES256",
        }

        # JWTトークン生成
        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="ES256",
            headers=headers,
        )

        # キャッシュに保存
        self.token_cache = token
        self.token_expires_at = expiration

        logger.debug(f"Generated new JWT token (expires at {expiration})")
        return token

    def _get_headers(self) -> dict[str, str]:
        """リクエストヘッダーを取得する

        Returns:
            認証ヘッダーを含むヘッダー辞書
        """
        token = self._generate_jwt_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """APIリクエストを実行する

        Args:
            method: HTTPメソッド（GET, POST等）
            endpoint: APIエンドポイント（/apps等）
            params: クエリパラメータ
            json: リクエストボディ（JSON）

        Returns:
            APIレスポンス（JSON）

        Raises:
            XcodeCloudAPIException: APIエラー時
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json,
                timeout=30,
            )

            # レート制限のログ出力
            if "X-Rate-Limit-Remaining" in response.headers:
                remaining = response.headers["X-Rate-Limit-Remaining"]
                logger.debug(f"App Store Connect API rate limit remaining: {remaining}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            error_msg = f"API request failed: {e}"
            response_data = None
            if e.response is not None:
                try:
                    response_data = e.response.json()
                    error_msg = f"API request failed: {response_data.get('errors', [{}])[0].get('detail', str(e))}"
                except Exception:
                    pass

            raise XcodeCloudAPIException(
                status_code=e.response.status_code if e.response else 500,
                message=error_msg,
                response=response_data,
            ) from e

        except requests.exceptions.RequestException as e:
            raise XcodeCloudAPIException(
                status_code=500,
                message=f"Request failed: {e}",
            ) from e

    def list_apps(self, limit: int = 200) -> list[dict[str, Any]]:
        """アプリ一覧を取得する

        Returns:
            アプリ情報のリスト

        Reference:
            https://developer.apple.com/documentation/appstoreconnectapi/list_apps
        """
        apps = []
        next_url = None
        endpoint = "/apps"

        while True:
            params = {"limit": limit}
            response = self._request("GET", endpoint, params=params)

            apps.extend(response.get("data", []))

            # ページネーション
            next_url = response.get("links", {}).get("next")
            if not next_url:
                break

            # 次のページのエンドポイントを抽出
            endpoint = next_url.replace(self.base_url, "")

        logger.info(f"Fetched {len(apps)} apps")
        return apps

    def list_ci_builds_for_app(
        self,
        app_id: str,
        limit: int = 200,
        filter_created_date_start: str | None = None,
        filter_created_date_end: str | None = None,
    ) -> list[dict[str, Any]]:
        """特定アプリのCI/CDビルド一覧を取得する

        Args:
            app_id: アプリID
            limit: 1リクエストあたりの取得件数（最大200）
            filter_created_date_start: 開始日時フィルタ（ISO8601形式）
            filter_created_date_end: 終了日時フィルタ（ISO8601形式）

        Returns:
            ビルド情報のリスト

        Reference:
            https://developer.apple.com/documentation/appstoreconnectapi/list_builds_for_an_app
        """
        builds = []
        endpoint = f"/apps/{app_id}/builds"

        params: dict[str, Any] = {
            "limit": limit,
            # Xcode Cloudビルドのみフィルタ
            "filter[processingState]": "VALID,PROCESSING,FAILED",
        }

        if filter_created_date_start:
            params["filter[preReleaseVersion.createdDate]"] = f"{filter_created_date_start}.."
        if filter_created_date_end and filter_created_date_start:
            params["filter[preReleaseVersion.createdDate]"] = f"{filter_created_date_start}..{filter_created_date_end}"

        while True:
            response = self._request("GET", endpoint, params=params)
            builds.extend(response.get("data", []))

            # ページネーション
            next_url = response.get("links", {}).get("next")
            if not next_url:
                break

            endpoint = next_url.replace(self.base_url, "")
            params = {}  # 次のURLには既にパラメータが含まれている

        logger.info(f"Fetched {len(builds)} builds for app {app_id}")
        return builds

    def get_build(self, build_id: str) -> dict[str, Any]:
        """特定ビルドの詳細を取得する

        Args:
            build_id: ビルドID

        Returns:
            ビルド詳細情報

        Reference:
            https://developer.apple.com/documentation/appstoreconnectapi/read_build_information
        """
        endpoint = f"/builds/{build_id}"
        response = self._request("GET", endpoint)
        return response.get("data", {})

    def __enter__(self) -> "XcodeCloudClient":
        """コンテキストマネージャーの開始"""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """コンテキストマネージャーの終了"""
        self.session.close()
