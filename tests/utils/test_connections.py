"""Connection管理のテスト

ConnectionRegistry, GitHubConnection, DatabaseConnectionなど
Connection層の動作を検証する。
"""

import os
from pathlib import Path

import pytest

from nagare.utils.connections import (
    BitriseConnection,
    CircleCIConnection,
    ConnectionRegistry,
    DatabaseConnection,
    GitHubAppAuth,
    GitHubConnection,
    GitHubTokenAuth,
    GitLabConnection,
)


class TestGitHubConnection:
    """GitHubConnection のテスト"""

    def test_from_env_with_token(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からToken認証の設定を生成"""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.delenv("GITHUB_APP_ID", raising=False)

        conn = GitHubConnection.from_env()

        assert isinstance(conn, GitHubTokenAuth)
        assert conn.token == "test_token"
        assert conn.base_url == "https://api.github.com"

    def test_from_env_with_app(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からGitHub Apps認証の設定を生成"""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_APP_ID", "123456")
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "789012")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test_key")

        conn = GitHubConnection.from_env()

        assert isinstance(conn, GitHubAppAuth)
        assert conn.app_id == 123456
        assert conn.installation_id == 789012
        assert conn.private_key == "test_key"

    def test_from_env_with_custom_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からカスタムベースURLを読み取り"""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("GITHUB_API_URL", "https://github.example.com/api/v3")

        conn = GitHubConnection.from_env()

        assert isinstance(conn, GitHubTokenAuth)
        assert conn.base_url == "https://github.example.com/api/v3"

    def test_validate_with_token(self):
        """Token認証の検証"""
        conn = GitHubTokenAuth(token="test_token")
        assert conn.validate() is True

    def test_validate_with_app(self):
        """GitHub Apps認証の検証"""
        conn = GitHubAppAuth(
            app_id=123456,
            installation_id=789012,
            private_key="test_key",
        )
        assert conn.validate() is True

    def test_validate_with_app_and_key_path(self):
        """GitHub Apps認証（鍵ファイルパス）の検証"""
        conn = GitHubAppAuth(
            app_id=123456,
            installation_id=789012,
            private_key_path="/path/to/key.pem",
        )
        assert conn.validate() is True

    def test_validate_invalid(self):
        """認証情報なしは無効"""
        conn = GitHubTokenAuth()  # tokenが空文字列
        assert conn.validate() is False

    def test_validate_app_incomplete(self):
        """GitHub Apps認証が不完全な場合は無効"""
        conn = GitHubAppAuth(app_id=123456)  # installation_idとprivate_keyがない
        assert conn.validate() is False

    def test_to_dict(self):
        """辞書形式への変換（シークレット除外）"""
        conn = GitHubTokenAuth(token="secret_token")
        result = conn.to_dict()

        assert result["type"] == "github_token"
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


class TestBitriseConnection:
    """BitriseConnection のテスト"""

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数から設定を生成"""
        monkeypatch.setenv("BITRISE_TOKEN", "test_bitrise_token")

        conn = BitriseConnection.from_env()

        assert conn.api_token == "test_bitrise_token"
        assert conn.base_url == "https://api.bitrise.io/v0.1"

    def test_from_env_with_custom_url(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からカスタムベースURLを読み取り"""
        monkeypatch.setenv("BITRISE_TOKEN", "test_token")
        monkeypatch.setenv("BITRISE_API_URL", "https://bitrise.example.com/v0.1")

        conn = BitriseConnection.from_env()

        assert conn.api_token == "test_token"
        assert conn.base_url == "https://bitrise.example.com/v0.1"

    def test_validate(self):
        """検証"""
        conn = BitriseConnection(api_token="test_token")
        assert conn.validate() is True

        conn_invalid = BitriseConnection()
        assert conn_invalid.validate() is False

    def test_to_dict(self):
        """辞書形式への変換（シークレット除外）"""
        conn = BitriseConnection(api_token="secret_token")
        result = conn.to_dict()

        assert result["type"] == "bitrise"
        assert result["base_url"] == "https://api.bitrise.io/v0.1"
        assert result["has_token"] is True
        assert "api_token" not in result  # シークレットは含まれない


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

        assert isinstance(conn, GitHubTokenAuth)
        assert conn.token == "test_token"

    def test_set_github(self):
        """GitHub接続を手動設定"""
        ConnectionRegistry.reset_all()
        custom_conn = GitHubTokenAuth(token="custom_token")

        ConnectionRegistry.set_github(custom_conn)
        conn = ConnectionRegistry.get_github()

        assert isinstance(conn, GitHubTokenAuth)
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

    def test_from_file_with_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """設定ファイルで環境変数展開"""
        ConnectionRegistry.reset_all()

        # 環境変数を設定
        monkeypatch.setenv("GITHUB_TOKEN", "env_token_value")
        monkeypatch.setenv("DB_HOST", "env.example.com")
        monkeypatch.setenv("DB_PORT", "5434")
        monkeypatch.setenv("DB_PASSWORD", "env_password")

        # YAMLファイルを作成（環境変数を使用）
        config_file = tmp_path / "connections.yml"
        config_file.write_text(
            """
github:
  token: ${GITHUB_TOKEN}

database:
  host: ${DB_HOST}
  port: ${DB_PORT}
  database: testdb
  user: testuser
  password: ${DB_PASSWORD}
"""
        )

        # ファイルから読み込み
        ConnectionRegistry.from_file(config_file)

        # GitHubの検証（環境変数から展開）
        github_conn = ConnectionRegistry.get_github()
        assert github_conn.token == "env_token_value"

        # Databaseの検証（環境変数から展開）
        db_conn = ConnectionRegistry.get_database()
        assert db_conn.host == "env.example.com"
        assert db_conn.port == "5434"
        assert db_conn.password == "env_password"

    def test_from_file_with_env_vars_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """設定ファイルで環境変数展開（デフォルト値）"""
        ConnectionRegistry.reset_all()

        # 一部の環境変数のみ設定（DB_HOSTは設定しない）
        monkeypatch.setenv("GITHUB_TOKEN", "token123")
        # DB_HOSTは設定しない → デフォルト値を使用

        # YAMLファイルを作成（デフォルト値付き環境変数）
        config_file = tmp_path / "connections.yml"
        config_file.write_text(
            """
github:
  token: ${GITHUB_TOKEN}

database:
  host: ${DB_HOST:-localhost}
  port: ${DB_PORT:-5432}
  database: testdb
  user: testuser
  password: ${DB_PASSWORD:-default_pass}
"""
        )

        # ファイルから読み込み
        ConnectionRegistry.from_file(config_file)

        # Databaseの検証（デフォルト値が使用される）
        db_conn = ConnectionRegistry.get_database()
        assert db_conn.host == "localhost"
        assert db_conn.port == "5432"
        assert db_conn.password == "default_pass"

    def test_expand_env_vars_string(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：文字列"""
        monkeypatch.setenv("TEST_VAR", "test_value")

        # 単純な展開
        result = ConnectionRegistry._expand_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_test_value_suffix"

        # デフォルト値付き（環境変数が存在する場合）
        result = ConnectionRegistry._expand_env_vars("${TEST_VAR:-default}")
        assert result == "test_value"

        # デフォルト値付き（環境変数が存在しない場合）
        result = ConnectionRegistry._expand_env_vars("${MISSING_VAR:-default}")
        assert result == "default"

        # 環境変数なし、デフォルトなし → 空文字
        result = ConnectionRegistry._expand_env_vars("${MISSING_VAR}")
        assert result == ""

    def test_expand_env_vars_dict(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：辞書"""
        monkeypatch.setenv("KEY1", "value1")
        monkeypatch.setenv("KEY2", "value2")

        data = {
            "field1": "${KEY1}",
            "field2": "${KEY2}",
            "field3": "static_value",
            "nested": {"inner": "${KEY1}_nested"},
        }

        result = ConnectionRegistry._expand_env_vars(data)

        assert result["field1"] == "value1"
        assert result["field2"] == "value2"
        assert result["field3"] == "static_value"
        assert result["nested"]["inner"] == "value1_nested"

    def test_expand_env_vars_list(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：リスト"""
        monkeypatch.setenv("ITEM", "expanded")

        data = ["${ITEM}", "static", {"key": "${ITEM}"}]

        result = ConnectionRegistry._expand_env_vars(data)

        assert result[0] == "expanded"
        assert result[1] == "static"
        assert result[2]["key"] == "expanded"

    def test_expand_env_vars_mixed_types(self):
        """環境変数展開：混在型（int, bool, None）"""
        data = {
            "port": 5432,
            "enabled": True,
            "optional": None,
            "mixed": ["text", 123, False, None],
        }

        result = ConnectionRegistry._expand_env_vars(data)

        # 数値、真偽値、Noneはそのまま
        assert result["port"] == 5432
        assert result["enabled"] is True
        assert result["optional"] is None
        assert result["mixed"] == ["text", 123, False, None]
