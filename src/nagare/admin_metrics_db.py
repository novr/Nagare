"""管理画面メトリクス用クエリ（`vw_l1_*` / `vw_l2_*`）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.engine import Engine

from nagare.admin_db import get_database_engine


def _dataframe_from_sql(
    engine: Engine,
    statement: Any,
    params: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """SQLAlchemy 経由で SELECT 結果を DataFrame にする。

    pandas 3.x の ``read_sql_query`` は ``con`` の型判定で SQLite 実装に落ち、
    ``sqlalchemy.text()`` 実行時に *Query must be a string unless using sqlalchemy*
    となることがあるため、pandas の SQL 層を使わない。
    """
    bind = dict(params) if params else {}
    with engine.connect() as conn:
        result = conn.execute(statement, bind)
        columns: list[str] = list(result.keys())
        rows = result.fetchall()
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([tuple(row) for row in rows], columns=columns)


def _jst_today() -> date:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date()


@st.cache_data(ttl=60)
def get_metrics_last_refresh() -> str | None:
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
    return _dataframe_from_sql(engine, q, params={"start": start})


@st.cache_data(ttl=60)
def get_l1_daily_overview_by_platform(days: int = 30) -> pd.DataFrame:
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
    return _dataframe_from_sql(engine, q, params={"start": start})


@st.cache_data(ttl=60)
def get_l1_daily_overview_by_project(days: int = 30) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT metric_date, project_name, total_runs, success_runs, failed_runs,
               success_rate_pct, avg_p50_duration_ms, last_computed_at
        FROM vw_l1_daily_overview_by_project
        WHERE metric_date >= :start
        ORDER BY metric_date ASC, project_name ASC
        """
    )
    return _dataframe_from_sql(engine, q, params={"start": start})


@st.cache_data(ttl=60)
def get_l1_daily_overview_by_tag(days: int = 30) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT metric_date, tag_slug, tag_name, total_runs, success_runs, failed_runs,
               success_rate_pct, avg_p50_duration_ms, last_computed_at
        FROM vw_l1_daily_overview_by_tag
        WHERE metric_date >= :start
        ORDER BY metric_date ASC, tag_slug ASC
        """
    )
    return _dataframe_from_sql(engine, q, params={"start": start})


@st.cache_data(ttl=60)
def get_l1_repo_health() -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT repo_full_name, platform, is_active, project_name, tag_slugs, total_runs_7d,
               success_rate_7d_pct, avg_p95_ms_7d, last_computed_at
        FROM vw_l1_repo_health
        ORDER BY success_rate_7d_pct ASC NULLS LAST, total_runs_7d DESC
        """
    )
    return _dataframe_from_sql(engine, q)


@st.cache_data(ttl=60)
def get_l1_repo_deterioration() -> pd.DataFrame:
    engine = get_database_engine()
    q = text(
        """
        SELECT repo_full_name, platform, success_rate_yesterday,
               success_rate_day_before, success_rate_delta_1d,
               avg_success_rate_7d, success_rate_vs_7d_avg,
               p95_ms_yesterday, p95_ms_day_before, failed_runs_yesterday,
               total_runs_yesterday, deterioration_flag, last_computed_at,
               project_name, tag_slugs
        FROM vw_l1_repo_deterioration
        ORDER BY deterioration_flag DESC, failed_runs_yesterday DESC NULLS LAST
        """
    )
    return _dataframe_from_sql(engine, q)


@st.cache_data(ttl=60)
def get_l2_repo_trend(repo_full_name: str, days: int = 30) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT metric_date, total_runs, success_runs, failed_runs,
               success_rate_pct, p50_duration_ms, p95_duration_ms,
               retry_runs, retry_rate_pct, computed_at
        FROM vw_l2_repo_trend
        WHERE repo_full_name = :repo AND metric_date >= :start
        ORDER BY metric_date ASC
        """
    )
    return _dataframe_from_sql(
        engine, q, params={"repo": repo_full_name, "start": start}
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
    return _dataframe_from_sql(engine, q, params={"repo": repo_full_name})


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
    return _dataframe_from_sql(engine, q, params={"repo": repo_full_name})


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
    return _dataframe_from_sql(engine, q, params={"repo": repo_full_name})


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
    return _dataframe_from_sql(engine, q, params={"repo": repo_full_name})


@st.cache_data(ttl=60)
def get_l2_retry_flake_trend(repo_full_name: str, days: int = 90) -> pd.DataFrame:
    engine = get_database_engine()
    start = _jst_today() - timedelta(days=days)
    q = text(
        """
        SELECT run_date, total_runs, retry_runs, retry_rate_pct
        FROM vw_l2_retry_flake_trend
        WHERE repo_full_name = :repo AND run_date >= :start
        ORDER BY run_date ASC
        """
    )
    return _dataframe_from_sql(
        engine, q, params={"repo": repo_full_name, "start": start}
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
    return _dataframe_from_sql(engine, q, params={"repo": repo_full_name})


def _tag_slugs_set(raw: object) -> set[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return set()
    s = str(raw).strip()
    if not s:
        return set()
    return {x.strip() for x in s.split(",") if x.strip()}


@st.cache_data(ttl=120)
def list_metrics_project_labels() -> list[str]:
    engine = get_database_engine()
    q = text(
        """
        SELECT DISTINCT COALESCE(project_name, '(未所属)') AS pl
        FROM dim_repo
        WHERE is_active = TRUE
        ORDER BY pl
        """
    )
    with engine.connect() as conn:
        return [str(r[0]) for r in conn.execute(q).fetchall()]


@st.cache_data(ttl=120)
def list_metrics_tag_slugs() -> list[tuple[str, str]]:
    engine = get_database_engine()
    q = text(
        """
        SELECT slug, name FROM tags ORDER BY slug
        """
    )
    with engine.connect() as conn:
        return [(str(r[0]), str(r[1])) for r in conn.execute(q).fetchall()]


@st.cache_data(ttl=120)
def list_repo_names_for_metrics(
    project_label: str | None = None,
    tag_slugs: list[str] | None = None,
    tag_match_all: bool = True,
) -> list[str]:
    """`dim_repo` をプロジェクト／タグで絞った `repo_full_name` 一覧（L2 選択用）。"""
    engine = get_database_engine()
    q = text(
        """
        SELECT repo_full_name, project_name, tag_slugs
        FROM dim_repo
        WHERE is_active = TRUE
        ORDER BY repo_full_name
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(q).fetchall()

    want_tags = [t.strip() for t in (tag_slugs or []) if t and str(t).strip()]
    names: list[str] = []
    for rname, pname, tgslugs in rows:
        if project_label:
            unassigned = pname is None or (isinstance(pname, str) and pname.strip() == "")
            if project_label == "(未所属)":
                if not unassigned:
                    continue
            else:
                if unassigned or str(pname) != project_label:
                    continue
        if want_tags:
            have = _tag_slugs_set(tgslugs)
            if tag_match_all:
                if not set(want_tags).issubset(have):
                    continue
            elif not (set(want_tags) & have):
                continue
        names.append(str(rname))
    return names
