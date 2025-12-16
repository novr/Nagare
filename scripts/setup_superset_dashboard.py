#!/usr/bin/env python3
"""Superset ダッシュボード自動セットアップスクリプト

このスクリプトはSupersetにCI/CDパフォーマンスダッシュボードを自動作成します。

使用方法:
    docker exec nagare-superset python3 /app/scripts/setup_superset_dashboard.py

前提条件:
    - PostgreSQLデータベースが起動していること
    - Supersetが起動していること
    - superset/init_views.sql が実行済みであること
    - PostgreSQLデータベース接続がSupersetに登録されていること
"""

import json
import sys


def setup_dashboard():
    """ダッシュボードをセットアップする"""
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        # データベースを取得
        database = db.session.query(Database).first()
        if not database:
            print("ERROR: データベース接続が見つかりません")
            print("Supersetで先にPostgreSQLデータベース接続を作成してください")
            sys.exit(1)

        print(f"Using Database: {database.database_name} (ID: {database.id})")

        # ============================================================
        # Step 1: データセット登録
        # ============================================================
        print("\n=== Step 1: データセット登録 ===")

        views = [
            "v_pipeline_overview",
            "v_daily_success_rate",
            "v_pipeline_stats",
            "v_recent_pipeline_runs",
            "v_pipeline_runs_by_hour",
        ]

        for view_name in views:
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

        # データセットのカラムを同期
        print("\n=== Syncing dataset columns ===")
        for table in db.session.query(SqlaTable).all():
            try:
                table.fetch_metadata()
                print(f"Synced: {table.table_name}")
            except Exception as e:
                print(f"Error syncing {table.table_name}: {e}")

        db.session.commit()

        # データセットIDマッピング
        datasets = {t.table_name: t for t in db.session.query(SqlaTable).all()}

        # ============================================================
        # Step 2: ダッシュボード作成
        # ============================================================
        print("\n=== Step 2: ダッシュボード作成 ===")

        dashboard = (
            db.session.query(Dashboard).filter_by(slug="cicd-performance").first()
        )
        if not dashboard:
            dashboard = Dashboard(
                dashboard_title="CI/CD パフォーマンスダッシュボード",
                slug="cicd-performance",
                published=True,
            )
            db.session.add(dashboard)
            db.session.commit()
            print(
                f"CREATED Dashboard: {dashboard.dashboard_title} (ID: {dashboard.id})"
            )
        else:
            print(f"SKIP Dashboard: {dashboard.dashboard_title} (already exists)")

        # ============================================================
        # Step 3: チャート作成
        # ============================================================
        print("\n=== Step 3: チャート作成 ===")

        charts_config = [
            {
                "slice_name": "全体成功率",
                "viz_type": "big_number_total",
                "datasource": datasets["v_pipeline_overview"],
                "params": {
                    "viz_type": "big_number_total",
                    "metric": {
                        "expressionType": "SIMPLE",
                        "column": {
                            "column_name": "overall_success_rate",
                            "type": "NUMERIC",
                        },
                        "aggregate": "AVG",
                        "label": "Success Rate",
                    },
                    "subheader": "% 全リポジトリ平均",
                    "y_axis_format": ".1f",
                },
            },
            {
                "slice_name": "日次成功率トレンド",
                "viz_type": "echarts_timeseries_line",
                "datasource": datasets["v_daily_success_rate"],
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "run_date",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {
                                "column_name": "success_rate",
                                "type": "NUMERIC",
                            },
                            "aggregate": "AVG",
                            "label": "AVG(success_rate)",
                        }
                    ],
                    "groupby": [],
                    "row_limit": 10000,
                    "order_desc": False,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "rich_tooltip": True,
                },
            },
            {
                "slice_name": "リポジトリ別実行数",
                "viz_type": "pie",
                "datasource": datasets["v_pipeline_overview"],
                "params": {
                    "viz_type": "pie",
                    "groupby": ["repository_name"],
                    "metric": {
                        "expressionType": "SIMPLE",
                        "column": {
                            "column_name": "total_pipeline_runs",
                            "type": "BIGINT",
                        },
                        "aggregate": "SUM",
                        "label": "SUM(total_pipeline_runs)",
                    },
                    "row_limit": 20,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "show_labels": True,
                },
            },
            {
                "slice_name": "時間帯別実行数",
                "viz_type": "echarts_timeseries_bar",
                "datasource": datasets["v_pipeline_runs_by_hour"],
                "params": {
                    "viz_type": "echarts_timeseries_bar",
                    "x_axis": "hour_of_day",
                    "x_axis_sort": "hour_of_day",
                    "x_axis_sort_asc": True,
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {"column_name": "run_count", "type": "BIGINT"},
                            "aggregate": "SUM",
                            "label": "SUM(run_count)",
                        }
                    ],
                    "groupby": [],
                    "row_limit": 24,
                    "order_desc": False,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "rich_tooltip": True,
                },
            },
            {
                "slice_name": "最新実行履歴",
                "viz_type": "table",
                "datasource": datasets["v_recent_pipeline_runs"],
                "params": {
                    "viz_type": "table",
                    "query_mode": "aggregate",
                    "groupby": [
                        "repository_name",
                        "pipeline_name",
                        "status",
                        "branch_name",
                        "started_at",
                        "duration_sec",
                    ],
                    "metrics": [],
                    "percent_metrics": [],
                    "row_limit": 50,
                    "include_time": False,
                    "order_desc": True,
                    "show_cell_bars": False,
                    "table_timestamp_format": "smart_date",
                },
            },
        ]

        slices = []
        for chart in charts_config:
            existing = (
                db.session.query(Slice).filter_by(slice_name=chart["slice_name"]).first()
            )
            if existing:
                print(f'SKIP Chart: {chart["slice_name"]} (already exists)')
                slices.append(existing)
                continue

            ds = chart["datasource"]
            params = chart["params"].copy()
            params["datasource"] = f"{ds.id}__table"

            slice_obj = Slice(
                slice_name=chart["slice_name"],
                viz_type=chart["viz_type"],
                datasource_id=ds.id,
                datasource_type="table",
                params=json.dumps(params),
            )
            db.session.add(slice_obj)
            db.session.commit()
            slices.append(slice_obj)
            print(f'CREATED Chart: {chart["slice_name"]} (ID: {slice_obj.id})')

        # ============================================================
        # Step 4: ダッシュボードにチャートを関連付け
        # ============================================================
        print("\n=== Step 4: ダッシュボードにチャートを関連付け ===")

        dashboard.slices = slices
        db.session.commit()
        print(f"Dashboard updated with {len(slices)} charts")

        # ============================================================
        # 完了
        # ============================================================
        print("\n" + "=" * 60)
        print("✅ セットアップ完了!")
        print("=" * 60)
        print(f"\nダッシュボードURL:")
        print(f"  http://localhost:8088/superset/dashboard/{dashboard.slug}/")
        print("\n注意: チャートのレイアウトはダッシュボード編集画面で調整してください")


if __name__ == "__main__":
    setup_dashboard()
