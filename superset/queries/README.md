# Superset SQL Queries

Supersetで使用するVirtual Dataset用のSQLクエリ集。

## クエリ一覧

| ファイル名 | Dataset名 | 説明 | 推奨チャート |
|-----------|----------|------|------------|
| `pipeline_daily_success_rate.sql` | pipeline_daily_success_rate | パイプライン実行の日次成功率 | Line Chart |
| `pipeline_daily_duration.sql` | pipeline_daily_duration | パイプライン実行時間の日次統計 | Line Chart |
| `job_duration_ranking.sql` | job_duration_ranking | ジョブ別実行時間ランキング | Bar Chart (横) |
| `repository_performance_summary.sql` | repository_performance_summary | リポジトリ別パフォーマンスサマリー | Table, Pie Chart |
| `failing_jobs_ranking.sql` | failing_jobs_ranking | 失敗が多いジョブのランキング | Table |

## 使用方法

### 1. Superset SQL Labでクエリを実行

```bash
# Supersetにアクセス
open http://localhost:8088

# SQL Lab → SQL Editorを開く
# DATABASEで "Nagare PostgreSQL" を選択
# SCHEMAで "public" を選択
```

### 2. クエリをコピー&ペースト

各`.sql`ファイルの内容をコピーして、SQL Editorに貼り付けます。

### 3. クエリを実行して確認

**RUN**ボタンをクリックして、結果を確認します。

### 4. Virtual Datasetとして保存

1. クエリエディタ右上の**SAVE** → **Save dataset**
2. Dataset名を入力（ファイル名の`Dataset名`を使用）
3. **SAVE & EXPLORE**をクリック

### 5. チャートを作成

データセットからチャートを作成し、ダッシュボードに追加します。

詳細は [Supersetダッシュボード設定ガイド](../../docs/03_setup/superset_dashboard.md)を参照してください。

## クエリのカスタマイズ

### 日数の変更

デフォルトでは過去30日間のデータを取得しますが、必要に応じて変更できます：

```sql
-- 過去7日間
WHERE pr.started_at >= CURRENT_DATE - INTERVAL '7 days'

-- 過去90日間
WHERE pr.started_at >= CURRENT_DATE - INTERVAL '90 days'
```

### 閾値の調整

ジョブのフィルタリング条件を調整：

```sql
-- 実行回数が10回以上
HAVING COUNT(*) >= 10

-- 失敗回数が5回以上
HAVING COUNT(*) >= 5
```

### 結果件数の変更

```sql
-- Top 100を表示
LIMIT 100
```

## トラブルシューティング

### クエリが遅い

```sql
-- EXPLAIN ANALYZEで実行計画を確認
EXPLAIN ANALYZE
SELECT ... (遅いクエリ);
```

### データが返らない

```bash
# データが存在するか確認
docker exec nagare-postgres psql -U nagare_user -d nagare -c "SELECT COUNT(*) FROM pipeline_runs;"
docker exec nagare-postgres psql -U nagare_user -d nagare -c "SELECT COUNT(*) FROM jobs;"
```

データがない場合：
1. Streamlit管理画面でリポジトリを登録
2. Airflow UIでDAGを手動実行
3. 数分待ってから再度確認

## 参考リンク

- [Supersetダッシュボード設定ガイド](../../docs/03_setup/superset_dashboard.md)
- [データモデル](../../docs/02_design/data_model.md)
- [PostgreSQL公式ドキュメント](https://www.postgresql.org/docs/)
