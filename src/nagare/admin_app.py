#!/usr/bin/env python3
"""Streamlit管理画面

リポジトリの追加・削除・有効化/無効化、データ収集状況の確認を行うWeb UI。

Usage:
    streamlit run src/nagare/admin_app.py --server.port 8501
"""

import os
import platform as platform_module
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

from nagare.admin_db import (
    _add_repositories_batch,
    add_repository,
    fetch_repositories_unified,
    get_all_cicd_connections,
    get_connections,
    get_database_engine,
    get_recent_pipeline_runs,
    get_registered_repository_names,
    get_repositories,
    test_connection,
    toggle_repository,
)
from nagare.admin_metrics_db import (
    get_l1_daily_overview,
    get_l1_daily_overview_by_platform,
    get_l1_repo_deterioration,
    get_l1_repo_health,
    get_l2_action_candidates,
    get_l2_failure_reason_breakdown,
    get_l2_repo_trend,
    get_l2_retry_flake_trend,
    get_l2_step_failure_heatmap,
    get_l2_workflow_duration_top,
    get_l2_workflow_fail_top,
    get_metrics_last_refresh,
    list_repo_names_for_metrics,
)
from nagare.constants import PipelineStatus, Platform, SourceType
from nagare.utils.connections import ConnectionRegistry

# Connection設定ファイルの読み込み
connection_load_error = None
connections_file = os.getenv("NAGARE_CONNECTIONS_FILE")
if connections_file and Path(connections_file).exists():
    try:
        ConnectionRegistry.from_file(connections_file)
    except ValueError as e:
        # 環境変数が設定されていない場合でもアプリは起動
        connection_load_error = str(e)
    except Exception as e:
        connection_load_error = f"設定ファイル読み込みエラー: {e}"

# ページ設定
st.set_page_config(
    page_title="Nagare 管理画面",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
        st.info(f"検索結果: 全{total_count}件 （ページ {current_page}）")
    else:
        st.info(f"{len(items)}件が見つかりました （ページ {current_page}）")

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
            if platform == Platform.GITHUB and item["metadata"].get("private"):
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
    nav_key = f"{session_key_prefix}_nav"
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if current_page > 1:
            if st.button("⬅️ 前のページ", key=f"{session_key_prefix}_prev"):
                st.session_state[nav_key] = "prev"
    with col2:
        st.write(f"ページ {current_page}")
    with col3:
        if has_next:
            if st.button("次のページ ➡️", key=f"{session_key_prefix}_next"):
                st.session_state[nav_key] = "next"

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


# メインUI
st.title("🌊 Nagare 管理画面")
st.markdown("CI/CD監視システムの管理インターフェース")

# Connection読み込みエラーの表示
if connection_load_error:
    st.error(
        f"⚠️ **Connection設定の読み込みエラー**\n\n{connection_load_error}\n\n"
        "**対処方法:**\n"
        "- 未使用のプラットフォーム（Bitrise/Xcode Cloud）の設定を `connections.yml` でコメントアウト\n"
        "- または、必要な環境変数を `.env` ファイルに設定\n"
        "- 設定後、ページをリロードしてください"
    )
    st.info(
        "💡 一部の機能（該当プラットフォームのリポジトリ検索など）が利用できませんが、"
        "アプリは起動しています。"
    )

# サイドバー
with st.sidebar:
    st.header("ナビゲーション")
    page = st.radio(
        "ページ選択",
        ["📊 メトリクス (L1/L2)", "📦 リポジトリ管理", "📈 実行履歴", "⚙️ 設定"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Powered by Streamlit")

# メトリクス（L1 / L2）
if page == "📊 メトリクス (L1/L2)":
    st.header("📊 CI/CD メトリクス（日次レビュー向け）")

    try:
        last_refresh = get_metrics_last_refresh()
        if last_refresh:
            st.caption(f"集約の最終更新（参考）: {last_refresh}")

        trend_days = st.slider("トレンド表示日数", min_value=7, max_value=90, value=30, step=1)

        st.subheader("L1 — トレンド")
        daily = get_l1_daily_overview(days=trend_days)
        if daily.empty:
            st.warning(
                "メトリクスデータがありません。`refresh_cicd_metrics_marts` DAG または "
                "`SELECT refresh_cicd_metrics_marts();` を実行し、パイプライン実行を取り込んでください。"
            )
        else:
            last_row = daily.iloc[-1]
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("総実行数（最終日）", int(last_row["total_runs"]))
            with c2:
                st.metric("成功率（最終日）", f"{last_row['success_rate_pct']}%")
            with c3:
                st.metric("失敗数（最終日）", int(last_row["failed_runs"]))
            with c4:
                p50 = last_row["avg_p50_duration_ms"]
                st.metric(
                    "平均p50相当(ms)",
                    f"{int(p50)}" if pd.notna(p50) else "N/A",
                )

            st.markdown("**トレンド（プラットフォーム別 / ALL）** — 下段は左: 成功率・右: 実行数")
            daily_pf = get_l1_daily_overview_by_platform(days=trend_days)
            if daily_pf.empty:
                st.info("プラットフォーム別トレンド用データがありません")
            else:
                l1_mode = st.radio(
                    "表示モード",
                    [
                        "すべて（凡例: 各platform + ALL）",
                        "ALL（全体合計）のみ",
                        "1プラットフォームのみ",
                    ],
                    horizontal=True,
                    key="l1_platform_trend_mode",
                )
                if l1_mode == "ALL（全体合計）のみ":
                    pf = daily_pf[daily_pf["platform"] == "ALL"].copy()
                elif l1_mode == "1プラットフォームのみ":
                    choices = sorted(
                        x for x in daily_pf["platform"].unique() if x != "ALL"
                    )
                    if not choices:
                        st.info("platform 行がありません")
                        pf = daily_pf.iloc[0:0]
                    else:
                        one = st.selectbox("プラットフォーム", choices, key="l1_one_platform")
                        pf = daily_pf[daily_pf["platform"] == one].copy()
                else:
                    pf = daily_pf.copy()

                if not pf.empty:
                    l1_t_left, l1_t_right = st.columns(2)
                    if l1_mode == "すべて（凡例: 各platform + ALL）":
                        sr = pf.pivot(
                            index="metric_date",
                            columns="platform",
                            values="success_rate_pct",
                        )
                        tr = pf.pivot(
                            index="metric_date",
                            columns="platform",
                            values="total_runs",
                        )
                        with l1_t_left:
                            st.markdown("**L1 成功率トレンド**")
                            st.caption("成功率(%)")
                            st.line_chart(sr)
                        with l1_t_right:
                            st.markdown("**L1 実行数トレンド**")
                            st.caption("実行数")
                            st.bar_chart(tr)
                    else:
                        with l1_t_left:
                            st.markdown("**L1 成功率トレンド**")
                            st.line_chart(
                                pf.set_index("metric_date")["success_rate_pct"].rename(
                                    "成功率(%)"
                                )
                            )
                        with l1_t_right:
                            st.markdown("**L1 実行数トレンド**")
                            st.bar_chart(
                                pf.set_index("metric_date")["total_runs"].rename(
                                    "実行数"
                                )
                            )

        st.divider()
        st.subheader("L1 — ヘルス")
        health = get_l1_repo_health()
        if not health.empty:
            st.dataframe(health, use_container_width=True, hide_index=True)
        else:
            st.info("ヘルスデータなし")

        st.markdown("**悪化フラグ付きリポジトリ**")
        det = get_l1_repo_deterioration()
        if not det.empty:
            st.dataframe(det, use_container_width=True, hide_index=True)
        else:
            st.info("悪化ビューに行がありません（昨日の集計がない可能性）")

        st.divider()
        st.subheader("L2 — リポジトリ詳細")
        repos = list_repo_names_for_metrics()
        if not repos:
            st.info("dim_repo にデータがありません（同期未実行の可能性）")
        else:
            selected_repo = st.selectbox("リポジトリを選択", repos, key="metrics_repo_l2")
            if selected_repo:
                l2c1, l2c2 = st.columns(2)
                with l2c1:
                    st.markdown("**L2 トレンド**")
                    tr = get_l2_repo_trend(selected_repo, days=trend_days)
                    if not tr.empty:
                        st.line_chart(
                            tr.set_index("metric_date")[
                                ["success_rate_pct", "p95_duration_ms"]
                            ].rename(
                                columns={
                                    "success_rate_pct": "成功率(%)",
                                    "p95_duration_ms": "p95(ms)",
                                }
                            )
                        )
                        with st.expander("日次データ（表）", expanded=False):
                            st.dataframe(tr, use_container_width=True, hide_index=True)
                    else:
                        st.info("このリポジトリの日次トレンドがありません")
                with l2c2:
                    st.markdown("**L2 ワークフロー**")
                    st.caption("失敗の多いワークフロー")
                    st.dataframe(
                        get_l2_workflow_fail_top(selected_repo),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption("実行時間の長いワークフロー")
                    st.dataframe(
                        get_l2_workflow_duration_top(selected_repo),
                        use_container_width=True,
                        hide_index=True,
                    )

                l2b1, l2b2, l2b3 = st.columns(3)
                with l2b1:
                    st.markdown("**L2 失敗**")
                    st.caption("失敗理由内訳")
                    st.dataframe(
                        get_l2_failure_reason_breakdown(selected_repo),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption("ステップ失敗")
                    st.dataframe(
                        get_l2_step_failure_heatmap(selected_repo),
                        use_container_width=True,
                        hide_index=True,
                    )
                with l2b2:
                    st.markdown("**L2 再実行**")
                    rtry = get_l2_retry_flake_trend(selected_repo)
                    if not rtry.empty:
                        st.line_chart(
                            rtry.set_index("run_date")["retry_rate_pct"].rename(
                                "再実行率(%)"
                            )
                        )
                        st.dataframe(rtry, use_container_width=True, hide_index=True)
                    else:
                        st.info("再実行トレンドデータがありません")
                with l2b3:
                    st.markdown("**L2 アクション**")
                    st.dataframe(
                        get_l2_action_candidates(selected_repo),
                        use_container_width=True,
                        hide_index=True,
                    )

    except Exception as e:
        st.error(f"メトリクス取得エラー: {e}")
        st.info(
            "初回は `docker compose` の airflow-init で metrics v2 SQL が適用されているか、"
            "Superset 手順書の SQL 適用を確認してください。"
        )

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
                    placeholder="owner/repo（GitHub）またはapp_id（Xcode Cloud）またはapp-slug（Bitrise）",
                    help="GitHub: 'owner/repo' 形式、Xcode Cloud: app ID、Bitrise: app-slug",
                )
            with col2:
                source = st.selectbox(
                    "プラットフォーム",
                    ["github_actions", "xcode_cloud", "bitrise"],
                    format_func=lambda x: {
                        SourceType.GITHUB_ACTIONS: "GitHub Actions",
                        SourceType.XCODE_CLOUD: "Xcode Cloud",
                        SourceType.BITRISE: "Bitrise"
                    }.get(x, x)
                )

            submitted = st.form_submit_button("追加", type="primary")

            if submitted:
                if new_repo:
                    try:
                        success, message = add_repository(new_repo, source)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.warning(message)
                    except ValueError as e:
                        st.error(f"入力エラー: {e}")
                    except Exception as e:
                        st.error(f"追加エラー: {e}")
                else:
                    st.error("リポジトリ/アプリ名を入力してください")

    # 統一検索UI（GitHub + Bitrise + Xcode Cloud）
    with st.expander("🔍 リポジトリ/アプリを検索して追加", expanded=True):
        st.markdown("**CI/CD Connectionから検索**")

        # Connection選択
        available_connections = get_all_cicd_connections()
        if not available_connections:
            st.warning("⚠️ GitHub/Bitrise/Xcode Cloud Connectionが登録されていません")
            st.info("⚙️ 設定ページでGitHub/Bitrise/Xcode Cloud Connectionの状態を確認してください")
        else:
            col_conn, col_per_page = st.columns([3, 1])
            with col_conn:
                selected_conn = st.selectbox(
                    "使用するConnection",
                    options=range(len(available_connections)),
                    format_func=lambda i: f"{available_connections[i][0]} (conn_type: {available_connections[i][2]})",
                    key="unified_connection_select"
                )
                conn_id = available_connections[selected_conn][0]
                platform = available_connections[selected_conn][2]

            with col_per_page:
                per_page = st.selectbox("表示件数", options=[10, 20, 30, 50], index=2, key="unified_per_page")

            # プラットフォーム表示
            platform_icons = {
                Platform.GITHUB: "📦",
                Platform.BITRISE: "📱",
                Platform.XCODE_CLOUD: "🍎"
            }
            platform_names = {
                Platform.GITHUB: "GitHub Actions",
                Platform.BITRISE: "Bitrise",
                Platform.XCODE_CLOUD: "Xcode Cloud"
            }
            platform_icon = platform_icons.get(platform, "📦")
            platform_name = platform_names.get(platform, platform)
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

            elif platform == Platform.BITRISE:
                search_params["conn_id"] = conn_id
                st.info("📱 Bitriseアプリ一覧を取得します")

            elif platform == Platform.XCODE_CLOUD:
                search_params["conn_id"] = conn_id
                st.info("🍎 Xcode Cloudアプリ一覧を取得します")

            # 検索ボタン
            can_search = (
                (platform == Platform.GITHUB and search_params.get("search_value")) or
                platform == Platform.BITRISE or
                platform == Platform.XCODE_CLOUD
            )
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
                nav_key = f"unified_{conn_id}_nav"
                render_repository_list(state["result"], platform, f"unified_{conn_id}")

                # ページング処理
                action = st.session_state.get(nav_key)
                if action == "prev" and state["page"] > 1:
                    st.session_state[nav_key] = None
                    state["page"] -= 1
                    params = state["params"]
                    with st.spinner("読み込み中..."):
                        result = fetch_repositories_unified(
                            params["platform"], params["search_params"], page=state["page"], per_page=params["per_page"]
                        )
                        state["result"] = result
                    st.rerun()

                elif action == "next":
                    st.session_state[nav_key] = None
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
                repos_df = repos_df[repos_df["有効"]]
            elif status_filter == "無効のみ":
                repos_df = repos_df[~repos_df["有効"]]

            st.caption(f"全{len(repos_df)}件")

            # リポジトリ一覧表示と操作
            for _idx, row in repos_df.iterrows():
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
                status = val.upper() if isinstance(val, str) else ""
                if status == PipelineStatus.SUCCESS:
                    return "background-color: #d4edda"
                elif status == PipelineStatus.FAILURE:
                    return "background-color: #f8d7da"
                else:
                    return ""

            st.dataframe(
                filtered_df.style.map(color_status, subset=["ステータス"]),
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

            # Xcode Cloud接続設定
            st.markdown("### Xcode Cloud接続設定")
            try:
                xcode_conn = ConnectionRegistry.get_xcode_cloud()

                col1, col2 = st.columns([1, 3])
                with col1:
                    st.metric("ベースURL", xcode_conn.base_url)
                with col2:
                    if xcode_conn.key_id and xcode_conn.issuer_id:
                        masked_key = xcode_conn.key_id[:4] + "..." + xcode_conn.key_id[-4:] if len(xcode_conn.key_id) > 8 else "***"
                        st.code(f"Key ID: {masked_key}\nIssuer ID: {xcode_conn.issuer_id}", language="text")
                        if xcode_conn.private_key:
                            st.caption("✅ Private Key loaded")
                        elif xcode_conn.private_key_path:
                            st.caption(f"📁 Private Key Path: {xcode_conn.private_key_path}")

            except Exception as e:
                st.warning(f"⚠️ Xcode Cloud設定が読み込まれていません\n\n詳細: {e}")
                st.info("💡 Xcode Cloudを使用する場合は、.envにAPPSTORE_*変数を設定してください")

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

            st.divider()

            # 全接続の一覧
            st.markdown("### 読み込まれた全接続")

            all_connections = ConnectionRegistry.get_all_connections()
            failed_connections = ConnectionRegistry.get_failed_connections()
            total_connections = len(all_connections) + len(failed_connections)

            if total_connections > 0:
                st.success(f"✅ {len(all_connections)}件が読み込まれました" +
                          (f" / ⚠️ {len(failed_connections)}件が失敗" if failed_connections else ""))

                # テーブル形式で表示
                conn_data = []

                # 成功した接続
                for conn_id, conn_obj in all_connections.items():
                    conn_type = type(conn_obj).__name__
                    platform = conn_obj.get_platform() if hasattr(conn_obj, 'get_platform') else 'unknown'
                    description = getattr(conn_obj, 'description', '-')

                    conn_data.append({
                        "conn_id": conn_id,
                        "conn_type": conn_type,
                        "platform": platform,
                        "status": "✅ OK",
                        "description": description if description else '-'
                    })

                # 失敗した接続
                for conn_id, failed_info in failed_connections.items():
                    conn_data.append({
                        "conn_id": conn_id,
                        "conn_type": failed_info["conn_type"],
                        "platform": failed_info["platform"],
                        "status": "⚠️ エラー",
                        "description": failed_info["error"][:80] + "..."
                    })

                df = pd.DataFrame(conn_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 読み込まれた接続がありません")

            # CI/CD接続の一覧
            st.markdown("### CI/CD接続（検索可能）")
            cicd_connections = get_all_cicd_connections()
            if cicd_connections:
                st.success(f"✅ {len(cicd_connections)}件のCI/CD接続が利用可能です")

                cicd_data = []
                for conn_id, description, platform in cicd_connections:
                    cicd_data.append({
                        "conn_id": conn_id,
                        "platform": platform,
                        "description": description if description else '-',
                        "display": f"{conn_id} (conn_type: {platform})"
                    })

                df_cicd = pd.DataFrame(cicd_data)
                st.dataframe(df_cicd, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 利用可能なCI/CD接続がありません")

            st.divider()

            # Airflow Connections一覧と接続テスト
            st.markdown("### Airflow Connections接続テスト")
            st.caption("データベースに登録されている接続の動作確認ができます")

            try:
                conns_df = get_connections()

                if not conns_df.empty:
                    st.caption(f"全{len(conns_df)}件のConnectionが登録されています")

                    # Connections一覧表示
                    for _idx, row in conns_df.iterrows():
                        with st.container():
                            col1, col2 = st.columns([2, 1])

                            with col1:
                                st.markdown(f"**🔌 {row['Connection ID']}** (Type: {row['Type']})")
                                if row['Description']:
                                    st.caption(f"📝 {row['Description']}")

                                # 接続情報を簡潔に表示
                                info_parts = []
                                if row['Host']:
                                    info_parts.append(f"🖥️ {row['Host']}")
                                if row['Port']:
                                    info_parts.append(f":{row['Port']}")
                                if row['Login']:
                                    info_parts.append(f"👤 {row['Login']}")
                                if row['Schema']:
                                    info_parts.append(f"🗄️ {row['Schema']}")

                                if info_parts:
                                    st.caption(" | ".join(info_parts))

                            with col2:
                                # 接続テストボタン
                                if st.button("🔍 接続テスト", key=f"test_conn_{row['ID']}", use_container_width=True):
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
                                                with st.expander("詳細情報"):
                                                    st.json(details)
                                        else:
                                            st.error("Connection情報の取得に失敗しました")

                            st.divider()
                else:
                    st.info("登録されているConnectionがありません")

            except Exception as e:
                st.error(f"Connections取得エラー: {e}")

        else:
            st.warning("⚠️ 設定ファイルが見つかりません")
            if connections_file:
                st.code(f"探索パス: {connections_file}", language="text")
            else:
                st.info("環境変数 `NAGARE_CONNECTIONS_FILE` が設定されていません")

    # タブ2: システム情報
    with tab2:
        st.subheader("システム情報")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Python**")
            st.code(f"Version: {sys.version.split()[0]}\nPath: {sys.executable}", language="text")

            st.markdown("**プラットフォーム**")
            st.code(f"OS: {platform_module.system()}\nVersion: {platform_module.release()}", language="text")

        with col2:
            st.markdown("**環境変数**")
            env_vars = {
                "NAGARE_CONNECTIONS_FILE": os.getenv("NAGARE_CONNECTIONS_FILE", "Not set"),
                "AIRFLOW_HOME": os.getenv("AIRFLOW_HOME", "Not set"),
            }
            for key, value in env_vars.items():
                st.code(f"{key}={value}", language="text")
