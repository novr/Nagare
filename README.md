# Nagare

CI/CDプロセスを監視・評価するための診断・分析支援ツール

## 概要

Nagareは、開発チームが自らの開発フローの健全性をデータに基づき理解し、ボトルネックを発見し、具体的な改善アクションに繋げるための診断・分析支援ツールです。

Kent Beck氏の警告「指標が目標になると、それは良い指標ではなくなる」を核心的な思想とし、単一のスコアを追うのではなく、プロセスの全体像と傾向を把握することを目的としています。

## 主な機能

### Streamlit管理画面
- **リポジトリ管理**: 監視対象リポジトリの追加・有効化・無効化
- **GitHub連携**: GitHub APIからの直接検索とインポート
  - 組織リポジトリ、ユーザーリポジトリ、キーワード検索に対応
  - ページネーション機能（10/20/30/50件表示）
  - バッチインポート対応
- **ダッシュボード**: リポジトリ統計と最近のパイプライン実行履歴
- **実行履歴の閲覧**: パイプライン実行のフィルタリングと詳細表示

### データ収集パイプライン（Airflow）
- **自動データ収集**: GitHub Actions のワークフロー実行データとジョブデータを定期収集
- **堅牢なエラーハンドリング**:
  - GitHub API Rate Limit監視と自動待機
  - 指数バックオフによる自動リトライ（502/503/504エラー）
  - 部分的失敗時の継続処理とエラー統計記録
- **冪等性の保証**: UPSERT処理による重複データの防止

### データ可視化（Superset）
- CI/CDメトリクスのダッシュボード作成
- 成功率、実行時間、トレンド分析

## 技術スタック

- **Python 3.11**
- **Apache Airflow**: データ収集パイプライン
- **Apache Superset**: ダッシュボード・可視化
- **Streamlit**: 管理画面UI
- **PostgreSQL**: データベース

## 環境構築

### Docker環境での実行（推奨）

Docker Composeを使用して、Airflow、PostgreSQL、Supersetを含む完全な環境を簡単に構築できます。

#### 前提条件

- [Docker](https://docs.docker.com/get-docker/) がインストールされていること
- [Docker Compose](https://docs.docker.com/compose/install/) がインストールされていること

#### セットアップ手順

1. リポジトリをクローン

```bash
git clone <repository-url>
cd Nagare
```

2. 環境変数ファイルの作成

```bash
cp .env.sample .env
```

3. パスワードの生成（推奨）

```bash
./scripts/setup-secrets.sh
```

このスクリプトは強力なランダムパスワードを自動生成します：
- `DATABASE_PASSWORD` - PostgreSQLパスワード
- `AIRFLOW_SECRET_KEY` - Airflow Secret Key
- `SUPERSET_SECRET_KEY` - Superset Secret Key

または、手動で強力なパスワードを`.env`に設定することもできます。

4. GitHub認証の設定

```bash
vi .env  # または任意のエディタ
```

以下の必須項目を設定してください：

**GITHUB_TOKEN（必須）**:
1. GitHub Settings → Developer settings → Personal access tokens → Generate new token
2. 必要な権限: `repo`, `read:org`, `workflow`
3. トークンを`.env`の`GITHUB_TOKEN`に設定

**AIRFLOW_ADMIN_PASSWORD（必須）**:
- Airflow管理画面にログインするためのパスワード
- 推奨: 16文字以上の強力なパスワード

**⚠️ セキュリティ警告**:
- `.env`ファイルは`.gitignore`で除外されています
- `.env`ファイルを誤ってコミットしないよう注意してください

5. Docker環境の起動

```bash
# バックグラウンドで起動
docker compose up -d

# ログを確認
docker compose logs -f
```

6. サービスへのアクセス

- **Airflow UI**: http://localhost:8080
  - ユーザー名: `admin`
  - パスワード: `.env`の`AIRFLOW_ADMIN_PASSWORD`
- **Streamlit管理画面**: http://localhost:8501
  - リポジトリの管理、GitHub検索、パイプライン実行履歴の確認
- **Superset**: http://localhost:8088
  - ユーザー名: `admin`
  - パスワード: `admin`（初回ログイン後に変更推奨）
  - データ可視化とダッシュボード
- **PostgreSQL**: `localhost:5432`
  - データベース名: `nagare`
  - ユーザー名: `nagare_user`
  - パスワード: `.env`の`DATABASE_PASSWORD`

7. 監視対象リポジトリの設定

http://localhost:8501 にアクセスして、Streamlit管理画面からリポジトリを追加します：

- **GitHub検索**: 組織名、ユーザー名、キーワードから検索してインポート
- **手動追加**: リポジトリ名（`owner/repo`形式）を直接入力

詳細は [Streamlit管理画面ガイド](docs/03_setup/streamlit_admin.md) を参照してください。

#### Docker環境の管理

```bash
# 停止
docker compose stop

# 再起動
docker compose restart

# 完全削除（データも削除）
docker compose down -v

# ログ確認
docker compose logs -f [service-name]

# サービスのステータス確認
docker compose ps
```

### ローカル開発環境のセットアップ

uvを使用したローカル開発環境の構築方法です。

#### 前提条件

- [uv](https://github.com/astral-sh/uv) がインストールされていること
- Python 3.11

#### セットアップ手順

1. リポジトリをクローン

```bash
git clone <repository-url>
cd Nagare
```

2. 依存関係をインストール

```bash
# ローカル開発環境用（Airflow/Supersetを含む）
uv sync --extra local --extra dev

# または、本番環境用の最小限の依存関係のみ
uv sync --extra dev
```

3. 環境変数の設定

```bash
cp .env.sample .env
# .envファイルを編集して必要な環境変数を設定
```

### 開発ツール

#### コードフォーマット

```bash
# コードをフォーマット
uv run ruff format src/
```

#### リント

```bash
# リント実行
uv run ruff check src/

# リント（自動修正付き）
uv run ruff check --fix src/

# 型チェック
uv run pyright src/
```

#### テスト

```bash
# すべてのテストを実行
uv run pytest

# カバレッジ付きで実行
uv run pytest --cov=src --cov-report=html
```

## Supersetダッシュボードのセットアップ

Supersetにログイン後、以下の手順でダッシュボードを作成できます:

1. **データベース接続の追加**
   - Settings → Database Connections → + Database
   - PostgreSQLを選択
   - 接続情報:
     ```
     Display Name: Nagare PostgreSQL
     SQLAlchemy URI: postgresql://nagare_user:your_secure_password_here@postgres:5432/nagare
     ```
   - Test Connection → Connect

2. **データセットの追加**
   - データベースに作成済みのビューを追加:
     - `v_pipeline_overview` - リポジトリ統計
     - `v_daily_success_rate` - 日次成功率
     - `v_pipeline_stats` - パイプライン統計
     - `v_recent_pipeline_runs` - 最新実行履歴
     - `v_job_stats` - ジョブ統計
     - `v_pipeline_runs_by_hour` - 時間帯別パターン

3. **チャートとダッシュボードの作成**
   - 詳細は [Supersetダッシュボード設定](docs/03_setup/superset_dashboard.md) を参照

## トラブルシューティング

### Supersetがデータベースに接続できない

**症状**: "Could not load database driver: PostgresEngineSpec" エラー

**解決策**: Supersetコンテナを再ビルド
```bash
docker-compose build superset
docker-compose up -d superset
```

### Airflowの DAG が表示されない

**原因**: DAG ファイルの構文エラーまたは依存関係の問題

**解決策**:
```bash
# ログを確認
docker compose logs airflow-scheduler

# DAGの構文チェック
docker exec nagare-airflow-scheduler airflow dags list
```

### データが収集されない

**確認ポイント**:
1. リポジトリが正しく登録されているか（Streamlit管理画面またはデータベースで確認）
2. GitHubトークンが正しく設定されているか（`.env`ファイル）
3. Airflow DAGが有効化されているか（Airflow UIで確認）
4. DAGの実行履歴にエラーがないか（Airflow UI → DAG → Log）

```bash
# リポジトリ一覧を確認
docker exec nagare-postgres psql -U nagare_user -d nagare -c "SELECT * FROM repositories;"

# DAG を手動実行
docker exec nagare-airflow-scheduler airflow dags trigger collect_github_actions_data
```

### データベースのパスワードエラー

**症状**: "password authentication failed for user"

**解決策**:
1. `.env`ファイルの`DATABASE_PASSWORD`と`secrets/db_password.txt`が一致しているか確認
2. コンテナを再起動
```bash
docker-compose down
docker-compose up -d
```

## ドキュメント

詳細なドキュメントは `docs/` ディレクトリを参照してください。

**プロダクト仕様**
- [プロダクト概要](docs/00_overview.md)
- [機能要件](docs/01_requirements/functional.md)
- [非機能要件](docs/01_requirements/nonfunctional.md)

**設計ドキュメント**
- [アーキテクチャ設計](docs/02_design/architecture.md)
- [データモデル](docs/02_design/data_model.md)
- [DAG設計](docs/02_design/dag_design.md)
- [実装ガイド](docs/02_design/implementation_guide.md)

**セットアップガイド**
- [データベースセットアップ](docs/03_setup/database_setup.md)
- [Streamlit管理画面](docs/03_setup/streamlit_admin.md)
- [Supersetダッシュボード設定](docs/03_setup/superset_dashboard.md)

**運用ガイド**
- [エラーハンドリング](docs/04_operation/error_handling.md)

**その他**
- [用語集](docs/99_glossary.md)

## ライセンス

（ライセンス情報を追加してください）
