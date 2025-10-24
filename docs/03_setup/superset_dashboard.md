# Superset ダッシュボード設定ガイド

Apache Supersetを使用したCI/CDメトリクスダッシュボードの設定方法。

## 概要

Supersetを使用して、GitHub Actionsから収集したデータを可視化します。

**アクセス情報**:
- URL: http://localhost:8088
- ユーザー名: `admin`
- パスワード: `.env`の`SUPERSET_ADMIN_PASSWORD`

## 1. PostgreSQLデータソースの接続

### 1.1. データベース接続の追加

1. Supersetにログイン後、右上の`+`メニューから**Data** → **Connect database**を選択

2. **PostgreSQL**を選択

3. 接続情報を入力:

```
BASIC タブ:
- HOST: postgres (Docker内部ホスト名)
- PORT: 5432
- DATABASE NAME: nagare
- USERNAME: nagare_user
- PASSWORD: .envのDATABASE_PASSWORD
- DISPLAY NAME: Nagare PostgreSQL

ADVANCED タブ:
- SQL Lab タブ: "Expose database in SQL Lab" をチェック
- Performance タブ: デフォルト設定でOK
```

4. **CONNECT**をクリックして接続テスト

5. 成功したら**FINISH**をクリック

### 1.2. 接続の確認

**SQL Lab**から接続を確認:
1. メニューから**SQL** → **SQL Lab**を選択
2. DATABASEで"Nagare PostgreSQL"を選択
3. SCHEMAで"public"を選択
4. 簡単なクエリで確認:

```sql
SELECT COUNT(*) FROM repositories;
SELECT COUNT(*) FROM pipeline_runs;
SELECT COUNT(*) FROM jobs;
```

## 2. データセット（Dataset）の作成

Supersetでチャートを作成するには、まずデータセットを定義します。

### 2.1. テーブルベースのデータセット

#### repositories テーブル

1. **Data** → **Datasets** → **+ Dataset**
2. DATABASE: Nagare PostgreSQL
3. SCHEMA: public
4. TABLE: repositories
5. **CREATE DATASET AND CREATE CHART**

### 2.2. SQLベースのデータセット（Virtual Dataset）

より複雑なメトリクスには、SQLクエリでデータセットを作成します。

#### パイプライン実行の成功率（日次）

```sql
-- Dataset名: pipeline_daily_success_rate
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
```

#### パイプライン実行時間の統計（日次）

```sql
-- Dataset名: pipeline_daily_duration
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
```

#### ジョブ別実行時間ランキング

```sql
-- Dataset名: job_duration_ranking
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
```

#### リポジトリ別パフォーマンスサマリー

```sql
-- Dataset名: repository_performance_summary
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
```

#### 失敗が多いジョブのランキング

```sql
-- Dataset名: failing_jobs_ranking
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
```

### 2.3. Virtual Datasetの作成方法

1. **SQL** → **SQL Lab**を選択
2. 上記のSQLクエリを貼り付けて実行
3. 結果が正しいことを確認
4. クエリエディタの右上から**SAVE** → **Save dataset**
5. Dataset名を入力（例: `pipeline_daily_success_rate`）
6. **SAVE & EXPLORE**をクリック

## 3. チャートの作成

### 3.1. 成功率トレンド（折れ線グラフ）

**使用データセット**: `pipeline_daily_success_rate`

1. **CHART TYPE**: Line Chart
2. **TIME**:
   - TEMPORAL COLUMN: `execution_date`
3. **METRICS**:
   - Metric: `success_rate_percent`
   - Label: "Success Rate (%)"
4. **DIMENSIONS**:
   - SERIES: `repository_name`
5. **FILTERS**:
   - 必要に応じて特定のリポジトリにフィルタ
6. **CUSTOMIZE**:
   - Title: "パイプライン成功率トレンド（30日間）"
   - X Axis Label: "日付"
   - Y Axis Label: "成功率 (%)"
   - Y Axis Bounds: Min 0, Max 100
7. **CREATE CHART** → **SAVE**

### 3.2. 平均実行時間トレンド（折れ線グラフ）

**使用データセット**: `pipeline_daily_duration`

1. **CHART TYPE**: Line Chart
2. **TIME**:
   - TEMPORAL COLUMN: `execution_date`
3. **METRICS**:
   - Metric: `avg_duration_seconds`
   - Label: "平均実行時間 (秒)"
4. **DIMENSIONS**:
   - SERIES: `repository_name`
5. **CUSTOMIZE**:
   - Title: "パイプライン平均実行時間トレンド（30日間）"
   - X Axis Label: "日付"
   - Y Axis Label: "実行時間 (秒)"
7. **CREATE CHART** → **SAVE**

### 3.3. ジョブ実行時間ランキング（横棒グラフ）

**使用データセット**: `job_duration_ranking`

1. **CHART TYPE**: Bar Chart
2. **QUERY**:
   - DIMENSIONS: `job_name`
   - METRICS: `avg_duration_seconds`
   - SORT BY: `avg_duration_seconds` DESC
   - ROW LIMIT: 20
3. **CUSTOMIZE**:
   - Title: "実行時間が長いジョブ Top 20"
   - X Axis Label: "平均実行時間 (秒)"
   - Y Axis Label: "ジョブ名"
   - Orientation: Horizontal (横向き)
4. **CREATE CHART** → **SAVE**

### 3.4. リポジトリ別成功率（円グラフ）

**使用データセット**: `repository_performance_summary`

1. **CHART TYPE**: Pie Chart
2. **QUERY**:
   - DIMENSION: `repository_name`
   - METRIC: `successful_runs`
3. **CUSTOMIZE**:
   - Title: "リポジトリ別成功実行数"
   - Show Labels: Yes
   - Show Legend: Yes
4. **CREATE CHART** → **SAVE**

### 3.5. 失敗ジョブランキング（テーブル）

**使用データセット**: `failing_jobs_ranking`

1. **CHART TYPE**: Table
2. **QUERY**:
   - COLUMNS: `repository_name`, `job_name`, `failure_count`, `failure_rate_percent`, `last_failure_at`
   - SORT BY: `failure_count` DESC
   - ROW LIMIT: 30
3. **CUSTOMIZE**:
   - Title: "失敗が多いジョブ Top 30"
   - Conditional Formatting:
     - `failure_rate_percent` > 50: 赤色
     - `failure_rate_percent` > 20: 黄色
4. **CREATE CHART** → **SAVE**

### 3.6. リポジトリパフォーマンスサマリー（Big Number）

**使用データセット**: `repository_performance_summary`

1. **CHART TYPE**: Big Number
2. **QUERY**:
   - METRIC: `AVG(success_rate_percent)`
3. **CUSTOMIZE**:
   - Title: "全体平均成功率"
   - Number Format: "0.00%"
   - Subheader: "過去30日間"
4. **CREATE CHART** → **SAVE**

## 4. ダッシュボードの作成

### 4.1. 新規ダッシュボード作成

1. **Dashboards** → **+ Dashboard**
2. Dashboard名: "CI/CD パフォーマンスダッシュボード"
3. **SAVE**

### 4.2. チャートの配置

作成したチャートをダッシュボードに追加:

**推奨レイアウト**:

```
┌─────────────────────────────────────────────────────────┐
│ タイトル: CI/CD パフォーマンスダッシュボード              │
├─────────────────────┬───────────────────────────────────┤
│ 全体平均成功率      │ リポジトリ別成功実行数（円グラフ）│
│ (Big Number)        │                                   │
├─────────────────────┴───────────────────────────────────┤
│ パイプライン成功率トレンド（折れ線グラフ）              │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ パイプライン平均実行時間トレンド（折れ線グラフ）        │
│                                                         │
├────────────────────────┬────────────────────────────────┤
│ 実行時間が長いジョブ   │ 失敗が多いジョブ               │
│ Top 20 (横棒グラフ)    │ Top 30 (テーブル)              │
└────────────────────────┴────────────────────────────────┘
```

### 4.3. フィルターの追加

ダッシュボードにインタラクティブなフィルターを追加:

1. **EDIT DASHBOARD**をクリック
2. **FILTERS**タブを選択
3. **+ ADD/EDIT FILTERS**
4. 以下のフィルターを追加:
   - **Date Range Filter**: `execution_date`
   - **Repository Filter**: `repository_name`
5. フィルターを全てのチャートに適用
6. **SAVE**

### 4.4. 自動更新の設定

1. **EDIT DASHBOARD**
2. 右上の設定アイコン → **AUTO REFRESH**
3. Interval: 5分
4. **SAVE**

## 5. ダッシュボードのエクスポート/インポート

### 5.1. エクスポート

ダッシュボード設定をバックアップ:

```bash
# Superset CLIを使用
docker exec nagare-superset superset export-dashboards \
    --dashboard-id <DASHBOARD_ID> \
    --file /tmp/dashboard_export.zip

# ファイルをローカルにコピー
docker cp nagare-superset:/tmp/dashboard_export.zip ./backups/
```

### 5.2. インポート

既存のダッシュボード設定をインポート:

```bash
# ファイルをコンテナにコピー
docker cp ./backups/dashboard_export.zip nagare-superset:/tmp/

# Superset CLIでインポート
docker exec nagare-superset superset import-dashboards \
    --path /tmp/dashboard_export.zip
```

## 6. トラブルシューティング

### 6.1. データベース接続エラー

**エラー**: "Could not connect to database"

**対処法**:
```bash
# PostgreSQLの状態確認
docker ps --filter "name=nagare-postgres"

# 接続テスト
docker exec nagare-superset ping -c 3 postgres

# ネットワーク確認
docker network inspect nagare-network
```

### 6.2. データが表示されない

**原因**: DAGがまだ実行されていない、またはリポジトリが登録されていない

**対処法**:
```bash
# リポジトリの登録確認
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py list

# DAGの実行確認
# Airflow UI: http://localhost:8080

# データの確認
docker exec nagare-postgres psql -U nagare_user -d nagare -c "SELECT COUNT(*) FROM pipeline_runs;"
```

### 6.3. クエリのパフォーマンスが遅い

**対処法**:
```sql
-- インデックスの確認
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('pipeline_runs', 'jobs', 'repositories');

-- 実行計画の確認
EXPLAIN ANALYZE
SELECT ... (遅いクエリ);
```

## 7. ベストプラクティス

### 7.1. SQLクエリの最適化

- **WHERE句で日付範囲を限定**: 常に`started_at >= CURRENT_DATE - INTERVAL '30 days'`のような条件を追加
- **JOINの最適化**: 必要なテーブルのみJOIN
- **集計の事前計算**: 頻繁に使うメトリクスはMaterialized Viewを検討

### 7.2. キャッシュの活用

1. **Dataset Cache**: データセット設定で"Cache timeout"を設定（例: 3600秒）
2. **Chart Cache**: チャート設定で"Cache timeout"を設定

### 7.3. パフォーマンス監視

- Supersetの**SQL Lab**で`EXPLAIN ANALYZE`を実行
- 長時間実行されるクエリを特定
- PostgreSQLのスロークエリログを確認

## 8. 次のステップ

### 8.1. カスタムメトリクスの追加

Four Keys メトリクスの実装:
- **Deployment Frequency**: mainブランチへのマージ頻度
- **Lead Time for Changes**: PRマージまでの時間
- **Change Failure Rate**: mainブランチでのビルド失敗率
- **Mean Time to Recovery (MTTR)**: 失敗から回復までの平均時間

### 8.2. アラート設定

Supersetのアラート機能を使用:
- 成功率が閾値を下回った場合
- 実行時間が通常の2倍を超えた場合

### 8.3. 詳細ダッシュボード

- **リポジトリ別詳細ダッシュボード**
- **ジョブ別詳細ダッシュボード**
- **エラー分析ダッシュボード**

## 関連ドキュメント

- [データモデル](../02_design/data_model.md)
- [データベースセットアップ](database_setup.md)
- [Streamlit管理画面](streamlit_admin.md)
- [Superset公式ドキュメント](https://superset.apache.org/docs/intro)
