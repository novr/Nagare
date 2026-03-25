"""CI/CD メトリクスマート（v2）のリフレッシュタスク。

PostgreSQL の refresh_cicd_metrics_marts() を実行する。
スキーマ・関数定義は scripts/*.sql で適用する。
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, text

from nagare.utils.connections import ConnectionRegistry

logger = logging.getLogger(__name__)


def run_metrics_mart_refresh() -> None:
    """dim_repo / fact_* / agg_daily_repo_metrics を legacy テーブルから同期する。"""
    db_conn = ConnectionRegistry.get_database()
    engine = create_engine(db_conn.url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("SELECT refresh_cicd_metrics_marts()"))
    logger.info("refresh_cicd_metrics_marts() completed")
