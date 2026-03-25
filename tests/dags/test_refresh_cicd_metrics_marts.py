"""refresh_cicd_metrics_marts DAG の構造テスト。"""

from __future__ import annotations

import pytest


@pytest.mark.require_airflow
def test_refresh_metrics_dag_structure() -> None:
    from nagare.dags import refresh_cicd_metrics_marts

    dag = refresh_cicd_metrics_marts.dag
    assert dag.dag_id == "refresh_cicd_metrics_marts"
    assert dag.catchup is False
    assert "metrics" in dag.tags
    assert len(dag.tasks) == 1
    assert dag.get_task("refresh_marts") is not None
