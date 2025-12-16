#!/usr/bin/env python3
"""Superset ダッシュボード自動セットアップスクリプト

このスクリプトはSupersetにCI/CDパフォーマンスダッシュボードを自動作成します。
冪等性: 何度実行しても同じ結果になります。

使用方法:
    docker exec nagare-superset python3 /app/scripts/setup_superset_dashboard.py
    docker exec nagare-superset python3 /app/scripts/setup_superset_dashboard.py --reset

オプション:
    --reset: 既存のチャートを削除してから再作成

前提条件:
    - PostgreSQLデータベースが起動していること
    - Supersetが起動していること
    - superset/init_views.sql が実行済みであること
    - PostgreSQLデータベース接続がSupersetに登録されていること
"""

import json
import sys


# このスクリプトで管理するチャート名のリスト
MANAGED_CHARTS = [
    "全体成功率",
    "最新実行履歴",
    "失敗が多いパイプライン Top10",
    "ブランチ別成功率",
    "ソースサマリー",
    "日次実行数",
    "成功率トレンド",
    "時間帯別実行数",
    "ビルド時間トレンド",
    "MTTRサマリー",
    "MTTRトレンド",
]


def setup_dashboard(reset: bool = False):
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
            # 基本ビュー
            "v_pipeline_overview",
            "v_recent_pipeline_runs",
            "v_failing_jobs",
            "v_branch_success_rate",
            # ソース別ビュー
            "v_source_summary",
            "v_daily_runs_by_source",
            "v_daily_success_rate_by_source",
            "v_hourly_runs_by_source",
            "v_daily_duration_by_source",
            # MTTRビュー
            "v_mttr",
            "v_daily_mttr",
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
            print(f"EXISTS Dashboard: {dashboard.dashboard_title} (ID: {dashboard.id})")

        # ============================================================
        # Step 2.5: リセットモードの場合、既存チャートを削除
        # ============================================================
        if reset:
            print("\n=== Reset Mode: 既存チャートを削除 ===")
            for chart_name in MANAGED_CHARTS:
                existing = (
                    db.session.query(Slice).filter_by(slice_name=chart_name).first()
                )
                if existing:
                    db.session.delete(existing)
                    print(f"DELETED: {chart_name}")
            db.session.commit()

        # ============================================================
        # Step 3: チャート作成/更新
        # ============================================================
        print("\n=== Step 3: チャート作成/更新 ===")

        charts_config = [
            # === 基本指標 ===
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
                "slice_name": "最新実行履歴",
                "viz_type": "table",
                "datasource": datasets["v_recent_pipeline_runs"],
                "params": {
                    "viz_type": "table",
                    "query_mode": "aggregate",
                    "groupby": [
                        "source",
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
            {
                "slice_name": "失敗が多いパイプライン Top10",
                "viz_type": "table",
                "datasource": datasets["v_failing_jobs"],
                "params": {
                    "viz_type": "table",
                    "query_mode": "aggregate",
                    "groupby": [
                        "repository_name",
                        "pipeline_name",
                        "failure_count",
                        "failure_rate",
                        "total_runs",
                    ],
                    "metrics": [],
                    "row_limit": 10,
                    "order_desc": True,
                    "show_cell_bars": True,
                },
            },
            {
                "slice_name": "ブランチ別成功率",
                "viz_type": "dist_bar",
                "datasource": datasets["v_branch_success_rate"],
                "params": {
                    "viz_type": "dist_bar",
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
                    "groupby": ["branch_type"],
                    "columns": [],
                    "row_limit": 20,
                    "color_scheme": "supersetColors",
                    "show_legend": False,
                    "y_axis_format": ",.1f",
                },
            },
            # === ソース別指標（GitHub / Bitrise / Xcode Cloud） ===
            {
                "slice_name": "ソースサマリー",
                "viz_type": "table",
                "datasource": datasets["v_source_summary"],
                "params": {
                    "viz_type": "table",
                    "query_mode": "aggregate",
                    "groupby": [
                        "source",
                        "total_runs",
                        "success_count",
                        "failure_count",
                        "success_rate",
                        "avg_duration_sec",
                    ],
                    "metrics": [],
                    "row_limit": 10,
                    "order_desc": True,
                    "show_cell_bars": True,
                },
            },
            {
                "slice_name": "日次実行数",
                "viz_type": "echarts_timeseries_bar",
                "datasource": datasets["v_daily_runs_by_source"],
                "params": {
                    "viz_type": "echarts_timeseries_bar",
                    "x_axis": "run_date",
                    "time_grain_sqla": "P1D",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {"column_name": "run_count", "type": "BIGINT"},
                            "aggregate": "SUM",
                            "label": "SUM(run_count)",
                        }
                    ],
                    "groupby": ["source"],
                    "row_limit": 10000,
                    "stack": "Stack",
                    "only_total": False,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "legendType": "scroll",
                    "legendOrientation": "top",
                    "rich_tooltip": True,
                    "tooltipTimeFormat": "smart_date",
                    "x_axis_time_format": "smart_date",
                },
            },
            {
                "slice_name": "成功率トレンド",
                "viz_type": "echarts_timeseries_line",
                "datasource": datasets["v_daily_success_rate_by_source"],
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
                    "groupby": ["source"],
                    "row_limit": 10000,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "rich_tooltip": True,
                },
            },
            {
                "slice_name": "時間帯別実行数",
                "viz_type": "echarts_timeseries_bar",
                "datasource": datasets["v_hourly_runs_by_source"],
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
                    "groupby": ["source"],
                    "row_limit": 100,
                    "stack": "Stack",
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "rich_tooltip": True,
                },
            },
            {
                "slice_name": "ビルド時間トレンド",
                "viz_type": "echarts_timeseries_line",
                "datasource": datasets["v_daily_duration_by_source"],
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "run_date",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {
                                "column_name": "avg_duration_sec",
                                "type": "NUMERIC",
                            },
                            "aggregate": "AVG",
                            "label": "AVG(avg_duration_sec)",
                        }
                    ],
                    "groupby": ["source"],
                    "row_limit": 10000,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "rich_tooltip": True,
                    "y_axis_format": ",.0f",
                },
            },
            # === MTTR指標 ===
            {
                "slice_name": "MTTRサマリー",
                "viz_type": "table",
                "datasource": datasets["v_mttr"],
                "params": {
                    "viz_type": "table",
                    "query_mode": "aggregate",
                    "groupby": [
                        "repository_name",
                        "source",
                        "failure_count",
                        "recovered_count",
                        "avg_mttr_minutes",
                        "min_mttr_minutes",
                        "max_mttr_minutes",
                    ],
                    "metrics": [],
                    "row_limit": 20,
                    "order_desc": True,
                    "show_cell_bars": True,
                },
            },
            {
                "slice_name": "MTTRトレンド",
                "viz_type": "echarts_timeseries_line",
                "datasource": datasets["v_daily_mttr"],
                "params": {
                    "viz_type": "echarts_timeseries_line",
                    "x_axis": "run_date",
                    "metrics": [
                        {
                            "expressionType": "SIMPLE",
                            "column": {
                                "column_name": "avg_mttr_minutes",
                                "type": "NUMERIC",
                            },
                            "aggregate": "AVG",
                            "label": "AVG(avg_mttr_minutes)",
                        }
                    ],
                    "groupby": ["source"],
                    "row_limit": 10000,
                    "color_scheme": "supersetColors",
                    "show_legend": True,
                    "rich_tooltip": True,
                    "y_axis_format": ",.0f",
                },
            },
        ]

        slices = []
        for chart in charts_config:
            ds = chart["datasource"]
            params = chart["params"].copy()
            params["datasource"] = f"{ds.id}__table"

            existing = (
                db.session.query(Slice).filter_by(slice_name=chart["slice_name"]).first()
            )
            if existing:
                # 既存チャートを更新（冪等性）
                existing.viz_type = chart["viz_type"]
                existing.datasource_id = ds.id
                existing.datasource_type = "table"
                existing.params = json.dumps(params)
                db.session.commit()
                slices.append(existing)
                print(f'UPDATED Chart: {chart["slice_name"]} (ID: {existing.id})')
                continue

            # 新規チャートを作成
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

        # クロスフィルターを有効化
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
        dashboard.json_metadata = json.dumps(metadata)

        db.session.commit()
        print(f"Dashboard updated with {len(slices)} charts")
        print("Cross-filtering enabled")

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
    reset_mode = "--reset" in sys.argv
    if reset_mode:
        print("🔄 Reset mode enabled: 既存チャートを削除して再作成します")
    setup_dashboard(reset=reset_mode)
