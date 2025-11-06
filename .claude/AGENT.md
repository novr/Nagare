# Nagare AI開発ガイドライン

このドキュメントは、NagareプロジェクトでAI支援開発を行う際のプロジェクト固有のガイドラインです。

## 📋 プロジェクト概要

**Nagare**は、CI/CDプロセスを監視・評価するための診断・分析支援ツールです。

### 技術スタック
- **Python 3.11**
- **Apache Airflow**: データ収集パイプライン
- **Apache Superset**: ダッシュボード・可視化
- **Streamlit**: 管理画面UI
- **PostgreSQL**: データベース
- **Docker Compose**: 開発環境

### アーキテクチャ原則
- **Pure DI + Factory Pattern** ([ADR-001](../../docs/02_design/adr/001-dependency-injection-strategy.md))
- **Connection Abstraction Layer** ([ADR-002](../../docs/02_design/adr/002-connection-management-architecture.md))

---

## 🐳 開発環境

### Docker中心の開発フロー

Nagareはすべての開発作業をDockerコンテナ内で実行します。

```bash
# 環境の起動
docker compose up -d

# コードフォーマット
docker compose exec airflow-scheduler uv run ruff format src/

# リント
docker compose exec airflow-scheduler uv run ruff check --fix src/

# テスト
docker compose exec airflow-scheduler uv run pytest

# Pythonシェル（デバッグ）
docker compose exec airflow-scheduler uv run python
```

### 重要な注意点

1. **ローカル環境でのuv実行は禁止**
   - すべての開発コマンドはDockerコンテナ内で実行
   - 依存関係の不一致を防ぐため

2. **環境変数はDocker Composeで管理**
   - DATABASE_HOST, DATABASE_PORT等は`.env`ではなく`docker-compose.yml`で設定済み
   - `.env`で設定が必要なのは:
     - `GITHUB_TOKEN`
     - `BITRISE_TOKEN`
     - `APPSTORE_KEY_ID`, `APPSTORE_ISSUER_ID`, `APPSTORE_PRIVATE_KEY`
     - `AIRFLOW_ADMIN_PASSWORD`
     - `DATABASE_PASSWORD`（`setup-secrets.sh`で生成）

3. **環境変数の更新方法（重要）**
   ```bash
   # ❌ Bad: restart では環境変数が更新されない
   docker compose restart streamlit-admin

   # ✅ Good: コンテナを再作成する必要がある
   docker compose down streamlit-admin
   docker compose up -d streamlit-admin

   # または、複数のサービスを一度に
   docker compose down airflow-webserver airflow-scheduler
   docker compose up -d airflow-webserver airflow-scheduler
   ```

   **理由**: `docker compose restart`はコンテナを再起動するだけで、
   環境変数は再読み込みされません。`.env`ファイルを更新した場合は、
   必ず`down`してから`up`する必要があります。

4. **データベース操作**
   ```bash
   # PostgreSQLに直接接続
   docker compose exec postgres psql -U nagare_user -d nagare
   ```

---

## 🏗️ アーキテクチャパターン

### 1. Pure Dependency Injection (ADR-001)

**必須ルール**: すべての依存関係は必須引数として注入

```python
# ✅ Good: Pure DI
class GitHubClient:
    def __init__(self, connection: GitHubConnection) -> None:
        self.connection = connection

# ❌ Bad: Optional injection
class GitHubClient:
    def __init__(self, connection: GitHubConnection | None = None) -> None:
        self.connection = connection or GitHubConnection.from_env()
```

**例外**: Factoryクラスのみが環境依存の処理を許可

```python
# ✅ Factory内でのみ環境変数参照を許可
class ClientFactory:
    @staticmethod
    def create_github_client(
        connection: GitHubConnection | None = None,
    ) -> GitHubClientProtocol:
        if connection is None:
            connection = ConnectionRegistry.get_github()
        return GitHubClient(connection=connection)
```

### 2. Connection Abstraction Layer (ADR-002)

**必須**: すべての外部接続はConnectionオブジェクトで抽象化

```python
# ✅ Good: Connection経由
from nagare.utils.connections import GitHubConnection, ConnectionRegistry

connection = ConnectionRegistry.get_github()
client = GitHubClient(connection=connection)

# ❌ Bad: 直接環境変数参照
import os
token = os.getenv("GITHUB_TOKEN")
client = GitHubClient(token=token)
```

**プラットフォーム追加時の3ステップ**:
1. `connections.py`に新しいConnectionクラスを追加
2. `ConnectionRegistry`に取得メソッドを追加
3. Clientクラスを実装

---

## 💻 コーディング規約

### 型ヒント

**必須**: すべての関数シグネチャに型ヒントを記述

```python
# ✅ Good
def fetch_workflow_runs(
    self, owner: str, repo: str, per_page: int = 100
) -> list[dict[str, Any]]:
    pass

# ❌ Bad
def fetch_workflow_runs(self, owner, repo, per_page=100):
    pass
```

### エラーハンドリング

**パターン**: GitHub APIの失敗ケースを必ず考慮

```python
# ✅ Good: Rate limit/Server error対応
try:
    response = self._make_request(url)
except GitHubRateLimitError:
    # Rate limit到達時の処理
    logger.warning(f"Rate limit reached. Waiting until {reset_time}")
    time.sleep(wait_time)
    response = self._make_request(url)  # リトライ
except GitHubServerError as e:
    # 5xx系エラーは指数バックオフでリトライ
    if e.status_code in (502, 503, 504):
        # exponential backoff
        pass
```

### 命名規則

- **関数**: `snake_case`, 動詞で始める (`fetch_`, `create_`, `validate_`)
- **クラス**: `PascalCase`
- **定数**: `UPPER_SNAKE_CASE`
- **プライベート**: `_leading_underscore`

---

## 🧪 テスト戦略

### 必須テストケース

1. **正常系**: 期待される動作
2. **異常系**: エラーケース
   - GitHub API Rate Limit
   - ネットワークエラー
   - 無効な認証情報
   - データベース接続失敗
3. **境界値**: 空リスト、None、空文字列

### テスト実行

```bash
# すべてのテスト
docker compose exec airflow-scheduler uv run pytest

# カバレッジ付き
docker compose exec airflow-scheduler uv run pytest --cov=src --cov-report=html

# 特定のテスト
docker compose exec airflow-scheduler uv run pytest tests/utils/test_github_client.py::test_fetch_workflow_runs
```

### モックの使用

**原則**: 外部APIは必ずモック化

```python
# ✅ Good: GitHub APIをモック
@pytest.fixture
def mock_github_response():
    return {
        "total_count": 1,
        "workflow_runs": [{"id": 123, "status": "completed"}]
    }

def test_fetch_workflow_runs(mock_github_response, monkeypatch):
    def mock_request(*args, **kwargs):
        return mock_github_response

    monkeypatch.setattr(GitHubClient, "_make_request", mock_request)
    # テスト実行
```

---

## 📚 ドキュメント

### ADR (Architecture Decision Records)

重要な設計決定は必ずADRに記録:

```bash
# ADR一覧
ls docs/02_design/adr/

# 新しいADR作成
touch docs/02_design/adr/003-new-decision.md
```

**ADRテンプレート**:
```markdown
# ADR-XXX: タイトル

## ステータス
Accepted / Rejected / Deprecated / Superseded

## コンテキスト
（問題の背景、制約条件）

## 決定内容
（選択した解決策）

## 結果（Consequences）
（ポジティブ/ネガティブな影響）

## 見直し条件
（再評価のトリガー）
```

### README.md更新

機能追加時に以下を更新:
- 主な機能
- セットアップ手順（必要に応じて）
- トラブルシューティング

---

## 🔐 セキュリティ

### 環境変数管理

**絶対禁止**: トークン・パスワードのハードコード

```python
# ❌ Bad: ハードコード
GITHUB_TOKEN = "ghp_xxxxxxxxxxxx"

# ✅ Good: Connection経由
connection = GitHubConnection.from_env()
```

### .envファイル

- `.env`は`.gitignore`に含まれている（コミット禁止）
- `setup-secrets.sh`でパスワード自動生成を推奨
- 本番環境ではSecrets Manager使用を検討

---

## 🚫 アンチパターン

### 1. Factory以外での環境変数直接参照

```python
# ❌ Bad
class GitHubClient:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")

# ✅ Good
class GitHubClient:
    def __init__(self, connection: GitHubConnection):
        self.connection = connection
```

### 2. Optional Dependency Injection

```python
# ❌ Bad
def __init__(self, client: GitHubClient | None = None):
    self.client = client or create_default_client()

# ✅ Good
def __init__(self, client: GitHubClient):
    self.client = client
```

### 3. 環境変数の散在

```python
# ❌ Bad: コード中で直接参照
database_host = os.getenv("DATABASE_HOST")
database_port = os.getenv("DATABASE_PORT")

# ✅ Good: Connectionオブジェクトで集約
connection = DatabaseConnection.from_env()
url = connection.url
```

---

## 🔄 ワークフロー

### 機能追加の標準フロー

1. **調査**: 既存コードを確認、関連ADRを読む
2. **設計**: 必要に応じてADR作成
3. **実装**: Pure DI + Factory パターンに従う
4. **テスト**: 正常系・異常系・境界値をカバー
5. **リント**: `ruff check --fix src/`
6. **フォーマット**: `ruff format src/`
7. **型チェック**: `pyright src/`
8. **ドキュメント**: README.md更新

### Git運用

```bash
# Conventional Commits形式
git commit -m "feat: Add GitLab connection support"
git commit -m "fix: Handle GitHub API rate limit correctly"
git commit -m "docs: Update README for Docker-based development"
git commit -m "refactor: Extract connection validation logic"
git commit -m "test: Add tests for CircleCI connection"
```

---

## 📖 参考資料

### プロジェクトドキュメント
- [README.md](../../README.md) - セットアップ手順
- [ADR-001](../../docs/02_design/adr/001-dependency-injection-strategy.md) - DI戦略
- [ADR-002](../../docs/02_design/adr/002-connection-management-architecture.md) - Connection管理
- [アーキテクチャ設計](../../docs/02_design/architecture.md)
- [データモデル](../../docs/02_design/data_model.md)

### 外部リソース
- [Airflow Documentation](https://airflow.apache.org/docs/)
- [Superset Documentation](https://superset.apache.org/docs/)
- [GitHub REST API](https://docs.github.com/en/rest)
- [Docker Compose](https://docs.docker.com/compose/)

---

## 🆘 よくある問題と解決策

### テストが失敗する

```bash
# 1. Docker環境を再起動
docker compose restart airflow-scheduler

# 2. キャッシュをクリア
docker compose exec airflow-scheduler uv run pytest --cache-clear

# 3. 特定のテストを詳細モードで実行
docker compose exec airflow-scheduler uv run pytest -vv tests/utils/test_github_client.py
```

### リントエラー

```bash
# 自動修正を試す
docker compose exec airflow-scheduler uv run ruff check --fix src/

# それでも残る場合は手動修正が必要
docker compose exec airflow-scheduler uv run ruff check src/
```

### 型エラー

```bash
# 型チェック実行
docker compose exec airflow-scheduler uv run pyright src/

# 型ヒントを追加または修正
```

### 環境変数が反映されない

**症状**: `.env`ファイルを更新したが、コンテナ内で古い値が使われている

**原因**: `docker compose restart`では環境変数が再読み込みされない

**解決方法**:
```bash
# 1. 影響を受けるサービスを特定
docker compose ps

# 2. サービスを再作成（例: streamlit-admin）
docker compose down streamlit-admin
docker compose up -d streamlit-admin

# 3. 複数サービスの場合
docker compose down airflow-webserver airflow-scheduler
docker compose up -d airflow-webserver airflow-scheduler

# 4. 環境変数が正しく読み込まれたか確認
docker exec <container-name> env | grep VARIABLE_NAME
```

---

**最終更新**: 2025年11月5日
**メンテナー**: プロジェクトオーナー
