-- ジョブ別実行時間ランキング
-- Dataset名: job_duration_ranking
-- 説明: 過去30日間のジョブ実行時間の統計と成功/失敗数

SELECT
    j.job_name,
    r.repository_name,
    COUNT(*) as execution_count,
    ROUND(AVG(j.duration_seconds)::numeric, 2) as avg_duration_seconds,
    ROUND(MAX(j.duration_seconds)::numeric, 2) as max_duration_seconds,
    SUM(CASE WHEN j.status = 'success' THEN 1 ELSE 0 END) as successful_count,
    SUM(CASE WHEN j.status IN ('failure', 'cancelled') THEN 1 ELSE 0 END) as failed_count
FROM jobs j
JOIN pipeline_runs pr ON j.pipeline_run_id = pr.id
JOIN repositories r ON pr.repository_id = r.id
WHERE j.started_at >= CURRENT_DATE - INTERVAL '30 days'
  AND j.duration_seconds IS NOT NULL
GROUP BY j.job_name, r.repository_name
HAVING COUNT(*) >= 5  -- 5回以上実行されたジョブのみ
ORDER BY avg_duration_seconds DESC
LIMIT 50;
