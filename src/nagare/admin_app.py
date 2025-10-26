#!/usr/bin/env python3
"""Streamlit管理画面

リポジトリの追加・削除・有効化/無効化、データ収集状況の確認を行うWeb UI。

Usage:
    streamlit run src/nagare/admin_app.py --server.port 8501
"""

import os
from datetime import datetime
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from github import GithubException
from sqlalchemy import create_engine, text

from nagare.utils.github_client import GitHubClient

# ページ設定
st.set_page_config(
    page_title="Nagare 管理画面",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_database_engine():
    """データベースエンジンを取得する"""
    db_host = os.getenv("DATABASE_HOST", "localhost")
    db_port = os.getenv("DATABASE_PORT", "5432")
    db_name = os.getenv("DATABASE_NAME", "nagare")
    db_user = os.getenv("DATABASE_USER", "nagare_user")
    db_password = os.getenv("DATABASE_PASSWORD", "")

    # パスワードをURLエンコード（特殊文字対策）
    db_url = f"postgresql://{db_user}:{quote_plus(db_password)}@{db_host}:{db_port}/{db_name}"
    return create_engine(db_url, pool_pre_ping=True)


@st.cache_resource
def get_github_client():
    """GitHubクライアントを取得する"""
    try:
        return GitHubClient()
    except ValueError as e:
        st.error(f"GitHub認証エラー: {e}")
        st.info("GitHub API機能を使用するには、環境変数を設定してください。")
        return None


def fetch_github_repositories(
    search_type: str, search_value: str, page: int = 1, per_page: int = 30
):
    """GitHubからリポジトリを取得する（ページング対応）

    Args:
        search_type: "organization", "user", "search"のいずれか
        search_value: 組織名、ユーザー名、または検索クエリ
        page: ページ番号（1から開始）
        per_page: 1ページあたりの件数

    Returns:
        辞書形式の検索結果、またはエラー時はNone
        - repos: リポジトリリスト
        - page: ページ番号
        - per_page: 1ページあたりの件数
        - has_next: 次のページがあるか
        - total_count: 総数（search_repositoriesのみ）
    """
    github_client = get_github_client()
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


def add_repository(repo_name: str, source: str = "github_actions"):
    """リポジトリを追加する"""
    engine = get_database_engine()
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


# メインUI
st.title("🌊 Nagare 管理画面")
st.markdown("CI/CD監視システムの管理インターフェース")

# サイドバー
with st.sidebar:
    st.header("ナビゲーション")
    page = st.radio(
        "ページ選択",
        ["📊 ダッシュボード", "📦 リポジトリ管理", "📈 実行履歴"],
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
                if row["ステータス"] == "success":
                    return ["background-color: #d4edda"] * len(row)
                elif row["ステータス"] == "failure":
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
    with st.expander("➕ リポジトリを手動で追加", expanded=False):
        with st.form("add_repository_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                new_repo = st.text_input(
                    "リポジトリ名",
                    placeholder="owner/repo",
                    help="GitHub リポジトリを 'owner/repo' 形式で入力",
                )
            with col2:
                source = st.selectbox("ソース", ["github_actions"], disabled=True)

            submitted = st.form_submit_button("追加", type="primary")

            if submitted:
                if new_repo and "/" in new_repo:
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
                    st.error("リポジトリ名を 'owner/repo' 形式で入力してください")

    # GitHubから検索して追加
    with st.expander("🔍 GitHubから検索して追加", expanded=False):
        st.markdown("**GitHub APIからリポジトリを検索**")

        # ページング用のセッションステート初期化
        if "gh_search_page" not in st.session_state:
            st.session_state.gh_search_page = 1
        if "gh_search_result" not in st.session_state:
            st.session_state.gh_search_result = None
        if "gh_search_params" not in st.session_state:
            st.session_state.gh_search_params = {}

        # 検索条件
        col1, col2 = st.columns([3, 1])
        with col1:
            search_type = st.radio(
                "検索方法",
                ["organization", "user", "search"],
                format_func=lambda x: {
                    "organization": "組織名で検索",
                    "user": "ユーザー名で検索",
                    "search": "キーワード検索"
                }[x],
                horizontal=True,
                key="search_type_radio"
            )
        with col2:
            per_page = st.selectbox(
                "表示件数",
                options=[10, 20, 30, 50],
                index=2,
                key="per_page_select"
            )

        if search_type in ["organization", "user"]:
            search_value = st.text_input(
                f"{search_type.capitalize()}名を入力",
                placeholder="organization-name" if search_type == "organization" else "username",
                key=f"{search_type}_input"
            )
        else:
            search_value = st.text_input(
                "検索クエリ",
                placeholder="例: org:myorg language:python",
                help="GitHub検索構文を使用できます",
                key="search_input"
            )

        search_button = st.button("検索", type="primary", key="search_github")

        # 新規検索の場合
        if search_button and search_value:
            st.session_state.gh_search_page = 1
            st.session_state.gh_search_params = {
                "search_type": search_type,
                "search_value": search_value,
                "per_page": per_page
            }
            with st.spinner("GitHubから取得中..."):
                result = fetch_github_repositories(
                    search_type, search_value, page=1, per_page=per_page
                )
                st.session_state.gh_search_result = result

        # 検索結果表示
        result = st.session_state.gh_search_result
        if result and "repos" in result:
            repos = result["repos"]
            current_page = result["page"]
            has_next = result["has_next"]
            total_count = result.get("total_count")

            # ヘッダー情報
            if total_count is not None:
                st.success(f"検索結果: 全{total_count}件 （ページ {current_page}）")
            else:
                st.success(f"{len(repos)}件のリポジトリが見つかりました （ページ {current_page}）")

            if repos:
                # リポジトリ選択用のセッションステート
                if "selected_repos" not in st.session_state:
                    st.session_state.selected_repos = set()

                # リポジトリ一覧表示
                for repo in repos:
                    col1, col2, col3 = st.columns([1, 6, 2])

                    with col1:
                        is_selected = st.checkbox(
                            "選択",
                            key=f"select_{repo['full_name']}_{current_page}",
                            label_visibility="collapsed"
                        )
                        if is_selected:
                            st.session_state.selected_repos.add(repo['full_name'])
                        elif repo['full_name'] in st.session_state.selected_repos:
                            st.session_state.selected_repos.remove(repo['full_name'])

                    with col2:
                        private_badge = "🔒" if repo.get("private") else "🌐"
                        st.markdown(f"**{private_badge} [{repo['full_name']}]({repo['html_url']})**")
                        if repo.get("description"):
                            st.caption(repo["description"])

                        # メタ情報
                        meta_info = []
                        if repo.get("language"):
                            meta_info.append(f"🔤 {repo['language']}")
                        if repo.get("stargazers_count") is not None:
                            meta_info.append(f"⭐ {repo['stargazers_count']}")
                        if repo.get("forks_count") is not None:
                            meta_info.append(f"🍴 {repo['forks_count']}")
                        if meta_info:
                            st.caption(" • ".join(meta_info))

                    with col3:
                        if st.button("追加", key=f"add_{repo['full_name']}_{current_page}"):
                            try:
                                success, message = add_repository(repo['full_name'], "github_actions")
                                if success:
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.warning(message)
                            except Exception as e:
                                st.error(f"追加エラー: {e}")

                    st.divider()

                # ページングボタン
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if current_page > 1:
                        if st.button("⬅️ 前のページ", key="prev_page"):
                            params = st.session_state.gh_search_params
                            st.session_state.gh_search_page = current_page - 1
                            with st.spinner("読み込み中..."):
                                result = fetch_github_repositories(
                                    params["search_type"],
                                    params["search_value"],
                                    page=current_page - 1,
                                    per_page=params["per_page"]
                                )
                                st.session_state.gh_search_result = result
                            st.rerun()

                with col2:
                    st.markdown(f"<center>ページ {current_page}</center>", unsafe_allow_html=True)

                with col3:
                    if has_next:
                        if st.button("次のページ ➡️", key="next_page"):
                            params = st.session_state.gh_search_params
                            st.session_state.gh_search_page = current_page + 1
                            with st.spinner("読み込み中..."):
                                result = fetch_github_repositories(
                                    params["search_type"],
                                    params["search_value"],
                                    page=current_page + 1,
                                    per_page=params["per_page"]
                                )
                                st.session_state.gh_search_result = result
                            st.rerun()

                # 一括追加ボタン
                if st.session_state.selected_repos:
                    st.divider()
                    st.markdown(f"**選択中: {len(st.session_state.selected_repos)}件**")
                    if st.button("選択したリポジトリを一括追加", type="primary", key="batch_add"):
                        success_count = 0
                        error_count = 0
                        for repo_name in st.session_state.selected_repos:
                            try:
                                success, _ = add_repository(repo_name, "github_actions")
                                if success:
                                    success_count += 1
                                else:
                                    error_count += 1
                            except Exception:
                                error_count += 1

                        if success_count > 0:
                            st.success(f"{success_count}件のリポジトリを追加しました")
                        if error_count > 0:
                            st.warning(f"{error_count}件のリポジトリは追加できませんでした（既存またはエラー）")

                        st.session_state.selected_repos.clear()
                        st.rerun()
            else:
                st.info("このページにリポジトリがありません")
        elif result is not None:
            st.info("リポジトリが見つかりませんでした")

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
                if val == "success":
                    return "background-color: #d4edda"
                elif val == "failure":
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
