# データベースセットアップガイド

本番PostgreSQLデータベースを使用してリポジトリを管理する手順。

## 前提条件

- Docker環境が起動していること (`docker-compose up -d`)
- PostgreSQLコンテナ (nagare-postgres) が healthy 状態であること

## 1. データベーススキーマの初期化

PostgreSQLコンテナ内でスキーマ初期化スクリプトを実行します。

```bash
# コンテナ内でSQLを実行
docker exec -i nagare-postgres psql -U nagare_user -d nagare < scripts/init_db.sql
```

正常に完了すると、以下のテーブルが作成されます：
- `projects` - プロジェクト管理
- `repositories` - リポジトリ管理
- `pipeline_runs` - パイプライン実行履歴
- `jobs` - ジョブ実行履歴

## 2. リポジトリの登録

### 方法A: CLIツールを使用（推奨）

```bash
# Dockerコンテナ内で実行
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py add owner/repo
```

#### CLIツールの使い方

```bash
# 一覧表示
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py list

# 追加
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py add novr/CIPette

# 無効化
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py disable novr/CIPette

# 有効化
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py enable novr/CIPette
```

### 方法B: SQLで直接挿入

```bash
docker exec -it nagare-postgres psql -U nagare_user -d nagare
```

SQLコンソール内で：

```sql
-- リポジトリを追加
INSERT INTO repositories (source_repository_id, source, repository_name, active)
VALUES ('owner_repo', 'github_actions', 'owner/repo', TRUE);

-- 確認
SELECT id, repository_name, source, active FROM repositories;
```

## 3. モックモードから本番モードへ切り替え

`.env`ファイルを編集してモックモードを無効化します：

```bash
# .envファイルを編集
vi .env
```

以下の行を変更：

```bash
# 変更前
USE_DB_MOCK=true

# 変更後
USE_DB_MOCK=false
```

## 4. Airflowサービスの再起動

環境変数の変更を反映させるため、Airflowサービスを再起動します：

```bash
docker-compose restart airflow-webserver airflow-scheduler
```

## 5. 動作確認

### リポジトリ取得の確認

Airflow UIにアクセスして、DAGが正常に動作するか確認します：

1. http://localhost:8080 にアクセス
2. `collect_github_actions_data` DAGを有効化
3. 手動実行（Trigger DAG）
4. ログを確認して、PostgreSQLからリポジトリが取得されていることを確認

### データベースの確認

```bash
# リポジトリ一覧
docker exec -it nagare-postgres psql -U nagare_user -d nagare -c "SELECT * FROM repositories;"

# パイプライン実行履歴（データ収集後）
docker exec -it nagare-postgres psql -U nagare_user -d nagare -c "SELECT id, pipeline_name, status, started_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 10;"

# ジョブ実行履歴
docker exec -it nagare-postgres psql -U nagare_user -d nagare -c "SELECT id, job_name, status, duration_ms FROM jobs ORDER BY created_at DESC LIMIT 10;"
```

## トラブルシューティング

### リポジトリが取得されない

1. `.env`で`USE_DB_MOCK=false`になっているか確認
2. Airflowサービスを再起動したか確認
3. リポジトリが `active=TRUE` で登録されているか確認

```sql
SELECT id, repository_name, active FROM repositories;
```

### データベース接続エラー

`.env`のデータベースパスワードを確認：

```bash
DATABASE_PASSWORD=your_secure_password_here
```

**設定の管理方針**:
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER` は`docker-compose.yml`で管理
- `.env`には機密情報（`DATABASE_PASSWORD`）のみ記載
- カスタマイズする場合は`docker-compose.yml`を編集

### スキーマが古い

スキーマを再初期化する場合：

```bash
# データを削除して再初期化（注意：既存データが削除されます）
docker exec -i nagare-postgres psql -U nagare_user -d nagare < scripts/init_db.sql
```

## 参考情報

- データモデル定義: [docs/02_design/data_model.md](../02_design/data_model.md)
- DatabaseClientの実装: `src/nagare/utils/database.py`
- リポジトリ管理CLI: `scripts/manage_repositories.py`
