-- Superset用のビューを作成
-- このスクリプトはダッシュボードで使用するビューを作成します
-- タイムゾーン: JST (Asia/Tokyo) で表示

-- ============================================================
-- 基本ビュー
-- ============================================================

-- 1. パイプラインとジョブの概要（全体成功率用）
CREATE OR REPLACE VIEW v_pipeline_overview AS
SELECT
    r.repository_name,
    COUNT(DISTINCT pr.id) as total_pipeline_runs,
    COUNT(DISTINCT j.id) as total_jobs,
    MAX(pr.started_at) as last_run_time,
    SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) as failure_count,
    ROUND(100.0 * SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) / NULLIF(COUNT(pr.id), 0), 2) as overall_success_rate
FROM repositories r
LEFT JOIN pipeline_runs pr ON r.id = pr.repository_id
LEFT JOIN jobs j ON pr.id = j.run_id
GROUP BY r.repository_name;

-- 2. 最新のパイプライン実行一覧
CREATE OR REPLACE VIEW v_recent_pipeline_runs AS
SELECT
    pr.source,
    r.repository_name,
    pr.pipeline_name,
    pr.status,
    pr.branch_name,
    (pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo') as started_at,
    pr.duration_ms / 1000.0 as duration_sec
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
ORDER BY pr.started_at DESC
LIMIT 100;

-- 3. 失敗パイプラインランキング（過去30日）
CREATE OR REPLACE VIEW v_failing_jobs AS
SELECT
    r.repository_name,
    pr.pipeline_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) as failure_count,
    ROUND((100.0 * SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*))::numeric, 1) as failure_rate,
    MAX((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')) as last_failure_at
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at >= NOW() - INTERVAL '30 days'
GROUP BY r.repository_name, pr.pipeline_name
HAVING SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) > 0
ORDER BY failure_count DESC;

-- 4. ブランチ別成功率（過去30日）
DROP VIEW IF EXISTS v_branch_success_rate CASCADE;
CREATE VIEW v_branch_success_rate AS
SELECT
    r.repository_name,
    CASE
        WHEN pr.branch_name IN ('main', 'master', 'develop', 'development') THEN pr.branch_name
        WHEN pr.branch_name LIKE 'feature/%' THEN 'feature/*'
        WHEN pr.branch_name LIKE 'fix/%' OR pr.branch_name LIKE 'bugfix/%' THEN 'fix/*'
        WHEN pr.branch_name LIKE 'release/%' THEN 'release/*'
        WHEN pr.branch_name LIKE 'dependabot/%' THEN 'dependabot/*'
        ELSE 'other'
    END as branch_type,
    COUNT(*) as total_runs,
    SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    ROUND((100.0 * SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*))::numeric, 1) as success_rate
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at >= NOW() - INTERVAL '30 days'
  AND pr.branch_name IS NOT NULL
GROUP BY
    r.repository_name,
    CASE
        WHEN pr.branch_name IN ('main', 'master', 'develop', 'development') THEN pr.branch_name
        WHEN pr.branch_name LIKE 'feature/%' THEN 'feature/*'
        WHEN pr.branch_name LIKE 'fix/%' OR pr.branch_name LIKE 'bugfix/%' THEN 'fix/*'
        WHEN pr.branch_name LIKE 'release/%' THEN 'release/*'
        WHEN pr.branch_name LIKE 'dependabot/%' THEN 'dependabot/*'
        ELSE 'other'
    END
ORDER BY total_runs DESC;

-- ============================================================
-- ソース別ビュー（GitHub / Bitrise / Xcode Cloud）
-- ============================================================

-- 5. ソース別サマリー
DROP VIEW IF EXISTS v_source_summary CASCADE;
CREATE VIEW v_source_summary AS
SELECT
    r.repository_name,
    pr.source,
    COUNT(*) as total_runs,
    SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) as failure_count,
    ROUND((100.0 * SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*))::numeric, 1) as success_rate,
    ROUND((AVG(pr.duration_ms) / 1000.0)::numeric, 1) as avg_duration_sec,
    ROUND((SUM(pr.duration_ms) / 1000.0)::numeric, 1) as total_sec
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
GROUP BY r.repository_name, pr.source
ORDER BY total_runs DESC;

-- 6. ソース別日次実行数（縦積みグラフ用）
DROP VIEW IF EXISTS v_daily_runs_by_source CASCADE;
CREATE VIEW v_daily_runs_by_source AS
SELECT
    DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')) as run_date,
    r.repository_name,
    pr.source,
    COUNT(*) as run_count,
    SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) as failure_count
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL
GROUP BY DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')), r.repository_name, pr.source
ORDER BY run_date DESC, pr.source;

-- 7. ソース別成功率トレンド
DROP VIEW IF EXISTS v_daily_success_rate_by_source CASCADE;
CREATE VIEW v_daily_success_rate_by_source AS
SELECT
    DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')) as run_date,
    r.repository_name,
    pr.source,
    COUNT(*) as total_runs,
    SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    ROUND((100.0 * SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*))::numeric, 1) as success_rate
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL
GROUP BY DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')), r.repository_name, pr.source;

-- 8. ソース別時間帯実行数（縦積みグラフ用）
DROP VIEW IF EXISTS v_hourly_runs_by_source CASCADE;
CREATE VIEW v_hourly_runs_by_source AS
SELECT
    EXTRACT(HOUR FROM (pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo'))::int as hour_of_day,
    r.repository_name,
    pr.source,
    COUNT(*) as run_count
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL
GROUP BY EXTRACT(HOUR FROM (pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo'))::int, r.repository_name, pr.source;

-- 9. ソース別ビルド時間トレンド
DROP VIEW IF EXISTS v_daily_duration_by_source CASCADE;
CREATE VIEW v_daily_duration_by_source AS
SELECT
    DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')) as run_date,
    r.repository_name,
    pr.source,
    COUNT(*) as run_count,
    ROUND((AVG(pr.duration_ms) / 1000.0)::numeric, 1) as avg_duration_sec
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL AND pr.duration_ms IS NOT NULL
GROUP BY DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')), r.repository_name, pr.source;

-- ============================================================
-- MTTR（Mean Time To Recovery）ビュー
-- ============================================================

-- 10. MTTRサマリー（リポジトリ別）
CREATE OR REPLACE VIEW v_mttr AS
WITH failure_recovery AS (
    SELECT
        r.repository_name,
        pr.pipeline_name,
        pr.source,
        pr.started_at as failure_time,
        (
            SELECT MIN(pr2.started_at)
            FROM pipeline_runs pr2
            WHERE pr2.repository_id = pr.repository_id
              AND pr2.pipeline_name = pr.pipeline_name
              AND pr2.status = 'SUCCESS'
              AND pr2.started_at > pr.started_at
        ) as recovery_time
    FROM pipeline_runs pr
    JOIN repositories r ON pr.repository_id = r.id
    WHERE pr.status = 'FAILURE'
      AND pr.started_at >= NOW() - INTERVAL '30 days'
)
SELECT
    repository_name,
    source,
    COUNT(*) as failure_count,
    COUNT(recovery_time) as recovered_count,
    ROUND(AVG(EXTRACT(EPOCH FROM (recovery_time - failure_time)) / 60)::numeric, 1) as avg_mttr_minutes,
    ROUND(MIN(EXTRACT(EPOCH FROM (recovery_time - failure_time)) / 60)::numeric, 1) as min_mttr_minutes,
    ROUND(MAX(EXTRACT(EPOCH FROM (recovery_time - failure_time)) / 60)::numeric, 1) as max_mttr_minutes
FROM failure_recovery
WHERE recovery_time IS NOT NULL
GROUP BY repository_name, source
ORDER BY avg_mttr_minutes DESC;

-- 11. MTTRトレンド（日次）
DROP VIEW IF EXISTS v_daily_mttr CASCADE;
CREATE VIEW v_daily_mttr AS
WITH failure_recovery AS (
    SELECT
        r.repository_name,
        pr.source,
        DATE((pr.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')) as failure_date,
        pr.started_at as failure_time,
        (
            SELECT MIN(pr2.started_at)
            FROM pipeline_runs pr2
            WHERE pr2.repository_id = pr.repository_id
              AND pr2.pipeline_name = pr.pipeline_name
              AND pr2.status = 'SUCCESS'
              AND pr2.started_at > pr.started_at
        ) as recovery_time
    FROM pipeline_runs pr
    JOIN repositories r ON pr.repository_id = r.id
    WHERE pr.status = 'FAILURE'
)
SELECT
    failure_date as run_date,
    repository_name,
    source,
    COUNT(*) as failure_count,
    ROUND(AVG(EXTRACT(EPOCH FROM (recovery_time - failure_time)) / 60)::numeric, 1) as avg_mttr_minutes
FROM failure_recovery
WHERE recovery_time IS NOT NULL
GROUP BY failure_date, repository_name, source
ORDER BY failure_date DESC;
