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

2. 環境変数の設定

```bash
cp .env.sample .env
# .envファイルを編集して必要な環境変数を設定
# Docker環境用の設定値を使用（DATABASE_HOST=postgres等）
```

3. Secretsファイルの生成

```bash
./scripts/setup-secrets.sh
```

このスクリプトは以下のファイルを生成します：
- `secrets/db_password.txt` - データベースパスワード
- `secrets/airflow_secret_key.txt` - Airflow Secret Key
- `secrets/superset_secret_key.txt` - Superset Secret Key

4. Docker環境の起動

```bash
# バックグラウンドで起動
docker compose up -d

# ログを確認
docker compose logs -f
```

5. サービスへのアクセス

- **Airflow UI**: http://localhost:8080
  - ユーザー名: `admin`
  - パスワード: `.env`の`AIRFLOW_ADMIN_PASSWORD`
- **Streamlit管理画面**: http://localhost:8501
  - リポジトリの管理、GitHub検索、パイプライン実行履歴の確認
- **Superset**: http://localhost:8088
  - データ可視化とダッシュボード
- **PostgreSQL**: `localhost:5432`

6. 監視対象リポジトリの設定

**方法1: Streamlit管理画面から設定（推奨）**

http://localhost:8501 にアクセスして、以下の方法でリポジトリを追加できます：

- **GitHub検索**: 組織名、ユーザー名、キーワードから検索してインポート
- **手動追加**: リポジトリ名（`owner/repo`形式）を直接入力

詳細は [Streamlit管理画面ガイド](docs/03_setup/streamlit_admin.md) を参照してください。

**方法2: CLIから設定**

```bash
# リポジトリを追加
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py add owner/repo

# リポジトリ一覧を表示
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py list
```

詳細は [データベースセットアップガイド](docs/03_setup/database_setup.md) を参照してください。

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

**運用ガイド**
- [エラーハンドリング](docs/04_operation/error_handling.md)

**その他**
- [用語集](docs/99_glossary.md)
- [リポジトリガイドライン](AGENT.md)

## ライセンス

（ライセンス情報を追加してください）
