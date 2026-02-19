"""Streamlit管理画面のデータベース操作

データベースアクセス、クライアント管理、リポジトリ/接続のCRUD操作を提供する。
"""

import logging
from typing import Any

import pandas as pd
import streamlit as st
from github import GithubException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL as SA_URL

from nagare.admin_helpers import (
    temporary_env_var,
    validate_connection_id,
    validate_repository_name,
)
from nagare.constants import Platform
from nagare.utils.bitrise_client import BitriseClient
from nagare.utils.connections import (
    BitriseConnection,
    ConnectionRegistry,
    XcodeCloudConnection,
)
from nagare.utils.github_client import GitHubClient
from nagare.utils.xcode_cloud_client import XcodeCloudClient

logger = logging.getLogger(__name__)


@st.cache_resource
def get_database_engine():
    """データベースエンジンを取得する

    ConnectionRegistryからデータベース接続情報を取得してエンジンを作成。
    Docker環境では connections.yml から、ローカルでは環境変数から接続情報を取得。
    """
    db_conn = ConnectionRegistry.get_database()
    return create_engine(db_conn.url, pool_pre_ping=True)


def get_available_github_connections():
    """利用可能なGitHub Connectionsを取得する"""
    engine = get_database_engine()
    query = text(
        """
        SELECT conn_id, description
        FROM connection
        WHERE conn_type = 'http' AND password IS NOT NULL AND password != ''
        ORDER BY conn_id
        """
    )
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()
        return [(row[0], row[1] or row[0]) for row in rows]


def get_all_cicd_connections():
    """利用可能な全てのCI/CD Connections（GitHub/Bitrise/Xcode Cloud）を取得する

    Returns:
        List[(conn_id, description, platform)] - Connection情報とプラットフォームのリスト
    """
    connections = []
    added_platforms = set()

    # connections.yml由来の接続を取得
    for conn_id, conn_obj in ConnectionRegistry.get_all_connections().items():
        platform = None
        description = getattr(conn_obj, "description", conn_id)

        # conn_typeを直接確認
        if hasattr(conn_obj, "get_platform"):
            platform_const = conn_obj.get_platform()
            # Platform定数から文字列に変換
            if platform_const == Platform.GITHUB:
                platform = "github"
            elif platform_const == Platform.BITRISE:
                platform = "bitrise"
            elif platform_const == Platform.XCODE_CLOUD:
                platform = "xcode_cloud"

        if platform:
            connections.append((conn_id, description, platform))
            added_platforms.add(platform)

    # デフォルト接続も追加（YAMLで明示的に定義されていない場合）
    if "github" not in added_platforms and ConnectionRegistry._github is not None:
        conn_id = "github"
        description = getattr(ConnectionRegistry._github, "description", "")
        connections.append((conn_id, description, "github"))
        added_platforms.add("github")

    if "bitrise" not in added_platforms and ConnectionRegistry._bitrise is not None:
        conn_id = "bitrise"
        description = getattr(ConnectionRegistry._bitrise, "description", "")
        connections.append((conn_id, description, "bitrise"))
        added_platforms.add("bitrise")

    if (
        "xcode_cloud" not in added_platforms
        and ConnectionRegistry._xcode_cloud is not None
    ):
        conn_id = "xcode_cloud"
        description = getattr(ConnectionRegistry._xcode_cloud, "description", "")
        connections.append((conn_id, description, "xcode_cloud"))
        added_platforms.add("xcode_cloud")

    # 読み込みエラーの接続も表示（トラブルシューティングのため）
    for conn_id, failed_info in ConnectionRegistry.get_failed_connections().items():
        platform = failed_info["platform"]

        if platform != "database" and platform not in added_platforms:
            description = f"⚠️ エラー: {failed_info['error'][:50]}..."
            connections.append((conn_id, description, platform))
            added_platforms.add(platform)

    # Airflow Connectionテーブルとの後方互換性維持
    existing_platforms = {platform for _, _, platform in connections}

    engine = get_database_engine()
    query = text(
        """
        SELECT conn_id, description
        FROM connection
        WHERE conn_type = 'http' AND password IS NOT NULL AND password != ''
        ORDER BY conn_id
        """
    )
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()
        for row in rows:
            conn_id = row[0]
            description = row[1] or conn_id

            # すでにConnectionRegistryから追加されている場合はスキップ
            if any(c[0] == conn_id for c in connections):
                continue

            # conn_idやdescriptionからプラットフォームを判定
            platform = detect_platform_from_connection(conn_id, description)
            if platform:
                # ConnectionRegistryに同じプラットフォームの接続が既に存在し、
                # かつ、このconn_idが*_defaultパターンの場合はスキップ
                if platform in existing_platforms and conn_id.endswith("_default"):
                    continue

                connections.append((conn_id, description, platform))

    return connections


def detect_platform_from_connection(conn_id: str, description: str) -> str | None:
    """ConnectionからプラットフォームGitHub/Bitrise/Xcode Cloud）を判定する

    Args:
        conn_id: Connection ID
        description: Connection description

    Returns:
        "github", "bitrise", "xcode_cloud", または None（判定不可）
    """
    conn_id_lower = conn_id.lower()
    description_lower = description.lower()

    # GitHub判定
    if "github" in conn_id_lower or "github" in description_lower:
        return "github"

    # Bitrise判定
    if "bitrise" in conn_id_lower or "bitrise" in description_lower:
        return "bitrise"

    # Xcode Cloud判定
    if (
        "xcode" in conn_id_lower
        or "xcode" in description_lower
        or "appstore" in conn_id_lower
    ):
        return "xcode_cloud"

    # デフォルトConnectionの判定（github_default, bitrise_default, xcode_cloud_default）
    if conn_id in ["github_default", "gh_default"]:
        return "github"
    if conn_id in ["bitrise_default", "br_default"]:
        return "bitrise"
    if conn_id in ["xcode_cloud_default", "xc_default", "appstore_default"]:
        return "xcode_cloud"

    # 判定不可
    return None


def get_github_client_from_connection(conn_id: str = None):
    """指定されたConnectionからGitHubクライアントを取得する

    Args:
        conn_id: Connection ID。Noneの場合はデフォルト動作

    Returns:
        GitHubClient or None
    """
    # Connection IDが指定された場合
    if conn_id:
        try:
            engine = get_database_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT password FROM connection WHERE conn_id = :conn_id"
                    ),
                    {"conn_id": conn_id},
                )
                row = result.fetchone()
                if row and row[0]:
                    with temporary_env_var("GITHUB_TOKEN", row[0]):
                        return GitHubClient()
        except Exception as e:
            st.error(f"Connection '{conn_id}' からの取得エラー: {e}")
            return None

    # Connection IDが指定されていない場合は、デフォルトの優先順位で取得
    # 1. github_default Connection
    try:
        engine = get_database_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT password FROM connection WHERE conn_id = :conn_id"
                ),
                {"conn_id": "github_default"},
            )
            row = result.fetchone()
            if row and row[0]:
                with temporary_env_var("GITHUB_TOKEN", row[0]):
                    return GitHubClient()
    except Exception:
        pass

    # 2. 環境変数から取得
    try:
        return GitHubClient()
    except ValueError as e:
        st.error(f"GitHub認証エラー: {e}")
        st.info(
            "GitHub API機能を使用するには、以下のいずれかを設定してください：\n"
            "- 🔌 Connections管理で GitHub Connection を登録（推奨）\n"
            "- 環境変数 `GITHUB_TOKEN` を設定"
        )
        return None


@st.cache_resource
def get_github_client():
    """GitHubクライアントを取得する（後方互換性のため残す）"""
    return get_github_client_from_connection()


def get_bitrise_client():
    """Bitriseクライアントを取得する"""
    try:
        bitrise_conn = ConnectionRegistry.get_bitrise()
        return BitriseClient(connection=bitrise_conn)
    except ValueError as e:
        st.error(f"Bitrise認証エラー: {e}")
        st.info(
            "Bitrise API機能を使用するには、connections.ymlでBitrise Connectionを設定してください"
        )
        return None


def get_bitrise_client_from_connection(conn_id: str = None):
    """指定されたConnectionからBitriseクライアントを取得する

    Args:
        conn_id: Connection ID。Noneの場合はデフォルト動作

    Returns:
        BitriseClient or None
    """
    # Connection IDが指定された場合
    if conn_id:
        try:
            engine = get_database_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT password, host FROM connection WHERE conn_id = :conn_id"
                    ),
                    {"conn_id": conn_id},
                )
                row = result.fetchone()
                if row and row[0]:
                    api_token = row[0]
                    base_url = row[1] or "https://api.bitrise.io/v0.1"

                    # スキームがない場合は追加
                    if base_url and not base_url.startswith(
                        ("http://", "https://")
                    ):
                        base_url = f"https://{base_url}"

                    bitrise_conn = BitriseConnection(
                        api_token=api_token, base_url=base_url
                    )
                    return BitriseClient(connection=bitrise_conn)
        except Exception as e:
            st.error(f"Connection '{conn_id}' からの取得エラー: {e}")
            return None

    # Connection IDが指定されていない場合は、デフォルト
    return get_bitrise_client()


def fetch_bitrise_apps():
    """Bitriseからアプリ一覧を取得する

    Returns:
        アプリのリスト、またはエラー時はNone
    """
    bitrise_client = get_bitrise_client()
    if not bitrise_client:
        return None

    try:
        apps = bitrise_client.get_apps(limit=50)
        return apps
    except Exception as e:
        st.error(f"Bitrise APIエラー: {e}")
        return None


def get_xcode_cloud_client():
    """Xcode Cloudクライアントを取得する"""
    try:
        xcode_cloud_conn = ConnectionRegistry.get_xcode_cloud()
        return XcodeCloudClient(connection=xcode_cloud_conn)
    except ValueError as e:
        st.error(f"Xcode Cloud認証エラー: {e}")
        st.info(
            "Xcode Cloud API機能を使用するには、connections.ymlでXcode Cloud Connectionを設定してください"
        )
        return None


def get_xcode_cloud_client_from_connection(conn_id: str = None):
    """指定されたConnectionからXcode Cloudクライアントを取得する

    Args:
        conn_id: Connection ID。Noneの場合はデフォルト動作

    Returns:
        XcodeCloudClient or None
    """
    # Connection IDが指定された場合
    if conn_id:
        try:
            engine = get_database_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT login, password, extra FROM connection WHERE conn_id = :conn_id"
                    ),
                    {"conn_id": conn_id},
                )
                row = result.fetchone()
                if row:
                    import json

                    extra = json.loads(row[2]) if row[2] else {}
                    key_id = row[0]  # login に key_id
                    issuer_id = row[1]  # password に issuer_id
                    private_key = extra.get("private_key")
                    private_key_path = extra.get("private_key_path")

                    xcode_cloud_conn = XcodeCloudConnection(
                        key_id=key_id,
                        issuer_id=issuer_id,
                        private_key=private_key,
                        private_key_path=private_key_path,
                    )
                    return XcodeCloudClient(connection=xcode_cloud_conn)
        except Exception as e:
            st.error(f"Connection '{conn_id}' からの取得エラー: {e}")
            return None

    # Connection IDが指定されていない場合は、デフォルト
    return get_xcode_cloud_client()


def fetch_xcode_cloud_apps():
    """Xcode Cloudからアプリ一覧を取得する

    Returns:
        アプリのリスト、またはエラー時はNone
    """
    xcode_cloud_client = get_xcode_cloud_client()
    if not xcode_cloud_client:
        return None

    try:
        apps = xcode_cloud_client.list_apps(limit=200)
        return apps
    except Exception as e:
        st.error(f"Xcode Cloud APIエラー: {e}")
        return None


def fetch_repositories_unified(
    platform: str, search_params: dict, page: int = 1, per_page: int = 30
):
    """統一されたインターフェースでリポジトリ/アプリを取得する（ページング対応）

    Args:
        platform: "github", "bitrise", または "xcode_cloud"
        search_params: プラットフォーム固有の検索パラメータ
            GitHub: {"search_type": str, "search_value": str, "conn_id": str}
            Bitrise: {"conn_id": str}
            Xcode Cloud: {"conn_id": str}
        page: ページ番号（1から開始）
        per_page: 1ページあたりの件数

    Returns:
        統一された形式の検索結果、またはエラー時はNone
        {
            "items": [
                {
                    "id": str,          # 一意識別子
                    "name": str,        # 表示名
                    "repo": str,        # リポジトリ/アプリ識別子
                    "updated_at": str,  # 更新日時（ISO 8601形式）
                    "url": str,         # URL
                    "description": str, # 説明
                    "platform": str,    # "github", "bitrise", or "xcode_cloud"
                    "metadata": dict    # その他のメタ情報
                }
            ],
            "page": int,
            "per_page": int,
            "has_next": bool,
            "total_count": int | None
        }
    """
    if platform == Platform.GITHUB:
        search_type = search_params.get("search_type")
        search_value = search_params.get("search_value")
        conn_id = search_params.get("conn_id")

        result = fetch_github_repositories(
            search_type, search_value, page, per_page, conn_id
        )
        if not result or "repos" not in result:
            return None

        # GitHubのデータを統一形式に変換
        items = []
        for repo in result["repos"]:
            # ownerの安全な取得
            owner = repo.get("owner", {})
            owner_login = (
                owner.get("login", "") if isinstance(owner, dict) else ""
            )

            items.append(
                {
                    "id": repo["full_name"],
                    "name": repo["name"],
                    "repo": repo["full_name"],
                    "updated_at": repo.get("updated_at", ""),
                    "url": repo.get("html_url", ""),
                    "description": repo.get("description", ""),
                    "platform": "github",
                    "metadata": {
                        "owner": owner_login,
                        "private": repo.get("private", False),
                        "language": repo.get("language"),
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                    },
                }
            )

        return {
            "items": items,
            "page": result["page"],
            "per_page": result["per_page"],
            "has_next": result["has_next"],
            "total_count": result.get("total_count"),
        }

    elif platform == Platform.BITRISE:
        conn_id = search_params.get("conn_id")
        bitrise_client = (
            get_bitrise_client_from_connection(conn_id)
            if conn_id
            else get_bitrise_client()
        )
        if not bitrise_client:
            return None

        try:
            # ページNを表示するために必要な最小件数: N*per_page + 1 (次ページ有無の判定用)
            limit = per_page * page + 1
            all_apps = bitrise_client.get_apps(limit=limit)

            # ページングのためのスライス
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_apps = all_apps[start_idx:end_idx]

            # Bitriseのデータを統一形式に変換
            items = []
            for app in page_apps:
                # リポジトリ名の構築（owner/repo形式）
                repo_name = None
                repo_owner = app.get("repo_owner")
                repo_slug = app.get("repo_slug")

                # 1. repo_ownerとrepo_slugから構築
                if repo_owner and repo_slug:
                    repo_name = f"{repo_owner}/{repo_slug}"
                # 2. repo_urlから抽出
                elif app.get("repo_url"):
                    # https://github.com/owner/repo.git → owner/repo
                    repo_url = app["repo_url"]
                    if "github.com/" in repo_url:
                        parts = (
                            repo_url.split("github.com/")[-1]
                            .replace(".git", "")
                            .strip("/")
                        )
                        if "/" in parts:
                            repo_name = parts
                    elif "bitbucket.org/" in repo_url:
                        parts = (
                            repo_url.split("bitbucket.org/")[-1]
                            .replace(".git", "")
                            .strip("/")
                        )
                        if "/" in parts:
                            repo_name = parts

                # 3. フォールバック：titleまたはslug
                if not repo_name:
                    repo_name = app.get("title", app["slug"])

                # Bitrise APIから更新日時を取得（project_type_idなどから推測）
                # 実際のAPIレスポンスに応じて調整が必要
                updated_at = ""  # Bitrise APIには更新日時がない場合がある

                items.append(
                    {
                        "id": app["slug"],
                        "name": app.get("title", app["slug"]),
                        "repo": repo_name,
                        "updated_at": updated_at,
                        "url": f"https://app.bitrise.io/app/{app['slug']}",
                        "description": f"App Slug: {app['slug']}",
                        "platform": "bitrise",
                        "metadata": {
                            "app_slug": app["slug"],  # 内部IDを保持
                            "project_type": app.get("project_type"),
                            "repo_url": app.get("repo_url"),
                            "repo_owner": repo_owner,
                            "repo_slug": repo_slug,
                        },
                    }
                )

            return {
                "items": items,
                "page": page,
                "per_page": per_page,
                "has_next": len(all_apps) > end_idx,
                "total_count": None,  # Bitriseは総数を返さない
            }

        except Exception as e:
            st.error(f"Bitrise APIエラー: {e}")
            return None

    elif platform == Platform.XCODE_CLOUD:
        conn_id = search_params.get("conn_id")
        xcode_cloud_client = (
            get_xcode_cloud_client_from_connection(conn_id)
            if conn_id
            else get_xcode_cloud_client()
        )
        if not xcode_cloud_client:
            return None

        try:
            # ページNを表示するために必要な最小件数: N*per_page + 1 (次ページ有無の判定用)
            limit = per_page * page + 1
            all_apps = xcode_cloud_client.list_apps(limit=limit)

            # ページングのためのスライス
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_apps = all_apps[start_idx:end_idx]

            # Xcode Cloudのデータを統一形式に変換
            items = []
            for app in page_apps:
                attributes = app.get("attributes", {})
                app_id = app.get("id")
                app_name = attributes.get("name", app_id)

                # Bundle IDを取得
                bundle_id = attributes.get("bundleId", "")

                items.append(
                    {
                        "id": app_id,
                        "name": app_name,
                        "repo": app_name,  # アプリ名をrepoとして使用
                        "updated_at": "",  # Xcode CloudにはAPI経由での更新日時がない
                        "url": f"https://appstoreconnect.apple.com/apps/{app_id}",
                        "description": f"Bundle ID: {bundle_id}",
                        "platform": "xcode_cloud",
                        "metadata": {
                            "app_id": app_id,  # 内部IDを保持
                            "bundle_id": bundle_id,
                            "sku": attributes.get("sku"),
                            "primary_locale": attributes.get("primaryLocale"),
                        },
                    }
                )

            return {
                "items": items,
                "page": page,
                "per_page": per_page,
                "has_next": len(all_apps) > end_idx,
                "total_count": None,  # Xcode Cloudは総数を返さない
            }

        except Exception as e:
            st.error(f"Xcode Cloud APIエラー: {e}")
            return None

    else:
        st.error(f"未対応のプラットフォーム: {platform}")
        return None


def fetch_github_repositories(
    search_type: str,
    search_value: str,
    page: int = 1,
    per_page: int = 30,
    conn_id: str = None,
):
    """GitHubからリポジトリを取得する（ページング対応）

    Args:
        search_type: "organization", "user", "search"のいずれか
        search_value: 組織名、ユーザー名、または検索クエリ
        page: ページ番号（1から開始）
        per_page: 1ページあたりの件数
        conn_id: 使用するConnection ID（Noneの場合はデフォルト）

    Returns:
        辞書形式の検索結果、またはエラー時はNone
        - repos: リポジトリリスト
        - page: ページ番号
        - per_page: 1ページあたりの件数
        - has_next: 次のページがあるか
        - total_count: 総数（search_repositoriesのみ）
    """
    # 指定されたConnectionからGitHubクライアントを取得
    github_client = (
        get_github_client_from_connection(conn_id)
        if conn_id
        else get_github_client()
    )
    if not github_client:
        return None

    try:
        if search_type == "organization":
            result = github_client.get_organization_repositories(
                search_value, page=page, per_page=per_page
            )
        elif search_type == "user":
            result = github_client.get_user_repositories(
                search_value, page=page, per_page=per_page
            )
        elif search_type == "search":
            result = github_client.search_repositories(
                search_value, page=page, per_page=per_page
            )
        else:
            st.error(f"不正な検索タイプ: {search_type}")
            return None

        return result
    except GithubException as e:
        st.error(f"GitHub APIエラー: {e}")
        return None
    except Exception as e:
        st.error(f"予期しないエラー: {e}")
        return None


def _add_repositories_batch(
    repo_items: list[dict[str, Any]], source_type: str
) -> tuple[int, int, list[str]]:
    """リポジトリを一括追加する（内部ヘルパー）

    Args:
        repo_items: 追加するリポジトリ情報のリスト
                   各辞書は{"repo": str, "source_repo_id": str (optional)}を含む
        source_type: ソースタイプ（"github_actions" または "bitrise"）

    Returns:
        (success_count, error_count, messages) のタプル
    """
    success_count = 0
    error_count = 0
    messages = []

    for item in repo_items:
        repo_name = item.get("repo", "")
        source_repo_id = item.get("source_repo_id")  # Bitriseの場合はapp_slug

        try:
            success, message = add_repository(
                repo_name, source_type, source_repo_id
            )
            if success:
                success_count += 1
                messages.append(f"✅ {repo_name}")
            else:
                error_count += 1
                messages.append(f"⚠️ {repo_name}: {message}")
        except Exception as e:
            error_count += 1
            messages.append(f"❌ {repo_name}: {e}")

    return success_count, error_count, messages


@st.cache_data(ttl=30)
def get_registered_repository_names(source: str = None) -> set[str]:
    """登録済みリポジトリ名のセットを取得する

    Args:
        source: ソースタイプでフィルタ（オプション）

    Returns:
        登録済みリポジトリ名のセット
    """
    engine = get_database_engine()
    if source:
        query = text(
            """
            SELECT repository_name
            FROM repositories
            WHERE source = :source AND active = true
            """
        )
        params = {"source": source}
    else:
        query = text(
            """
            SELECT repository_name
            FROM repositories
            WHERE active = true
            """
        )
        params = {}

    with engine.connect() as conn:
        result = conn.execute(query, params)
        rows = result.fetchall()
        return {row[0] for row in rows}


@st.cache_data(ttl=30)
def get_repositories():
    """リポジトリ一覧を取得する"""
    engine = get_database_engine()
    query = text(
        """
        SELECT id, repository_name, source, active, created_at, updated_at
        FROM repositories
        ORDER BY active DESC, repository_name
        """
    )
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()
        if rows:
            return pd.DataFrame(
                rows,
                columns=["ID", "リポジトリ名", "ソース", "有効", "作成日時", "更新日時"],
            )
        return pd.DataFrame(
            columns=["ID", "リポジトリ名", "ソース", "有効", "作成日時", "更新日時"]
        )


def add_repository(
    repo_name: str, source: str = "github_actions", source_repo_id: str | None = None
):
    """リポジトリを追加する

    Args:
        repo_name: リポジトリ名（表示用、例: "yumemi/sheep-poc-sdk"）
        source: ソースタイプ（"github_actions", "bitrise"など）
        source_repo_id: プラットフォーム固有ID（BitriseのUUID app_slug等）
                       指定しない場合はrepo_nameから生成

    Raises:
        ValueError: リポジトリ名の形式が不正な場合
    """
    # GitHub Actionsの場合はリポジトリ名の形式を検証
    if source == "github_actions":
        is_valid, error_message = validate_repository_name(repo_name)
        if not is_valid:
            raise ValueError(error_message)

    engine = get_database_engine()
    # source_repo_idが指定されない場合はrepo_nameから生成（GitHub用）
    if source_repo_id is None:
        source_repo_id = repo_name.replace("/", "_")

    with engine.begin() as conn:
        # 既存チェック
        result = conn.execute(
            text(
                """
                SELECT id, active FROM repositories
                WHERE repository_name = :repo_name AND source = :source
                """
            ),
            {"repo_name": repo_name, "source": source},
        )
        existing = result.fetchone()

        if existing:
            if existing.active:
                return False, f"リポジトリ '{repo_name}' は既に登録されています"
            else:
                # 無効状態のリポジトリを有効化
                conn.execute(
                    text(
                        """
                        UPDATE repositories
                        SET active = TRUE, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": existing.id},
                )
                get_repositories.clear()
                get_registered_repository_names.clear()
                get_statistics.clear()
                return (
                    True,
                    f"リポジトリ '{repo_name}' を有効化しました (ID: {existing.id})",
                )

        # 新規追加
        result = conn.execute(
            text(
                """
                INSERT INTO repositories (source_repository_id, source, repository_name, active)
                VALUES (:source_repo_id, :source, :repo_name, TRUE)
                RETURNING id
                """
            ),
            {
                "source_repo_id": source_repo_id,
                "source": source,
                "repo_name": repo_name,
            },
        )
        repo_id = result.fetchone()[0]
        get_repositories.clear()
        get_registered_repository_names.clear()
        get_statistics.clear()
        return True, f"リポジトリ '{repo_name}' を追加しました (ID: {repo_id})"


def toggle_repository(repo_id: int, active: bool):
    """リポジトリの有効/無効を切り替える"""
    engine = get_database_engine()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE repositories
                SET active = :active, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"id": repo_id, "active": active},
        )
    get_repositories.clear()
    get_registered_repository_names.clear()
    get_statistics.clear()
    status = "有効化" if active else "無効化"
    return True, f"リポジトリ (ID: {repo_id}) を{status}しました"


@st.cache_data(ttl=30)
def get_statistics():
    """統計情報を取得する"""
    engine = get_database_engine()

    with engine.connect() as conn:
        # リポジトリ統計
        result = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE active = TRUE) as active_count,
                    COUNT(*) FILTER (WHERE active = FALSE) as inactive_count
                FROM repositories
                """
            )
        )
        repo_stats = result.fetchone()

        # パイプライン実行統計（直近24時間）
        result = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) as total_runs,
                    COUNT(*) FILTER (WHERE status = 'success') as success_count,
                    COUNT(*) FILTER (WHERE status = 'failure') as failure_count,
                    AVG(duration_ms) as avg_duration
                FROM pipeline_runs
                WHERE started_at >= NOW() - INTERVAL '24 hours'
                """
            )
        )
        pipeline_stats = result.fetchone()

        return {
            "repositories": {
                "total": repo_stats.total if repo_stats else 0,
                "active": repo_stats.active_count if repo_stats else 0,
                "inactive": repo_stats.inactive_count if repo_stats else 0,
            },
            "pipeline_runs": {
                "total": pipeline_stats.total_runs if pipeline_stats else 0,
                "success": pipeline_stats.success_count if pipeline_stats else 0,
                "failure": pipeline_stats.failure_count if pipeline_stats else 0,
                "avg_duration_sec": (
                    float(pipeline_stats.avg_duration) / 1000
                    if pipeline_stats and pipeline_stats.avg_duration
                    else 0
                ),
            },
        }


@st.cache_data(ttl=30)
def get_recent_pipeline_runs(limit: int = 10):
    """最近のパイプライン実行履歴を取得する"""
    engine = get_database_engine()
    query = text(
        """
        SELECT
            pr.id,
            r.repository_name,
            pr.pipeline_name,
            pr.status,
            pr.started_at,
            pr.duration_ms
        FROM pipeline_runs pr
        JOIN repositories r ON pr.repository_id = r.id
        ORDER BY pr.started_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        result = conn.execute(query, {"limit": limit})
        rows = result.fetchall()
        if rows:
            return pd.DataFrame(
                rows,
                columns=[
                    "ID",
                    "リポジトリ",
                    "パイプライン名",
                    "ステータス",
                    "開始時刻",
                    "実行時間(ms)",
                ],
            )
        return pd.DataFrame(
            columns=[
                "ID",
                "リポジトリ",
                "パイプライン名",
                "ステータス",
                "開始時刻",
                "実行時間(ms)",
            ]
        )


@st.cache_data(ttl=30)
def get_connections():
    """Airflow Connectionsを取得する"""
    engine = get_database_engine()
    query = text(
        """
        SELECT id, conn_id, conn_type, description, host, schema, login, port, extra
        FROM connection
        ORDER BY conn_id
        """
    )
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()
        if rows:
            return pd.DataFrame(
                rows,
                columns=[
                    "ID",
                    "Connection ID",
                    "Type",
                    "Description",
                    "Host",
                    "Schema",
                    "Login",
                    "Port",
                    "Extra",
                ],
            )
        return pd.DataFrame(
            columns=[
                "ID",
                "Connection ID",
                "Type",
                "Description",
                "Host",
                "Schema",
                "Login",
                "Port",
                "Extra",
            ]
        )


def add_connection(
    conn_id: str,
    conn_type: str,
    description: str = "",
    host: str = "",
    schema: str = "",
    login: str = "",
    password: str = "",
    port: int = None,
    extra: str = "",
):
    """Connectionを追加する

    Raises:
        ValueError: 接続IDの形式が不正な場合
    """
    # 接続IDの形式を検証
    is_valid, error_message = validate_connection_id(conn_id)
    if not is_valid:
        raise ValueError(error_message)

    engine = get_database_engine()

    with engine.begin() as conn:
        # 既存チェック
        result = conn.execute(
            text("SELECT id FROM connection WHERE conn_id = :conn_id"),
            {"conn_id": conn_id},
        )
        existing = result.fetchone()

        if existing:
            return False, f"Connection '{conn_id}' は既に存在します"

        # 新規追加
        conn.execute(
            text(
                """
                INSERT INTO connection (conn_id, conn_type, description, host, schema, login, password, port, extra)
                VALUES (:conn_id, :conn_type, :description, :host, :schema, :login, :password, :port, :extra)
                """
            ),
            {
                "conn_id": conn_id,
                "conn_type": conn_type,
                "description": description,
                "host": host,
                "schema": schema,
                "login": login,
                "password": password,
                "port": port,
                "extra": extra,
            },
        )
        return True, f"Connection '{conn_id}' を追加しました"


def update_connection(
    connection_id: int,
    conn_type: str,
    description: str = "",
    host: str = "",
    schema: str = "",
    login: str = "",
    password: str = "",
    port: int = None,
    extra: str = "",
):
    """Connectionを更新する"""
    engine = get_database_engine()

    with engine.begin() as conn:
        # パスワードが空の場合は更新しない
        if password:
            conn.execute(
                text(
                    """
                    UPDATE connection
                    SET conn_type = :conn_type, description = :description, host = :host,
                        schema = :schema, login = :login, password = :password, port = :port, extra = :extra
                    WHERE id = :id
                    """
                ),
                {
                    "id": connection_id,
                    "conn_type": conn_type,
                    "description": description,
                    "host": host,
                    "schema": schema,
                    "login": login,
                    "password": password,
                    "port": port,
                    "extra": extra,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    UPDATE connection
                    SET conn_type = :conn_type, description = :description, host = :host,
                        schema = :schema, login = :login, port = :port, extra = :extra
                    WHERE id = :id
                    """
                ),
                {
                    "id": connection_id,
                    "conn_type": conn_type,
                    "description": description,
                    "host": host,
                    "schema": schema,
                    "login": login,
                    "port": port,
                    "extra": extra,
                },
            )
        return True, f"Connection (ID: {connection_id}) を更新しました"


def delete_connection(connection_id: int):
    """Connectionを削除する"""
    engine = get_database_engine()

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM connection WHERE id = :id"), {"id": connection_id}
        )
        return True, f"Connection (ID: {connection_id}) を削除しました"


def test_connection(
    connection_id: int,
    conn_type: str,
    host: str = None,
    port: int = None,
    login: str = None,
    password: str = None,
    schema: str = None,
    extra: str = None,
):
    """Connectionの接続テストを実行する

    Args:
        connection_id: Connection ID
        conn_type: Connection Type
        host: ホスト
        port: ポート
        login: ログイン名
        password: パスワード
        schema: スキーマ/データベース名
        extra: 追加設定

    Returns:
        (成功フラグ, メッセージ, 詳細情報)
    """
    try:
        if conn_type == "postgres":
            # PostgreSQL接続テスト
            from sqlalchemy import create_engine as create_test_engine

            if not all([host, login, password, schema]):
                return False, "PostgreSQL接続に必要な情報が不足しています", None

            test_url = SA_URL.create(
                "postgresql",
                username=login,
                password=password,
                host=host,
                port=port or 5432,
                database=schema,
            )
            test_engine = create_test_engine(test_url, pool_pre_ping=True)

            with test_engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                return True, "✅ 接続成功！", {"version": version[:100]}

        elif conn_type == "mysql":
            # MySQL接続テスト
            from sqlalchemy import create_engine as create_test_engine

            if not all([host, login, password, schema]):
                return False, "MySQL接続に必要な情報が不足しています", None

            test_url = SA_URL.create(
                "mysql+pymysql",
                username=login,
                password=password,
                host=host,
                port=port or 3306,
                database=schema,
            )
            test_engine = create_test_engine(test_url, pool_pre_ping=True)

            with test_engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                return True, "✅ 接続成功！", {"version": version}

        elif conn_type == "http":
            # HTTP接続テスト（GitHub/Bitrise等）
            if not password:  # passwordにトークンが格納されている想定
                return False, "トークン/パスワードが設定されていません", None

            # 簡易的なHTTPリクエストテスト
            import requests

            # hostからtest_urlを構築（スキームを確認）
            if host:
                # スキームがない場合はhttps://を付加
                if not host.startswith(("http://", "https://")):
                    test_url = f"https://{host}"
                else:
                    test_url = host

                # パスがない場合、プラットフォームに応じたデフォルトエンドポイントを追加
                if not test_url.endswith(("/user", "/me", "/apps")):
                    if "github" in host.lower():
                        test_url = f"{test_url.rstrip('/')}/user"
                    elif "bitrise" in host.lower():
                        test_url = f"{test_url.rstrip('/')}/me"
            else:
                # hostが未指定の場合はGitHubをデフォルト
                test_url = "https://api.github.com/user"

            # GitHub/Bitrise APIは"token "プレフィックス、その他は"Bearer "
            if "github" in test_url.lower() or "bitrise" in test_url.lower():
                headers = {"Authorization": f"token {password}"}
            else:
                headers = {"Authorization": f"Bearer {password}"}

            response = requests.get(test_url, headers=headers, timeout=10)

            if response.status_code == 200:
                return (
                    True,
                    "✅ 接続成功！",
                    {"status_code": response.status_code, "url": test_url},
                )
            elif response.status_code == 401:
                return (
                    False,
                    "❌ 認証失敗（トークンが無効）",
                    {"status_code": response.status_code, "url": test_url},
                )
            else:
                return (
                    False,
                    f"❌ 接続失敗（ステータス: {response.status_code}）",
                    {"status_code": response.status_code, "url": test_url},
                )

        elif conn_type == "sqlite":
            # SQLite接続テスト
            import sqlite3

            if not host:  # hostにファイルパスが格納されている想定
                return False, "SQLiteファイルパスが指定されていません", None

            with sqlite3.connect(host) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT sqlite_version()")
                version = cursor.fetchone()[0]
            return True, "✅ 接続成功！", {"version": version}

        else:
            # その他のタイプは基本的な情報確認のみ
            info = {
                "conn_type": conn_type,
                "host": host,
                "port": port,
                "login": login,
                "has_password": bool(password),
            }
            return (
                True,
                f"ℹ️ Connection Type '{conn_type}' の自動テストは未実装です",
                info,
            )

    except Exception as e:
        return False, f"❌ 接続失敗: {str(e)}", None
