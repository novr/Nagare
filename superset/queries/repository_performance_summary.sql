-- リポジトリ別パフォーマンスサマリー
-- Dataset名: repository_performance_summary
-- 説明: 過去30日間のリポジトリ別実行統計（総実行数、成功率、平均実行時間）

SELECT
    r.repository_name,
    COUNT(DISTINCT pr.id) as total_runs,
    SUM(CASE WHEN pr.status = 'success' THEN 1 ELSE 0 END) as successful_runs,
    SUM(CASE WHEN pr.status IN ('failure', 'cancelled') THEN 1 ELSE 0 END) as failed_runs,
    ROUND(
        100.0 * SUM(CASE WHEN pr.status = 'success' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) as success_rate_percent,
    ROUND(AVG(pr.duration_seconds)::numeric, 2) as avg_duration_seconds,
    MAX(pr.started_at) as last_run_at
FROM repositories r
LEFT JOIN pipeline_runs pr ON r.id = pr.repository_id
    AND pr.started_at >= CURRENT_DATE - INTERVAL '30 days'
WHERE r.active = true
GROUP BY r.repository_name
ORDER BY total_runs DESC;
