# Nagare

CI/CDプロセスを監視・評価するための診断・分析支援ツール

## 概要

Nagareは、開発チームが自らの開発フローの健全性をデータに基づき理解し、ボトルネックを発見し、具体的な改善アクションに繋げるための診断・分析支援ツールです。

Kent Beck氏の警告「指標が目標になると、それは良い指標ではなくなる」を核心的な思想とし、単一のスコアを追うのではなく、プロセスの全体像と傾向を把握することを目的としています。

## 技術スタック

- **Python 3.11**
- **Apache Airflow**: データ収集パイプライン
- **Apache Superset**: ダッシュボード・可視化
- **PostgreSQL**: データベース

## 開発環境のセットアップ

### 前提条件

- [uv](https://github.com/astral-sh/uv) がインストールされていること

### セットアップ手順

1. リポジトリをクローン

```bash
git clone <repository-url>
cd Nagare
```

2. 依存関係をインストール

```bash
uv sync --all-extras
```

3. 環境変数の設定

```bash
cp .env.example .env
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

## プロジェクト構成

```
Nagare/
├── src/nagare/          # アプリケーションコード
├── tests/               # テストコード
├── docs/                # ドキュメント
│   ├── 00_overview.md
│   ├── 01_requirements/
│   ├── 02_design/
│   ├── 05_frontend/
│   └── 99_glossary.md
├── pyproject.toml       # プロジェクト設定（ruff、pyright等の設定も含む）
└── AGENT.md             # リポジトリガイドライン
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

**その他**
- [用語集](docs/99_glossary.md)
- [リポジトリガイドライン](AGENT.md)

## ライセンス

（ライセンス情報を追加してください）
