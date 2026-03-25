"""Streamlit メトリクス画面用の DB クエリ（v2 ビュー）。"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import text

from nagare.admin_db import get_database_engine


def _jst_today() -> date:
    """テスト容易性のため UTC 基準の今日（UI は日付フィルタで補正）。"""
    return date.today()


@st.cache_data(ttl=60)
def get_metrics_last_refresh() -> str | None:
    """集約テーブルの最終計算時刻（代表値）。"""
    engine = get_database_engine()
    q = text(
        """
        SELECT MAX(computed_at)::text FROM agg_daily_repo_metrics
        """
    )
    with engine.connect() as conn:
        row = conn.execute(q).fetchone()
        return row[0] if row and row[0] else None


@st.cache_data(ttl=60)
def get_l1_daily_overview(days: int = 30) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT metric_date, total_runs, success_runs, failed_runs,
               success_rate_pct, avg_p50_duration_ms, last_computed_at
        FROM vw_l1_daily_overview
        WHERE metric_date >= :start
        ORDER BY metric_date ASC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"start": start})


@st.cache_data(ttl=60)
def get_l1_daily_overview_by_platform(days: int = 30) -> pd.DataFrame:
    """プラットフォーム別行 + platform='ALL' の合計行。"""
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT metric_date, platform, total_runs, success_runs, failed_runs,
               success_rate_pct, avg_p50_duration_ms, last_computed_at
        FROM vw_l1_daily_overview_by_platform
        WHERE metric_date >= :start
        ORDER BY metric_date ASC, platform ASC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"start": start})


@st.cache_data(ttl=60)
def get_l1_repo_health() -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT repo_full_name, platform, is_active, total_runs_7d,
               success_rate_7d_pct, avg_p95_ms_7d, last_computed_at
        FROM vw_l1_repo_health
        ORDER BY success_rate_7d_pct ASC NULLS LAST, total_runs_7d DESC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn)


@st.cache_data(ttl=60)
def get_l1_repo_deterioration() -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT repo_full_name, platform, success_rate_yesterday,
               success_rate_day_before, success_rate_delta_1d,
               avg_success_rate_7d, success_rate_vs_7d_avg,
               p95_ms_yesterday, p95_ms_day_before, failed_runs_yesterday,
               total_runs_yesterday, deterioration_flag, last_computed_at
        FROM vw_l1_repo_deterioration
        ORDER BY deterioration_flag DESC, failed_runs_yesterday DESC NULLS LAST
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn)


@st.cache_data(ttl=60)
def get_l2_repo_trend(repo_full_name: str, days: int = 30) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT metric_date, total_runs, success_runs, failed_runs,
               success_rate_pct, p50_duration_ms, p95_duration_ms,
               retry_runs, retry_rate_pct, flake_suspect_rate_pct, computed_at
        FROM vw_l2_repo_trend
        WHERE repo_full_name = :repo AND metric_date >= :start
        ORDER BY metric_date ASC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(
            q, conn, params={"repo": repo_full_name, "start": start}
        )


@st.cache_data(ttl=60)
def get_l2_workflow_fail_top(repo_full_name: str) -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT workflow_name, total_runs, failure_count, failure_rate_pct, last_failure_at
        FROM vw_l2_workflow_fail_top
        WHERE repo_full_name = :repo
        ORDER BY failure_count DESC
        LIMIT 20
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"repo": repo_full_name})


@st.cache_data(ttl=60)
def get_l2_workflow_duration_top(repo_full_name: str) -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT workflow_name, total_runs, p50_duration_ms, p95_duration_ms, avg_duration_ms
        FROM vw_l2_workflow_duration_top
        WHERE repo_full_name = :repo
        ORDER BY p95_duration_ms DESC NULLS LAST
        LIMIT 20
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"repo": repo_full_name})


@st.cache_data(ttl=60)
def get_l2_step_failure_heatmap(repo_full_name: str) -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT run_date, step_name, step_runs, step_failures, step_failure_rate_pct
        FROM vw_l2_step_failure_heatmap
        WHERE repo_full_name = :repo
        ORDER BY run_date DESC, step_failures DESC
        LIMIT 500
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"repo": repo_full_name})


@st.cache_data(ttl=60)
def get_l2_failure_reason_breakdown(repo_full_name: str) -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT fail_date, reason_category, reason_subcategory, failure_runs
        FROM vw_l2_failure_reason_breakdown
        WHERE repo_full_name = :repo
        ORDER BY fail_date DESC, failure_runs DESC
        LIMIT 200
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"repo": repo_full_name})


@st.cache_data(ttl=60)
def get_l2_retry_flake_trend(repo_full_name: str, days: int = 90) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT run_date, total_runs, retry_runs, retry_rate_pct, flake_suspect_rate_pct
        FROM vw_l2_retry_flake_trend
        WHERE repo_full_name = :repo AND run_date >= :start
        ORDER BY run_date ASC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(
            q, conn, params={"repo": repo_full_name, "start": start}
        )


@st.cache_data(ttl=60)
def get_l2_action_candidates(repo_full_name: str) -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT target_workflow, failure_count, failure_rate_pct, last_failure_at,
               suggested_action, priority_rank
        FROM vw_l2_action_candidates
        WHERE repo_full_name = :repo
        ORDER BY priority_rank ASC, failure_count DESC
        LIMIT 20
        """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(q, conn, params={"repo": repo_full_name})


@st.cache_data(ttl=120)
def list_repo_names_for_metrics() -> list[str]:
    engine = get_database_engine()
    q = text(
        """
        SELECT DISTINCT repo_full_name FROM dim_repo WHERE is_active = TRUE
        ORDER BY repo_full_name
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()
        return [r[0] for r in rows]
