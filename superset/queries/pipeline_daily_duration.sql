-- パイプライン実行時間の統計（日次）
-- Dataset名: pipeline_daily_duration
-- 説明: 過去30日間の日次パイプライン実行時間の統計（平均、最小、最大、中央値）

SELECT
    DATE(pr.started_at) as execution_date,
    r.repository_name,
    COUNT(*) as run_count,
    ROUND(AVG(pr.duration_seconds)::numeric, 2) as avg_duration_seconds,
    ROUND(MIN(pr.duration_seconds)::numeric, 2) as min_duration_seconds,
    ROUND(MAX(pr.duration_seconds)::numeric, 2) as max_duration_seconds,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pr.duration_seconds)::numeric, 2) as median_duration_seconds
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at >= CURRENT_DATE - INTERVAL '30 days'
  AND pr.duration_seconds IS NOT NULL
GROUP BY DATE(pr.started_at), r.repository_name
ORDER BY execution_date DESC, repository_name;
