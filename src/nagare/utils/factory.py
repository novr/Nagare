"""依存性注入用のFactoryパターン

このモジュールはクライアントの生成を一元管理する。
テスト時はFactoryを差し替えることで、モックを注入可能。

ADR-002: Connection管理アーキテクチャに準拠し、
ConnectionRegistryから接続情報を取得してクライアントを生成する。
"""

import logging

from nagare.utils.bitrise_client import BitriseClient
from nagare.utils.connections import (
    BitriseConnection,
    ConnectionRegistry,
    DatabaseConnection,
    GitHubConnection,
    XcodeCloudConnection,
)
from nagare.utils.database import DatabaseClient
from nagare.utils.github_client import GitHubClient
from nagare.utils.protocols import (
    BitriseClientProtocol,
    DatabaseClientProtocol,
    GitHubClientProtocol,
    XcodeCloudClientProtocol,
)
from nagare.utils.xcode_cloud_client import XcodeCloudClient

logger = logging.getLogger(__name__)


class ClientFactory:
    """クライアントインスタンスを生成するFactoryクラス

    ConnectionRegistryから接続情報を取得してクライアントを生成する。
    テスト時はcreate_*メソッドをオーバーライドしたサブクラスを使用。
    """

    @staticmethod
    def create_database_client(
        connection: DatabaseConnection | None = None,
    ) -> DatabaseClientProtocol:
        """DatabaseClientインスタンスを生成する

        ConnectionRegistryから接続情報を取得してDatabaseClientを生成する。

        Args:
            connection: データベース接続設定（省略時はRegistryから取得）

        Returns:
            DatabaseClientProtocol実装インスタンス
        """
        logger.debug("Creating DatabaseClient (production mode)")
        # Connection優先、なければRegistryから取得
        if connection is None:
            connection = ConnectionRegistry.get_database()
        return DatabaseClient(connection=connection)

    @staticmethod
    def create_github_client(
        connection: GitHubConnection | None = None,
        conn_id: str | None = None,
    ) -> GitHubClientProtocol:
        """GitHubClientインスタンスを生成する

        優先順位:
        1. connection引数（明示的に指定されたConnection）
        2. conn_id引数（Airflow Connection ID）
        3. ConnectionRegistry（環境変数または設定ファイル）

        Args:
            connection: GitHub接続設定（省略時はconn_idまたはRegistryから取得）
            conn_id: Airflow Connection ID（省略時はRegistryから取得）

        Returns:
            GitHubClientProtocol実装インスタンス

        Example:
            # Airflow Connectionから作成
            client = ClientFactory.create_github_client(conn_id="github_default")

            # 環境変数から作成（デフォルト）
            client = ClientFactory.create_github_client()
        """
        # 1. connection引数が指定されている場合はそれを使用
        if connection is not None:
            return GitHubClient(connection=connection)

        # 2. conn_id が指定されている場合はAirflow Connectionから取得
        if conn_id is not None:
            try:
                connection = GitHubConnection.from_airflow(conn_id)
                logger.debug(f"Using Airflow Connection: {conn_id}")
                return GitHubClient(connection=connection)
            except (ImportError, ValueError) as e:
                logger.warning(
                    f"Failed to load Airflow Connection '{conn_id}': {e}. "
                    f"Falling back to environment variables."
                )

        # 3. ConnectionRegistryから取得（環境変数）
        connection = ConnectionRegistry.get_github()
        logger.debug("Using environment variables for GitHub authentication")
        return GitHubClient(connection=connection)

    @staticmethod
    def create_bitrise_client(
        connection: BitriseConnection | None = None,
        conn_id: str | None = None,
    ) -> BitriseClientProtocol:
        """BitriseClientインスタンスを生成する

        優先順位:
        1. connection引数（明示的に指定されたConnection）
        2. conn_id引数（Airflow Connection ID）
        3. ConnectionRegistry（環境変数または設定ファイル）

        Args:
            connection: Bitrise接続設定（省略時はconn_idまたはRegistryから取得）
            conn_id: Airflow Connection ID（省略時はRegistryから取得）

        Returns:
            BitriseClientProtocol実装インスタンス

        Example:
            # Airflow Connectionから作成
            client = ClientFactory.create_bitrise_client(conn_id="bitrise_default")

            # 環境変数から作成（デフォルト）
            client = ClientFactory.create_bitrise_client()
        """
        # 1. connection引数が指定されている場合はそれを使用
        if connection is not None:
            return BitriseClient(connection=connection)

        # 2. conn_id が指定されている場合はAirflow Connectionから取得
        if conn_id is not None:
            try:
                connection = BitriseConnection.from_airflow(conn_id)
                logger.debug(f"Using Airflow Connection: {conn_id}")
                return BitriseClient(connection=connection)
            except (ImportError, ValueError) as e:
                logger.warning(
                    f"Failed to load Airflow Connection '{conn_id}': {e}. "
                    f"Falling back to environment variables."
                )

        # 3. ConnectionRegistryから取得（環境変数）
        connection = ConnectionRegistry.get_bitrise()
        logger.debug("Using environment variables for Bitrise authentication")
        return BitriseClient(connection=connection)

    @staticmethod
    def create_xcode_cloud_client(
        connection: XcodeCloudConnection | None = None,
        conn_id: str | None = None,
    ) -> XcodeCloudClientProtocol:
        """XcodeCloudClientインスタンスを生成する

        優先順位:
        1. connection引数（明示的に指定されたConnection）
        2. conn_id引数（Airflow Connection ID）
        3. ConnectionRegistry（環境変数または設定ファイル）

        Args:
            connection: Xcode Cloud接続設定（省略時はconn_idまたはRegistryから取得）
            conn_id: Airflow Connection ID（省略時はRegistryから取得）

        Returns:
            XcodeCloudClientProtocol実装インスタンス

        Example:
            # Airflow Connectionから作成
            client = ClientFactory.create_xcode_cloud_client(conn_id="xcode_cloud_default")

            # 環境変数から作成（デフォルト）
            client = ClientFactory.create_xcode_cloud_client()
        """
        # 1. connection引数が指定されている場合はそれを使用
        if connection is not None:
            return XcodeCloudClient(connection=connection)

        # 2. conn_id が指定されている場合はAirflow Connectionから取得
        if conn_id is not None:
            try:
                connection = XcodeCloudConnection.from_airflow(conn_id)
                logger.debug(f"Using Airflow Connection: {conn_id}")
                return XcodeCloudClient(connection=connection)
            except (ImportError, ValueError) as e:
                logger.warning(
                    f"Failed to load Airflow Connection '{conn_id}': {e}. "
                    f"Falling back to environment variables."
                )

        # 3. ConnectionRegistryから取得（環境変数）
        connection = ConnectionRegistry.get_xcode_cloud()
        logger.debug("Using environment variables for Xcode Cloud authentication")
        return XcodeCloudClient(connection=connection)


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
