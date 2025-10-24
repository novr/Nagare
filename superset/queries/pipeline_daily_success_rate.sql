-- パイプライン実行の成功率（日次）
-- Dataset名: pipeline_daily_success_rate
-- 説明: 過去30日間の日次パイプライン実行の成功率をリポジトリ別に集計

SELECT
    DATE(pr.started_at) as execution_date,
    r.repository_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN pr.status = 'success' THEN 1 ELSE 0 END) as successful_runs,
    ROUND(
        100.0 * SUM(CASE WHEN pr.status = 'success' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) as success_rate_percent
FROM pipeline_runs pr
JOIN repositories r ON pr.repository_id = r.id
WHERE pr.started_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(pr.started_at), r.repository_name
ORDER BY execution_date DESC, repository_name;
