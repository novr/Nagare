-- Superset用のビューを作成
-- このスクリプトはダッシュボードで使用するビューを作成します

-- 1. パイプライン実行の統計ビュー
CREATE OR REPLACE VIEW v_pipeline_stats AS
SELECT
    r.repository_name,
    pr.status,
    DATE(pr.started_at) as run_date,
    COUNT(*) as run_count,
    AVG(pr.duration_ms) / 1000.0 as avg_duration_sec,
    MIN(pr.duration_ms) / 1000.0 as min_duration_sec,
    MAX(pr.duration_ms) / 1000.0 as max_duration_sec
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL
GROUP BY r.repository_name, pr.status, DATE(pr.started_at);

-- 2. 日次パイプライン成功率ビュー
CREATE OR REPLACE VIEW v_daily_success_rate AS
SELECT
    r.repository_name,
    DATE(pr.started_at) as run_date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN pr.status = 'FAILURE' THEN 1 ELSE 0 END) as failure_count,
    ROUND(100.0 * SUM(CASE WHEN pr.status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL
GROUP BY r.repository_name, DATE(pr.started_at);

-- 3. 最新のパイプライン実行一覧ビュー
CREATE OR REPLACE VIEW v_recent_pipeline_runs AS
SELECT
    r.repository_name,
    pr.pipeline_name,
    pr.status,
    pr.branch_name,
    pr.trigger_event,
    pr.started_at,
    pr.completed_at,
    pr.duration_ms / 1000.0 as duration_sec,
    pr.url
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
ORDER BY pr.started_at DESC
LIMIT 100;

-- 4. ジョブの統計ビュー
CREATE OR REPLACE VIEW v_job_stats AS
SELECT
    r.repository_name,
    j.job_name,
    j.status,
    DATE(j.started_at) as run_date,
    COUNT(*) as job_count,
    AVG(j.duration_ms) / 1000.0 as avg_duration_sec
FROM jobs j
JOIN pipeline_runs pr ON j.run_id = pr.id
JOIN repositories r ON pr.repository_id = r.id
WHERE j.started_at IS NOT NULL
GROUP BY r.repository_name, j.job_name, j.status, DATE(j.started_at);

-- 5. 時間帯別のパイプライン実行数
CREATE OR REPLACE VIEW v_pipeline_runs_by_hour AS
SELECT
    r.repository_name,
    EXTRACT(HOUR FROM pr.started_at) as hour_of_day,
    COUNT(*) as run_count,
    AVG(pr.duration_ms) / 1000.0 as avg_duration_sec
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at IS NOT NULL
GROUP BY r.repository_name, EXTRACT(HOUR FROM pr.started_at);

-- 6. パイプラインとジョブの概要
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
