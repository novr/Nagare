"""metrics_mart_refresh タスクのユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nagare.tasks.metrics_mart_refresh import run_metrics_mart_refresh


def test_run_metrics_mart_refresh_calls_sql() -> None:
    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = False
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_ctx

    mock_db = MagicMock()
    mock_db.url = "postgresql://user:pass@localhost:5432/nagare"

    with patch(
        "nagare.tasks.metrics_mart_refresh.create_engine", return_value=mock_engine
    ):
        with patch(
            "nagare.tasks.metrics_mart_refresh.ConnectionRegistry.get_database",
            return_value=mock_db,
        ):
            run_metrics_mart_refresh()

    mock_conn.execute.assert_called_once()
    sql_text = str(mock_conn.execute.call_args[0][0]).lower()
    assert "refresh_cicd_metrics_marts(false)" in sql_text
