"""リポジトリデータのソースタイプ別アダプター

各CI/CDプラットフォームのリポジトリデータ構造をパースし、
統一されたインターフェースで扱えるようにする。

Design:
    Strategy パターンを使用し、ソースタイプごとに異なるパース処理を提供する。
    新しいソースタイプの追加は、パーサー関数を追加してマッピングに登録するだけ。

Usage:
    >>> from nagare.utils.repository_adapters import parse_repository_data
    >>> from nagare.constants import SourceType
    >>>
    >>> # データベースのrow（NamedTuple等）からパース
    >>> repo = parse_repository_data(SourceType.GITHUB_ACTIONS, row)
    >>> print(repo)  # {"owner": "org", "repo": "name"}
"""

import logging
from typing import Any

from nagare.constants import SourceType

logger = logging.getLogger(__name__)


def parse_github_repository(row: Any) -> dict[str, str]:
    """GitHub Actions形式のリポジトリデータをパースする

    Args:
        row: データベースのrow（id, repository_name, source, source_repository_id）

    Returns:
        GitHub用のリポジトリ情報: {"owner": str, "repo": str}

    Raises:
        ValueError: repository_nameが"owner/repo"形式でない場合
    """
    parts = row.repository_name.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid GitHub repository format: '{row.repository_name}'. "
            f"Expected 'owner/repo' format."
        )

    owner, repo = parts
    if not owner or not repo:
        raise ValueError(
            f"Invalid GitHub repository format: '{row.repository_name}'. "
            f"Both owner and repo must be non-empty."
        )

    return {"owner": owner, "repo": repo}


def parse_bitrise_repository(row: Any) -> dict[str, str]:
    """Bitrise形式のリポジトリデータをパースする

    Args:
        row: データベースのrow（id, repository_name, source, source_repository_id）

    Returns:
        Bitrise用のリポジトリ情報:
        {
            "id": int,
            "repository_name": str,
            "source_repository_id": str  # app_slug (UUID)
        }
    """
    return {
        "id": row.id,
        "repository_name": row.repository_name,
        "source_repository_id": row.source_repository_id,
    }


def parse_xcode_cloud_repository(row: Any) -> dict[str, str]:
    """Xcode Cloud形式のリポジトリデータをパースする

    Args:
        row: データベースのrow（id, repository_name, source, source_repository_id）

    Returns:
        Xcode Cloud用のリポジトリ情報:
        {
            "id": int,
            "repository_name": str,
            "source_repository_id": str  # App ID
        }
    """
    return {
        "id": row.id,
        "repository_name": row.repository_name,
        "source_repository_id": row.source_repository_id,
    }


# ソースタイプとパーサー関数のマッピング
REPOSITORY_PARSERS: dict[str, Any] = {
    SourceType.GITHUB_ACTIONS: parse_github_repository,
    SourceType.BITRISE: parse_bitrise_repository,
    SourceType.XCODE_CLOUD: parse_xcode_cloud_repository,
}


def get_repository_parser(source_type: str) -> Any:
    """ソースタイプに対応するパーサー関数を取得する

    Args:
        source_type: ソースタイプ（SourceType定数）

    Returns:
        パーサー関数。未知のソースタイプの場合はGitHubパーサー（デフォルト）

    Example:
        >>> parser = get_repository_parser(SourceType.BITRISE)
        >>> repo = parser(row)
    """
    parser = REPOSITORY_PARSERS.get(source_type)
    if parser is None:
        logger.warning(
            f"Unknown source type '{source_type}'. Using GitHub parser as default."
        )
        return parse_github_repository
    return parser


def parse_repository_data(source_type: str, row: Any) -> dict[str, str]:
    """リポジトリデータをソースタイプに応じてパースする

    Args:
        source_type: ソースタイプ（SourceType定数）
        row: データベースのrow（id, repository_name, source, source_repository_id）

    Returns:
        パースされたリポジトリ情報（ソースタイプによって構造が異なる）

    Raises:
        ValueError: パース処理で形式エラーが発生した場合

    Example:
        >>> repo = parse_repository_data(SourceType.GITHUB_ACTIONS, row)
        >>> print(repo)  # {"owner": "org", "repo": "name"}
    """
    parser = get_repository_parser(source_type)
    return parser(row)
