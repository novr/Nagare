-- メトリクスマートの同期（repositories / pipeline_runs / jobs → v2 スキーマ）
-- 冪等: 何度実行してもよい。
-- 実行: SELECT refresh_cicd_metrics_marts();

-- ---------------------------------------------------------------------------
-- 同期関数
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_cicd_metrics_marts()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dim_failure_reason (reason_id, reason_category, reason_subcategory, severity)
    VALUES
        (1, 'uncategorized', 'unknown', 1),
        (2, 'test', 'test_failure', 2),
        (3, 'timeout', 'timeout', 2),
        (4, 'cancelled', 'cancelled', 1),
        (5, 'lint', 'static_analysis', 2),
        (6, 'build', 'compile_or_assemble', 2),
        (7, 'deploy', 'release_or_publish', 2),
        (8, 'dependency', 'packages_or_tools', 2),
        (9, 'security', 'sast_or_supply_chain', 2)
    ON CONFLICT (reason_id) DO NOTHING;

    PERFORM setval(
        'dim_failure_reason_reason_id_seq',
        GREATEST((SELECT COALESCE(MAX(reason_id), 1) FROM dim_failure_reason), 1)
    );

    -- dim_repo
    INSERT INTO dim_repo (repo_id, repo_full_name, platform, is_active, updated_at)
    SELECT
        r.id,
        r.repository_name,
        r.source,
        r.active,
        NOW()
    FROM repositories AS r
    ON CONFLICT (repo_id) DO UPDATE SET
        repo_full_name = EXCLUDED.repo_full_name,
        platform = EXCLUDED.platform,
        is_active = EXCLUDED.is_active,
        updated_at = NOW();

    -- fact_pipeline_run（pipeline_runs から）
    INSERT INTO fact_pipeline_run (
        legacy_run_id,
        repo_id,
        source_run_id,
        source,
        workflow_name,
        branch,
        event_type,
        status,
        started_at,
        completed_at,
        duration_ms,
        commit_sha,
        is_retry,
        retry_group_key,
        url,
        synced_at
    )
    SELECT
        pr.id,
        pr.repository_id,
        pr.source_run_id,
        pr.source,
        pr.pipeline_name,
        pr.branch_name,
        pr.trigger_event,
        pr.status,
        pr.started_at,
        pr.completed_at,
        pr.duration_ms,
        pr.commit_sha,
        FALSE,
        NULL,
        pr.url,
        NOW()
    FROM pipeline_runs AS pr
    ON CONFLICT (legacy_run_id) DO UPDATE SET
        repo_id = EXCLUDED.repo_id,
        source_run_id = EXCLUDED.source_run_id,
        source = EXCLUDED.source,
        workflow_name = EXCLUDED.workflow_name,
        branch = EXCLUDED.branch,
        event_type = EXCLUDED.event_type,
        status = EXCLUDED.status,
        started_at = EXCLUDED.started_at,
        completed_at = EXCLUDED.completed_at,
        duration_ms = EXCLUDED.duration_ms,
        commit_sha = EXCLUDED.commit_sha,
        url = EXCLUDED.url,
        synced_at = NOW();

    -- 同一 commit + workflow + branch で 2 回目以降を再実行とみなす
    WITH ranked AS (
        SELECT
            run_pk,
            ROW_NUMBER() OVER (
                PARTITION BY
                    repo_id,
                    workflow_name,
                    COALESCE(branch, ''),
                    COALESCE(commit_sha, '')
                ORDER BY started_at NULLS LAST, run_pk
            ) AS rn
        FROM fact_pipeline_run
        WHERE commit_sha IS NOT NULL AND started_at IS NOT NULL
    )
    UPDATE fact_pipeline_run AS f
    SET is_retry = (r.rn > 1),
        retry_group_key =
            f.repo_id::text || '|' || f.workflow_name || '|' || COALESCE(f.branch, '') || '|'
            || COALESCE(f.commit_sha, '')
    FROM ranked AS r
    WHERE f.run_pk = r.run_pk;

    -- commit なしは再実行フラグを落とす
    UPDATE fact_pipeline_run
    SET is_retry = FALSE,
        retry_group_key = NULL
    WHERE commit_sha IS NULL OR started_at IS NULL;

    -- fact_step_run
    INSERT INTO fact_step_run (
        legacy_job_id,
        run_pk,
        step_name,
        status,
        started_at,
        completed_at,
        duration_ms,
        synced_at
    )
    SELECT
        j.id,
        f.run_pk,
        j.job_name,
        j.status,
        j.started_at,
        j.completed_at,
        j.duration_ms,
        NOW()
    FROM jobs AS j
    INNER JOIN fact_pipeline_run AS f ON f.legacy_run_id = j.run_id
    ON CONFLICT (legacy_job_id) DO UPDATE SET
        run_pk = EXCLUDED.run_pk,
        step_name = EXCLUDED.step_name,
        status = EXCLUDED.status,
        started_at = EXCLUDED.started_at,
        completed_at = EXCLUDED.completed_at,
        duration_ms = EXCLUDED.duration_ms,
        synced_at = NOW();

    -- 失敗理由（ヒューリスティック: 失敗ジョブ名 > ワークフロー名 > パイプライン status）
    TRUNCATE TABLE fact_run_failure_reason;

    INSERT INTO fact_run_failure_reason (run_pk, reason_id, confidence, detected_from)
    SELECT
        f.run_pk,
        CASE
            WHEN UPPER(f.status) = 'CANCELLED' THEN 4
            WHEN UPPER(f.status) = 'TIMEOUT' THEN 3
            WHEN EXISTS (
                SELECT 1
                FROM fact_step_run AS s
                WHERE s.run_pk = f.run_pk
                  AND UPPER(s.status) IN ('FAILURE', 'TIMEOUT')
                  AND s.step_name ~* '(^|[^a-z])(test|tests|testing|spec|jest|pytest|rspec|vitest|mocha|unittest|xctest|espresso|robolectric|detox|playwright|cypress|karma|e2e|ui[[:space:]]*test|instrumentation)([^a-z]|$)'
            )
            THEN 2
            WHEN EXISTS (
                SELECT 1
                FROM fact_step_run AS s
                WHERE s.run_pk = f.run_pk
                  AND UPPER(s.status) IN ('FAILURE', 'TIMEOUT')
                  AND s.step_name ~* '(lint|swiftlint|detekt|ktlint|rubocop|eslint|prettier|checkstyle|sonar|spotbugs|pmd|static[[:space:]]*analysis|code[[:space:]]*style)'
            )
            THEN 5
            WHEN EXISTS (
                SELECT 1
                FROM fact_step_run AS s
                WHERE s.run_pk = f.run_pk
                  AND UPPER(s.status) IN ('FAILURE', 'TIMEOUT')
                  AND s.step_name ~* '(deploy|release|publish|upload|distribution|testflight|app[[:space:]]*store|play[[:space:]]*store|firebase[[:space:]]*app|hockeyapp|bitrise[[:space:]]*deploy)'
            )
            THEN 7
            WHEN EXISTS (
                SELECT 1
                FROM fact_step_run AS s
                WHERE s.run_pk = f.run_pk
                  AND UPPER(s.status) IN ('FAILURE', 'TIMEOUT')
                  AND s.step_name ~* '(npm|yarn|pnpm|bun|bundle[[:space:]]*install|pod[[:space:]]*install|carthage|cocoapods|gradle[[:space:]]*dependencies|pip[[:space:]]*install|poetry|nuget|dependabot|renovate|cache[[:space:]]*dependencies|install[[:space:]]*deps)'
            )
            THEN 8
            WHEN EXISTS (
                SELECT 1
                FROM fact_step_run AS s
                WHERE s.run_pk = f.run_pk
                  AND UPPER(s.status) IN ('FAILURE', 'TIMEOUT')
                  AND s.step_name ~* '(codeql|snyk|trivy|grype|osv|secret[[:space:]]*scan|gitleaks|trufflehog|semgrep)'
            )
            THEN 9
            WHEN EXISTS (
                SELECT 1
                FROM fact_step_run AS s
                WHERE s.run_pk = f.run_pk
                  AND UPPER(s.status) IN ('FAILURE', 'TIMEOUT')
                  AND s.step_name ~* '(build|compile|assemble|xcodebuild|gradle|buck|bazel|cmake|cmake[[:space:]]*build|make[[:space:]]+|carthage|archive|package[[:space:]]*app)'
            )
            THEN 6
            WHEN f.workflow_name ~* '(^|[^a-z])(test|tests|spec|jest|pytest|unittest|e2e|instrumentation)([^a-z]|$)'
            THEN 2
            WHEN f.workflow_name ~* '(lint|swiftlint|detekt|eslint|sonar|static)'
            THEN 5
            WHEN f.workflow_name ~* '(deploy|release|publish|distribute|store|testflight)'
            THEN 7
            WHEN f.workflow_name ~* '(dependabot|renovate|npm|yarn|gradle|pod|cocoapods|carthage|bundle)'
            THEN 8
            WHEN f.workflow_name ~* '(codeql|snyk|security|scan)'
            THEN 9
            WHEN f.workflow_name ~* '(build|compile|assemble|xcodebuild|ci|continuous[[:space:]]*integration)'
            THEN 6
            ELSE 1
        END,
        0.8,
        'heuristic_v2'
    FROM fact_pipeline_run AS f
    WHERE UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED');

    -- 日次集約（直近120日を再計算）
    DELETE FROM agg_daily_repo_metrics
    WHERE metric_date >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Tokyo')::date - 120;

    INSERT INTO agg_daily_repo_metrics (
        metric_date,
        repo_id,
        total_runs,
        success_runs,
        failed_runs,
        success_rate,
        p50_duration_ms,
        p95_duration_ms,
        retry_runs,
        retry_rate,
        flake_suspect_rate,
        computed_at
    )
    SELECT
        (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date AS metric_date,
        f.repo_id,
        COUNT(*)::int AS total_runs,
        SUM(
            CASE WHEN UPPER(f.status) = 'SUCCESS' THEN 1 ELSE 0 END
        )::int AS success_runs,
        SUM(
            CASE WHEN UPPER(f.status) IN ('FAILURE', 'TIMEOUT', 'CANCELLED') THEN 1 ELSE 0 END
        )::int AS failed_runs,
        ROUND(
            100.0 * SUM(CASE WHEN UPPER(f.status) = 'SUCCESS' THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0),
            2
        ) AS success_rate,
        (percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_ms))::bigint AS p50_duration_ms,
        (percentile_cont(0.95) WITHIN GROUP (ORDER BY f.duration_ms))::bigint AS p95_duration_ms,
        SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END)::int AS retry_runs,
        ROUND(
            100.0 * SUM(CASE WHEN f.is_retry THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
            2
        ) AS retry_rate,
        0::numeric(6, 2) AS flake_suspect_rate,
        NOW()
    FROM fact_pipeline_run AS f
    WHERE f.started_at IS NOT NULL
      AND (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date
          >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Tokyo')::date - 120
    GROUP BY
        (f.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo')::date,
        f.repo_id;

    RETURN;
END;
$$;
