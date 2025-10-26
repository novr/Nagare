# Nagare Superset ダッシュボード セットアップガイド

## 1. データベース接続の設定

1. Supersetにアクセス: http://localhost:8088
2. ログイン情報:
   - Username: `admin`
   - Password: `admin`

3. データベース接続を追加:
   - Settings → Database Connections → + Database
   - Database name: `Nagare PostgreSQL`
   - SQLAlchemy URI: `postgresql://nagare_user:your_secure_password_here@postgres:5432/nagare`
   - Test Connection → Connect

## 2. 利用可能なビュー

PostgreSQLに以下のビューが作成されています：

### v_pipeline_overview
リポジトリごとの全体的な統計（成功率、総実行数など）

### v_daily_success_rate
日次のパイプライン成功率

### v_pipeline_stats
パイプラインのステータス別統計（平均実行時間など）

### v_recent_pipeline_runs
最新100件のパイプライン実行履歴

### v_job_stats
ジョブごとの統計情報

### v_pipeline_runs_by_hour
時間帯別のパイプライン実行数

## 3. 推奨チャート

### チャート1: パイプライン成功率の推移
- **データソース**: v_daily_success_rate
- **Chart Type**: Line Chart
- **X軸**: run_date
- **Y軸**: success_rate
- **Group by**: repository_name

### チャート2: リポジトリ別成功率
- **データソース**: v_pipeline_overview
- **Chart Type**: Bar Chart
- **X軸**: repository_name
- **Y軸**: overall_success_rate

### チャート3: 最新のパイプライン実行状況
- **データソース**: v_recent_pipeline_runs
- **Chart Type**: Table
- **Columns**: repository_name, pipeline_name, status, branch_name, started_at, duration_sec

### チャート4: 平均実行時間の推移
- **データソース**: v_pipeline_stats
- **Chart Type**: Line Chart
- **X軸**: run_date
- **Y軸**: avg_duration_sec
- **Group by**: repository_name
- **Filter**: status = 'SUCCESS'

### チャート5: ステータス別実行数
- **データソース**: v_pipeline_stats
- **Chart Type**: Pie Chart
- **Dimension**: status
- **Metric**: SUM(run_count)

### チャート6: 時間帯別実行パターン
- **データソース**: v_pipeline_runs_by_hour
- **Chart Type**: Bar Chart
- **X軸**: hour_of_day
- **Y軸**: run_count
- **Group by**: repository_name

## 4. ダッシュボード作成

1. Dashboards → + Dashboard
2. Dashboard name: `Nagare CI/CD Overview`
3. 上記のチャートをダッシュボードに追加
4. レイアウトを調整して保存
