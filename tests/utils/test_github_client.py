"""github_client.pyのユニットテスト"""

import pytest


def test_github_client_init_with_token() -> None:
    """Personal Access Tokenで初期化できることを確認"""
    from nagare.utils.github_client import GitHubClient

    client = GitHubClient(token="test_token_12345")

    assert client.github is not None
    client.close()


def test_github_client_init_with_github_app() -> None:
    """GitHub Appsで初期化できることを確認"""
    from nagare.utils.github_client import GitHubClient

    # テスト用の秘密鍵（実際には使用されない形式でも初期化可能）
    private_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF0yXRHMaH+nXvhWNkwVYNPFGzT5f
...
-----END RSA PRIVATE KEY-----"""

    # 注: このテストは実際のGitHub APIにアクセスしないため、
    # 無効な認証情報でも初期化自体は成功する
    client = GitHubClient(
        app_id=123456, installation_id=12345678, private_key=private_key
    )

    assert client.github is not None
    client.close()


def test_github_client_init_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """認証情報なしでの初期化はValueErrorが発生することを確認"""
    from nagare.utils.github_client import GitHubClient

    # 環境変数をクリア
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValueError, match="GitHub authentication not configured"):
        GitHubClient()


def test_github_client_init_with_partial_app_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不完全なGitHub Apps認証情報での初期化はValueErrorが発生することを確認"""
    from nagare.utils.github_client import GitHubClient

    # 環境変数をクリア
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    # app_idのみ
    with pytest.raises(ValueError, match="GitHub authentication not configured"):
        GitHubClient(app_id=123456)

    # installation_idのみ
    with pytest.raises(ValueError, match="GitHub authentication not configured"):
        GitHubClient(installation_id=12345678)

    # private_keyのみ
    with pytest.raises(ValueError, match="GitHub authentication not configured"):
        GitHubClient(private_key="some_key")


def test_github_client_init_from_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数GITHUB_TOKENから認証情報を読み取ることを確認"""
    from nagare.utils.github_client import GitHubClient

    # 環境変数設定
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "test_token_from_env")

    client = GitHubClient()

    assert client.github is not None
    client.close()


def test_github_client_close() -> None:
    """close()メソッドが正常に実行されることを確認"""
    from nagare.utils.github_client import GitHubClient

    client = GitHubClient(token="test_token")

    # エラーなく実行されることを確認
    client.close()


def test_github_client_custom_base_url() -> None:
    """カスタムbase_URLで初期化できることを確認"""
    from nagare.utils.github_client import GitHubClient

    # GitHub Enterprise用のカスタムURL
    client = GitHubClient(
        token="test_token", base_url="https://github.example.com/api/v3"
    )

    assert client.github is not None
    client.close()


def test_github_client_init_invalid_app_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """GITHUB_APP_IDが整数でない場合にValueErrorが発生することを確認"""
    from nagare.utils.github_client import GitHubClient

    # 環境変数設定
    monkeypatch.setenv("GITHUB_APP_ID", "not_an_integer")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "12345678")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test_key")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValueError, match="Invalid GITHUB_APP_ID or GITHUB_APP_INSTALLATION_ID"):
        GitHubClient()


def test_github_client_init_invalid_installation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GITHUB_APP_INSTALLATION_IDが整数でない場合にValueErrorが発生することを確認"""
    from nagare.utils.github_client import GitHubClient

    # 環境変数設定
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "not_an_integer")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test_key")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(
        ValueError, match="Invalid GITHUB_APP_ID or GITHUB_APP_INSTALLATION_ID"
    ):
        GitHubClient()


def test_github_client_init_private_key_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """秘密鍵ファイルが存在しない場合にValueErrorが発生することを確認"""
    from nagare.utils.github_client import GitHubClient

    # 環境変数設定
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "12345678")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", "/nonexistent/path/key.pem")
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValueError, match="private key file not found"):
        GitHubClient()


def test_github_client_init_partial_arguments_with_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """部分的な引数指定では初期化に失敗することを確認（新しいABC-based実装）"""
    from nagare.utils.github_client import GitHubClient

    # app_idのみ引数で指定、残りは環境変数にあっても無視される
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "12345678")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test_key_from_env")
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    # app_idのみでは不十分（installation_idとprivate_keyが必要）
    # 環境変数からの自動読み取りも行われない（明確な分離）
    with pytest.raises(ValueError, match="GitHub authentication not configured"):
        GitHubClient(app_id=123456)


def test_github_client_repository_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    """リポジトリオブジェクトがキャッシュされることを確認"""
    from unittest.mock import Mock

    from nagare.utils.github_client import GitHubClient

    client = GitHubClient(token="test_token")

    # github.get_repo()をモックする
    mock_repo = Mock()
    client.github.get_repo = Mock(return_value=mock_repo)

    # キャッシュが空であることを確認
    assert len(client._repo_cache) == 0  # type: ignore[reportPrivateUsage]

    # _get_repositoryを呼び出すとキャッシュされる
    repo1 = client._get_repository("test-org", "test-repo")  # type: ignore[reportPrivateUsage]
    assert len(client._repo_cache) == 1  # type: ignore[reportPrivateUsage]
    assert "test-org/test-repo" in client._repo_cache  # type: ignore[reportPrivateUsage]
    assert client.github.get_repo.call_count == 1

    # 同じリポジトリを再度取得してもキャッシュから返される
    repo2 = client._get_repository("test-org", "test-repo")  # type: ignore[reportPrivateUsage]
    assert repo1 is repo2  # 同一オブジェクト
    assert len(client._repo_cache) == 1  # type: ignore[reportPrivateUsage]
    assert client.github.get_repo.call_count == 1  # API呼び出しは増えない

    # 異なるリポジトリはキャッシュに追加される
    _repo3 = client._get_repository("test-org", "another-repo")  # type: ignore[reportPrivateUsage]
    assert len(client._repo_cache) == 2  # type: ignore[reportPrivateUsage]
    assert "test-org/another-repo" in client._repo_cache  # type: ignore[reportPrivateUsage]
    assert client.github.get_repo.call_count == 2  # 2回目のAPI呼び出し

    client.close()


def test_github_client_retry_configuration() -> None:
    """リトライ設定が正しくGitHubクライアントに渡されていることを確認

    Note: PyGithubの内部実装に依存せず、GitHubClientの初期化パラメータを確認。
    実際のリトライ動作はPyGithubライブラリに委ねる。
    """
    from unittest.mock import MagicMock, patch

    from nagare.constants import GitHubConfig

    # Githubクラスをモック
    with patch("nagare.utils.github_client.Github") as mock_github_class:
        mock_github_instance = MagicMock()
        mock_github_class.return_value = mock_github_instance

        from nagare.utils.github_client import GitHubClient

        # GitHubClientを初期化
        client = GitHubClient(token="test_token")

        # Githubクラスが正しい引数で呼ばれたことを確認
        assert mock_github_class.called

        # 呼び出し時の引数を取得
        call_kwargs = mock_github_class.call_args.kwargs

        # retryパラメータが渡されていることを確認
        assert "retry" in call_kwargs
        retry = call_kwargs["retry"]

        # リトライ設定の検証
        assert retry.total == GitHubConfig.RETRY_TOTAL  # 3回
        assert retry.backoff_factor == GitHubConfig.RETRY_BACKOFF_FACTOR  # 1.0

        # status_forcelistに必要なステータスコードがすべて含まれていることを確認
        # Note: PyGithubが自動的に追加するステータスコードもあるため、完全一致ではなく包含チェック
        for status_code in GitHubConfig.RETRY_STATUS_FORCELIST:
            assert status_code in retry.status_forcelist

        client.close()


def test_github_client_retry_status_codes() -> None:
    """リトライ対象のHTTPステータスコードが正しく設定されていることを確認"""
    from unittest.mock import MagicMock, patch

    with patch("nagare.utils.github_client.Github") as mock_github_class:
        mock_github_instance = MagicMock()
        mock_github_class.return_value = mock_github_instance

        from nagare.utils.github_client import GitHubClient

        client = GitHubClient(token="test_token")

        # リトライ設定を取得
        retry = mock_github_class.call_args.kwargs["retry"]

        # Forbiddenエラー（403、レート制限などで使用）が含まれていることを確認
        assert 403 in retry.status_forcelist

        # レート制限エラー（429）が含まれていることを確認
        assert 429 in retry.status_forcelist

        # サーバーエラー（5xx）が含まれていることを確認
        assert 500 in retry.status_forcelist
        assert 502 in retry.status_forcelist
        assert 503 in retry.status_forcelist
        assert 504 in retry.status_forcelist

        client.close()


def test_github_client_retry_backoff_factor() -> None:
    """指数バックオフの設定が正しいことを確認

    backoff_factor=1.0の場合、リトライ間隔は:
    - 1回目のリトライ: 1秒
    - 2回目のリトライ: 2秒
    - 3回目のリトライ: 4秒
    """
    from unittest.mock import MagicMock, patch

    with patch("nagare.utils.github_client.Github") as mock_github_class:
        mock_github_instance = MagicMock()
        mock_github_class.return_value = mock_github_instance

        from nagare.constants import GitHubConfig
        from nagare.utils.github_client import GitHubClient

        client = GitHubClient(token="test_token")

        # リトライ設定を取得
        retry = mock_github_class.call_args.kwargs["retry"]

        # バックオフファクターの検証
        assert retry.backoff_factor == GitHubConfig.RETRY_BACKOFF_FACTOR
        assert retry.backoff_factor == 1.0  # 明示的な値の確認

        # リトライ回数の検証
        assert retry.total == 3

        client.close()
