"""Streamlit管理画面の統合テスト

admin_db.pyの主要な関数をテストする。
Streamlit特有のUIテストは含まれないが、ビジネスロジックを検証する。
"""

from unittest.mock import MagicMock, patch

import pytest


class TestAdminAppFunctions:
    """admin_appの主要関数のテスト"""

    @patch("nagare.admin_db.create_engine")
    @patch("nagare.admin_db.ConnectionRegistry.get_database")
    def test_get_database_engine(
        self, mock_get_database: MagicMock, mock_create_engine: MagicMock
    ) -> None:
        """データベースエンジンの作成"""
        from nagare.admin_db import get_database_engine

        # Streamlitのキャッシュをクリア
        get_database_engine.clear()

        # DatabaseConnectionをモック
        mock_db_conn = MagicMock()
        mock_db_conn.url = "postgresql://testuser:testpass@testhost:5432/testdb"
        mock_get_database.return_value = mock_db_conn

        get_database_engine()

        # create_engineが正しいURLで呼ばれたか確認
        mock_create_engine.assert_called_once_with(
            "postgresql://testuser:testpass@testhost:5432/testdb", pool_pre_ping=True
        )

    @patch("nagare.admin_db.GitHubClient")
    def test_get_github_client_success(self, mock_github_client: MagicMock) -> None:
        """GitHubクライアントの作成（成功）"""
        from nagare.admin_db import get_github_client

        # Streamlitのキャッシュをクリア
        get_github_client.clear()

        # モックの設定
        mock_instance = MagicMock()
        mock_github_client.return_value = mock_instance

        client = get_github_client()

        assert client is not None
        mock_github_client.assert_called_once()

    @patch("nagare.admin_db.GitHubClient")
    def test_get_github_client_failure(self, mock_github_client: MagicMock) -> None:
        """GitHubクライアントの作成（失敗）"""
        from nagare.admin_db import get_github_client

        # Streamlitのキャッシュをクリア
        get_github_client.clear()

        # エラーを発生させる
        mock_github_client.side_effect = ValueError("GitHub Token not configured")

        # Streamlitのエラー表示をモック
        with patch("nagare.admin_db.st") as mock_st:
            client = get_github_client()

            assert client is None
            mock_st.error.assert_called()
            mock_st.info.assert_called()

    @patch("nagare.admin_db.get_github_client")
    def test_fetch_github_repositories_organization(
        self, mock_get_client: MagicMock
    ) -> None:
        """組織リポジトリの取得"""
        from nagare.admin_db import fetch_github_repositories

        # モッククライアントの設定
        mock_client = MagicMock()
        mock_client.get_organization_repositories.return_value = {
            "repos": [{"full_name": "org/repo1"}],
            "page": 1,
            "per_page": 30,
            "has_next": False,
        }
        mock_get_client.return_value = mock_client

        result = fetch_github_repositories("organization", "test-org", page=1, per_page=30)

        assert result is not None
        assert "repos" in result
        assert len(result["repos"]) == 1
        mock_client.get_organization_repositories.assert_called_once_with(
            "test-org", page=1, per_page=30
        )

    @patch("nagare.admin_db.get_github_client")
    def test_fetch_github_repositories_user(self, mock_get_client: MagicMock) -> None:
        """ユーザーリポジトリの取得"""
        from nagare.admin_db import fetch_github_repositories

        mock_client = MagicMock()
        mock_client.get_user_repositories.return_value = {
            "repos": [{"full_name": "user/repo1"}],
            "page": 1,
            "per_page": 30,
            "has_next": False,
        }
        mock_get_client.return_value = mock_client

        result = fetch_github_repositories("user", "test-user", page=1, per_page=30)

        assert result is not None
        assert "repos" in result
        mock_client.get_user_repositories.assert_called_once()

    @patch("nagare.admin_db.get_github_client")
    def test_fetch_github_repositories_search(self, mock_get_client: MagicMock) -> None:
        """キーワード検索"""
        from nagare.admin_db import fetch_github_repositories

        mock_client = MagicMock()
        mock_client.search_repositories.return_value = {
            "repos": [{"full_name": "search/result"}],
            "page": 1,
            "per_page": 30,
            "has_next": True,
            "total_count": 100,
        }
        mock_get_client.return_value = mock_client

        result = fetch_github_repositories("search", "python", page=1, per_page=30)

        assert result is not None
        assert result["total_count"] == 100
        mock_client.search_repositories.assert_called_once()

    @patch("nagare.admin_db.get_github_client")
    def test_fetch_github_repositories_error(self, mock_get_client: MagicMock) -> None:
        """GitHub APIエラーのハンドリング"""
        from github import GithubException

        from nagare.admin_db import fetch_github_repositories

        mock_client = MagicMock()
        mock_client.get_organization_repositories.side_effect = GithubException(
            404, "Not Found", {}
        )
        mock_get_client.return_value = mock_client

        with patch("nagare.admin_db.st") as mock_st:
            result = fetch_github_repositories("organization", "notfound", page=1, per_page=30)

            assert result is None
            mock_st.error.assert_called()

    @patch("nagare.admin_db.get_database_engine")
    def test_get_repositories(self, mock_get_engine: MagicMock) -> None:
        """リポジトリ一覧の取得"""
        from nagare.admin_db import get_repositories

        # モックエンジンとコネクションの設定
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()

        # モックデータ
        mock_rows = [
            (1, "owner/repo1", "github_actions", True, "2024-01-01", "2024-01-02"),
            (2, "owner/repo2", "github_actions", False, "2024-01-01", "2024-01-02"),
        ]
        mock_result.fetchall.return_value = mock_rows

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        df = get_repositories()

        assert not df.empty
        assert len(df) == 2
        assert list(df.columns) == [
            "ID",
            "リポジトリ名",
            "ソース",
            "有効",
            "作成日時",
            "更新日時",
        ]

    @patch("nagare.admin_db.get_database_engine")
    def test_add_repository_new(self, mock_get_engine: MagicMock) -> None:
        """新規リポジトリの追加"""
        from nagare.admin_db import add_repository

        mock_engine = MagicMock()
        mock_conn = MagicMock()

        # 既存チェック（無し）
        mock_existing_result = MagicMock()
        mock_existing_result.fetchone.return_value = None

        # 新規追加
        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = [1]  # 新しいID

        mock_conn.execute.side_effect = [mock_existing_result, mock_insert_result]
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        success, message = add_repository("owner/repo", "github_actions")

        assert success is True
        assert "追加しました" in message
        assert "ID: 1" in message

    @patch("nagare.admin_db.get_database_engine")
    def test_add_repository_existing_active(self, mock_get_engine: MagicMock) -> None:
        """既に有効なリポジトリの追加（失敗）"""
        from nagare.admin_db import add_repository

        mock_engine = MagicMock()
        mock_conn = MagicMock()

        # 既存チェック（有効）
        mock_existing_result = MagicMock()
        mock_existing = MagicMock()
        mock_existing.active = True
        mock_existing_result.fetchone.return_value = mock_existing

        mock_conn.execute.return_value = mock_existing_result
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        success, message = add_repository("owner/repo", "github_actions")

        assert success is False
        assert "既に登録されています" in message

    @patch("nagare.admin_db.get_database_engine")
    def test_add_repository_reactivate(self, mock_get_engine: MagicMock) -> None:
        """無効なリポジトリの再有効化"""
        from nagare.admin_db import add_repository

        mock_engine = MagicMock()
        mock_conn = MagicMock()

        # 既存チェック（無効）
        mock_existing_result = MagicMock()
        mock_existing = MagicMock()
        mock_existing.active = False
        mock_existing.id = 5
        mock_existing_result.fetchone.return_value = mock_existing

        # 再有効化
        mock_update_result = MagicMock()

        mock_conn.execute.side_effect = [mock_existing_result, mock_update_result]
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        success, message = add_repository("owner/repo", "github_actions")

        assert success is True
        assert "有効化しました" in message
        assert "ID: 5" in message

    @patch("nagare.admin_db.get_database_engine")
    def test_toggle_repository_enable(self, mock_get_engine: MagicMock) -> None:
        """リポジトリの有効化"""
        from nagare.admin_db import toggle_repository

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None

        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        success, message = toggle_repository(1, True)

        assert success is True
        assert "有効化しました" in message

    @patch("nagare.admin_db.get_database_engine")
    def test_toggle_repository_disable(self, mock_get_engine: MagicMock) -> None:
        """リポジトリの無効化"""
        from nagare.admin_db import toggle_repository

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None

        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        success, message = toggle_repository(1, False)

        assert success is True
        assert "無効化しました" in message

    @patch("nagare.admin_db.get_database_engine")
    def test_get_statistics(self, mock_get_engine: MagicMock) -> None:
        """統計情報の取得"""
        from nagare.admin_db import get_statistics

        mock_engine = MagicMock()
        mock_conn = MagicMock()

        # リポジトリ統計
        mock_repo_result = MagicMock()
        mock_repo_stats = MagicMock()
        mock_repo_stats.total = 10
        mock_repo_stats.active_count = 8
        mock_repo_stats.inactive_count = 2
        mock_repo_result.fetchone.return_value = mock_repo_stats

        # パイプライン統計
        mock_pipeline_result = MagicMock()
        mock_pipeline_stats = MagicMock()
        mock_pipeline_stats.total_runs = 100
        mock_pipeline_stats.success_count = 85
        mock_pipeline_stats.failure_count = 15
        mock_pipeline_stats.avg_duration = 60000.0  # 60秒
        mock_pipeline_result.fetchone.return_value = mock_pipeline_stats

        mock_conn.execute.side_effect = [mock_repo_result, mock_pipeline_result]
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        stats = get_statistics()

        assert stats["repositories"]["total"] == 10
        assert stats["repositories"]["active"] == 8
        assert stats["pipeline_runs"]["total"] == 100
        assert stats["pipeline_runs"]["success"] == 85
        assert stats["pipeline_runs"]["avg_duration_sec"] == 60.0

    @patch("nagare.admin_db.get_database_engine")
    def test_get_recent_pipeline_runs(self, mock_get_engine: MagicMock) -> None:
        """最近のパイプライン実行履歴の取得"""
        from nagare.admin_db import get_recent_pipeline_runs

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()

        mock_rows = [
            (1, "owner/repo", "CI", "success", "2024-01-01 10:00:00", 30000),
            (2, "owner/repo", "Deploy", "failure", "2024-01-01 09:00:00", 45000),
        ]
        mock_result.fetchall.return_value = mock_rows

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        df = get_recent_pipeline_runs(10)

        assert not df.empty
        assert len(df) == 2
        assert list(df.columns) == [
            "ID",
            "リポジトリ",
            "パイプライン名",
            "ステータス",
            "開始時刻",
            "実行時間(ms)",
        ]


class TestAdminAppEdgeCases:
    """エッジケースのテスト"""

    @patch("nagare.admin_db.get_database_engine")
    def test_get_repositories_empty(self, mock_get_engine: MagicMock) -> None:
        """リポジトリが0件の場合"""
        from nagare.admin_db import get_repositories

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        df = get_repositories()

        assert df.empty
        assert list(df.columns) == [
            "ID",
            "リポジトリ名",
            "ソース",
            "有効",
            "作成日時",
            "更新日時",
        ]

    @patch("nagare.admin_db.get_database_engine")
    def test_get_statistics_no_data(self, mock_get_engine: MagicMock) -> None:
        """統計データが無い場合"""
        from nagare.admin_db import get_statistics

        mock_engine = MagicMock()
        mock_conn = MagicMock()

        # データ無し
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        stats = get_statistics()

        # デフォルト値が返されることを確認
        assert stats["repositories"]["total"] == 0
        assert stats["pipeline_runs"]["total"] == 0
        assert stats["pipeline_runs"]["avg_duration_sec"] == 0

    @patch("nagare.admin_db.get_github_client")
    def test_fetch_github_repositories_no_client(
        self, mock_get_client: MagicMock
    ) -> None:
        """GitHubクライアントが無い場合"""
        from nagare.admin_db import fetch_github_repositories

        mock_get_client.return_value = None

        result = fetch_github_repositories("organization", "test", page=1, per_page=30)

        assert result is None

    @patch("nagare.admin_db.get_database_engine")
    def test_add_repository_invalid_format(self, mock_get_engine: MagicMock) -> None:
        """不正なリポジトリ名の処理"""
        from nagare.admin_db import add_repository

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        # GitHub Actionsの場合は入力検証が行われ、不正な形式はValueErrorが発生する
        # スラッシュが無いリポジトリ名
        with pytest.raises(ValueError) as exc_info:
            add_repository("invalid_repo_name", "github_actions")

        assert "owner/repo" in str(exc_info.value)

        # Bitriseの場合は検証が行われないため、処理は継続される
        mock_conn = MagicMock()
        mock_existing_result = MagicMock()
        mock_existing_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = [1]

        mock_conn.execute.side_effect = [mock_existing_result, mock_insert_result]
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        success, message = add_repository("invalid_repo_name", "bitrise")

        assert success is True
