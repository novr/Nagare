-- メトリクス v2 用ダッシュボードビュー（Superset / Streamlit）
-- 前提: metrics_dashboard_v2_schema.sql と refresh 済み
--
-- CREATE OR REPLACE VIEW は列の追加位置が変わると失敗するため、毎回 DROP してから定義する。

DROP VIEW IF EXISTS vw_l2_action_candidates_by_tag CASCADE;
DROP VIEW IF EXISTS vw_l2_action_candidates_by_project CASCADE;
DROP VIEW IF EXISTS vw_l2_action_candidates_by_platform CASCADE;
DROP VIEW IF EXISTS vw_l2_retry_flake_trend_by_tag CASCADE;
DROP VIEW IF EXISTS vw_l2_retry_flake_trend_by_project CASCADE;
DROP VIEW IF EXISTS vw_l2_retry_flake_trend_by_platform CASCADE;
DROP VIEW IF EXISTS vw_l2_failure_reason_breakdown_by_tag CASCADE;
DROP VIEW IF EXISTS vw_l2_failure_reason_breakdown_by_project CASCADE;
DROP VIEW IF EXISTS vw_l2_failure_reason_breakdown_by_platform CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_duration_top_by_tag CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_duration_top_by_project CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_duration_top_by_platform CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_fail_top_by_tag CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_fail_top_by_project CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_fail_top_by_platform CASCADE;
DROP VIEW IF EXISTS vw_l2_tag_trend CASCADE;
DROP VIEW IF EXISTS vw_l2_project_trend CASCADE;
DROP VIEW IF EXISTS vw_l2_platform_trend CASCADE;
DROP VIEW IF EXISTS vw_l2_action_candidates CASCADE;
DROP VIEW IF EXISTS vw_l2_retry_flake_trend CASCADE;
DROP VIEW IF EXISTS vw_l2_step_failure_heatmap CASCADE;
DROP VIEW IF EXISTS vw_l2_failure_reason_breakdown CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_duration_top CASCADE;
DROP VIEW IF EXISTS vw_l2_workflow_fail_top CASCADE;
DROP VIEW IF EXISTS vw_l2_repo_trend CASCADE;
DROP VIEW IF EXISTS vw_l1_repo_deterioration CASCADE;
DROP VIEW IF EXISTS vw_l1_repo_health CASCADE;
DROP VIEW IF EXISTS vw_l1_daily_overview_by_tag CASCADE;
DROP VIEW IF EXISTS vw_l1_daily_overview_by_project CASCADE;
DROP VIEW IF EXISTS vw_l1_daily_overview_by_platform CASCADE;
DROP VIEW IF EXISTS vw_l1_daily_overview CASCADE;

-- ---------------------------------------------------------------------------
-- L1: 日次全体サマリー
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l1_daily_overview AS
SELECT
    a.metric_date,
    SUM(a.total_runs) AS total_runs,
    SUM(a.success_runs) AS success_runs,
    SUM(a.failed_runs) AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
GROUP BY a.metric_date;

-- ---------------------------------------------------------------------------
-- L1: 日次サマリー（プラットフォーム別 + ALL）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l1_daily_overview_by_platform AS
SELECT
    a.metric_date,
    d.platform,
    SUM(a.total_runs)::bigint AS total_runs,
    SUM(a.success_runs)::bigint AS success_runs,
    SUM(a.failed_runs)::bigint AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id
GROUP BY a.metric_date, d.platform

UNION ALL

SELECT
    a.metric_date,
    'ALL'::text AS platform,
    SUM(a.total_runs)::bigint AS total_runs,
    SUM(a.success_runs)::bigint AS success_runs,
    SUM(a.failed_runs)::bigint AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
GROUP BY a.metric_date;

-- ---------------------------------------------------------------------------
-- L1: 日次サマリー（プロジェクト別 + ALL）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l1_daily_overview_by_project AS
SELECT
    a.metric_date,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    SUM(a.total_runs)::bigint AS total_runs,
    SUM(a.success_runs)::bigint AS success_runs,
    SUM(a.failed_runs)::bigint AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id
GROUP BY a.metric_date, COALESCE(d.project_name, '(未所属)')

UNION ALL

SELECT
    a.metric_date,
    'ALL'::text AS project_name,
    SUM(a.total_runs)::bigint AS total_runs,
    SUM(a.success_runs)::bigint AS success_runs,
    SUM(a.failed_runs)::bigint AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
GROUP BY a.metric_date;

-- ---------------------------------------------------------------------------
-- L1: 日次サマリー（タグ別: 1 リポジトリが複数タグのとき実行数はタグごとに重複計上 + ALL）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l1_daily_overview_by_tag AS
SELECT
    a.metric_date,
    t.slug AS tag_slug,
    t.name AS tag_name,
    SUM(a.total_runs)::bigint AS total_runs,
    SUM(a.success_runs)::bigint AS success_runs,
    SUM(a.failed_runs)::bigint AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id
INNER JOIN repository_tags AS rt ON rt.repository_id = d.repo_id
INNER JOIN tags AS t ON t.id = rt.tag_id
GROUP BY a.metric_date, t.slug, t.name

UNION ALL

SELECT
    a.metric_date,
    'ALL'::text AS tag_slug,
    '全体'::text AS tag_name,
    SUM(a.total_runs)::bigint AS total_runs,
    SUM(a.success_runs)::bigint AS success_runs,
    SUM(a.failed_runs)::bigint AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS avg_p50_duration_ms,
    MAX(a.computed_at) AS last_computed_at
FROM agg_daily_repo_metrics AS a
GROUP BY a.metric_date;

-- ---------------------------------------------------------------------------
-- L1: リポジトリヘルス（直近7日集約）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l1_repo_health AS
WITH windowed AS (
    SELECT *
    FROM agg_daily_repo_metrics
    WHERE metric_date
        >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Tokyo')::date - 7
)
SELECT
    d.repo_full_name,
    d.platform,
    d.is_active,
    SUM(w.total_runs) AS total_runs_7d,
    ROUND(
        100.0 * SUM(w.success_runs) / NULLIF(SUM(w.total_runs), 0),
        2
    ) AS success_rate_7d_pct,
    ROUND(AVG(w.p95_duration_ms)::numeric, 0) AS avg_p95_ms_7d,
    MAX(w.computed_at) AS last_computed_at,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM windowed AS w
INNER JOIN dim_repo AS d ON d.repo_id = w.repo_id
GROUP BY
    d.repo_id,
    d.repo_full_name,
    d.platform,
    d.project_name,
    d.tag_slugs,
    d.is_active;

-- ---------------------------------------------------------------------------
-- L1: 悪化リポジトリ（前日 vs 前々日、および7日平均）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l1_repo_deterioration AS
WITH dates AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Tokyo')::date AS today_jst
),
bounds AS (
    SELECT
        today_jst - 1 AS d_yesterday,
        today_jst - 2 AS d_before,
        today_jst - 8 AS d_week_start
    FROM dates
),
y AS (
    SELECT a.* FROM agg_daily_repo_metrics AS a
    CROSS JOIN bounds AS b
    WHERE a.metric_date = b.d_yesterday
),
b AS (
    SELECT a.* FROM agg_daily_repo_metrics AS a
    CROSS JOIN bounds AS bo
    WHERE a.metric_date = bo.d_before
),
avg7 AS (
    SELECT
        a.repo_id,
        ROUND(AVG(a.success_rate)::numeric, 2) AS avg_success_rate_7d,
        ROUND(AVG(a.p95_duration_ms)::numeric, 0) AS avg_p95_ms_7d
    FROM agg_daily_repo_metrics AS a
    CROSS JOIN bounds AS bo
    WHERE a.metric_date > bo.d_week_start AND a.metric_date <= bo.d_yesterday
    GROUP BY a.repo_id
)
SELECT
    d.repo_full_name,
    d.platform,
    y.success_rate AS success_rate_yesterday,
    b.success_rate AS success_rate_day_before,
    ROUND((y.success_rate - b.success_rate)::numeric, 2) AS success_rate_delta_1d,
    a7.avg_success_rate_7d,
    ROUND((y.success_rate - a7.avg_success_rate_7d)::numeric, 2) AS success_rate_vs_7d_avg,
    y.p95_duration_ms AS p95_ms_yesterday,
    b.p95_duration_ms AS p95_ms_day_before,
    a7.avg_p95_ms_7d,
    y.failed_runs AS failed_runs_yesterday,
    y.total_runs AS total_runs_yesterday,
    CASE
        WHEN y.success_rate < b.success_rate - 5 THEN TRUE
        WHEN y.p95_duration_ms > b.p95_duration_ms * 1.25
            AND b.p95_duration_ms > 0 THEN TRUE
        WHEN y.failed_runs > b.failed_runs * 1.5 AND y.failed_runs >= 3 THEN TRUE
        ELSE FALSE
    END AS deterioration_flag,
    y.computed_at AS last_computed_at,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM y
INNER JOIN dim_repo AS d ON d.repo_id = y.repo_id
LEFT JOIN b ON b.repo_id = y.repo_id
LEFT JOIN avg7 AS a7 ON a7.repo_id = y.repo_id;

-- ---------------------------------------------------------------------------
-- L2: リポジトリ日次トレンド
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_repo_trend AS
SELECT
    d.repo_full_name,
    a.metric_date,
    a.total_runs,
    a.success_runs,
    a.failed_runs,
    a.success_rate AS success_rate_pct,
    a.p50_duration_ms,
    a.p95_duration_ms,
    a.retry_runs,
    a.retry_rate AS retry_rate_pct,
    a.computed_at,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id;

-- ---------------------------------------------------------------------------
-- L2: 失敗の多いワークフロー（過去30日）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_workflow_fail_top AS
SELECT
    d.repo_full_name,
    f.workflow_name,
    COUNT(*) AS total_runs,
    SUM(
        CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
    ) AS failure_count,
    ROUND(
        100.0 * SUM(
            CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS failure_rate_pct,
    MAX(f.started_at) FILTER (
        WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
    ) AS last_failure_at,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
GROUP BY
    d.repo_full_name,
    d.project_name,
    d.tag_slugs,
    f.workflow_name;

-- ---------------------------------------------------------------------------
-- L2: 実行時間の長いワークフロー（過去30日）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_workflow_duration_top AS
SELECT
    d.repo_full_name,
    f.workflow_name,
    COUNT(*) AS total_runs,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p50_duration_ms,
    ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p95_duration_ms,
    ROUND(AVG(f.duration_ms)::numeric, 0) AS avg_duration_ms,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
  AND f.duration_ms IS NOT NULL
GROUP BY
    d.repo_full_name,
    d.project_name,
    d.tag_slugs,
    f.workflow_name;

-- ---------------------------------------------------------------------------
-- L2: 失敗理由内訳
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_failure_reason_breakdown AS
SELECT
    d.repo_full_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS fail_date,
    dr.reason_category,
    dr.reason_subcategory,
    COUNT(*) AS failure_runs,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN fact_run_failure_reason AS fr ON fr.run_pk = f.run_pk
INNER JOIN dim_failure_reason AS dr ON dr.reason_id = fr.reason_id
WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
  AND f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    d.repo_full_name,
    d.project_name,
    d.tag_slugs,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date,
    dr.reason_category,
    dr.reason_subcategory;

-- ---------------------------------------------------------------------------
-- L2: ステップ失敗ヒートマップ
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_step_failure_heatmap AS
SELECT
    d.repo_full_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS run_date,
    s.step_name,
    COUNT(*) AS step_runs,
    SUM(
        CASE WHEN UPPER(s.status) IN ('FAILURE', 'TIMEOUT') THEN 1 ELSE 0 END
    ) AS step_failures,
    ROUND(
        100.0 * SUM(
            CASE WHEN UPPER(s.status) IN ('FAILURE', 'TIMEOUT') THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS step_failure_rate_pct,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM fact_step_run AS s
INNER JOIN fact_pipeline_run AS f ON f.run_pk = s.run_pk
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
GROUP BY
    d.repo_full_name,
    d.project_name,
    d.tag_slugs,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date,
    s.step_name;

-- ---------------------------------------------------------------------------
-- L2: 再実行率（日次）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_retry_flake_trend AS
SELECT
    d.repo_full_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS run_date,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) AS retry_runs,
    ROUND(
        100.0 * SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS retry_rate_pct,
    COALESCE(d.project_name, '(未所属)') AS project_name,
    NULLIF(d.tag_slugs, '') AS tag_slugs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    d.repo_full_name,
    d.project_name,
    d.tag_slugs,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date;

-- ---------------------------------------------------------------------------
-- L2: アクション候補（ルールベース）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_action_candidates AS
SELECT
    w.repo_full_name,
    w.workflow_name AS target_workflow,
    w.failure_count,
    w.failure_rate_pct,
    w.last_failure_at,
    'review_failures'::text AS suggested_action,
    CASE
        WHEN w.failure_rate_pct >= 50 AND w.failure_count >= 5 THEN 1
        WHEN w.failure_count >= 10 THEN 2
        ELSE 3
    END AS priority_rank,
    w.project_name,
    w.tag_slugs
FROM vw_l2_workflow_fail_top AS w
WHERE w.failure_count >= 3;

-- ---------------------------------------------------------------------------
-- L2: 日次トレンド（プラットフォーム / プロジェクト / タグ集約）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_platform_trend AS
SELECT
    d.platform,
    a.metric_date,
    SUM(a.total_runs) AS total_runs,
    SUM(a.success_runs) AS success_runs,
    SUM(a.failed_runs) AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS p50_duration_ms,
    ROUND(AVG(a.p95_duration_ms)::numeric, 0) AS p95_duration_ms,
    SUM(a.retry_runs) AS retry_runs,
    ROUND(
        100.0 * SUM(a.retry_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS retry_rate_pct,
    MAX(a.computed_at) AS computed_at
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id
GROUP BY d.platform, a.metric_date;

CREATE OR REPLACE VIEW vw_l2_project_trend AS
SELECT
    COALESCE(d.project_name, '(未所属)') AS project_name,
    a.metric_date,
    SUM(a.total_runs) AS total_runs,
    SUM(a.success_runs) AS success_runs,
    SUM(a.failed_runs) AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS p50_duration_ms,
    ROUND(AVG(a.p95_duration_ms)::numeric, 0) AS p95_duration_ms,
    SUM(a.retry_runs) AS retry_runs,
    ROUND(
        100.0 * SUM(a.retry_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS retry_rate_pct,
    MAX(a.computed_at) AS computed_at
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id
GROUP BY COALESCE(d.project_name, '(未所属)'), a.metric_date;

CREATE OR REPLACE VIEW vw_l2_tag_trend AS
SELECT
    t.slug AS tag_slug,
    t.name AS tag_name,
    a.metric_date,
    SUM(a.total_runs) AS total_runs,
    SUM(a.success_runs) AS success_runs,
    SUM(a.failed_runs) AS failed_runs,
    ROUND(
        100.0 * SUM(a.success_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS success_rate_pct,
    ROUND(AVG(a.p50_duration_ms)::numeric, 0) AS p50_duration_ms,
    ROUND(AVG(a.p95_duration_ms)::numeric, 0) AS p95_duration_ms,
    SUM(a.retry_runs) AS retry_runs,
    ROUND(
        100.0 * SUM(a.retry_runs) / NULLIF(SUM(a.total_runs), 0),
        2
    ) AS retry_rate_pct,
    MAX(a.computed_at) AS computed_at
FROM agg_daily_repo_metrics AS a
INNER JOIN dim_repo AS d ON d.repo_id = a.repo_id
INNER JOIN repository_tags AS rt ON rt.repository_id = d.repo_id
INNER JOIN tags AS t ON t.id = rt.tag_id
GROUP BY t.slug, t.name, a.metric_date;

-- ---------------------------------------------------------------------------
-- L2: ワークフロー系（プラットフォーム / プロジェクト / タグ）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_l2_workflow_fail_top_by_platform AS
SELECT
    d.platform,
    f.workflow_name,
    COUNT(*) AS total_runs,
    SUM(
        CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
    ) AS failure_count,
    ROUND(
        100.0 * SUM(
            CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS failure_rate_pct,
    MAX(f.started_at) FILTER (
        WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
    ) AS last_failure_at
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
GROUP BY d.platform, f.workflow_name;

CREATE OR REPLACE VIEW vw_l2_workflow_fail_top_by_project AS
SELECT
    COALESCE(d.project_name, '(未所属)') AS project_name,
    f.workflow_name,
    COUNT(*) AS total_runs,
    SUM(
        CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
    ) AS failure_count,
    ROUND(
        100.0 * SUM(
            CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS failure_rate_pct,
    MAX(f.started_at) FILTER (
        WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
    ) AS last_failure_at
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
GROUP BY COALESCE(d.project_name, '(未所属)'), f.workflow_name;

CREATE OR REPLACE VIEW vw_l2_workflow_fail_top_by_tag AS
SELECT
    t.slug AS tag_slug,
    t.name AS tag_name,
    f.workflow_name,
    COUNT(*) AS total_runs,
    SUM(
        CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
    ) AS failure_count,
    ROUND(
        100.0 * SUM(
            CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS failure_rate_pct,
    MAX(f.started_at) FILTER (
        WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
    ) AS last_failure_at
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN repository_tags AS rt ON rt.repository_id = d.repo_id
INNER JOIN tags AS t ON t.id = rt.tag_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
GROUP BY t.slug, t.name, f.workflow_name;

CREATE OR REPLACE VIEW vw_l2_workflow_duration_top_by_platform AS
SELECT
    d.platform,
    f.workflow_name,
    COUNT(*) AS total_runs,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p50_duration_ms,
    ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p95_duration_ms,
    ROUND(AVG(f.duration_ms)::numeric, 0) AS avg_duration_ms
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
  AND f.duration_ms IS NOT NULL
GROUP BY d.platform, f.workflow_name;

CREATE OR REPLACE VIEW vw_l2_workflow_duration_top_by_project AS
SELECT
    COALESCE(d.project_name, '(未所属)') AS project_name,
    f.workflow_name,
    COUNT(*) AS total_runs,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p50_duration_ms,
    ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p95_duration_ms,
    ROUND(AVG(f.duration_ms)::numeric, 0) AS avg_duration_ms
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
  AND f.duration_ms IS NOT NULL
GROUP BY COALESCE(d.project_name, '(未所属)'), f.workflow_name;

CREATE OR REPLACE VIEW vw_l2_workflow_duration_top_by_tag AS
SELECT
    t.slug AS tag_slug,
    t.name AS tag_name,
    f.workflow_name,
    COUNT(*) AS total_runs,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p50_duration_ms,
    ROUND((percentile_cont(0.95) WITHIN GROUP (ORDER BY f.duration_ms))::numeric, 0) AS p95_duration_ms,
    ROUND(AVG(f.duration_ms)::numeric, 0) AS avg_duration_ms
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN repository_tags AS rt ON rt.repository_id = d.repo_id
INNER JOIN tags AS t ON t.id = rt.tag_id
WHERE f.started_at >= NOW() - INTERVAL '30 days'
  AND f.duration_ms IS NOT NULL
GROUP BY t.slug, t.name, f.workflow_name;

CREATE OR REPLACE VIEW vw_l2_failure_reason_breakdown_by_platform AS
SELECT
    d.platform,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS fail_date,
    dr.reason_category,
    dr.reason_subcategory,
    COUNT(*) AS failure_runs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN fact_run_failure_reason AS fr ON fr.run_pk = f.run_pk
INNER JOIN dim_failure_reason AS dr ON dr.reason_id = fr.reason_id
WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
  AND f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    d.platform,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date,
    dr.reason_category,
    dr.reason_subcategory;

CREATE OR REPLACE VIEW vw_l2_failure_reason_breakdown_by_project AS
SELECT
    COALESCE(d.project_name, '(未所属)') AS project_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS fail_date,
    dr.reason_category,
    dr.reason_subcategory,
    COUNT(*) AS failure_runs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN fact_run_failure_reason AS fr ON fr.run_pk = f.run_pk
INNER JOIN dim_failure_reason AS dr ON dr.reason_id = fr.reason_id
WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
  AND f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    COALESCE(d.project_name, '(未所属)'),
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date,
    dr.reason_category,
    dr.reason_subcategory;

CREATE OR REPLACE VIEW vw_l2_failure_reason_breakdown_by_tag AS
SELECT
    t.slug AS tag_slug,
    t.name AS tag_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS fail_date,
    dr.reason_category,
    dr.reason_subcategory,
    COUNT(*) AS failure_runs
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN repository_tags AS rt ON rt.repository_id = d.repo_id
INNER JOIN tags AS t ON t.id = rt.tag_id
INNER JOIN fact_run_failure_reason AS fr ON fr.run_pk = f.run_pk
INNER JOIN dim_failure_reason AS dr ON dr.reason_id = fr.reason_id
WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED')
  AND f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    t.slug,
    t.name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date,
    dr.reason_category,
    dr.reason_subcategory;

CREATE OR REPLACE VIEW vw_l2_retry_flake_trend_by_platform AS
SELECT
    d.platform,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS run_date,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) AS retry_runs,
    ROUND(
        100.0 * SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS retry_rate_pct
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    d.platform,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date;

CREATE OR REPLACE VIEW vw_l2_retry_flake_trend_by_project AS
SELECT
    COALESCE(d.project_name, '(未所属)') AS project_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS run_date,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) AS retry_runs,
    ROUND(
        100.0 * SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS retry_rate_pct
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
WHERE f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    COALESCE(d.project_name, '(未所属)'),
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date;

CREATE OR REPLACE VIEW vw_l2_retry_flake_trend_by_tag AS
SELECT
    t.slug AS tag_slug,
    t.name AS tag_name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS run_date,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) AS retry_runs,
    ROUND(
        100.0 * SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS retry_rate_pct
FROM fact_pipeline_run AS f
INNER JOIN dim_repo AS d ON d.repo_id = f.repo_id
INNER JOIN repository_tags AS rt ON rt.repository_id = d.repo_id
INNER JOIN tags AS t ON t.id = rt.tag_id
WHERE f.started_at >= NOW() - INTERVAL '90 days'
GROUP BY
    t.slug,
    t.name,
    (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date;

CREATE OR REPLACE VIEW vw_l2_action_candidates_by_platform AS
SELECT
    w.platform,
    w.workflow_name AS target_workflow,
    w.failure_count,
    w.failure_rate_pct,
    w.last_failure_at,
    'review_failures'::text AS suggested_action,
    CASE
        WHEN w.failure_rate_pct >= 50 AND w.failure_count >= 5 THEN 1
        WHEN w.failure_count >= 10 THEN 2
        ELSE 3
    END AS priority_rank
FROM vw_l2_workflow_fail_top_by_platform AS w
WHERE w.failure_count >= 3;

CREATE OR REPLACE VIEW vw_l2_action_candidates_by_project AS
SELECT
    w.project_name,
    w.workflow_name AS target_workflow,
    w.failure_count,
    w.failure_rate_pct,
    w.last_failure_at,
    'review_failures'::text AS suggested_action,
    CASE
        WHEN w.failure_rate_pct >= 50 AND w.failure_count >= 5 THEN 1
        WHEN w.failure_count >= 10 THEN 2
        ELSE 3
    END AS priority_rank
FROM vw_l2_workflow_fail_top_by_project AS w
WHERE w.failure_count >= 3;

CREATE OR REPLACE VIEW vw_l2_action_candidates_by_tag AS
SELECT
    w.tag_slug,
    w.tag_name,
    w.workflow_name AS target_workflow,
    w.failure_count,
    w.failure_rate_pct,
    w.last_failure_at,
    'review_failures'::text AS suggested_action,
    CASE
        WHEN w.failure_rate_pct >= 50 AND w.failure_count >= 5 THEN 1
        WHEN w.failure_count >= 10 THEN 2
        ELSE 3
    END AS priority_rank
FROM vw_l2_workflow_fail_top_by_tag AS w
WHERE w.failure_count >= 3;
