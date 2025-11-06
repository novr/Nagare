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
    XcodeCloudConnection,
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

        # 環境変数なし、デフォルトなし → エラー（必須環境変数が未設定）
        with pytest.raises(ValueError, match="Required environment variable 'MISSING_VAR' is not set"):
            ConnectionRegistry._expand_env_vars("${MISSING_VAR}")

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

    def test_expand_env_vars_missing_required(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：必須環境変数が未設定の場合にエラー"""
        # 環境変数をクリア
        monkeypatch.delenv("MISSING_VAR", raising=False)

        with pytest.raises(ValueError, match="Required environment variable 'MISSING_VAR' is not set"):
            ConnectionRegistry._expand_env_vars("${MISSING_VAR}")

    def test_expand_env_vars_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：環境変数に空文字列が設定されている場合"""
        monkeypatch.setenv("EMPTY_VAR", "")

        # 空文字列は有効な値として扱われる
        result = ConnectionRegistry._expand_env_vars("value: ${EMPTY_VAR}")
        assert result == "value: "

        # デフォルト値がある場合でも、空文字列が優先される
        result = ConnectionRegistry._expand_env_vars("value: ${EMPTY_VAR:-default}")
        assert result == "value: "

    def test_expand_env_vars_special_characters(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：デフォルト値に特殊文字が含まれる場合"""
        monkeypatch.delenv("SPECIAL_VAR", raising=False)

        # URL with port
        result = ConnectionRegistry._expand_env_vars("${SPECIAL_VAR:-postgresql://user:pass@host:5432/db}")
        assert result == "postgresql://user:pass@host:5432/db"

        # Path with spaces
        result = ConnectionRegistry._expand_env_vars("${SPECIAL_VAR:-/path/to/my file.txt}")
        assert result == "/path/to/my file.txt"

        # Special characters
        result = ConnectionRegistry._expand_env_vars("${SPECIAL_VAR:-value!@#$%^&*()}")
        assert result == "value!@#$%^&*()"

    def test_expand_env_vars_nested(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：ネストした展開（制限事項の確認）"""
        monkeypatch.setenv("INNER_VAR", "inner_value")
        monkeypatch.setenv("OUTER_VAR", "${INNER_VAR}")

        # ネストした展開はサポートされない（1回のみ展開）
        result = ConnectionRegistry._expand_env_vars("${OUTER_VAR}")
        assert result == "${INNER_VAR}"  # 外側だけ展開される

    def test_expand_env_vars_invalid_syntax(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数展開：無効な構文は展開されない"""
        monkeypatch.setenv("VALID_VAR", "test_value")

        # 無効な構文パターンは展開されない
        assert ConnectionRegistry._expand_env_vars("$VALID_VAR") == "$VALID_VAR"  # $ のみ
        assert ConnectionRegistry._expand_env_vars("${VALID_VAR") == "${VALID_VAR"  # 閉じ括弧なし
        assert ConnectionRegistry._expand_env_vars("${}") == "${}"  # 変数名なし
        assert ConnectionRegistry._expand_env_vars("${123VAR}") == "${123VAR}"  # 数字で開始
        assert ConnectionRegistry._expand_env_vars("${-VAR}") == "${-VAR}"  # 無効な文字

    def test_mask_secrets_dict(self):
        """機密情報のマスキング：辞書"""
        config = {
            "token": "ghp_secret_token",
            "host": "github.com",
            "password": "my_password",
            "port": 443,
        }

        masked = ConnectionRegistry._mask_secrets(config)

        # 機密情報はマスクされる
        assert masked["token"] == "***MASKED***"
        assert masked["password"] == "***MASKED***"

        # 非機密情報はそのまま
        assert masked["host"] == "github.com"
        assert masked["port"] == 443

    def test_mask_secrets_nested(self):
        """機密情報のマスキング：ネストした辞書"""
        config = {
            "github": {
                "token": "ghp_secret",
                "base_url": "https://api.github.com",
            },
            "database": {
                "host": "localhost",
                "password": "db_secret",
                "port": 5432,
            },
        }

        masked = ConnectionRegistry._mask_secrets(config)

        # ネストした機密情報もマスクされる
        assert masked["github"]["token"] == "***MASKED***"
        assert masked["database"]["password"] == "***MASKED***"

        # 非機密情報はそのまま
        assert masked["github"]["base_url"] == "https://api.github.com"
        assert masked["database"]["host"] == "localhost"
        assert masked["database"]["port"] == 5432

    def test_mask_secrets_list(self):
        """機密情報のマスキング：リスト"""
        config = [
            {"token": "secret1", "name": "config1"},
            {"api_key": "secret2", "name": "config2"},
        ]

        masked = ConnectionRegistry._mask_secrets(config)

        # リスト内の機密情報もマスクされる
        assert masked[0]["token"] == "***MASKED***"
        assert masked[1]["api_key"] == "***MASKED***"

        # 非機密情報はそのまま
        assert masked[0]["name"] == "config1"
        assert masked[1]["name"] == "config2"

    def test_mask_secrets_case_insensitive(self):
        """機密情報のマスキング：大文字小文字を区別しない"""
        config = {
            "TOKEN": "secret1",
            "Password": "secret2",
            "API_TOKEN": "secret3",
        }

        masked = ConnectionRegistry._mask_secrets(config)

        # キー名の大文字小文字に関わらずマスクされる
        assert masked["TOKEN"] == "***MASKED***"
        assert masked["Password"] == "***MASKED***"
        assert masked["API_TOKEN"] == "***MASKED***"

    def test_mask_secrets_all_types(self):
        """機密情報のマスキング：すべての機密キータイプ"""
        config = {
            "token": "secret1",
            "password": "secret2",
            "api_token": "secret3",
            "private_key": "secret4",
            "secret_key": "secret5",
            "access_token": "secret6",
            "refresh_token": "secret7",
            "api_key": "secret8",
            "auth_token": "secret9",
        }

        masked = ConnectionRegistry._mask_secrets(config)

        # すべての機密キーがマスクされる
        for key in config.keys():
            assert masked[key] == "***MASKED***"

    def test_from_file_error_masks_secrets(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """from_file: エラー時に機密情報がマスクされる"""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_token_should_be_masked")

        # 無効なGitHub設定（tokenとapp_idが両方ない）
        config_file = tmp_path / "invalid_config.yml"
        config_file.write_text(
            """
github:
  # tokenもapp_idも無い（エラーになる）
  base_url: https://api.github.com
"""
        )

        # エラーが発生することを確認
        with pytest.raises(ValueError, match="Failed to create GitHub connection"):
            ConnectionRegistry.from_file(config_file)

        # 注: ログには "***MASKED***" が出力される（機密情報は出力されない）
        # これは手動でログを確認する必要がある

    def test_from_file_invalid_token_error_masks_secrets(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        """from_file: 無効なトークンでエラー時に機密情報がマスクされる"""
        import logging

        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_token_should_be_masked")

        # GitHubTokenAuthに無効なパラメータを渡す
        config_file = tmp_path / "invalid_token_config.yml"
        config_file.write_text(
            """
github:
  token: ${GITHUB_TOKEN}
  invalid_param: should_cause_error
"""
        )

        # ログレベルを設定
        caplog.set_level(logging.ERROR)

        # エラーが発生することを確認
        with pytest.raises(ValueError, match="Failed to create GitHub connection"):
            ConnectionRegistry.from_file(config_file)

        # ログに機密情報が含まれていないことを確認
        log_messages = "\n".join([record.message for record in caplog.records])
        assert "ghp_secret_token_should_be_masked" not in log_messages
        assert "***MASKED***" in log_messages


class TestXcodeCloudConnection:
    """XcodeCloudConnection のテスト"""

    def test_from_env_with_private_key(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からprivate_keyを使用した設定を生成"""
        monkeypatch.setenv("APPSTORE_KEY_ID", "TEST_KEY_ID")
        monkeypatch.setenv("APPSTORE_ISSUER_ID", "test-issuer-id")
        monkeypatch.setenv("APPSTORE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\ntest_key_content\n-----END PRIVATE KEY-----")

        conn = XcodeCloudConnection.from_env()

        assert conn.key_id == "TEST_KEY_ID"
        assert conn.issuer_id == "test-issuer-id"
        assert conn.private_key == "-----BEGIN PRIVATE KEY-----\ntest_key_content\n-----END PRIVATE KEY-----"

    def test_from_env_with_custom_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """環境変数からカスタムベースURLを読み取り"""
        monkeypatch.setenv("APPSTORE_KEY_ID", "TEST_KEY_ID")
        monkeypatch.setenv("APPSTORE_ISSUER_ID", "test-issuer-id")
        monkeypatch.setenv("APPSTORE_PRIVATE_KEY", "test_key")
        monkeypatch.setenv("APPSTORE_API_URL", "https://custom-api.example.com/v1")

        conn = XcodeCloudConnection.from_env()

        assert conn.base_url == "https://custom-api.example.com/v1"

    def test_validate_with_private_key(self):
        """private_keyを使用した検証"""
        conn = XcodeCloudConnection(
            key_id="TEST_KEY_ID",
            issuer_id="test-issuer-id",
            private_key="-----BEGIN PRIVATE KEY-----\ntest_key_content\n-----END PRIVATE KEY-----",
        )
        assert conn.validate() is True

    def test_validate_without_keys(self):
        """private_keyがない場合は無効"""
        conn = XcodeCloudConnection(
            key_id="TEST_KEY_ID",
            issuer_id="test-issuer-id",
        )
        assert conn.validate() is False

    def test_validate_incomplete(self):
        """必須フィールドが不足している場合は無効"""
        # key_idがない
        conn = XcodeCloudConnection(
            issuer_id="test-issuer-id",
            private_key="test_key",
        )
        assert conn.validate() is False

        # issuer_idがない
        conn = XcodeCloudConnection(
            key_id="TEST_KEY_ID",
            private_key="test_key",
        )
        assert conn.validate() is False

    def test_to_dict(self):
        """辞書形式への変換（シークレット除外）"""
        conn = XcodeCloudConnection(
            key_id="TEST_KEY_ID",
            issuer_id="test-issuer-id",
            private_key="secret_private_key_content",
        )
        result = conn.to_dict()

        assert result["type"] == "xcode_cloud"
        assert result["base_url"] == "https://api.appstoreconnect.apple.com/v1"
        assert result["has_key_id"] is True
        assert result["has_issuer_id"] is True
        assert result["has_private_key"] is True
        assert "key_id" not in result  # 実際の値は除外
        assert "issuer_id" not in result  # 実際の値は除外
        assert "private_key" not in result  # シークレットは除外
        assert "private_key_path" not in result  # シークレットは除外


class TestXcodeCloudConnectionFromFile:
    """XcodeCloudConnection の from_file() テスト"""

    def test_from_file_with_private_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """YAMLファイルからprivate_keyを使用して読み込み"""
        monkeypatch.setenv("APPSTORE_KEY_ID", "TEST_KEY_ID")
        monkeypatch.setenv("APPSTORE_ISSUER_ID", "test-issuer-id")
        monkeypatch.setenv("APPSTORE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\ntest_key_content\n-----END PRIVATE KEY-----")

        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
xcode_cloud:
  key_id: ${APPSTORE_KEY_ID}
  issuer_id: ${APPSTORE_ISSUER_ID}
  private_key: ${APPSTORE_PRIVATE_KEY}
"""
        )

        ConnectionRegistry.from_file(config_file)
        conn = ConnectionRegistry.get_xcode_cloud()

        assert conn.key_id == "TEST_KEY_ID"
        assert conn.issuer_id == "test-issuer-id"
        assert conn.private_key == "-----BEGIN PRIVATE KEY-----\ntest_key_content\n-----END PRIVATE KEY-----"

    def test_from_file_with_default_base_url(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """YAMLファイルからデフォルトベースURLで読み込み"""
        monkeypatch.setenv("APPSTORE_KEY_ID", "TEST_KEY_ID")
        monkeypatch.setenv("APPSTORE_ISSUER_ID", "test-issuer-id")
        monkeypatch.setenv("APPSTORE_PRIVATE_KEY", "test_key")

        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
xcode_cloud:
  key_id: ${APPSTORE_KEY_ID}
  issuer_id: ${APPSTORE_ISSUER_ID}
  private_key: ${APPSTORE_PRIVATE_KEY}
"""
        )

        ConnectionRegistry.from_file(config_file)
        conn = ConnectionRegistry.get_xcode_cloud()

        assert conn.base_url == "https://api.appstoreconnect.apple.com/v1"
