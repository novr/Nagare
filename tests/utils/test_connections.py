"""Connection管理のテスト

ConnectionRegistry, GitHubConnection, DatabaseConnectionなど
Connection層の動作を検証する。
"""

import os
from pathlib import Path

import pytest

from nagare.utils.connections import (
    CircleCIConnection,
    ConnectionRegistry,
    DatabaseConnection,
    GitHubConnection,
    GitLabConnection,
)


class TestGitHubConnection:
    """GitHubConnection のテスト"""

    def test_from_env_with_token(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からToken認証の設定を生成"""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.delenv("GITHUB_APP_ID", raising=False)

        conn = GitHubConnection.from_env()

        assert conn.token == "test_token"
        assert conn.app_id is None
        assert conn.base_url == "https://api.github.com"

    def test_from_env_with_app(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からGitHub Apps認証の設定を生成"""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_APP_ID", "123456")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "789012")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test_key")

        conn = GitHubConnection.from_env()

        assert conn.token is None
        assert conn.app_id == 123456
        assert conn.installation_id == 789012
        assert conn.private_key == "test_key"

    def test_from_env_with_custom_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からカスタムベースURLを読み取り"""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("GITHUB_API_URL", "https://github.example.com/api/v3")

        conn = GitHubConnection.from_env()

        assert conn.base_url == "https://github.example.com/api/v3"

    def test_validate_with_token(self):
        """Token認証の検証"""
        conn = GitHubConnection(token="test_token")
        assert conn.validate() is True

    def test_validate_with_app(self):
        """GitHub Apps認証の検証"""
        conn = GitHubConnection(
            app_id=123456,
            installation_id=789012,
            private_key="test_key",
        )
        assert conn.validate() is True

    def test_validate_with_app_and_key_path(self):
        """GitHub Apps認証（鍵ファイルパス）の検証"""
        conn = GitHubConnection(
            app_id=123456,
            installation_id=789012,
            private_key_path="/path/to/key.pem",
        )
        assert conn.validate() is True

    def test_validate_invalid(self):
        """認証情報なしは無効"""
        conn = GitHubConnection()
        assert conn.validate() is False

    def test_validate_app_incomplete(self):
        """GitHub Apps認証が不完全な場合は無効"""
        conn = GitHubConnection(app_id=123456)  # installation_idとprivate_keyがない
        assert conn.validate() is False

    def test_to_dict(self):
        """辞書形式への変換（シークレット除外）"""
        conn = GitHubConnection(token="secret_token")
        result = conn.to_dict()

        assert result["type"] == "github"
        assert result["auth_type"] == "token"
        assert result["has_token"] is True
        assert "token" not in result  # シークレットは含まれない


class TestGitLabConnection:
    """GitLabConnection のテスト"""

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数から設定を生成"""
        monkeypatch.setenv("GITLAB_TOKEN", "test_gitlab_token")
        monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")

        conn = GitLabConnection.from_env()

        assert conn.token == "test_gitlab_token"
        assert conn.base_url == "https://gitlab.example.com"

    def test_validate(self):
        """検証"""
        conn = GitLabConnection(token="test_token")
        assert conn.validate() is True

        conn_invalid = GitLabConnection()
        assert conn_invalid.validate() is False

    def test_to_dict(self):
        """辞書形式への変換"""
        conn = GitLabConnection(token="secret_token")
        result = conn.to_dict()

        assert result["type"] == "gitlab"
        assert result["has_token"] is True
        assert "token" not in result


class TestCircleCIConnection:
    """CircleCIConnection のテスト"""

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数から設定を生成"""
        monkeypatch.setenv("CIRCLECI_TOKEN", "test_circleci_token")

        conn = CircleCIConnection.from_env()

        assert conn.api_token == "test_circleci_token"
        assert conn.base_url == "https://circleci.com/api"

    def test_validate(self):
        """検証"""
        conn = CircleCIConnection(api_token="test_token")
        assert conn.validate() is True

        conn_invalid = CircleCIConnection()
        assert conn_invalid.validate() is False


class TestDatabaseConnection:
    """DatabaseConnection のテスト"""

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数から設定を生成"""
        monkeypatch.setenv("DATABASE_HOST", "db.example.com")
        monkeypatch.setenv("DATABASE_PORT", "5433")
        monkeypatch.setenv("DATABASE_NAME", "test_db")
        monkeypatch.setenv("DATABASE_USER", "test_user")
        monkeypatch.setenv("DATABASE_PASSWORD", "test_pass")

        conn = DatabaseConnection.from_env()

        assert conn.host == "db.example.com"
        assert conn.port == 5433
        assert conn.database == "test_db"
        assert conn.user == "test_user"
        assert conn.password == "test_pass"

    def test_url_property(self):
        """SQLAlchemy URL生成"""
        conn = DatabaseConnection(
            host="localhost",
            port=5432,
            database="nagare",
            user="nagare_user",
            password="secret",
        )

        expected = "postgresql://nagare_user:secret@localhost:5432/nagare"
        assert conn.url == expected

    def test_validate(self):
        """検証"""
        conn = DatabaseConnection(
            host="localhost",
            database="nagare",
            user="nagare_user",
        )
        assert conn.validate() is True

        # hostがない場合は無効
        conn_invalid = DatabaseConnection(database="nagare", user="nagare_user")
        conn_invalid.host = ""
        assert conn_invalid.validate() is False

    def test_to_dict(self):
        """辞書形式への変換（パスワード除外）"""
        conn = DatabaseConnection(
            host="localhost",
            database="nagare",
            user="nagare_user",
            password="secret",
        )
        result = conn.to_dict()

        assert result["type"] == "database"
        assert result["host"] == "localhost"
        assert result["database"] == "nagare"
        assert result["user"] == "nagare_user"
        assert result["has_password"] is True
        assert "password" not in result


class TestConnectionRegistry:
    """ConnectionRegistry のテスト"""

    def test_get_github_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からGitHub接続を取得"""
        ConnectionRegistry.reset_all()
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")

        conn = ConnectionRegistry.get_github()

        assert conn.token == "test_token"

    def test_set_github(self):
        """GitHub接続を手動設定"""
        ConnectionRegistry.reset_all()
        custom_conn = GitHubConnection(token="custom_token")

        ConnectionRegistry.set_github(custom_conn)
        conn = ConnectionRegistry.get_github()

        assert conn.token == "custom_token"

    def test_get_database_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からDatabase接続を取得"""
        ConnectionRegistry.reset_all()
        monkeypatch.setenv("DATABASE_HOST", "localhost")
        monkeypatch.setenv("DATABASE_NAME", "nagare")
        monkeypatch.setenv("DATABASE_USER", "test_user")

        conn = ConnectionRegistry.get_database()

        assert conn.host == "localhost"
        assert conn.database == "nagare"
        assert conn.user == "test_user"

    def test_set_database(self):
        """Database接続を手動設定"""
        ConnectionRegistry.reset_all()
        custom_conn = DatabaseConnection(
            host="custom.example.com",
            database="custom_db",
            user="custom_user",
        )

        ConnectionRegistry.set_database(custom_conn)
        conn = ConnectionRegistry.get_database()

        assert conn.host == "custom.example.com"

    def test_reset_all(self, monkeypatch: pytest.MonkeyPatch):
        """全Connectionをリセット"""
        # セットアップ
        monkeypatch.setenv("GITHUB_TOKEN", "token1")
        ConnectionRegistry.reset_all()
        conn1 = ConnectionRegistry.get_github()
        assert conn1.token == "token1"

        # リセット後、環境変数が変わっても再読み込みされる
        monkeypatch.setenv("GITHUB_TOKEN", "token2")
        ConnectionRegistry.reset_all()
        conn2 = ConnectionRegistry.get_github()
        assert conn2.token == "token2"

    def test_validate_all(self, monkeypatch: pytest.MonkeyPatch):
        """全Connectionの検証"""
        ConnectionRegistry.reset_all()
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("DATABASE_HOST", "localhost")
        monkeypatch.setenv("DATABASE_NAME", "nagare")
        monkeypatch.setenv("DATABASE_USER", "test_user")

        result = ConnectionRegistry.validate_all()

        assert result["github"] is True
        assert result["gitlab"] is False  # トークンなし
        assert result["circleci"] is False  # トークンなし
        assert result["database"] is True

    def test_from_file(self, tmp_path: Path):
        """設定ファイルから読み込み"""
        ConnectionRegistry.reset_all()

        # YAMLファイルを作成
        config_file = tmp_path / "connections.yml"
        config_file.write_text(
            """
github:
  token: file_token
  base_url: https://github.example.com/api/v3

database:
  host: file.example.com
  port: 5433
  database: file_db
  user: file_user
  password: file_pass
"""
        )

        # ファイルから読み込み
        ConnectionRegistry.from_file(config_file)

        # GitHubの検証
        github_conn = ConnectionRegistry.get_github()
        assert github_conn.token == "file_token"
        assert github_conn.base_url == "https://github.example.com/api/v3"

        # Databaseの検証
        db_conn = ConnectionRegistry.get_database()
        assert db_conn.host == "file.example.com"
        assert db_conn.port == 5433
        assert db_conn.database == "file_db"

    def test_from_file_not_found(self):
        """存在しないファイルはエラー"""
        with pytest.raises(FileNotFoundError):
            ConnectionRegistry.from_file("/path/to/nonexistent.yml")

    def test_from_file_empty(self, tmp_path: Path):
        """空のファイルはエラーにしない"""
        ConnectionRegistry.reset_all()
        config_file = tmp_path / "empty.yml"
        config_file.write_text("")

        # エラーにならない
        ConnectionRegistry.from_file(config_file)
