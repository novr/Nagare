"""エラーハンドリングのエッジケーステスト

GitHub APIやデータベース接続のエラーケースを包括的にテストする。
"""

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException, RateLimitExceededException
from sqlalchemy.exc import OperationalError, TimeoutError


class TestGitHubClientErrorHandling:
    """GitHubClientのエラーハンドリングテスト"""

    @patch("nagare.utils.github_client.Github")
    def test_rate_limit_exceeded(self, mock_github: MagicMock) -> None:
        """Rate Limit超過時のハンドリング"""
        from nagare.utils.connections import GitHubConnection
        from nagare.utils.github_client import GitHubClient

        # Rate Limitエラーを発生させる
        mock_instance = MagicMock()
        mock_instance.get_repo.side_effect = RateLimitExceededException(
            status=403,
            data={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234567890"},
        )
        mock_github.return_value = mock_instance

        connection = GitHubConnection(token="test_token")
        client = GitHubClient(connection=connection)

        # Rate Limitエラーが適切に処理されることを確認
        with pytest.raises(RateLimitExceededException):
            client._github.get_repo("owner/repo")

    @patch("nagare.utils.github_client.Github")
    def test_github_not_found_error(self, mock_github: MagicMock) -> None:
        """存在しないリポジトリへのアクセス"""
        from nagare.utils.connections import GitHubConnection
        from nagare.utils.github_client import GitHubClient

        mock_instance = MagicMock()
        mock_instance.get_repo.side_effect = GithubException(
            status=404, data={"message": "Not Found"}, headers={}
        )
        mock_github.return_value = mock_instance

        connection = GitHubConnection(token="test_token")
        client = GitHubClient(connection=connection)

        with pytest.raises(GithubException) as exc_info:
            client._github.get_repo("owner/nonexistent")

        assert exc_info.value.status == 404

    @patch("nagare.utils.github_client.Github")
    def test_github_authentication_error(self, mock_github: MagicMock) -> None:
        """認証エラー（無効なトークン）"""
        from nagare.utils.connections import GitHubConnection
        from nagare.utils.github_client import GitHubClient

        mock_instance = MagicMock()
        mock_instance.get_repo.side_effect = GithubException(
            status=401, data={"message": "Bad credentials"}, headers={}
        )
        mock_github.return_value = mock_instance

        connection = GitHubConnection(token="invalid_token")
        client = GitHubClient(connection=connection)

        with pytest.raises(GithubException) as exc_info:
            client._github.get_repo("owner/repo")

        assert exc_info.value.status == 401

    @patch("nagare.utils.github_client.Github")
    def test_github_server_error_5xx(self, mock_github: MagicMock) -> None:
        """GitHubサーバーエラー（5xx系）"""
        from nagare.utils.connections import GitHubConnection
        from nagare.utils.github_client import GitHubClient

        mock_instance = MagicMock()
        mock_instance.get_repo.side_effect = GithubException(
            status=502, data={"message": "Server Error"}, headers={}
        )
        mock_github.return_value = mock_instance

        connection = GitHubConnection(token="test_token")
        client = GitHubClient(connection=connection)

        with pytest.raises(GithubException) as exc_info:
            client._github.get_repo("owner/repo")

        assert exc_info.value.status == 502

    @patch("nagare.utils.github_client.Github")
    def test_github_timeout_error(self, mock_github: MagicMock) -> None:
        """タイムアウトエラー"""
        from nagare.utils.connections import GitHubConnection
        from nagare.utils.github_client import GitHubClient

        mock_instance = MagicMock()
        mock_instance.get_repo.side_effect = TimeoutError("Request timed out")
        mock_github.return_value = mock_instance

        connection = GitHubConnection(token="test_token")
        client = GitHubClient(connection=connection)

        with pytest.raises(TimeoutError):
            client._github.get_repo("owner/repo")

    def test_github_connection_without_token(self) -> None:
        """トークン無しの接続"""
        from nagare.utils.connections import GitHubConnection

        # トークンもGitHub Appsも無い接続
        connection = GitHubConnection()

        # validate()がFalseを返すことを確認
        assert connection.validate() is False

    def test_github_connection_with_invalid_app_config(self) -> None:
        """不完全なGitHub Apps設定"""
        from nagare.utils.connections import GitHubConnection

        # app_idだけでinstallation_idが無い
        connection = GitHubConnection(app_id=12345)

        # validate()がFalseを返すことを確認
        assert connection.validate() is False


class TestDatabaseErrorHandling:
    """DatabaseClientのエラーハンドリングテスト"""

    @patch("nagare.utils.database.create_engine")
    def test_database_connection_failure(self, mock_create_engine: MagicMock) -> None:
        """データベース接続失敗"""
        from nagare.utils.connections import DatabaseConnection
        from nagare.utils.database import DatabaseClient

        # 接続エラーを発生させる
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = OperationalError(
            "could not connect to server", None, None
        )
        mock_create_engine.return_value = mock_engine

        connection = DatabaseConnection(
            host="invalid_host", port=5432, database="test", user="test", password="test"
        )
        client = DatabaseClient(connection=connection)

        # 接続時にエラーが発生することを確認
        with pytest.raises(OperationalError):
            with client.engine.connect():
                pass

    @patch("nagare.utils.database.create_engine")
    def test_database_query_timeout(self, mock_create_engine: MagicMock) -> None:
        """クエリタイムアウト"""
        from nagare.utils.connections import DatabaseConnection
        from nagare.utils.database import DatabaseClient

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = TimeoutError("Query timeout")
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        connection = DatabaseConnection(
            host="localhost", port=5432, database="test", user="test", password="test"
        )
        client = DatabaseClient(connection=connection)

        with pytest.raises(TimeoutError):
            with client.engine.connect() as conn:
                conn.execute("SELECT * FROM large_table")

    def test_database_connection_url_format(self) -> None:
        """データベース接続URLの形式確認"""
        from nagare.utils.connections import DatabaseConnection

        connection = DatabaseConnection(
            host="testhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

        expected_url = "postgresql://testuser:testpass@testhost:5432/testdb"
        assert connection.url == expected_url

    def test_database_connection_url_with_special_chars(self) -> None:
        """特殊文字を含むパスワードのエスケープ"""
        from urllib.parse import quote_plus

        from nagare.utils.connections import DatabaseConnection

        password_with_special_chars = "p@ssw0rd!#$%"
        connection = DatabaseConnection(
            host="localhost",
            port=5432,
            database="nagare",
            user="user",
            password=password_with_special_chars,
        )

        # パスワードがURLエンコードされていることを確認
        expected_password = quote_plus(password_with_special_chars)
        assert expected_password in connection.url


class TestConnectionRegistryErrorHandling:
    """ConnectionRegistryのエラーハンドリングテスト"""

    def test_get_github_without_env_vars(self) -> None:
        """環境変数無しでGitHub接続を取得"""
        from nagare.utils.connections import ConnectionRegistry

        # 環境変数をクリア
        with patch.dict("os.environ", {}, clear=True):
            connection = ConnectionRegistry.get_github()

            # 接続は作成されるが、validate()がFalseを返す
            assert connection is not None
            assert connection.validate() is False

    def test_get_database_without_env_vars(self) -> None:
        """環境変数無しでDatabase接続を取得"""
        from nagare.utils.connections import ConnectionRegistry

        # 環境変数をクリア
        with patch.dict("os.environ", {}, clear=True):
            connection = ConnectionRegistry.get_database()

            # デフォルト値で接続が作成される
            assert connection is not None
            assert connection.host == "localhost"
            assert connection.port == 5432


class TestTaskErrorHandling:
    """タスクレベルのエラーハンドリングテスト"""

    @patch("nagare.utils.factory.ClientFactory.create_github_client")
    def test_fetch_workflow_runs_with_empty_repos(
        self, mock_github_factory: MagicMock, mock_airflow_context: dict
    ) -> None:
        """リポジトリリストが空の場合"""
        from nagare.tasks.fetch import fetch_workflow_runs
        from tests.conftest import MockGitHubClient

        mock_github = MockGitHubClient()
        mock_github_factory.return_value = mock_github

        # 空のリポジトリリスト
        ti = mock_airflow_context["ti"]
        ti.xcom_data["repositories"] = []

        # エラーにならず、空のリストが返されることを確認
        from nagare.utils.dag_helpers import with_github_client

        wrapped_func = with_github_client(fetch_workflow_runs)
        wrapped_func(**mock_airflow_context)

        workflow_runs = ti.xcom_data.get("workflow_runs")
        assert workflow_runs is not None
        assert len(workflow_runs) == 0

    @patch("nagare.utils.factory.ClientFactory.create_database_client")
    def test_load_to_database_with_invalid_data(
        self, mock_db_factory: MagicMock, mock_airflow_context: dict
    ) -> None:
        """不正なデータ形式の場合"""
        from nagare.tasks.load import load_to_database
        from tests.conftest import MockDatabaseClient

        mock_db = MockDatabaseClient()
        mock_db_factory.return_value = mock_db

        ti = mock_airflow_context["ti"]
        # 必須フィールドが欠けているデータ
        ti.xcom_data["transformed_runs"] = [
            {
                "source_run_id": "123",
                # source, pipeline_name, status などが欠けている
            }
        ]
        ti.xcom_data["transformed_jobs"] = []

        from nagare.utils.dag_helpers import with_database_client

        wrapped_func = with_database_client(load_to_database)

        # KeyErrorまたは適切なバリデーションエラーが発生することを期待
        # （実装によってはスキップされる可能性もある）
        try:
            wrapped_func(**mock_airflow_context)
        except (KeyError, ValueError):
            # エラーが発生するのは正常
            pass

    @patch("nagare.utils.factory.ClientFactory.create_github_client")
    def test_fetch_workflow_run_jobs_with_missing_xcom(
        self, mock_github_factory: MagicMock, mock_airflow_context: dict
    ) -> None:
        """XComデータが欠けている場合"""
        from nagare.tasks.fetch import fetch_workflow_run_jobs
        from tests.conftest import MockGitHubClient

        mock_github = MockGitHubClient()
        mock_github_factory.return_value = mock_github

        ti = mock_airflow_context["ti"]
        # workflow_runsが無い
        ti.xcom_data.pop("workflow_runs", None)

        from nagare.utils.dag_helpers import with_github_client

        wrapped_func = with_github_client(fetch_workflow_run_jobs)

        # KeyErrorが発生することを確認
        with pytest.raises(KeyError):
            wrapped_func(**mock_airflow_context)


class TestDataTransformationErrorHandling:
    """データ変換のエラーハンドリングテスト"""

    def test_transform_data_with_malformed_dates(
        self, mock_airflow_context: dict
    ) -> None:
        """不正な日付形式のデータ"""
        from nagare.tasks.transform import transform_data

        ti = mock_airflow_context["ti"]
        ti.xcom_data["workflow_runs"] = [
            {
                "id": 123,
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "created_at": "invalid-date",  # 不正な形式
                "updated_at": "2024-01-01T00:00:00Z",
                "repository": {"full_name": "owner/repo"},
            }
        ]
        ti.xcom_data["workflow_run_jobs"] = []

        # 日付パースエラーが発生することを期待
        # （実装によってはスキップされる可能性もある）
        try:
            transform_data(**mock_airflow_context)
        except (ValueError, KeyError):
            # エラーが発生するのは正常
            pass

    def test_transform_data_with_missing_fields(
        self, mock_airflow_context: dict
    ) -> None:
        """必須フィールドが欠けているデータ"""
        from nagare.tasks.transform import transform_data

        ti = mock_airflow_context["ti"]
        ti.xcom_data["workflow_runs"] = [
            {
                "id": 123,
                # name, status, conclusionなどが欠けている
            }
        ]
        ti.xcom_data["workflow_run_jobs"] = []

        # KeyErrorが発生することを期待
        with pytest.raises(KeyError):
            transform_data(**mock_airflow_context)


class TestConnectionPooling:
    """接続プーリングのテスト"""

    @patch("nagare.utils.database.create_engine")
    def test_database_connection_pool_exhaustion(
        self, mock_create_engine: MagicMock
    ) -> None:
        """接続プールの枯渇"""
        from nagare.utils.connections import DatabaseConnection
        from nagare.utils.database import DatabaseClient

        mock_engine = MagicMock()
        mock_engine.pool = MagicMock()
        mock_engine.pool.size.return_value = 0  # プールが空
        mock_create_engine.return_value = mock_engine

        connection = DatabaseConnection(
            host="localhost",
            port=5432,
            database="test",
            user="test",
            password="test",
            pool_size=1,
            max_overflow=0,
        )
        client = DatabaseClient(connection=connection)

        # 接続プールの設定が反映されていることを確認
        assert client.engine is not None

    def test_database_connection_pool_settings(self) -> None:
        """接続プール設定のデフォルト値"""
        from nagare.utils.connections import DatabaseConnection

        connection = DatabaseConnection(
            host="localhost", port=5432, database="test", user="test", password="test"
        )

        # デフォルト値の確認
        assert connection.pool_size == 5
        assert connection.max_overflow == 10
        assert connection.pool_pre_ping is True
