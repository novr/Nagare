-- CI/CD メトリクスダッシュボード v2（Star schema）
-- 既存の repositories / pipeline_runs / jobs から同期して利用する。
-- 適用: psql -f scripts/metrics_dashboard_v2_schema.sql

-- ---------------------------------------------------------------------------
-- ディメンション: リポジトリ（repositories.id と 1:1）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_repo (
    repo_id BIGINT PRIMARY KEY REFERENCES repositories (id) ON DELETE CASCADE,
    repo_full_name VARCHAR(512) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_repo_active ON dim_repo (is_active);

-- ---------------------------------------------------------------------------
-- ファクト: パイプライン実行（pipeline_runs.id と 1:1）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_pipeline_run (
    run_pk BIGSERIAL PRIMARY KEY,
    legacy_run_id BIGINT NOT NULL UNIQUE REFERENCES pipeline_runs (id) ON DELETE CASCADE,
    repo_id BIGINT NOT NULL REFERENCES dim_repo (repo_id) ON DELETE CASCADE,
    source_run_id VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL,
    workflow_name VARCHAR(1000) NOT NULL,
    branch VARCHAR(500),
    event_type VARCHAR(50),
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    commit_sha VARCHAR(255),
    is_retry BOOLEAN NOT NULL DEFAULT FALSE,
    retry_group_key TEXT,
    url TEXT,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_pipeline_run_repo_started
    ON fact_pipeline_run (repo_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_run_status ON fact_pipeline_run (status);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_run_source ON fact_pipeline_run (source);

-- ---------------------------------------------------------------------------
-- ファクト: ステップ（ジョブ）実行 — jobs.id と 1:1
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_step_run (
    step_pk BIGSERIAL PRIMARY KEY,
    legacy_job_id BIGINT NOT NULL UNIQUE REFERENCES jobs (id) ON DELETE CASCADE,
    run_pk BIGINT NOT NULL REFERENCES fact_pipeline_run (run_pk) ON DELETE CASCADE,
    step_name VARCHAR(512) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_step_run_run_pk ON fact_step_run (run_pk);
CREATE INDEX IF NOT EXISTS idx_fact_step_run_status ON fact_step_run (status);

-- ---------------------------------------------------------------------------
-- 失敗理由ディメンション・紐付け
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_failure_reason (
    reason_id SERIAL PRIMARY KEY,
    reason_category VARCHAR(100) NOT NULL,
    reason_subcategory VARCHAR(100),
    matcher_rule TEXT,
    severity INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fact_run_failure_reason (
    run_pk BIGINT NOT NULL REFERENCES fact_pipeline_run (run_pk) ON DELETE CASCADE,
    reason_id INT NOT NULL REFERENCES dim_failure_reason (reason_id) ON DELETE CASCADE,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.0,
    detected_from VARCHAR(64) NOT NULL DEFAULT 'default',
    PRIMARY KEY (run_pk, reason_id)
);

-- ---------------------------------------------------------------------------
-- 日次集約（L1/L2 表示用）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agg_daily_repo_metrics (
    metric_date DATE NOT NULL,
    repo_id BIGINT NOT NULL REFERENCES dim_repo (repo_id) ON DELETE CASCADE,
    total_runs INT NOT NULL,
    success_runs INT NOT NULL,
    failed_runs INT NOT NULL,
    success_rate NUMERIC(6, 2),
    p50_duration_ms BIGINT,
    p95_duration_ms BIGINT,
    retry_runs INT NOT NULL DEFAULT 0,
    retry_rate NUMERIC(6, 2),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (metric_date, repo_id)
);

CREATE INDEX IF NOT EXISTS idx_agg_daily_repo_metrics_date ON agg_daily_repo_metrics (metric_date DESC);

-- ---------------------------------------------------------------------------
-- 増分 refresh 用ウォーターマーク（1 行のみ id=1）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metrics_mart_sync_state (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_pipeline_updated_at TIMESTAMPTZ,
    last_job_updated_at TIMESTAMPTZ,
    row_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO metrics_mart_sync_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
