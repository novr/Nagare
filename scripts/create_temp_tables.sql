-- 一時テーブル作成スクリプト
-- ADR-006: 一時テーブル方式によるDAG間データ転送
--
-- 目的: XComの代わりに一時テーブルを使用してDAGタスク間でデータを転送
-- XComサイズを99%削減（81MB → 数KB）
--
-- 使用方法:
--   docker-compose exec -T postgres psql -U nagare_user -d nagare < scripts/create_temp_tables.sql

-- ワークフロー実行データの一時テーブル
-- GitHub ActionsとBitriseの生データを保存
CREATE TABLE IF NOT EXISTS temp_workflow_runs (
    task_id VARCHAR(250) NOT NULL,          -- バッチタスクID（識別用、例: fetch_github_batch_0）
    run_id VARCHAR(250) NOT NULL,           -- DAG run ID（Airflow生成、例: manual__2025-11-04T10:00:00）
    source_run_id VARCHAR(255) NOT NULL,    -- GitHub/BitriseのRun ID（例: 12345678）
    source VARCHAR(50) NOT NULL,            -- ソース識別子（github_actions, bitrise）
    data JSONB NOT NULL,                    -- 生データ（GitHub/Bitrise API レスポンス）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (task_id, run_id, source_run_id)
);

-- 変換済みワークフロー実行データの一時テーブル
-- transform_dataタスクで汎用データモデルに変換されたデータ
CREATE TABLE IF NOT EXISTS temp_transformed_runs (
    run_id VARCHAR(250) NOT NULL,           -- DAG run ID
    source_run_id VARCHAR(255) NOT NULL,    -- GitHub/BitriseのRun ID
    source VARCHAR(50) NOT NULL,            -- ソース識別子
    data JSONB NOT NULL,                    -- 変換済みデータ（汎用データモデル形式）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (run_id, source_run_id)
);

-- ジョブデータの一時テーブル
-- GitHub Actionsのワークフロージョブの詳細データ
CREATE TABLE IF NOT EXISTS temp_workflow_jobs (
    run_id VARCHAR(250) NOT NULL,           -- DAG run ID
    source_job_id VARCHAR(255) NOT NULL,    -- GitHubのJob ID
    source_run_id VARCHAR(255) NOT NULL,    -- 親のWorkflow Run ID
    data JSONB NOT NULL,                    -- ジョブデータ
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (run_id, source_job_id)
);

-- インデックス（クエリパフォーマンス最適化）
-- run_idでの全件取得を高速化（最も頻繁なクエリパターン）
CREATE INDEX IF NOT EXISTS idx_temp_workflow_runs_run_id
    ON temp_workflow_runs(run_id);

CREATE INDEX IF NOT EXISTS idx_temp_transformed_runs_run_id
    ON temp_transformed_runs(run_id);

CREATE INDEX IF NOT EXISTS idx_temp_workflow_jobs_run_id
    ON temp_workflow_jobs(run_id);

-- 古いデータの自動削除用インデックス
-- cleanup_temp_tables DAGで使用
CREATE INDEX IF NOT EXISTS idx_temp_workflow_runs_created_at
    ON temp_workflow_runs(created_at);

CREATE INDEX IF NOT EXISTS idx_temp_transformed_runs_created_at
    ON temp_transformed_runs(created_at);

CREATE INDEX IF NOT EXISTS idx_temp_workflow_jobs_created_at
    ON temp_workflow_jobs(created_at);

-- パフォーマンス統計情報を表示
DO $$
DECLARE
    temp_runs_count INT;
    temp_transformed_count INT;
    temp_jobs_count INT;
BEGIN
    SELECT COUNT(*) INTO temp_runs_count FROM temp_workflow_runs;
    SELECT COUNT(*) INTO temp_transformed_count FROM temp_transformed_runs;
    SELECT COUNT(*) INTO temp_jobs_count FROM temp_workflow_jobs;

    RAISE NOTICE '✅ Temporary tables created successfully';
    RAISE NOTICE '   - temp_workflow_runs: % records', temp_runs_count;
    RAISE NOTICE '   - temp_transformed_runs: % records', temp_transformed_count;
    RAISE NOTICE '   - temp_workflow_jobs: % records', temp_jobs_count;
END $$;
