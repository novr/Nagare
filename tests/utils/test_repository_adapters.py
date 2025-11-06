"""リポジトリアダプターのテスト

各CI/CDプラットフォームのリポジトリデータパース処理をテストする。
"""

from unittest.mock import MagicMock

import pytest

from nagare.constants import SourceType
from nagare.utils.repository_adapters import (
    get_repository_parser,
    parse_bitrise_repository,
    parse_github_repository,
    parse_repository_data,
    parse_xcode_cloud_repository,
)


class TestGitHubParser:
    """GitHubリポジトリパーサーのテスト"""

    def test_parse_github_repository_valid(self) -> None:
        """正常なGitHub形式のパース"""
        row = MagicMock()
        row.repository_name = "owner/repo"

        result = parse_github_repository(row)

        assert result == {"owner": "owner", "repo": "repo"}

    def test_parse_github_repository_with_slash_in_repo_name(self) -> None:
        """リポジトリ名にスラッシュが含まれる場合（正常系）"""
        row = MagicMock()
        row.repository_name = "owner/repo-name/extra"

        result = parse_github_repository(row)

        # 最初のスラッシュで分割されることを確認
        assert result == {"owner": "owner", "repo": "repo-name/extra"}

    def test_parse_github_repository_invalid_no_slash(self) -> None:
        """スラッシュがない不正な形式"""
        row = MagicMock()
        row.repository_name = "invalid_repo"

        with pytest.raises(ValueError) as exc_info:
            parse_github_repository(row)

        assert "Invalid GitHub repository format" in str(exc_info.value)
        assert "invalid_repo" in str(exc_info.value)

    def test_parse_github_repository_invalid_empty_owner(self) -> None:
        """オーナーが空の不正な形式"""
        row = MagicMock()
        row.repository_name = "/repo"

        with pytest.raises(ValueError) as exc_info:
            parse_github_repository(row)

        assert "Both owner and repo must be non-empty" in str(exc_info.value)

    def test_parse_github_repository_invalid_empty_repo(self) -> None:
        """リポジトリ名が空の不正な形式"""
        row = MagicMock()
        row.repository_name = "owner/"

        with pytest.raises(ValueError) as exc_info:
            parse_github_repository(row)

        assert "Both owner and repo must be non-empty" in str(exc_info.value)


class TestBitriseParser:
    """Bitriseリポジトリパーサーのテスト"""

    def test_parse_bitrise_repository(self) -> None:
        """正常なBitrise形式のパース"""
        row = MagicMock()
        row.id = 123
        row.repository_name = "my-app"
        row.source_repository_id = "abc123-uuid"

        result = parse_bitrise_repository(row)

        assert result == {
            "id": 123,
            "repository_name": "my-app",
            "source_repository_id": "abc123-uuid",
        }


class TestXcodeCloudParser:
    """Xcode Cloudリポジトリパーサーのテスト"""

    def test_parse_xcode_cloud_repository(self) -> None:
        """正常なXcode Cloud形式のパース"""
        row = MagicMock()
        row.id = 456
        row.repository_name = "MyiOSApp"
        row.source_repository_id = "1234567890"

        result = parse_xcode_cloud_repository(row)

        assert result == {
            "id": 456,
            "repository_name": "MyiOSApp",
            "source_repository_id": "1234567890",
        }


class TestGetRepositoryParser:
    """パーサー取得関数のテスト"""

    def test_get_github_parser(self) -> None:
        """GitHub用パーサーの取得"""
        parser = get_repository_parser(SourceType.GITHUB_ACTIONS)

        assert parser == parse_github_repository

    def test_get_bitrise_parser(self) -> None:
        """Bitrise用パーサーの取得"""
        parser = get_repository_parser(SourceType.BITRISE)

        assert parser == parse_bitrise_repository

    def test_get_xcode_cloud_parser(self) -> None:
        """Xcode Cloud用パーサーの取得"""
        parser = get_repository_parser(SourceType.XCODE_CLOUD)

        assert parser == parse_xcode_cloud_repository

    def test_get_unknown_parser_returns_default(self) -> None:
        """未知のソースタイプはデフォルト（GitHub）パーサーを返す"""
        parser = get_repository_parser("unknown_source")

        assert parser == parse_github_repository


class TestParseRepositoryData:
    """統合パース関数のテスト"""

    def test_parse_github_data(self) -> None:
        """GitHubデータのパース"""
        row = MagicMock()
        row.repository_name = "owner/repo"

        result = parse_repository_data(SourceType.GITHUB_ACTIONS, row)

        assert result == {"owner": "owner", "repo": "repo"}

    def test_parse_bitrise_data(self) -> None:
        """Bitriseデータのパース"""
        row = MagicMock()
        row.id = 123
        row.repository_name = "my-app"
        row.source_repository_id = "abc123"

        result = parse_repository_data(SourceType.BITRISE, row)

        assert result == {
            "id": 123,
            "repository_name": "my-app",
            "source_repository_id": "abc123",
        }

    def test_parse_xcode_cloud_data(self) -> None:
        """Xcode Cloudデータのパース"""
        row = MagicMock()
        row.id = 456
        row.repository_name = "MyApp"
        row.source_repository_id = "app123"

        result = parse_repository_data(SourceType.XCODE_CLOUD, row)

        assert result == {
            "id": 456,
            "repository_name": "MyApp",
            "source_repository_id": "app123",
        }

    def test_parse_unknown_source_uses_github_parser(self) -> None:
        """未知のソースタイプはGitHubパーサーで処理"""
        row = MagicMock()
        row.repository_name = "owner/repo"

        result = parse_repository_data("unknown_source", row)

        assert result == {"owner": "owner", "repo": "repo"}

    def test_parse_invalid_data_raises_error(self) -> None:
        """不正なデータはValueErrorを発生させる"""
        row = MagicMock()
        row.repository_name = "invalid"  # スラッシュがない

        with pytest.raises(ValueError):
            parse_repository_data(SourceType.GITHUB_ACTIONS, row)
