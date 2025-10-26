"""Connection管理モジュール

CI/CDプラットフォームおよびデータベースへの接続情報を一元管理する。
新しいプラットフォーム追加時は、以下の3ステップで拡張可能：
1. Connectionクラスの追加
2. ConnectionRegistryへのメソッド追加
3. ClientFactoryへの統合

使用例:
    # 環境変数から自動取得
    github_conn = ConnectionRegistry.get_github()

    # テスト時のモック注入
    ConnectionRegistry.set_github(GitHubConnection(token="test"))

    # 設定ファイルから一括読み込み
    ConnectionRegistry.from_file("connections.yml")
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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
# 2. GitHub Connection
# ============================================================================


@dataclass
class GitHubConnection:
    """GitHub接続設定

    Personal Access Token または GitHub Apps 認証に対応。

    Attributes:
        token: Personal Access Token（推奨）
        app_id: GitHub App ID
        installation_id: GitHub App Installation ID
        private_key: GitHub App Private Key（文字列）
        private_key_path: GitHub App Private Keyファイルパス
        base_url: GitHub API ベースURL（GitHub Enterpriseの場合に変更）

    使用例:
        # Personal Access Token認証
        conn = GitHubConnection(token="ghp_xxx")

        # GitHub Apps認証
        conn = GitHubConnection(
            app_id=123456,
            installation_id=789012,
            private_key_path="/path/to/key.pem"
        )

        # 環境変数から自動生成
        conn = GitHubConnection.from_env()
    """

    # Personal Access Token認証
    token: str | None = None

    # GitHub Apps認証
    app_id: int | None = None
    installation_id: int | None = None
    private_key: str | None = None
    private_key_path: str | None = None

    # 共通設定
    base_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> "GitHubConnection":
        """環境変数から生成

        以下の環境変数を読み取る：
        - GITHUB_TOKEN: Personal Access Token
        - GITHUB_APP_ID: GitHub App ID
        - GITHUB_APP_INSTALLATION_ID: GitHub App Installation ID
        - GITHUB_APP_PRIVATE_KEY: Private Key（文字列）
        - GITHUB_APP_PRIVATE_KEY_PATH: Private Keyファイルパス
        - GITHUB_API_URL: ベースURL（デフォルト: https://api.github.com）

        Returns:
            GitHubConnection: 環境変数から生成されたConnection
        """
        # App ID/Installation IDの読み取り（0はNoneとして扱う）
        app_id_str = os.getenv("GITHUB_APP_ID", "")
        installation_id_str = os.getenv("GITHUB_APP_INSTALLATION_ID", "")

        app_id = None
        if app_id_str:
            try:
                app_id = int(app_id_str)
                if app_id == 0:
                    app_id = None
            except ValueError:
                logger.warning(f"Invalid GITHUB_APP_ID: {app_id_str}")

        installation_id = None
        if installation_id_str:
            try:
                installation_id = int(installation_id_str)
                if installation_id == 0:
                    installation_id = None
            except ValueError:
                logger.warning(
                    f"Invalid GITHUB_APP_INSTALLATION_ID: {installation_id_str}"
                )

        return cls(
            token=os.getenv("GITHUB_TOKEN"),
            app_id=app_id,
            installation_id=installation_id,
            private_key=os.getenv("GITHUB_APP_PRIVATE_KEY"),
            private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
            base_url=os.getenv("GITHUB_API_URL", "https://api.github.com"),
        )

    def validate(self) -> bool:
        """接続情報の検証

        Token認証 または GitHub Apps認証のいずれかが有効な場合にTrueを返す。

        Returns:
            有効な設定の場合True
        """
        # Personal Access Token認証
        if self.token:
            return True

        # GitHub Apps認証
        if self.app_id and self.installation_id:
            return bool(self.private_key or self.private_key_path)

        return False

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（シークレットは除外）

        Returns:
            シークレットを含まない設定情報
        """
        return {
            "type": "github",
            "base_url": self.base_url,
            "auth_type": "token" if self.token else "app",
            "has_token": bool(self.token),
            "has_app_id": bool(self.app_id),
            "has_private_key": bool(self.private_key or self.private_key_path),
        }


# ============================================================================
# 3. GitLab Connection（将来の拡張用）
# ============================================================================


@dataclass
class GitLabConnection:
    """GitLab接続設定（将来の拡張用）

    Attributes:
        token: Personal Access Token
        base_url: GitLab API ベースURL

    使用例:
        conn = GitLabConnection(token="glpat-xxx")
        conn = GitLabConnection.from_env()
    """

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
# 4. CircleCI Connection（将来の拡張用）
# ============================================================================


@dataclass
class CircleCIConnection:
    """CircleCI接続設定（将来の拡張用）

    Attributes:
        api_token: API Token
        base_url: CircleCI API ベースURL

    使用例:
        conn = CircleCIConnection(api_token="xxx")
        conn = CircleCIConnection.from_env()
    """

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


# ============================================================================
# 5. Database Connection
# ============================================================================


@dataclass
class DatabaseConnection:
    """データベース接続設定

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

        # 環境変数から自動生成
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

        Returns:
            PostgreSQL接続URL
        """
        return (
            f"postgresql://{self.user}:{self.password}"
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
# 6. ConnectionRegistry（一元管理）
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
            cls._github = GitHubConnection(**gh_config)
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

        # Databaseの設定
        if "database" in config:
            db_config = config["database"]
            cls._database = DatabaseConnection(**db_config)
            logger.info("Database connection loaded from file")
