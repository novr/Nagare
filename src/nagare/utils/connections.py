"""Connection管理モジュール

CI/CDプラットフォームおよびデータベースへの接続情報を一元管理する。

アーキテクチャ:
    - BaseConnection: 基底抽象クラス（Airflow Connection統合）
    - Platform-specific: GitHubConnection, GitLabConnectionなど
    - ConnectionRegistry: シングルトンレジストリ
    - ConnectionLoader: Airflow Connection読み込みユーティリティ

新しいプラットフォーム追加時の手順:
    1. BaseConnectionを継承した具体クラスを作成
    2. from_airflow_extra()メソッドを実装
    3. ConnectionRegistryにgetter/setterを追加
    4. ClientFactoryに統合

使用例:
    # Airflow Connectionから（推奨）
    github_conn = GitHubConnection.from_airflow("github_default")

    # 環境変数から（後方互換）
    github_conn = GitHubConnection.from_env()

    # Registryから
    github_conn = ConnectionRegistry.get_github()
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Connection Protocol（共通インターフェース）
# ============================================================================


@runtime_checkable
class ConnectionProtocol(Protocol):
    """Connection設定の共通インターフェース

    各CI/CDプラットフォームのConnection設定はこのProtocolを実装する。
    """

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）"""
        ...


# ============================================================================
# 2. Base Connection（基底クラス）
# ============================================================================


@dataclass
class BaseConnection(ABC):
    """Connection設定の基底クラス

    すべてのプラットフォーム固有のConnection設定はこのクラスを継承する。
    Airflow Connectionからの読み込みロジックを共通化。

    Attributes:
        conn_type: Airflow Connection Type（例: "http", "postgres"）
        description: 説明（オプション）
    """

    # クラス変数：各サブクラスで定義
    CONN_TYPE: ClassVar[str] = "generic"

    description: str = ""

    @classmethod
    @abstractmethod
    def from_env(cls) -> "BaseConnection":
        """環境変数から生成（各プラットフォームで実装）

        Returns:
            BaseConnection: 環境変数から生成されたConnection
        """
        ...

    @classmethod
    def from_airflow(cls, conn_id: str) -> "BaseConnection":
        """Airflow Connectionから生成（共通ロジック）

        Args:
            conn_id: Airflow Connection ID

        Returns:
            BaseConnection: Airflow Connectionから生成されたConnection

        Raises:
            ImportError: Airflow がインストールされていない場合
            ValueError: Connectionが見つからない、または型が一致しない場合
        """
        try:
            from airflow.hooks.base import BaseHook
        except ImportError as e:
            raise ImportError(
                "Apache Airflow is required to use from_airflow(). "
                "Install it with: pip install apache-airflow"
            ) from e

        try:
            # Airflow Connectionを取得
            connection = BaseHook.get_connection(conn_id)

            # Connection typeのチェック（サブクラスのCONN_TYPEと一致するか）
            if hasattr(cls, "CONN_TYPE") and cls.CONN_TYPE != "generic":
                expected_type = cls.CONN_TYPE
                if connection.conn_type != expected_type:
                    logger.warning(
                        f"Connection '{conn_id}' type mismatch: "
                        f"expected '{expected_type}', got '{connection.conn_type}'"
                    )

            # extraフィールドからJSON読み取り
            extra = connection.extra_dejson if hasattr(connection, "extra_dejson") else {}

            # プラットフォーム固有のパース処理を呼び出す
            return cls.from_airflow_extra(
                conn_id=conn_id,
                password=connection.password,  # type: ignore[arg-type]
                host=connection.host,
                port=connection.port,
                schema=connection.schema,
                login=connection.login,
                extra=extra,
                description=connection.description or "",
            )

        except Exception as e:
            raise ValueError(f"Failed to load Airflow Connection '{conn_id}': {e}") from e

    @classmethod
    @abstractmethod
    def from_airflow_extra(
        cls,
        conn_id: str,
        password: str | None,
        host: str | None,
        port: int | None,
        schema: str | None,
        login: str | None,
        extra: dict[str, Any],
        description: str,
    ) -> "BaseConnection":
        """Airflow Connectionの各フィールドからインスタンスを生成

        各プラットフォーム固有のパース処理を実装する。

        Args:
            conn_id: Connection ID
            password: パスワードフィールド（多くの場合、トークンとして使用）
            host: ホスト
            port: ポート
            schema: スキーマ/データベース名
            login: ログイン/ユーザー名
            extra: 追加設定（JSON）
            description: 説明

        Returns:
            BaseConnection: 生成されたConnectionインスタンス
        """
        ...

    @abstractmethod
    def validate(self) -> bool:
        """接続情報の検証（各プラットフォームで実装）

        Returns:
            有効な設定の場合True
        """
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        各プラットフォームで実装。

        Returns:
            シークレットを含まない設定情報
        """
        ...


# ============================================================================
# 3. GitHub Connection（プラットフォーム固有）
# ============================================================================


class GitHubConnectionBase(BaseConnection, ABC):
    """GitHub接続設定の抽象基底クラス

    Token認証とApp認証を明確に分離するための基底クラス。
    サブクラス：GitHubTokenAuth, GitHubAppAuth

    使用例:
        # Airflow Connectionから（自動的に適切なサブクラスを返す）
        conn = GitHubConnectionBase.from_airflow("github_default")

        # 環境変数から（自動的に適切なサブクラスを返す）
        conn = GitHubConnectionBase.from_env()

        # 直接サブクラスを使用
        conn = GitHubTokenAuth(token="ghp_xxx")
        conn = GitHubAppAuth(app_id=123, installation_id=456, private_key="...")
    """

    # クラス変数
    CONN_TYPE: ClassVar[str] = "http"

    @property
    @abstractmethod
    def base_url(self) -> str:
        """GitHub API ベースURL"""
        ...

    @classmethod
    def from_env(cls) -> "GitHubConnectionBase":
        """環境変数から適切なサブクラスを生成

        以下の環境変数を読み取り、Token認証かApp認証かを自動判定：
        - GITHUB_TOKEN: Personal Access Token（Token認証）
        - GITHUB_APP_ID + GITHUB_APP_INSTALLATION_ID: GitHub App認証
        - GITHUB_API_URL: ベースURL（デフォルト: https://api.github.com）

        Token認証を優先し、なければApp認証を試す。

        Returns:
            GitHubConnectionBase: GitHubTokenAuth または GitHubAppAuth

        Raises:
            ValueError: いずれの認証情報も設定されていない場合
        """
        token = os.getenv("GITHUB_TOKEN")
        base_url = os.getenv("GITHUB_API_URL", "https://api.github.com")

        # Token認証を優先
        if token:
            return GitHubTokenAuth(token=token, _base_url=base_url)

        # GitHub App認証
        app_id_str = os.getenv("GITHUB_APP_ID", "")
        installation_id_str = os.getenv("GITHUB_APP_INSTALLATION_ID", "")

        if app_id_str and installation_id_str:
            try:
                app_id = int(app_id_str)
                installation_id = int(installation_id_str)

                return GitHubAppAuth(
                    app_id=app_id,
                    installation_id=installation_id,
                    private_key=os.getenv("GITHUB_APP_PRIVATE_KEY"),
                    private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
                    _base_url=base_url,
                )
            except ValueError as e:
                raise ValueError(
                    f"Invalid GITHUB_APP_ID or GITHUB_APP_INSTALLATION_ID: {e}"
                ) from e

        # いずれも設定されていない
        raise ValueError(
            "GitHub authentication not configured. "
            "Set either GITHUB_TOKEN or (GITHUB_APP_ID + GITHUB_APP_INSTALLATION_ID)"
        )

    @classmethod
    def from_airflow_extra(
        cls,
        conn_id: str,
        password: str | None,
        host: str | None,
        port: int | None,
        schema: str | None,
        login: str | None,
        extra: dict[str, Any],
        description: str,
    ) -> "GitHubConnectionBase":
        """Airflow Connectionから適切なサブクラスを生成

        Airflow Connectionのフィールドマッピング：
        - password: Personal Access Token（Token認証）
        - host: API base URL（例: api.github.com）
        - extra.app_id + extra.installation_id: GitHub App認証

        Args:
            conn_id: Connection ID（ロギング用）
            password: Personal Access Token
            host: APIホスト
            port: ポート（未使用）
            schema: スキーマ（未使用）
            login: ログイン（未使用）
            extra: 追加設定（GitHub Apps認証用）
            description: 説明

        Returns:
            GitHubConnectionBase: GitHubTokenAuth または GitHubAppAuth

        Raises:
            ValueError: いずれの認証情報も設定されていない場合
        """
        # Base URLの決定
        base_url = "https://api.github.com"
        if host:
            if not host.startswith(("http://", "https://")):
                base_url = f"https://{host}"
            else:
                base_url = host

        # Token認証を優先
        if password:
            return GitHubTokenAuth(
                token=password,
                _base_url=base_url,
                description=description,
            )

        # GitHub Apps認証
        app_id = extra.get("app_id")
        installation_id = extra.get("installation_id")
        private_key = extra.get("private_key")

        if app_id and installation_id:
            try:
                return GitHubAppAuth(
                    app_id=int(app_id),
                    installation_id=int(installation_id),
                    private_key=private_key,
                    _base_url=base_url,
                    description=description,
                )
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid app_id or installation_id in Connection '{conn_id}': {e}"
                ) from e

        # いずれも設定されていない
        raise ValueError(
            f"Connection '{conn_id}' must have either password (token) "
            "or extra.app_id + extra.installation_id (GitHub App)"
        )


@dataclass
class GitHubTokenAuth(GitHubConnectionBase):
    """GitHub Personal Access Token認証

    Personal Access Tokenを使用したGitHub API認証。
    個人開発や小規模プロジェクトに推奨。

    Attributes:
        token: Personal Access Token（必須）
        base_url: GitHub API ベースURL
        description: 説明（BaseConnectionから継承）

    使用例:
        # 直接インスタンス化
        conn = GitHubTokenAuth(token="ghp_xxxxxxxxxxxx")

        # Airflow Connectionから
        conn = GitHubConnectionBase.from_airflow("github_default")
    """

    CONN_TYPE: ClassVar[str] = "http"

    token: str = ""  # 必須、validate()で検証
    _base_url: str = "https://api.github.com"

    @property
    def base_url(self) -> str:
        """GitHub API ベースURL"""
        return self._base_url

    @classmethod
    def from_env(cls) -> "GitHubTokenAuth":
        """環境変数から生成

        以下の環境変数を読み取る：
        - GITHUB_TOKEN: Personal Access Token（必須）
        - GITHUB_API_URL: ベースURL（デフォルト: https://api.github.com）

        Returns:
            GitHubTokenAuth: 環境変数から生成されたインスタンス

        Raises:
            ValueError: GITHUB_TOKENが設定されていない場合
        """
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable is required")

        return cls(
            token=token,
            _base_url=os.getenv("GITHUB_API_URL", "https://api.github.com"),
        )

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        return bool(self.token)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        Returns:
            シークレットを含まない設定情報
        """
        return {
            "type": "github_token",
            "base_url": self.base_url,
            "has_token": bool(self.token),
        }


@dataclass
class GitHubAppAuth(GitHubConnectionBase):
    """GitHub App認証

    GitHub Appを使用したGitHub API認証。
    エンタープライズや組織での利用に推奨。

    Attributes:
        app_id: GitHub App ID（必須）
        installation_id: GitHub App Installation ID（必須）
        private_key: GitHub App Private Key（文字列、オプション）
        private_key_path: Private Keyファイルパス（オプション）
        base_url: GitHub API ベースURL
        description: 説明（BaseConnectionから継承）

    private_keyまたはprivate_key_pathのいずれかが必須。

    使用例:
        # Private Key文字列を指定
        conn = GitHubAppAuth(
            app_id=123456,
            installation_id=789012,
            private_key="-----BEGIN RSA PRIVATE KEY-----\\n..."
        )

        # Private Keyファイルパスを指定
        conn = GitHubAppAuth(
            app_id=123456,
            installation_id=789012,
            private_key_path="/path/to/key.pem"
        )
    """

    CONN_TYPE: ClassVar[str] = "http"

    app_id: int = 0  # 必須、validate()で検証
    installation_id: int = 0  # 必須、validate()で検証
    private_key: str | None = None
    private_key_path: str | None = None
    _base_url: str = "https://api.github.com"

    @property
    def base_url(self) -> str:
        """GitHub API ベースURL"""
        return self._base_url

    @classmethod
    def from_env(cls) -> "GitHubAppAuth":
        """環境変数から生成

        以下の環境変数を読み取る：
        - GITHUB_APP_ID: GitHub App ID（必須）
        - GITHUB_APP_INSTALLATION_ID: Installation ID（必須）
        - GITHUB_APP_PRIVATE_KEY: Private Key文字列（オプション）
        - GITHUB_APP_PRIVATE_KEY_PATH: Private Keyファイルパス（オプション）
        - GITHUB_API_URL: ベースURL（デフォルト: https://api.github.com）

        private_keyまたはprivate_key_pathのいずれかが必須。

        Returns:
            GitHubAppAuth: 環境変数から生成されたインスタンス

        Raises:
            ValueError: 必須の環境変数が設定されていない場合
        """
        app_id_str = os.getenv("GITHUB_APP_ID")
        installation_id_str = os.getenv("GITHUB_APP_INSTALLATION_ID")

        if not app_id_str or not installation_id_str:
            raise ValueError(
                "GITHUB_APP_ID and GITHUB_APP_INSTALLATION_ID are required"
            )

        try:
            app_id = int(app_id_str)
            installation_id = int(installation_id_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid GITHUB_APP_ID or GITHUB_APP_INSTALLATION_ID: {e}"
            ) from e

        return cls(
            app_id=app_id,
            installation_id=installation_id,
            private_key=os.getenv("GITHUB_APP_PRIVATE_KEY"),
            private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
            _base_url=os.getenv("GITHUB_API_URL", "https://api.github.com"),
        )

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        if not self.app_id or not self.installation_id:
            return False
        return bool(self.private_key or self.private_key_path)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        Returns:
            シークレットを含まない設定情報
        """
        return {
            "type": "github_app",
            "base_url": self.base_url,
            "app_id": self.app_id,
            "installation_id": self.installation_id,
            "has_private_key": bool(self.private_key or self.private_key_path),
        }


# 後方互換性のための型エイリアス
# 既存コードで GitHubConnection を使用している箇所が動作するように
GitHubConnection = GitHubConnectionBase


# ============================================================================
# 4. GitLab Connection（将来の拡張用）
# ============================================================================


@dataclass
class GitLabConnection(BaseConnection):
    """GitLab接続設定（将来の拡張用）

    Attributes:
        token: Personal Access Token
        base_url: GitLab API ベースURL
        description: 説明（BaseConnectionから継承）

    使用例:
        # Airflow Connectionから
        conn = GitLabConnection.from_airflow("gitlab_default")

        # 環境変数から
        conn = GitLabConnection.from_env()
    """

    CONN_TYPE: ClassVar[str] = "http"

    token: str | None = None
    base_url: str = "https://gitlab.com"

    @classmethod
    def from_env(cls) -> "GitLabConnection":
        """環境変数から生成

        以下の環境変数を読み取る：
        - GITLAB_TOKEN: Personal Access Token
        - GITLAB_URL: ベースURL（デフォルト: https://gitlab.com）

        Returns:
            GitLabConnection: 環境変数から生成されたConnection
        """
        return cls(
            token=os.getenv("GITLAB_TOKEN"),
            base_url=os.getenv("GITLAB_URL", "https://gitlab.com"),
        )

    @classmethod
    def from_airflow_extra(
        cls,
        conn_id: str,
        password: str | None,
        host: str | None,
        port: int | None,
        schema: str | None,
        login: str | None,
        extra: dict[str, Any],
        description: str,
    ) -> "GitLabConnection":
        """Airflow Connectionの各フィールドからインスタンスを生成

        Airflow Connectionのフィールドマッピング：
        - password: Personal Access Token
        - host: GitLab base URL（例: gitlab.com）

        Args:
            conn_id: Connection ID（ロギング用）
            password: Personal Access Token
            host: GitLabホスト
            port: ポート（未使用）
            schema: スキーマ（未使用）
            login: ログイン（未使用）
            extra: 追加設定（未使用）
            description: 説明

        Returns:
            GitLabConnection: 生成されたインスタンス
        """
        base_url = "https://gitlab.com"
        if host:
            if not host.startswith(("http://", "https://")):
                base_url = f"https://{host}"
            else:
                base_url = host

        return cls(
            token=password or None,
            base_url=base_url,
            description=description,
        )

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        return bool(self.token)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        Returns:
            シークレットを含まない設定情報
        """
        return {
            "type": "gitlab",
            "base_url": self.base_url,
            "has_token": bool(self.token),
        }


# ============================================================================
# 5. CircleCI Connection（将来の拡張用）
# ============================================================================


@dataclass
class CircleCIConnection(BaseConnection):
    """CircleCI接続設定（将来の拡張用）

    Attributes:
        api_token: API Token
        base_url: CircleCI API ベースURL
        description: 説明（BaseConnectionから継承）

    使用例:
        # Airflow Connectionから
        conn = CircleCIConnection.from_airflow("circleci_default")

        # 環境変数から
        conn = CircleCIConnection.from_env()
    """

    CONN_TYPE: ClassVar[str] = "http"

    api_token: str | None = None
    base_url: str = "https://circleci.com/api"

    @classmethod
    def from_env(cls) -> "CircleCIConnection":
        """環境変数から生成

        以下の環境変数を読み取る：
        - CIRCLECI_TOKEN: API Token
        - CIRCLECI_API_URL: ベースURL（デフォルト: https://circleci.com/api）

        Returns:
            CircleCIConnection: 環境変数から生成されたConnection
        """
        return cls(
            api_token=os.getenv("CIRCLECI_TOKEN"),
            base_url=os.getenv("CIRCLECI_API_URL", "https://circleci.com/api"),
        )

    @classmethod
    def from_airflow_extra(
        cls,
        conn_id: str,
        password: str | None,
        host: str | None,
        port: int | None,
        schema: str | None,
        login: str | None,
        extra: dict[str, Any],
        description: str,
    ) -> "CircleCIConnection":
        """Airflow Connectionの各フィールドからインスタンスを生成

        Airflow Connectionのフィールドマッピング：
        - password: API Token
        - host: CircleCI base URL（例: circleci.com/api）

        Args:
            conn_id: Connection ID（ロギング用）
            password: API Token
            host: CircleCIホスト
            port: ポート（未使用）
            schema: スキーマ（未使用）
            login: ログイン（未使用）
            extra: 追加設定（未使用）
            description: 説明

        Returns:
            CircleCIConnection: 生成されたインスタンス
        """
        base_url = "https://circleci.com/api"
        if host:
            if not host.startswith(("http://", "https://")):
                base_url = f"https://{host}"
            else:
                base_url = host

        return cls(
            api_token=password or None,
            base_url=base_url,
            description=description,
        )

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        return bool(self.api_token)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        Returns:
            シークレットを含まない設定情報
        """
        return {
            "type": "circleci",
            "base_url": self.base_url,
            "has_token": bool(self.api_token),
        }


@dataclass
class BitriseConnection(BaseConnection):
    """Bitrise API接続設定

    Bitriseはモバイルアプリ向けCI/CDプラットフォーム。
    Personal Access Token認証を使用。

    Reference:
        https://api-docs.bitrise.io/
    """

    CONN_TYPE: ClassVar[str] = "http"

    api_token: str | None = None
    base_url: str = "https://api.bitrise.io/v0.1"

    @classmethod
    def from_env(cls) -> "BitriseConnection":
        """環境変数から生成

        Environment Variables:
            BITRISE_TOKEN: Personal Access Token
            BITRISE_API_URL: ベースURL（デフォルト: https://api.bitrise.io/v0.1）

        Returns:
            BitriseConnection インスタンス
        """
        return cls(
            api_token=os.getenv("BITRISE_TOKEN"),
            base_url=os.getenv("BITRISE_API_URL", "https://api.bitrise.io/v0.1"),
        )

    @classmethod
    def from_airflow_extra(
        cls, conn_id: str, extra: dict[str, Any]
    ) -> "BitriseConnection":
        """Airflow Connectionから生成

        Args:
            conn_id: Connection ID
            extra: Airflow ConnectionのExtra JSON

        Returns:
            BitriseConnection インスタンス
        """
        return cls(
            api_token=extra.get("api_token"),
            base_url=extra.get("base_url", "https://api.bitrise.io/v0.1"),
        )

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        return bool(self.api_token)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        Returns:
            シークレットを含まない設定情報
        """
        return {
            "type": "bitrise",
            "base_url": self.base_url,
            "has_token": bool(self.api_token),
        }


# ============================================================================
# 6. Database Connection（インフラストラクチャ設定）
# ============================================================================


@dataclass
class DatabaseConnection:
    """データベース接続設定

    IMPORTANT: データベース接続は環境変数で管理し、Airflow Connectionとは分離する。
    理由:
    - データベースはインフラストラクチャの一部であり、アプリケーション設定とは異なる
    - Airflow自体もこのデータベースを使用するため、Airflowメタストアと分離が必要
    - 環境ごと（dev/staging/prod）で異なる接続情報を使用
    - コンテナ起動時に環境変数として注入するのが標準的な運用

    一方、GitHub/GitLab等のAPI認証情報は:
    - アプリケーションレベルの設定
    - UI（Streamlit管理画面）から変更可能
    - 複数アカウントの管理が必要
    - Airflow Connectionでの管理が適切

    Attributes:
        host: データベースホスト
        port: ポート番号
        database: データベース名
        user: ユーザー名
        password: パスワード
        pool_size: コネクションプールサイズ
        max_overflow: プールの最大オーバーフロー数
        pool_pre_ping: 接続前のpingチェック

    使用例:
        conn = DatabaseConnection(
            host="localhost",
            database="nagare",
            user="nagare_user",
            password="secret"
        )

        # 環境変数から自動生成（推奨）
        conn = DatabaseConnection.from_env()

        # SQLAlchemy URL取得
        engine = create_engine(conn.url)
    """

    host: str = "localhost"
    port: int = 5432
    database: str = "nagare"
    user: str = "nagare_user"
    password: str = ""

    # Connection pooling設定
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True

    @property
    def url(self) -> str:
        """SQLAlchemy URL生成

        パスワードはURLエンコードされます（特殊文字対策）。

        Returns:
            PostgreSQL接続URL
        """
        return (
            f"postgresql://{self.user}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @classmethod
    def from_env(cls) -> "DatabaseConnection":
        """環境変数から生成

        以下の環境変数を読み取る：
        - DATABASE_HOST: ホスト（デフォルト: localhost）
        - DATABASE_PORT: ポート（デフォルト: 5432）
        - DATABASE_NAME: データベース名（デフォルト: nagare）
        - DATABASE_USER: ユーザー名（デフォルト: nagare_user）
        - DATABASE_PASSWORD: パスワード

        Returns:
            DatabaseConnection: 環境変数から生成されたConnection
        """
        return cls(
            host=os.getenv("DATABASE_HOST", "localhost"),
            port=int(os.getenv("DATABASE_PORT", "5432")),
            database=os.getenv("DATABASE_NAME", "nagare"),
            user=os.getenv("DATABASE_USER", "nagare_user"),
            password=os.getenv("DATABASE_PASSWORD", ""),
        )

    def validate(self) -> bool:
        """接続情報の検証

        Returns:
            有効な設定の場合True
        """
        return bool(self.host and self.database and self.user)

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（パスワードは除外）

        Returns:
            パスワードを含まない設定情報
        """
        return {
            "type": "database",
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "has_password": bool(self.password),
        }


# ============================================================================
# 7. ConnectionRegistry（一元管理）
# ============================================================================


class ConnectionRegistry:
    """Connection設定を一元管理するレジストリ

    シングルトンパターンで実装し、アプリケーション全体で同一インスタンスを共有。
    テスト時はset_*メソッドでモック注入可能。

    使用例:
        # 取得
        github_conn = ConnectionRegistry.get_github()

        # テスト時のモック注入
        ConnectionRegistry.set_github(GitHubConnection(token="test"))

        # 全リセット
        ConnectionRegistry.reset_all()

        # 設定ファイルから読み込み
        ConnectionRegistry.from_file("connections.yml")
    """

    _github: GitHubConnection | None = None
    _gitlab: GitLabConnection | None = None
    _circleci: CircleCIConnection | None = None
    _bitrise: BitriseConnection | None = None
    _database: DatabaseConnection | None = None

    @classmethod
    def get_github(cls) -> GitHubConnection:
        """GitHub接続設定を取得

        Returns:
            GitHubConnection: GitHub接続設定
        """
        if cls._github is None:
            cls._github = GitHubConnection.from_env()
        return cls._github

    @classmethod
    def set_github(cls, conn: GitHubConnection) -> None:
        """GitHub接続設定を設定（テスト用）

        Args:
            conn: GitHubConnection
        """
        cls._github = conn
        logger.debug("GitHub connection updated")

    @classmethod
    def get_gitlab(cls) -> GitLabConnection:
        """GitLab接続設定を取得

        Returns:
            GitLabConnection: GitLab接続設定
        """
        if cls._gitlab is None:
            cls._gitlab = GitLabConnection.from_env()
        return cls._gitlab

    @classmethod
    def set_gitlab(cls, conn: GitLabConnection) -> None:
        """GitLab接続設定を設定（テスト用）

        Args:
            conn: GitLabConnection
        """
        cls._gitlab = conn
        logger.debug("GitLab connection updated")

    @classmethod
    def get_circleci(cls) -> CircleCIConnection:
        """CircleCI接続設定を取得

        Returns:
            CircleCIConnection: CircleCI接続設定
        """
        if cls._circleci is None:
            cls._circleci = CircleCIConnection.from_env()
        return cls._circleci

    @classmethod
    def set_circleci(cls, conn: CircleCIConnection) -> None:
        """CircleCI接続設定を設定（テスト用）

        Args:
            conn: CircleCIConnection
        """
        cls._circleci = conn
        logger.debug("CircleCI connection updated")

    @classmethod
    def get_bitrise(cls) -> BitriseConnection:
        """Bitrise接続設定を取得

        Returns:
            BitriseConnection: Bitrise接続設定
        """
        if cls._bitrise is None:
            cls._bitrise = BitriseConnection.from_env()
        return cls._bitrise

    @classmethod
    def set_bitrise(cls, conn: BitriseConnection) -> None:
        """Bitrise接続設定を設定（テスト用）

        Args:
            conn: BitriseConnection
        """
        cls._bitrise = conn
        logger.debug("Bitrise connection updated")

    @classmethod
    def get_database(cls) -> DatabaseConnection:
        """データベース接続設定を取得

        Returns:
            DatabaseConnection: データベース接続設定
        """
        if cls._database is None:
            cls._database = DatabaseConnection.from_env()
        return cls._database

    @classmethod
    def set_database(cls, conn: DatabaseConnection) -> None:
        """データベース接続設定を設定（テスト用）

        Args:
            conn: DatabaseConnection
        """
        cls._database = conn
        logger.debug("Database connection updated")

    @classmethod
    def reset_all(cls) -> None:
        """全てのConnectionをリセット（テスト用）"""
        cls._github = None
        cls._gitlab = None
        cls._circleci = None
        cls._bitrise = None
        cls._database = None
        logger.debug("All connections reset")

    @classmethod
    def validate_all(cls) -> dict[str, bool]:
        """全てのConnection設定を検証

        Returns:
            各Connectionの検証結果の辞書
        """
        return {
            "github": cls.get_github().validate(),
            "gitlab": cls.get_gitlab().validate(),
            "circleci": cls.get_circleci().validate(),
            "database": cls.get_database().validate(),
        }

    @classmethod
    def from_file(cls, path: str | Path) -> None:
        """設定ファイルから全てのConnectionを読み込み

        YAML形式の設定ファイルから接続情報を読み込む。
        環境変数の展開には対応していない（単純なYAMLパース）。

        Args:
            path: YAML設定ファイルのパス

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            ImportError: PyYAMLがインストールされていない場合

        Example:
            ConnectionRegistry.from_file("connections.yml")
        """
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "PyYAML is required for file-based configuration. "
                "Install it with: pip install pyyaml"
            ) from e

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Connection file not found: {path}")

        with open(path) as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning(f"Empty configuration file: {path}")
            return

        # GitHubの設定
        if "github" in config:
            gh_config = config["github"]
            # token と app_id のどちらが設定されているかで適切なクラスを選択
            # base_url を _base_url にマッピング
            if "base_url" in gh_config:
                gh_config["_base_url"] = gh_config.pop("base_url")

            if "token" in gh_config:
                cls._github = GitHubTokenAuth(**gh_config)
            elif "app_id" in gh_config and "installation_id" in gh_config:
                cls._github = GitHubAppAuth(**gh_config)
            else:
                raise ValueError(
                    "GitHub config must have either 'token' or ('app_id' and 'installation_id')"
                )
            logger.info("GitHub connection loaded from file")

        # GitLabの設定
        if "gitlab" in config:
            gl_config = config["gitlab"]
            cls._gitlab = GitLabConnection(**gl_config)
            logger.info("GitLab connection loaded from file")

        # CircleCIの設定
        if "circleci" in config:
            ci_config = config["circleci"]
            cls._circleci = CircleCIConnection(**ci_config)
            logger.info("CircleCI connection loaded from file")

        # Bitriseの設定
        if "bitrise" in config:
            br_config = config["bitrise"]
            cls._bitrise = BitriseConnection(**br_config)
            logger.info("Bitrise connection loaded from file")

        # Databaseの設定
        if "database" in config:
            db_config = config["database"]
            cls._database = DatabaseConnection(**db_config)
            logger.info("Database connection loaded from file")
