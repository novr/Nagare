#!/usr/bin/env python3
"""Streamlit管理画面

リポジトリの追加・削除・有効化/無効化、データ収集状況の確認を行うWeb UI。

Usage:
    streamlit run src/nagare/admin_app.py --server.port 8501
"""

import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from github import GithubException
from sqlalchemy import create_engine, text

from nagare.constants import Platform, PipelineStatus, SourceType
from nagare.utils.connections import ConnectionRegistry
from nagare.utils.github_client import GitHubClient
from nagare.utils.bitrise_client import BitriseClient

# Connection設定ファイルの読み込み
connections_file = os.getenv("NAGARE_CONNECTIONS_FILE")
if connections_file and Path(connections_file).exists():
    ConnectionRegistry.from_file(connections_file)

# ページ設定
st.set_page_config(
    page_title="Nagare 管理画面",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
    """利用可能な全てのCI/CD Connections（GitHub/Bitrise）を取得する

    Returns:
        List[(conn_id, description, platform)] - Connection情報とプラットフォームのリスト
    """
    engine = get_database_engine()
    query = text(
        """
        SELECT conn_id, description
        FROM connection
        WHERE conn_type = 'http' AND password IS NOT NULL AND password != ''
        ORDER BY conn_id
        """
    )
    connections = []
    with engine.connect() as conn:
        result = conn.execute(query)
        rows = result.fetchall()
        for row in rows:
            conn_id = row[0]
            description = row[1] or conn_id

            # conn_idやdescriptionからプラットフォームを判定
            platform = detect_platform_from_connection(conn_id, description)
            if platform:  # GitHub または Bitrise のみ
                connections.append((conn_id, description, platform))

    return connections


def detect_platform_from_connection(conn_id: str, description: str) -> str | None:
    """ConnectionからプラットフォームGitHub/Bitrise）を判定する

    Args:
        conn_id: Connection ID
        description: Connection description

    Returns:
        "github", "bitrise", または None（判定不可）
    """
    conn_id_lower = conn_id.lower()
    description_lower = description.lower()

    # GitHub判定
    if "github" in conn_id_lower or "github" in description_lower:
        return "github"

    # Bitrise判定
    if "bitrise" in conn_id_lower or "bitrise" in description_lower:
        return "bitrise"

    # デフォルトConnectionの判定（github_default, bitrise_default）
    if conn_id in ["github_default", "gh_default"]:
        return "github"
    if conn_id in ["bitrise_default", "br_default"]:
        return "bitrise"

    # 判定不可
    return None


def get_github_client_from_connection(conn_id: str = None):
    """指定されたConnectionからGitHubクライアントを取得する

    Args:
        conn_id: Connection ID。Noneの場合はデフォルト動作

    Returns:
        GitHubClient or None
    """
    import os

    # Connection IDが指定された場合
    if conn_id:
        try:
            engine = get_database_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT password FROM connection WHERE conn_id = :conn_id"),
                    {"conn_id": conn_id}
                )
                row = result.fetchone()
                if row and row[0]:
                    # 一時的に環境変数を設定
                    original_token = os.environ.get("GITHUB_TOKEN")
                    os.environ["GITHUB_TOKEN"] = row[0]
                    try:
                        client = GitHubClient()
                        # 元に戻す
                        if original_token:
                            os.environ["GITHUB_TOKEN"] = original_token
                        else:
                            os.environ.pop("GITHUB_TOKEN", None)
                        return client
                    except Exception as e:
                        # 元に戻す
                        if original_token:
                            os.environ["GITHUB_TOKEN"] = original_token
                        else:
                            os.environ.pop("GITHUB_TOKEN", None)
                        raise e
        except Exception as e:
            st.error(f"Connection '{conn_id}' からの取得エラー: {e}")
            return None

    # Connection IDが指定されていない場合は、デフォルトの優先順位で取得
    # 1. github_default Connection
    try:
        engine = get_database_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT password FROM connection WHERE conn_id = :conn_id"),
                {"conn_id": "github_default"}
            )
            row = result.fetchone()
            if row and row[0]:
                original_token = os.environ.get("GITHUB_TOKEN")
                os.environ["GITHUB_TOKEN"] = row[0]
                try:
                    client = GitHubClient()
                    if original_token:
                        os.environ["GITHUB_TOKEN"] = original_token
                    else:
                        os.environ.pop("GITHUB_TOKEN", None)
                    return client
                except Exception:
                    if original_token:
                        os.environ["GITHUB_TOKEN"] = original_token
                    else:
                        os.environ.pop("GITHUB_TOKEN", None)
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
    from nagare.utils.connections import BitriseConnection

    # Connection IDが指定された場合
    if conn_id:
        try:
            engine = get_database_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT password, host FROM connection WHERE conn_id = :conn_id"),
                    {"conn_id": conn_id}
                )
                row = result.fetchone()
                if row and row[0]:
                    api_token = row[0]
                    base_url = row[1] or "https://api.bitrise.io/v0.1"

                    # スキームがない場合は追加
                    if base_url and not base_url.startswith(("http://", "https://")):
                        base_url = f"https://{base_url}"

                    bitrise_conn = BitriseConnection(
                        api_token=api_token,
                        base_url=base_url
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


def fetch_repositories_unified(platform: str, search_params: dict, page: int = 1, per_page: int = 30):
    """統一されたインターフェースでリポジトリ/アプリを取得する（ページング対応）

    Args:
        platform: "github" または "bitrise"
        search_params: プラットフォーム固有の検索パラメータ
            GitHub: {"search_type": str, "search_value": str, "conn_id": str}
            Bitrise: {} (パラメータなし)
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
                    "platform": str,    # "github" or "bitrise"
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

        result = fetch_github_repositories(search_type, search_value, page, per_page, conn_id)
        if not result or "repos" not in result:
            return None

        # GitHubのデータを統一形式に変換
        items = []
        for repo in result["repos"]:
            # ownerの安全な取得
            owner = repo.get("owner", {})
            owner_login = owner.get("login", "") if isinstance(owner, dict) else ""

            items.append({
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
                }
            })

        return {
            "items": items,
            "page": result["page"],
            "per_page": result["per_page"],
            "has_next": result["has_next"],
            "total_count": result.get("total_count")
        }

    elif platform == Platform.BITRISE:
        conn_id = search_params.get("conn_id")
        bitrise_client = get_bitrise_client_from_connection(conn_id) if conn_id else get_bitrise_client()
        if not bitrise_client:
            return None

        try:
            # Bitriseは全件取得してからページングを実装
            # 実際にはAPIがページングをサポートしているが、ここでは簡易実装
            limit = per_page * (page + 1)  # 次のページも考慮して多めに取得
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
                        parts = repo_url.split("github.com/")[-1].replace(".git", "").strip("/")
                        if "/" in parts:
                            repo_name = parts
                    elif "bitbucket.org/" in repo_url:
                        parts = repo_url.split("bitbucket.org/")[-1].replace(".git", "").strip("/")
                        if "/" in parts:
                            repo_name = parts

                # 3. フォールバック：titleまたはslug
                if not repo_name:
                    repo_name = app.get("title", app["slug"])

                # Bitrise APIから更新日時を取得（project_type_idなどから推測）
                # 実際のAPIレスポンスに応じて調整が必要
                updated_at = ""  # Bitrise APIには更新日時がない場合がある

                items.append({
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
                    }
                })

            return {
                "items": items,
                "page": page,
                "per_page": per_page,
                "has_next": len(all_apps) > end_idx,
                "total_count": None  # Bitriseは総数を返さない
            }

        except Exception as e:
            st.error(f"Bitrise APIエラー: {e}")
            return None

    else:
        st.error(f"未対応のプラットフォーム: {platform}")
        return None


def fetch_github_repositories(
    search_type: str, search_value: str, page: int = 1, per_page: int = 30, conn_id: str = None
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
    github_client = get_github_client_from_connection(conn_id) if conn_id else get_github_client()
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


def _add_repositories_batch(repo_items: list[dict[str, Any]], source_type: str) -> tuple[int, int, list[str]]:
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
            success, message = add_repository(repo_name, source_type, source_repo_id)
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


def render_repository_list(result: dict, platform: str, session_key_prefix: str):
    """統一されたリポジトリ/アプリリストを表示する（ページング対応）

    Args:
        result: fetch_repositories_unified()の戻り値
        platform: "github" または "bitrise"
        session_key_prefix: セッションステートのキープレフィックス
    """
    if not result or "items" not in result:
        st.info("リポジトリ/アプリが見つかりませんでした")
        return

    items = result["items"]
    current_page = result["page"]
    has_next = result["has_next"]
    total_count = result.get("total_count")

    # ヘッダー情報
    if total_count is not None:
        st.success(f"検索結果: 全{total_count}件 （ページ {current_page}）")
    else:
        st.success(f"{len(items)}件が見つかりました （ページ {current_page}）")

    if not items:
        st.info("このページにアイテムがありません")
        return

    # 登録済みリポジトリの一覧を取得
    source_type = SourceType.GITHUB_ACTIONS if platform == Platform.GITHUB else SourceType.BITRISE
    registered_repos = get_registered_repository_names(source_type)

    # 選択状態の管理
    selected_key = f"{session_key_prefix}_selected"
    repo_mapping_key = f"{session_key_prefix}_repo_mapping"
    if selected_key not in st.session_state:
        st.session_state[selected_key] = set()
    if repo_mapping_key not in st.session_state:
        st.session_state[repo_mapping_key] = {}

    # リスト表示
    for item in items:
        # 登録済みかどうかをチェック
        is_registered = item['repo'] in registered_repos

        col1, col2, col3 = st.columns([1, 6, 2])

        with col1:
            # 登録済みの場合はチェックボックスを無効化
            is_selected = st.checkbox(
                "選択",
                key=f"{session_key_prefix}_select_{item['id']}_{current_page}",
                label_visibility="collapsed",
                disabled=is_registered
            )
            if is_selected:
                st.session_state[selected_key].add(item['id'])
                # item['id'] -> item (全情報) のマッピングを保存
                st.session_state[repo_mapping_key][item['id']] = item
            elif item['id'] in st.session_state[selected_key]:
                st.session_state[selected_key].remove(item['id'])
                # マッピングからも削除
                st.session_state[repo_mapping_key].pop(item['id'], None)

        with col2:
            # プラットフォーム固有のアイコン
            icon = "📦" if platform == Platform.GITHUB else "📱"
            if platform == "github" and item["metadata"].get("private"):
                icon = "🔒"

            # リポジトリ/アプリ名表示（登録済みの場合はバッジ追加）
            if is_registered:
                st.markdown(f"**{icon} [{item['name']}]({item['url']})** :green[✅ 登録済み]")
            else:
                st.markdown(f"**{icon} [{item['name']}]({item['url']})**")

            # repo識別子表示
            st.caption(f"📂 {item['repo']}")

            # 説明表示
            if item.get("description"):
                st.caption(item["description"])

            # メタ情報表示
            meta_info = []

            # 更新日時
            if item.get("updated_at"):
                try:
                    updated = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                    meta_info.append(f"🕒 {updated.strftime('%Y-%m-%d %H:%M')}")
                except (ValueError, AttributeError):
                    if item["updated_at"]:
                        meta_info.append(f"🕒 {item['updated_at']}")

            # プラットフォーム固有のメタ情報
            if platform == Platform.GITHUB:
                metadata = item["metadata"]
                if metadata.get("language"):
                    meta_info.append(f"🔤 {metadata['language']}")
                if metadata.get("stars") is not None:
                    meta_info.append(f"⭐ {metadata['stars']}")
                if metadata.get("forks") is not None:
                    meta_info.append(f"🍴 {metadata['forks']}")
            elif platform == Platform.BITRISE:
                metadata = item["metadata"]
                if metadata.get("project_type"):
                    meta_info.append(f"📦 {metadata['project_type']}")
                if metadata.get("repo_url"):
                    meta_info.append(f"🔗 {metadata['repo_url']}")

            if meta_info:
                st.caption(" • ".join(meta_info))

        with col3:
            source_type = SourceType.GITHUB_ACTIONS if platform == Platform.GITHUB else SourceType.BITRISE
            # 登録済みの場合は追加ボタンを無効化
            if st.button("追加", key=f"{session_key_prefix}_add_{item['id']}_{current_page}", disabled=is_registered):
                # リポジトリ情報を準備（Bitriseの場合はapp_slugも含める）
                repo_item = {"repo": item["repo"]}
                if platform == Platform.BITRISE and "metadata" in item and "app_slug" in item["metadata"]:
                    repo_item["source_repo_id"] = item["metadata"]["app_slug"]

                # 共通処理を使用
                success_count, error_count, messages = _add_repositories_batch([repo_item], source_type)

                if success_count > 0:
                    st.success(f"リポジトリ '{item['repo']}' を追加しました")
                    st.rerun()
                elif error_count > 0:
                    # エラーメッセージを表示
                    if messages:
                        st.warning(messages[0].replace("⚠️ ", "").replace("❌ ", ""))
                    else:
                        st.error("追加に失敗しました")

        st.divider()

    # ページングボタン
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if current_page > 1:
            if st.button("⬅️ 前のページ", key=f"{session_key_prefix}_prev"):
                return "prev"
    with col2:
        st.markdown(f"<center>ページ {current_page}</center>", unsafe_allow_html=True)
    with col3:
        if has_next:
            if st.button("次のページ ➡️", key=f"{session_key_prefix}_next"):
                return "next"

    # 一括追加ボタン
    if st.session_state[selected_key]:
        st.divider()
        st.markdown(f"**選択中: {len(st.session_state[selected_key])}件**")
        if st.button("選択したアイテムを一括追加", type="primary", key=f"{session_key_prefix}_batch_add"):
            source_type = SourceType.GITHUB_ACTIONS if platform == Platform.GITHUB else SourceType.BITRISE

            # マッピングから item 情報のリストを取得してrepo_items形式に変換
            repo_items = []
            for item_id in st.session_state[selected_key]:
                item = st.session_state[repo_mapping_key].get(item_id)
                if item:
                    repo_item = {"repo": item["repo"]}
                    # Bitriseの場合はapp_slugも含める
                    if platform == Platform.BITRISE and "metadata" in item and "app_slug" in item["metadata"]:
                        repo_item["source_repo_id"] = item["metadata"]["app_slug"]
                    repo_items.append(repo_item)

            # 共通処理を使用
            success_count, error_count, messages = _add_repositories_batch(repo_items, source_type)

            if success_count > 0:
                st.success(f"{success_count}件を追加しました")
            if error_count > 0:
                st.warning(f"{error_count}件は追加できませんでした（既存またはエラー）")
                # 詳細なエラーメッセージを展開可能なセクションに表示
                with st.expander("詳細を表示"):
                    for msg in messages:
                        if "⚠️" in msg or "❌" in msg:
                            st.caption(msg)

            st.session_state[selected_key].clear()
            st.session_state[repo_mapping_key].clear()
            st.rerun()

    return None


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


def add_repository(repo_name: str, source: str = "github_actions", source_repo_id: str | None = None):
    """リポジトリを追加する

    Args:
        repo_name: リポジトリ名（表示用、例: "yumemi/sheep-poc-sdk"）
        source: ソースタイプ（"github_actions", "bitrise"など）
        source_repo_id: プラットフォーム固有ID（BitriseのUUID app_slug等）
                       指定しない場合はrepo_nameから生成
    """
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
                return True, f"リポジトリ '{repo_name}' を有効化しました (ID: {existing.id})"

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
    status = "有効化" if active else "無効化"
    return True, f"リポジトリ (ID: {repo_id}) を{status}しました"


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
                columns=["ID", "Connection ID", "Type", "Description", "Host", "Schema", "Login", "Port", "Extra"],
            )
        return pd.DataFrame(
            columns=["ID", "Connection ID", "Type", "Description", "Host", "Schema", "Login", "Port", "Extra"]
        )


def add_connection(conn_id: str, conn_type: str, description: str = "", host: str = "",
                   schema: str = "", login: str = "", password: str = "", port: int = None, extra: str = ""):
    """Connectionを追加する"""
    engine = get_database_engine()

    with engine.begin() as conn:
        # 既存チェック
        result = conn.execute(
            text("SELECT id FROM connection WHERE conn_id = :conn_id"),
            {"conn_id": conn_id}
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


def update_connection(connection_id: int, conn_type: str, description: str = "", host: str = "",
                      schema: str = "", login: str = "", password: str = "", port: int = None, extra: str = ""):
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
            text("DELETE FROM connection WHERE id = :id"),
            {"id": connection_id}
        )
        return True, f"Connection (ID: {connection_id}) を削除しました"


def test_connection(connection_id: int, conn_type: str, host: str = None, port: int = None,
                    login: str = None, password: str = None, schema: str = None, extra: str = None):
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

            test_url = f"postgresql://{login}:{password}@{host}:{port or 5432}/{schema}"
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

            test_url = f"mysql+pymysql://{login}:{password}@{host}:{port or 3306}/{schema}"
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
                return True, "✅ 接続成功！", {"status_code": response.status_code, "url": test_url}
            elif response.status_code == 401:
                return False, "❌ 認証失敗（トークンが無効）", {"status_code": response.status_code, "url": test_url}
            else:
                return False, f"❌ 接続失敗（ステータス: {response.status_code}）", {"status_code": response.status_code, "url": test_url}

        elif conn_type == "sqlite":
            # SQLite接続テスト
            import sqlite3
            if not host:  # hostにファイルパスが格納されている想定
                return False, "SQLiteファイルパスが指定されていません", None

            conn = sqlite3.connect(host)
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            conn.close()
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
            return True, f"ℹ️ Connection Type '{conn_type}' の自動テストは未実装です", info

    except Exception as e:
        return False, f"❌ 接続失敗: {str(e)}", None


# メインUI
st.title("🌊 Nagare 管理画面")
st.markdown("CI/CD監視システムの管理インターフェース")

# サイドバー
with st.sidebar:
    st.header("ナビゲーション")
    page = st.radio(
        "ページ選択",
        ["📊 ダッシュボード", "📦 リポジトリ管理", "🔌 Connections管理", "📈 実行履歴", "⚙️ 設定"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Powered by Streamlit")

# ダッシュボード
if page == "📊 ダッシュボード":
    st.header("📊 ダッシュボード")

    try:
        stats = get_statistics()

        # メトリクス表示
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "登録リポジトリ",
                stats["repositories"]["total"],
                delta=f"有効: {stats['repositories']['active']}",
            )

        with col2:
            st.metric(
                "パイプライン実行（24h）",
                stats["pipeline_runs"]["total"],
                delta=f"成功: {stats['pipeline_runs']['success']}",
            )

        with col3:
            avg_duration = stats["pipeline_runs"]["avg_duration_sec"]
            st.metric(
                "平均実行時間（24h）",
                f"{avg_duration:.1f}秒" if avg_duration > 0 else "N/A",
            )

        st.divider()

        # 最近の実行履歴
        st.subheader("最近のパイプライン実行")
        recent_runs = get_recent_pipeline_runs(20)

        if not recent_runs.empty:
            # ステータスに色を付ける
            def highlight_status(row):
                status = row["ステータス"].upper() if isinstance(row["ステータス"], str) else ""
                if status == PipelineStatus.SUCCESS:
                    return ["background-color: #d4edda"] * len(row)
                elif status == PipelineStatus.FAILURE:
                    return ["background-color: #f8d7da"] * len(row)
                else:
                    return [""] * len(row)

            st.dataframe(
                recent_runs.style.apply(highlight_status, axis=1),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("まだパイプライン実行履歴がありません")

    except Exception as e:
        st.error(f"データ取得エラー: {e}")

# リポジトリ管理
elif page == "📦 リポジトリ管理":
    st.header("📦 リポジトリ管理")

    # リポジトリ追加フォーム（手動入力）
    with st.expander("➕ リポジトリ/アプリを手動で追加", expanded=False):
        with st.form("add_repository_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                new_repo = st.text_input(
                    "リポジトリ/アプリ名",
                    placeholder="owner/repo（GitHub）またはapp-slug（Bitrise）",
                    help="GitHub: 'owner/repo' 形式、Bitrise: app-slug",
                )
            with col2:
                source = st.selectbox(
                    "プラットフォーム",
                    ["github_actions", "bitrise"],
                    format_func=lambda x: "GitHub Actions" if x == SourceType.GITHUB_ACTIONS else "Bitrise"
                )

            submitted = st.form_submit_button("追加", type="primary")

            if submitted:
                if new_repo:
                    # GitHub Actionsの場合は '/' が必要
                    if source == SourceType.GITHUB_ACTIONS and "/" not in new_repo:
                        st.error("GitHubリポジトリ名を 'owner/repo' 形式で入力してください")
                    else:
                        try:
                            success, message = add_repository(new_repo, source)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.warning(message)
                        except Exception as e:
                            st.error(f"追加エラー: {e}")
                else:
                    st.error("リポジトリ/アプリ名を入力してください")

    # 統一検索UI（GitHub + Bitrise）
    with st.expander("🔍 リポジトリ/アプリを検索して追加", expanded=True):
        st.markdown("**CI/CD Connectionから検索**")

        # Connection選択
        available_connections = get_all_cicd_connections()
        if not available_connections:
            st.warning("⚠️ GitHub/Bitrise Connectionが登録されていません")
            st.info("🔌 Connections管理ページでGitHub/Bitrise Connectionを登録してください")
        else:
            col_conn, col_per_page = st.columns([3, 1])
            with col_conn:
                selected_conn = st.selectbox(
                    "使用するConnection",
                    options=range(len(available_connections)),
                    format_func=lambda i: f"{available_connections[i][1]} ({available_connections[i][2].upper()})",
                    key="unified_connection_select"
                )
                conn_id = available_connections[selected_conn][0]
                platform = available_connections[selected_conn][2]

            with col_per_page:
                per_page = st.selectbox("表示件数", options=[10, 20, 30, 50], index=2, key="unified_per_page")

            # プラットフォーム表示
            platform_icon = "📦" if platform == Platform.GITHUB else "📱"
            platform_name = "GitHub Actions" if platform == Platform.GITHUB else "Bitrise"
            st.caption(f"{platform_icon} プラットフォーム: **{platform_name}**")

            # セッションステートの初期化
            search_state_key = f"unified_{conn_id}_search"
            if search_state_key not in st.session_state:
                st.session_state[search_state_key] = {"result": None, "page": 1, "params": {}}

            # プラットフォーム固有の検索条件
            search_params = {}

            if platform == Platform.GITHUB:
                search_params["conn_id"] = conn_id

                # 検索方法選択
                search_type = st.radio(
                    "検索方法",
                    ["organization", "user", "search"],
                    format_func=lambda x: {"organization": "組織名", "user": "ユーザー名", "search": "キーワード"}[x],
                    horizontal=True,
                    key="unified_search_type"
                )

                # 検索値入力
                if search_type in ["organization", "user"]:
                    search_value = st.text_input(
                        f"{search_type.capitalize()}名",
                        placeholder="organization-name" if search_type == "organization" else "username",
                        key="unified_search_value"
                    )
                else:
                    search_value = st.text_input(
                        "検索クエリ",
                        placeholder="例: org:myorg language:python",
                        help="GitHub検索構文を使用できます",
                        key="unified_search_query"
                    )

                search_params["search_type"] = search_type
                search_params["search_value"] = search_value

            else:  # bitrise
                search_params["conn_id"] = conn_id
                st.info("📱 Bitriseアプリ一覧を取得します")

            # 検索ボタン
            can_search = (platform == Platform.GITHUB and search_params.get("search_value")) or platform == Platform.BITRISE
            if st.button("検索", type="primary", key="unified_search_btn", disabled=not can_search):
                st.session_state[search_state_key]["page"] = 1
                st.session_state[search_state_key]["params"] = {
                    "search_params": search_params,
                    "per_page": per_page,
                    "platform": platform
                }

                with st.spinner(f"{platform_name}から取得中..."):
                    result = fetch_repositories_unified(platform, search_params, page=1, per_page=per_page)
                    st.session_state[search_state_key]["result"] = result

            # 検索結果表示
            state = st.session_state[search_state_key]
            if state["result"]:
                action = render_repository_list(state["result"], platform, f"unified_{conn_id}")

                # ページング処理
                if action == "prev" and state["page"] > 1:
                    state["page"] -= 1
                    params = state["params"]
                    with st.spinner("読み込み中..."):
                        result = fetch_repositories_unified(
                            params["platform"], params["search_params"], page=state["page"], per_page=params["per_page"]
                        )
                        state["result"] = result
                    st.rerun()

                elif action == "next":
                    state["page"] += 1
                    params = state["params"]
                    with st.spinner("読み込み中..."):
                        result = fetch_repositories_unified(
                            params["platform"], params["search_params"], page=state["page"], per_page=params["per_page"]
                        )
                        state["result"] = result
                    st.rerun()


    st.divider()

    # リポジトリ一覧
    st.subheader("登録済みリポジトリ")

    try:
        repos_df = get_repositories()

        if not repos_df.empty:
            # フィルタ
            col1, col2 = st.columns([1, 3])
            with col1:
                status_filter = st.selectbox(
                    "ステータスフィルタ", ["すべて", "有効のみ", "無効のみ"]
                )

            if status_filter == "有効のみ":
                repos_df = repos_df[repos_df["有効"] == True]
            elif status_filter == "無効のみ":
                repos_df = repos_df[repos_df["有効"] == False]

            st.caption(f"全{len(repos_df)}件")

            # リポジトリ一覧表示と操作
            for idx, row in repos_df.iterrows():
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

                    with col1:
                        status_icon = "✅" if row["有効"] else "⚪"
                        st.markdown(f"**{status_icon} {row['リポジトリ名']}**")
                        st.caption(f"ID: {row['ID']} | ソース: {row['ソース']}")

                    with col2:
                        st.caption(f"作成: {row['作成日時'].strftime('%Y-%m-%d %H:%M')}")

                    with col3:
                        st.caption(f"更新: {row['更新日時'].strftime('%Y-%m-%d %H:%M')}")

                    with col4:
                        if row["有効"]:
                            if st.button("無効化", key=f"disable_{row['ID']}"):
                                try:
                                    success, message = toggle_repository(
                                        row["ID"], False
                                    )
                                    st.success(message)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"エラー: {e}")
                        else:
                            if st.button("有効化", key=f"enable_{row['ID']}"):
                                try:
                                    success, message = toggle_repository(row["ID"], True)
                                    st.success(message)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"エラー: {e}")

                    st.divider()
        else:
            st.info("登録されているリポジトリがありません。上のフォームから追加してください。")

    except Exception as e:
        st.error(f"リポジトリ取得エラー: {e}")

# Connections管理
elif page == "🔌 Connections管理":
    st.header("🔌 Airflow Connections管理")

    try:
        conns_df = get_connections()

        if not conns_df.empty:
            st.caption(f"全{len(conns_df)}件")

            # Connections一覧表示と操作
            for idx, row in conns_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 2])

                    with col1:
                        st.markdown(f"**🔌 {row['Connection ID']}**")
                        st.caption(f"ID: {row['ID']} | Type: {row['Type']}")
                        if row['Description']:
                            st.caption(f"📝 {row['Description']}")

                    with col2:
                        if row['Host']:
                            st.caption(f"🖥️ Host: {row['Host']}")
                        if row['Port']:
                            st.caption(f"🔌 Port: {row['Port']}")

                    with col3:
                        if row['Login']:
                            st.caption(f"👤 Login: {row['Login']}")
                        if row['Schema']:
                            st.caption(f"🗄️ Schema: {row['Schema']}")

                    # 接続テストセクション
                    with st.expander("🔍 接続テスト", expanded=False):
                        if st.button("接続テストを実行", key=f"test_{row['ID']}", type="primary"):
                            with st.spinner("接続テスト中..."):
                                # データベースから最新のConnection情報を取得（パスワード含む）
                                engine = get_database_engine()
                                with engine.connect() as conn:
                                    result = conn.execute(
                                        text("SELECT host, port, login, password, schema, extra FROM connection WHERE id = :id"),
                                        {"id": row['ID']}
                                    )
                                    conn_data = result.fetchone()

                                if conn_data:
                                    success, message, details = test_connection(
                                        connection_id=row['ID'],
                                        conn_type=row['Type'],
                                        host=conn_data[0],
                                        port=conn_data[1],
                                        login=conn_data[2],
                                        password=conn_data[3],
                                        schema=conn_data[4],
                                        extra=conn_data[5]
                                    )

                                    if success:
                                        st.success(message)
                                    else:
                                        st.error(message)

                                    if details:
                                        st.json(details)
                                else:
                                    st.error("Connection情報の取得に失敗しました")

                    st.divider()
        else:
            st.info("登録されているConnectionがありません。")

    except Exception as e:
        st.error(f"Connections取得エラー: {e}")

# 実行履歴
elif page == "📈 実行履歴":
    st.header("📈 パイプライン実行履歴")

    try:
        # 表示件数選択
        limit = st.slider("表示件数", min_value=10, max_value=100, value=50, step=10)

        runs_df = get_recent_pipeline_runs(limit)

        if not runs_df.empty:
            # ステータスフィルタ
            status_filter = st.multiselect(
                "ステータスフィルタ",
                options=runs_df["ステータス"].unique(),
                default=runs_df["ステータス"].unique(),
            )

            filtered_df = runs_df[runs_df["ステータス"].isin(status_filter)]

            st.caption(f"全{len(filtered_df)}件（フィルタ後）")

            # データ表示
            def color_status(val):
                status = val.upper() if isinstance(val, str) else ""
                if status == PipelineStatus.SUCCESS:
                    return "background-color: #d4edda"
                elif status == PipelineStatus.FAILURE:
                    return "background-color: #f8d7da"
                else:
                    return ""

            st.dataframe(
                filtered_df.style.applymap(color_status, subset=["ステータス"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("実行履歴がありません")

    except Exception as e:
        st.error(f"データ取得エラー: {e}")

# 設定ページ
elif page == "⚙️ 設定":
    st.header("⚙️ 設定")

    tab1, tab2 = st.tabs(["接続設定", "システム情報"])

    # タブ1: 接続設定
    with tab1:
        st.subheader("接続設定の確認")

        connections_file = os.getenv("NAGARE_CONNECTIONS_FILE")

        if connections_file and Path(connections_file).exists():
            st.success(f"✅ 設定ファイル: `{connections_file}`")

            # GitHub接続設定
            st.markdown("### GitHub接続設定")
            try:
                github_conn = ConnectionRegistry.get_github()

                col1, col2 = st.columns([1, 3])
                with col1:
                    st.metric("認証方式", "Token" if github_conn.token else "GitHub App")
                with col2:
                    if github_conn.token:
                        masked_token = github_conn.token[:8] + "..." + github_conn.token[-4:] if len(github_conn.token) > 12 else "***"
                        st.code(f"Token: {masked_token}", language="text")
                    else:
                        st.code(f"App ID: {github_conn.app_id}\nInstallation ID: {github_conn.installation_id}", language="text")

            except Exception as e:
                st.error(f"GitHub設定の読み込みエラー: {e}")

            st.divider()

            # Bitrise接続設定
            st.markdown("### Bitrise接続設定")
            try:
                bitrise_conn = ConnectionRegistry.get_bitrise()

                col1, col2 = st.columns([1, 3])
                with col1:
                    st.metric("ベースURL", bitrise_conn.base_url)
                with col2:
                    if bitrise_conn.api_token:
                        masked_token = bitrise_conn.api_token[:8] + "..." + bitrise_conn.api_token[-4:] if len(bitrise_conn.api_token) > 12 else "***"
                        st.code(f"API Token: {masked_token}", language="text")

            except Exception as e:
                st.error(f"Bitrise設定の読み込みエラー: {e}")

            st.divider()

            # Database接続設定
            st.markdown("### Database接続設定")
            try:
                db_conn = ConnectionRegistry.get_database()

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("ホスト", db_conn.host)
                with col2:
                    st.metric("ポート", db_conn.port)
                with col3:
                    st.metric("データベース", db_conn.database)

                st.code(f"User: {db_conn.user}\nPassword: {'*' * len(db_conn.password) if db_conn.password else 'Not set'}", language="text")

            except Exception as e:
                st.error(f"Database設定の読み込みエラー: {e}")

        else:
            st.warning("⚠️ 設定ファイルが見つかりません")
            if connections_file:
                st.code(f"探索パス: {connections_file}", language="text")
            else:
                st.info("環境変数 `NAGARE_CONNECTIONS_FILE` が設定されていません")

    # タブ2: システム情報
    with tab2:
        st.subheader("システム情報")

        import sys
        import platform

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Python**")
            st.code(f"Version: {sys.version.split()[0]}\nPath: {sys.executable}", language="text")

            st.markdown("**プラットフォーム**")
            st.code(f"OS: {platform.system()}\nVersion: {platform.release()}", language="text")

        with col2:
            st.markdown("**環境変数**")
            env_vars = {
                "NAGARE_CONNECTIONS_FILE": os.getenv("NAGARE_CONNECTIONS_FILE", "Not set"),
                "AIRFLOW_HOME": os.getenv("AIRFLOW_HOME", "Not set"),
            }
            for key, value in env_vars.items():
                st.code(f"{key}={value}", language="text")
