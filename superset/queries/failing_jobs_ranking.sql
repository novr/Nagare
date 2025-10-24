-- 失敗が多いジョブのランキング
-- Dataset名: failing_jobs_ranking
-- 説明: 過去30日間で失敗が多いジョブのランキング（失敗率を含む）

SELECT
    j.job_name,
    r.repository_name,
    COUNT(*) as total_executions,
    SUM(CASE WHEN j.status IN ('failure', 'cancelled') THEN 1 ELSE 0 END) as failure_count,
    ROUND(
        100.0 * SUM(CASE WHEN j.status IN ('failure', 'cancelled') THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) as failure_rate_percent,
    MAX(j.started_at) as last_failure_at
FROM jobs j
JOIN pipeline_runs pr ON j.pipeline_run_id = pr.id
JOIN repositories r ON pr.repository_id = r.id
WHERE j.started_at >= CURRENT_DATE - INTERVAL '30 days'
  AND j.status IN ('failure', 'cancelled')
GROUP BY j.job_name, r.repository_name
HAVING COUNT(*) >= 3  -- 3回以上失敗したジョブのみ
ORDER BY failure_count DESC, failure_rate_percent DESC
LIMIT 30;
