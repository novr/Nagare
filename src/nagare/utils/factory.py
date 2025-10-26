"""依存性注入用のFactoryパターン

このモジュールはクライアントの生成を一元管理する。
テスト時はFactoryを差し替えることで、モックを注入可能。

ADR-002: Connection管理アーキテクチャに準拠し、
ConnectionRegistryから接続情報を取得してクライアントを生成する。
"""

import logging
import os

from nagare.utils.connections import (
    ConnectionRegistry,
    DatabaseConnection,
    GitHubConnection,
)
from nagare.utils.database import DatabaseClient
from nagare.utils.database_mock import MockDatabaseClient
from nagare.utils.github_client import GitHubClient
from nagare.utils.protocols import DatabaseClientProtocol, GitHubClientProtocol

logger = logging.getLogger(__name__)


class ClientFactory:
    """クライアントインスタンスを生成するFactoryクラス

    環境変数に基づいて適切な実装を返す。
    - USE_DB_MOCK=true: MockDatabaseClient（開発環境）
    - USE_DB_MOCK=false: DatabaseClient（本番環境）

    テスト時はcreate_*メソッドをオーバーライドしたサブクラスを使用。
    """

    @staticmethod
    def create_database_client(
        connection: DatabaseConnection | None = None,
    ) -> DatabaseClientProtocol:
        """DatabaseClientインスタンスを生成する

        環境変数USE_DB_MOCKに基づいて適切な実装を返す。

        Args:
            connection: データベース接続設定（省略時はRegistryから取得）

        Returns:
            DatabaseClientProtocol実装インスタンス
        """
        use_mock = os.getenv("USE_DB_MOCK", "false").lower() == "true"
        if use_mock:
            logger.debug("Creating MockDatabaseClient (development mode)")
            return MockDatabaseClient()
        else:
            logger.debug("Creating DatabaseClient (production mode)")
            # Connection優先、なければRegistryから取得
            if connection is None:
                connection = ConnectionRegistry.get_database()
            return DatabaseClient(connection=connection)

    @staticmethod
    def create_github_client(
        connection: GitHubConnection | None = None,
    ) -> GitHubClientProtocol:
        """GitHubClientインスタンスを生成する

        Args:
            connection: GitHub接続設定（省略時はRegistryから取得）

        Returns:
            GitHubClientProtocol実装インスタンス
        """
        # Connection優先、なければRegistryから取得
        if connection is None:
            connection = ConnectionRegistry.get_github()
        return GitHubClient(connection=connection)


# グローバルなFactoryインスタンス
# テスト時はこれを差し替える
_factory: ClientFactory = ClientFactory()


def get_factory() -> ClientFactory:
    """現在のFactoryインスタンスを取得する

    Returns:
        ClientFactoryインスタンス
    """
    return _factory


def set_factory(factory: ClientFactory) -> None:
    """Factoryインスタンスを設定する

    テスト時にモック用のFactoryを注入する際に使用。

    Args:
        factory: 新しいClientFactoryインスタンス
    """
    global _factory
    _factory = factory
    logger.debug(f"Factory changed to {factory.__class__.__name__}")
