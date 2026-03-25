-- 旧 Superset 用ビュー（superset/init_views.sql）の削除。メトリクス v2 のみを使う場合に実行。
-- 冪等: 存在しなければ何もしない。

DROP VIEW IF EXISTS v_daily_mttr CASCADE;
DROP VIEW IF EXISTS v_mttr CASCADE;
DROP VIEW IF EXISTS v_daily_duration_by_source CASCADE;
DROP VIEW IF EXISTS v_hourly_runs_by_source CASCADE;
DROP VIEW IF EXISTS v_daily_success_rate_by_source CASCADE;
DROP VIEW IF EXISTS v_daily_runs_by_source CASCADE;
DROP VIEW IF EXISTS v_source_summary CASCADE;
DROP VIEW IF EXISTS v_branch_success_rate CASCADE;
DROP VIEW IF EXISTS v_failing_jobs CASCADE;
DROP VIEW IF EXISTS v_recent_pipeline_runs CASCADE;
DROP VIEW IF EXISTS v_pipeline_overview CASCADE;
