from __future__ import annotations

import logging

from sqlalchemy import create_engine, text

from nagare.utils.connections import ConnectionRegistry

logger = logging.getLogger(__name__)


def run_metrics_mart_refresh() -> None:
    db_conn = ConnectionRegistry.get_database()
    engine = create_engine(db_conn.url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("SELECT refresh_cicd_metrics_marts(FALSE)"))
    logger.info("refresh_cicd_metrics_marts(FALSE) completed")
