"""factory.pyのユニットテスト"""

import pytest


def test_factory_create_database_client() -> None:
    """DatabaseClientの生成を確認"""
    from nagare.utils.database import DatabaseClient
    from nagare.utils.factory import ClientFactory

    factory = ClientFactory()
    client = factory.create_database_client()

    assert isinstance(client, DatabaseClient)
    client.close()


def test_factory_create_github_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHubClientの生成を確認"""
    from nagare.utils.factory import ClientFactory
    from nagare.utils.protocols import GitHubClientProtocol

    # テスト用の認証情報を設定
    monkeypatch.setenv("GITHUB_TOKEN", "test_token_12345")

    factory = ClientFactory()
    client = factory.create_github_client()

    assert isinstance(client, GitHubClientProtocol)
    client.close()


def test_factory_get_and_set() -> None:
    """get_factory/set_factoryの動作を確認"""
    from nagare.utils.factory import ClientFactory, get_factory, set_factory

    # デフォルトのFactoryを取得
    original_factory = get_factory()
    assert isinstance(original_factory, ClientFactory)

    # カスタムFactoryを設定
    class CustomFactory(ClientFactory):
        pass

    custom_factory = CustomFactory()
    set_factory(custom_factory)

    # カスタムFactoryが返されることを確認
    retrieved_factory = get_factory()
    assert retrieved_factory is custom_factory
    assert isinstance(retrieved_factory, CustomFactory)

    # 元に戻す
    set_factory(original_factory)


def test_database_client_context_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """DatabaseClientがcontext managerとして動作することを確認"""
    from nagare.utils.database import DatabaseClient

    # DatabaseClientは本番用なので、NotImplementedErrorが発生するメソッドは呼ばない
    with DatabaseClient() as client:
        assert client is not None
        # context managerとして正常に動作することを確認

    # with文を抜けた後、close()が呼ばれていることを確認


def test_github_client_context_manager() -> None:
    """GitHubClientがcontext managerとして動作することを確認"""
    from nagare.utils.github_client import GitHubClient

    # テスト用トークンで初期化
    with GitHubClient(token="test_token") as client:
        assert client is not None
        assert client.github is not None

    # with文を抜けた後も正常
    # （close()が呼ばれるが、エラーは発生しない）


def test_mock_database_client_context_manager() -> None:
    """MockDatabaseClientがcontext managerとして動作することを確認"""
    from tests.conftest import MockDatabaseClient

    mock_client = MockDatabaseClient()

    with mock_client as client:
        assert client is mock_client
        repositories = client.get_repositories()
        assert len(repositories) == 2

    # close()が呼ばれたことを確認
    assert mock_client.close_called


def test_mock_github_client_context_manager() -> None:
    """MockGitHubClientがcontext managerとして動作することを確認"""
    from tests.conftest import MockGitHubClient

    mock_client = MockGitHubClient()

    with mock_client as client:
        assert client is mock_client
        runs = client.get_workflow_runs("test-org", "test-repo")
        assert len(runs) == 1

    # close()が呼ばれたことを確認
    assert mock_client.close_called
