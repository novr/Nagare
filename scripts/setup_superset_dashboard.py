#!/usr/bin/env python3
"""Superset CI/CD メトリクス v2 ダッシュボード自動セットアップ

使用方法:
    docker cp scripts/setup_superset_dashboard.py nagare-superset:/tmp/setup_superset_dashboard.py
    docker exec nagare-superset python3 /tmp/setup_superset_dashboard.py
    docker exec nagare-superset python3 /tmp/setup_superset_dashboard.py --reset

前提:
    - nagare DB に metrics v2 のビューが作成済み
    - Superset に PostgreSQL (nagare) 接続が登録済み
"""

from __future__ import annotations

import json
import os
import sys

MANAGED_CHARTS = [
    "L1成功率トレンド",
    "L1実行数トレンド",
    "L1リポジトリヘルス",
    "L1悪化リポジトリ",
    "L2リポジトリトレンド",
    "L2失敗ワークフローTop",
    "L2実行時間ワークフロー",
    "L2失敗理由内訳",
    "L2再実行率",
    "L2アクション候補",
]

VIEW_DATASETS = [
    "vw_l1_daily_overview",
    "vw_l1_daily_overview_by_platform",
    "vw_l1_repo_health",
    "vw_l1_repo_deterioration",
    "vw_l2_repo_trend",
    "vw_l2_workflow_fail_top",
    "vw_l2_workflow_duration_top",
    "vw_l2_failure_reason_breakdown",
    "vw_l2_retry_flake_trend",
    "vw_l2_action_candidates",
]


def setup_dashboard(reset: bool = False) -> None:
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        env_db = os.environ.get("NAGARE_SUPERSET_DATABASE_NAME")
        candidates = [c for c in (env_db, "Nagare PostgreSQL", "nagare") if c]
        database = None
        for name in candidates:
            database = (
                db.session.query(Database)
                .filter(Database.database_name == name)
                .one_or_none()
            )
            if database:
                break
        if not database:
            print(
                "ERROR: Nagare 用 Database が見つかりません。"
                " Superset の接続表示名を NAGARE_SUPERSET_DATABASE_NAME に合わせるか、"
                " 'Nagare PostgreSQL' / 'nagare' で登録してください。"
            )
            sys.exit(1)

        print(f"Using Database: {database.database_name} (ID: {database.id})")

        print("\n=== Step 1: データセット登録 ===")
        for view_name in VIEW_DATASETS:
            existing = (
                db.session.query(SqlaTable)
                .filter_by(table_name=view_name, database_id=database.id)
                .first()
            )
            if existing:
                print(f"SKIP: {view_name} (already exists, ID: {existing.id})")
                continue
            table = SqlaTable(
                table_name=view_name, database_id=database.id, schema="public"
            )
            db.session.add(table)
            db.session.commit()
            print(f"CREATED: {view_name} (ID: {table.id})")

        print("\n=== Syncing dataset columns (v2 views only) ===")
        v2_tables = (
            db.session.query(SqlaTable)
            .filter(
                SqlaTable.database_id == database.id,
                SqlaTable.table_name.in_(VIEW_DATASETS),
            )
            .all()
        )
        for table in v2_tables:
            try:
                table.fetch_metadata()
                print(f"Synced: {table.table_name}")
            except Exception as e:
                print(f"Error syncing {table.table_name}: {e}")
        db.session.commit()

        datasets = {
            t.table_name: t
            for t in db.session.query(SqlaTable).filter(
                SqlaTable.database_id == database.id
            )
        }

        def _ds(name: str) -> SqlaTable | None:
            t = datasets.get(name)
            if t is None:
                print(f"WARN: dataset not found: {name}")
            return t

        print("\n=== Step 2: ダッシュボード ===")
        dashboard = (
            db.session.query(Dashboard).filter_by(slug="cicd-metrics-v2").first()
        )
        if not dashboard:
            dashboard = Dashboard(
                dashboard_title="CI/CD メトリクス (v2)",
                slug="cicd-metrics-v2",
                published=True,
            )
            db.session.add(dashboard)
            db.session.commit()
            print(f"CREATED Dashboard: {dashboard.dashboard_title} (ID: {dashboard.id})")
        else:
            print(f"EXISTS Dashboard: {dashboard.dashboard_title} (ID: {dashboard.id})")

        if reset:
            print("\n=== Reset: レガシーダッシュボード削除 ===")
            for legacy_slug in ("cicd-performance",):
                old_dash = (
                    db.session.query(Dashboard)
                    .filter_by(slug=legacy_slug)
                    .first()
                )
                if old_dash:
                    db.session.delete(old_dash)
                    print(f"DELETED legacy dashboard slug={legacy_slug} (id={old_dash.id})")
            db.session.commit()

            print("\n=== Reset: 既存チャート削除 ===")
            for chart_name in MANAGED_CHARTS:
                existing = (
                    db.session.query(Slice).filter_by(slice_name=chart_name).first()
                )
                if existing:
                    db.session.delete(existing)
                    print(f"DELETED: {chart_name}")
            db.session.commit()

        print("\n=== Step 3: チャート作成 ===")
        charts_config: list[dict[str, object]] = [
            {
                "slice_name": "L1成功率トレンド",
                "viz_type": "echarts_timeseries_line",
                "datasource": _ds("vw_l1_daily_overview_by_platform"),
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "metric_date",
                    "time_grain_sqla": "P1D",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {
                                "column_name": "success_rate_pct",
                                "type": "NUMERIC",
                            },
                            "aggregate": "AVG",
                            "label": "成功率(%)",
                        }
                    ],
                    "groupby": ["platform"],
                    "row_limit": 10000,
                    "show_legend": True,
                    "rich_tooltip": True,
                },
            },
            {
                "slice_name": "L1実行数トレンド",
                "viz_type": "echarts_timeseries_bar",
                "datasource": _ds("vw_l1_daily_overview_by_platform"),
                "params": {
                    "viz_type": "echarts_timeseries_bar",
                    "x_axis": "metric_date",
                    "time_grain_sqla": "P1D",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {"column_name": "total_runs", "type": "BIGINT"},
                            "aggregate": "SUM",
                            "label": "実行数",
                        }
                    ],
                    "groupby": ["platform"],
                    "row_limit": 10000,
                    "stack": "Stack",
                    "show_legend": True,
                },
            },
            {
                "slice_name": "L1リポジトリヘルス",
                "viz_type": "table",
                "datasource": _ds("vw_l1_repo_health"),
                "params": {
                    "viz_type": "table",
                    "query_mode": "raw",
                    "all_columns": [
                        "repo_full_name",
                        "platform",
                        "total_runs_7d",
                        "success_rate_7d_pct",
                        "avg_p95_ms_7d",
                    ],
                    "row_limit": 1000,
                },
            },
            {
                "slice_name": "L1悪化リポジトリ",
                "viz_type": "table",
                "datasource": _ds("vw_l1_repo_deterioration"),
                "params": {
                    "viz_type": "table",
                    "query_mode": "raw",
                    "all_columns": [
                        "repo_full_name",
                        "deterioration_flag",
                        "success_rate_yesterday",
                        "success_rate_delta_1d",
                        "failed_runs_yesterday",
                        "p95_ms_yesterday",
                    ],
                    "row_limit": 500,
                },
            },
            {
                "slice_name": "L2リポジトリトレンド",
                "viz_type": "echarts_timeseries_line",
                "datasource": _ds("vw_l2_repo_trend"),
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "metric_date",
                    "time_grain_sqla": "P1D",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {
                                "column_name": "success_rate_pct",
                                "type": "NUMERIC",
                            },
                            "aggregate": "AVG",
                            "label": "成功率",
                        }
                    ],
                    "groupby": ["repo_full_name"],
                    "row_limit": 10000,
                    "show_legend": True,
                },
            },
            {
                "slice_name": "L2失敗ワークフローTop",
                "viz_type": "table",
                "datasource": _ds("vw_l2_workflow_fail_top"),
                "params": {
                    "viz_type": "table",
                    "query_mode": "raw",
                    "all_columns": [
                        "repo_full_name",
                        "workflow_name",
                        "failure_count",
                        "failure_rate_pct",
                        "last_failure_at",
                    ],
                    "row_limit": 500,
                },
            },
            {
                "slice_name": "L2実行時間ワークフロー",
                "viz_type": "table",
                "datasource": _ds("vw_l2_workflow_duration_top"),
                "params": {
                    "viz_type": "table",
                    "query_mode": "raw",
                    "all_columns": [
                        "repo_full_name",
                        "workflow_name",
                        "p50_duration_ms",
                        "p95_duration_ms",
                        "total_runs",
                    ],
                    "row_limit": 500,
                },
            },
            {
                "slice_name": "L2失敗理由内訳",
                "viz_type": "echarts_timeseries_bar",
                "datasource": _ds("vw_l2_failure_reason_breakdown"),
                "params": {
                    "viz_type": "echarts_timeseries_bar",
                    "x_axis": "fail_date",
                    "time_grain_sqla": "P1D",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {"column_name": "failure_runs", "type": "BIGINT"},
                            "aggregate": "SUM",
                            "label": "失敗実行数",
                        }
                    ],
                    "groupby": ["reason_category"],
                    "row_limit": 10000,
                    "stack": "Stack",
                    "show_legend": True,
                },
            },
            {
                "slice_name": "L2再実行率",
                "viz_type": "echarts_timeseries_line",
                "datasource": _ds("vw_l2_retry_flake_trend"),
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "run_date",
                    "time_grain_sqla": "P1D",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {
                                "column_name": "retry_rate_pct",
                                "type": "NUMERIC",
                            },
                            "aggregate": "AVG",
                            "label": "再実行率%",
                        }
                    ],
                    "groupby": ["repo_full_name"],
                    "row_limit": 10000,
                    "show_legend": True,
                },
            },
            {
                "slice_name": "L2アクション候補",
                "viz_type": "table",
                "datasource": _ds("vw_l2_action_candidates"),
                "params": {
                    "viz_type": "table",
                    "query_mode": "raw",
                    "all_columns": [
                        "repo_full_name",
                        "target_workflow",
                        "failure_count",
                        "failure_rate_pct",
                        "priority_rank",
                        "suggested_action",
                    ],
                    "row_limit": 200,
                },
            },
        ]

        slices: list[Slice] = []
        for chart in charts_config:
            ds = chart["datasource"]
            if ds is None:
                print(f"SKIP missing dataset for {chart['slice_name']}")
                continue
            params = chart["params"].copy()  # type: ignore[union-attr]
            params["datasource"] = f"{ds.id}__table"

            existing = (
                db.session.query(Slice).filter_by(slice_name=chart["slice_name"]).first()
            )
            if existing:
                existing.viz_type = str(chart["viz_type"])
                existing.datasource_id = ds.id
                existing.datasource_type = "table"
                existing.params = json.dumps(params)
                db.session.commit()
                slices.append(existing)
                print(f"UPDATED Chart: {chart['slice_name']} (ID: {existing.id})")
                continue

            slice_obj = Slice(
                slice_name=str(chart["slice_name"]),
                viz_type=str(chart["viz_type"]),
                datasource_id=ds.id,
                datasource_type="table",
                params=json.dumps(params),
            )
            db.session.add(slice_obj)
            db.session.commit()
            slices.append(slice_obj)
            print(f"CREATED Chart: {chart['slice_name']} (ID: {slice_obj.id})")

        print("\n=== Step 4: ダッシュボードに関連付け ===")
        dashboard.slices = slices

        metadata = json.loads(dashboard.json_metadata) if dashboard.json_metadata else {}
        metadata["cross_filters_enabled"] = True
        metadata["chart_configuration"] = {}
        for s in slices:
            metadata["chart_configuration"][str(s.id)] = {
                "id": s.id,
                "crossFilters": {
                    "scope": "global",
                    "chartsInScope": [x.id for x in slices if x.id != s.id],
                },
            }

        ds_trend = _ds("vw_l2_repo_trend")
        ds_l1_pf = _ds("vw_l1_daily_overview_by_platform")
        native_filters: list[dict[str, object]] = []
        if ds_trend:
            native_filters.append(
                {
                    "id": "NATIVE_FILTER-repo",
                    "name": "Repository",
                    "filterType": "filter_select",
                    "targets": [
                        {
                            "datasetId": ds_trend.id,
                            "column": {"name": "repo_full_name"},
                        }
                    ],
                    "defaultDataMask": {
                        "extraFormData": {},
                        "filterState": {},
                        "ownState": {},
                    },
                    "controlValues": {
                        "enableEmptyFilter": True,
                        "defaultToFirstItem": False,
                        "multiSelect": True,
                        "searchAllOptions": True,
                        "inverseSelection": False,
                    },
                    "cascadeParentIds": [],
                    "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                    "isInstant": True,
                    "description": "L2 系チャート用",
                    "type": "NATIVE_FILTER",
                }
            )
        if ds_l1_pf:
            native_filters.append(
                {
                    "id": "NATIVE_FILTER-l1-platform",
                    "name": "L1 Platform (ALL / 個別)",
                    "filterType": "filter_select",
                    "targets": [
                        {
                            "datasetId": ds_l1_pf.id,
                            "column": {"name": "platform"},
                        }
                    ],
                    "defaultDataMask": {
                        "extraFormData": {},
                        "filterState": {},
                        "ownState": {},
                    },
                    "controlValues": {
                        "enableEmptyFilter": True,
                        "defaultToFirstItem": False,
                        "multiSelect": True,
                        "searchAllOptions": False,
                        "inverseSelection": False,
                    },
                    "cascadeParentIds": [],
                    "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                    "isInstant": True,
                    "description": "空欄ですべて表示。ALL または bitrise 等を選択で絞り込み",
                    "type": "NATIVE_FILTER",
                }
            )
        if native_filters:
            metadata["native_filter_configuration"] = native_filters

        dashboard.json_metadata = json.dumps(metadata)
        db.session.commit()
        print(f"Dashboard updated with {len(slices)} charts")

        print("\n" + "=" * 60)
        print("完了")
        print("=" * 60)
        print(f"\nダッシュボードURL:\n  http://localhost:8088/superset/dashboard/{dashboard.slug}/")
        print("\n注意: レイアウトは Superset 編集画面で調整してください")


if __name__ == "__main__":
    reset_mode = "--reset" in sys.argv
    if reset_mode:
        print("Reset mode: 既存チャートを削除して再作成します")
    setup_dashboard(reset=reset_mode)
