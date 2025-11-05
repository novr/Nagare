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

NagareはDocker Composeを使用した開発環境を提供しています。Airflow、PostgreSQL、Superset、Streamlitを含む完全な環境を簡単に構築できます。

### 前提条件

- [Docker](https://docs.docker.com/get-docker/) がインストールされていること
- [Docker Compose](https://docs.docker.com/compose/install/) がインストールされていること

### セットアップ手順

1. リポジトリをクローン

```bash
git clone <repository-url>
cd Nagare
```

2. 環境変数ファイルの作成

```bash
cp .env.sample .env
```

3. Connection設定ファイルの作成

```bash
cp connections.yml.sample connections.yml
```

このファイルでCI/CDプラットフォーム（GitHub/Bitrise/Xcode Cloud）の接続設定を管理します。
使用するプラットフォームのセクションのコメントを外してください。

4. パスワードの生成（推奨）

```bash
./scripts/setup-secrets.sh
```

このスクリプトは強力なランダムパスワードを自動生成します：
- `DATABASE_PASSWORD` - PostgreSQLパスワード
- `AIRFLOW_SECRET_KEY` - Airflow Secret Key
- `SUPERSET_SECRET_KEY` - Superset Secret Key

または、手動で強力なパスワードを`.env`に設定することもできます。

5. GitHub認証の設定

**GitHub認証設定（必須）**:

Nagareは2つの認証方式をサポートしています。**Personal Access Token（推奨）**を使用するか、GitHub Apps認証を選択できます。

**方法A: Personal Access Token（推奨）** - 個人利用・小規模チーム向け
1. [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)
2. "Generate new token (classic)" をクリック
3. 必要な権限を選択:
   - ✅ `repo` - プライベートリポジトリへのアクセス
   - ✅ `read:org` - 組織情報の読み取り
   - ✅ `workflow` - GitHub Actionsワークフローへのアクセス
4. トークンを生成し、**コピー**（後で確認できないため注意）
5. `.env`ファイルにトークンを設定:
   ```bash
   GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
   ```
6. `connections.yml`のGitHubセクションのコメントを外す（既にデフォルトで有効）

**方法B: GitHub Apps認証** - エンタープライズ・大規模チーム向け
1. [GitHub Settings → Developer settings → GitHub Apps](https://github.com/settings/apps) で新規App作成
2. Repository permissions設定:
   - Actions: Read
   - Metadata: Read
   - Workflows: Read
3. Private keyを生成してダウンロード
4. `.env`ファイルにApp情報を設定:
   ```bash
   GITHUB_APP_ID=123456
   GITHUB_APP_INSTALLATION_ID=789012
   GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
   ```
5. `connections.yml`のGitHub Appsセクションのコメントを外す

**どちらを選ぶべき？**
- 👤 **個人利用・小規模チーム**: Personal Access Token（シンプル、5分で設定完了）
- 🏢 **エンタープライズ・大規模チーム**: GitHub Apps（セキュアな権限管理、監査ログ）

**AIRFLOW_ADMIN_PASSWORD（必須）**:
- Airflow管理画面にログインするためのパスワード
- 推奨: 16文字以上の強力なパスワード（`./scripts/setup-secrets.sh`で自動生成可能）

**⚠️ セキュリティ警告**:
- `connections.yml`は個人設定ファイルです（`.gitignore`で除外済み）
- 実際の機密情報は`.env`ファイルに保存し、`connections.yml`では環境変数参照（`${VAR_NAME}`）を使用
- GitHubトークンや秘密鍵を**絶対に**`connections.yml`に直接記載しないでください
- `connections.yml.sample`はテンプレートとしてgit管理されています

詳細は [ADR-002: Connection管理アーキテクチャ](docs/02_design/adr/002-connection-management-architecture.md) を参照。

6. Docker環境の起動

```bash
# バックグラウンドで起動
docker compose up -d

# ログを確認
docker compose logs -f
```

**⏱️ 初回起動の待ち時間について**:
- **初回起動時は5-10分程度かかります**（Airflow/Supersetの初期化）
- 起動状況の確認:
  ```bash
  docker compose ps  # ステータス確認
  docker compose logs -f airflow-init  # 初期化ログ
  ```
- すべてのサービスが`healthy`になるまで待機してください
- 2回目以降の起動は約30秒で完了します

7. サービスへのアクセス

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

8. 監視対象リポジトリの設定

http://localhost:8501 にアクセスして、Streamlit管理画面からリポジトリを追加します：

- **GitHub検索**: 組織名、ユーザー名、キーワードから検索してインポート
- **手動追加**: リポジトリ名（`owner/repo`形式）を直接入力

詳細は [Streamlit管理画面ガイド](docs/03_setup/streamlit_admin.md) を参照してください。

### Docker環境の管理

#### 基本操作

```bash
# 停止
docker-compose stop

# 再起動
docker-compose restart

# 完全削除（データも削除）
docker-compose down -v

# ログ確認
docker-compose logs -f [service-name]

# サービスのステータス確認
docker-compose ps
```

#### ビルド環境の選択

Dockerイメージは環境に応じて2種類のビルドが可能です：

**開発環境（デフォルト）**:
```bash
# docker-compose.yml のデフォルト設定（BUILD_ENV=development）
# テスト実行に必要な開発依存関係（pytest, ruff, pyright）を含む
docker-compose build
docker-compose up -d
```

**本番環境**:
```bash
# 開発依存関係を除外した軽量イメージ（約50-100MB削減）
docker build --build-arg BUILD_ENV=production -t nagare:latest .

# または docker-compose.yml を編集して BUILD_ENV: production に変更
```

詳細は [ADR-004: Docker環境での開発依存関係管理戦略](docs/02_design/adr/004-docker-dev-dependencies-strategy.md) を参照。

## 開発ツール

Nagareの開発では、すべての開発ツール（リント、フォーマット、テスト）をDockerコンテナ内で実行します。

### コードフォーマット

```bash
# コードをフォーマット
docker-compose exec airflow-scheduler ruff format src/
```

### リント

```bash
# リント実行
docker-compose exec airflow-scheduler ruff check src/

# リント（自動修正付き）
docker-compose exec airflow-scheduler ruff check --fix src/

# 型チェック
docker-compose exec airflow-scheduler pyright src/
```

### テスト

```bash
# すべてのテストを実行
docker-compose exec airflow-scheduler pytest

# カバレッジ付きで実行
docker-compose exec airflow-scheduler pytest --cov=src --cov-report=html

# 特定のテストを実行
docker-compose exec airflow-scheduler pytest tests/utils/test_connections.py::TestBitriseConnection -v
```

### Pythonシェル（デバッグ用）

```bash
# Airflowコンテナ内でPythonシェルを起動
docker-compose exec airflow-scheduler python

# IPythonがインストールされている場合（別途インストール必要）
docker-compose exec airflow-scheduler ipython
```

### データベース操作

```bash
# PostgreSQLに接続
docker-compose exec postgres psql -U nagare_user -d nagare

# SQLファイルを実行
docker-compose exec -T postgres psql -U nagare_user -d nagare < sql/schema.sql
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
docker-compose logs airflow-scheduler

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
