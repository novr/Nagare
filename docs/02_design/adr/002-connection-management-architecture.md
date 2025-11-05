# ADR-002: Connection管理アーキテクチャ

## ステータス

**Accepted** - 2025年10月26日

## コンテキスト

Nagareプロジェクトでは、現在GitHub APIのみを使用しているが、将来的にGitLab、CircleCI、Jenkinsなど複数のCI/CDプラットフォームへの対応が想定される。現状の問題点と拡張性を考慮した設計が必要である。

### 現状の問題点

1. **認証情報管理が散在**
   ```python
   # 4箇所で個別に環境変数を読み込み
   GitHubClient.__init__()      # github_client.py:149
   DatabaseClient.__init__()    # database.py:31-35
   get_database_engine()        # admin_app.py:32-36
   docker-compose.yml           # 全サービスに環境変数を個別配布
   ```

2. **コードの重複（DRY違反）**
   - データベース接続URL構築が3箇所に重複
   - 環境変数読み込みロジックの重複
   - 接続情報の検証ロジックが未統一

3. **拡張性の欠如**
   - 新しいプラットフォーム追加時に各クライアントを個別修正
   - 接続情報の型安全性がない（環境変数は文字列）
   - 設定の一元管理ができない

4. **テスト・モックが困難**
   - 各クライアントが環境変数に直接依存
   - 接続情報のモック注入が煩雑

### プロジェクト要件

- **ADR-001準拠**: Pure DI + Factoryパターンを維持
- **拡張性**: 新規プラットフォーム追加が容易
- **保守性**: 接続情報管理の一元化
- **後方互換性**: 既存コードへの影響を最小化
- **テスト容易性**: モック注入が簡単

### 検討した選択肢

#### 選択肢A: 現状維持
**メリット**:
- 変更不要

**デメリット**:
- ❌ 拡張性なし
- ❌ コード重複
- ❌ 保守コスト高

---

#### 選択肢B: Airflow Connection統合
```python
from airflow.hooks.base import BaseHook

def get_github_connection():
    conn = BaseHook.get_connection("github_default")
    return conn.password  # token
```

**メリット**:
- ✅ Airflow標準の暗号化
- ✅ UIから管理可能

**デメリット**:
- ❌ Streamlit/SupersetもAirflow依存
- ❌ ローカル開発環境で複雑化
- ❌ Airflowのセットアップが必須

---

#### 選択肢C: Connection抽象化層（推奨）
```python
@dataclass
class GitHubConnection:
    token: str | None = None
    app_id: int | None = None

    @classmethod
    def from_env(cls) -> "GitHubConnection":
        return cls(token=os.getenv("GITHUB_TOKEN"), ...)

    def validate(self) -> bool:
        return bool(self.token or (self.app_id and ...))

class ConnectionRegistry:
    @classmethod
    def get_github(cls) -> GitHubConnection:
        if cls._github is None:
            cls._github = GitHubConnection.from_env()
        return cls._github
```

**メリット**:
- ✅ 型安全性（@dataclass）
- ✅ DRY原則（URL構築等が1箇所）
- ✅ 拡張容易（新プラットフォーム追加が3ステップ）
- ✅ テスト容易（Registry.set_*でモック注入）
- ✅ 設定ファイル対応可能（YAML/JSON）
- ✅ ADR-001準拠（Pure DI + Factory継続）

**デメリット**:
- 🟡 新規レイヤー追加（学習コスト）
- 🟡 既存コード修正が必要

---

#### 選択肢D: ハイブリッド方式
Airflow環境ではAirflow Connection、それ以外では独自Connection。

**メリット**:
- ✅ 両方の利点を活用

**デメリット**:
- ❌ 複雑性増加
- ❌ メンテナンスコスト高
- ❌ 現在の規模には過剰

---

## 決定内容

**選択肢C: Connection抽象化層** を採用する。

### 設計原則

1. **ADR-001準拠**
   - Pure DI + Factoryパターンを継続
   - Protocolベースの抽象化
   - 外部DIコンテナ不使用

2. **拡張性優先**
   - 新プラットフォーム追加が容易
   - プラグインアーキテクチャを想定

3. **型安全性**
   - @dataclassで厳密な型定義
   - 実行時検証

4. **後方互換性**
   - 既存の引数も残す
   - 段階的移行を可能に

### アーキテクチャ

```
┌─────────────────────────────────────────┐
│         Application Layer               │
│  (DAG, Streamlit, Superset)             │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│         Factory Layer (ADR-001)         │
│  ClientFactory.create_*_client()        │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│      Connection Layer (NEW)             │
│  - ConnectionRegistry                   │
│  - GitHubConnection                     │
│  - GitLabConnection (future)            │
│  - DatabaseConnection                   │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│         Client Layer                    │
│  - GitHubClient(connection)             │
│  - GitLabClient(connection) (future)    │
│  - DatabaseClient(connection)           │
└─────────────────────────────────────────┘
```

### 実装方針

#### 1. Connection定義（@dataclass）

```python
@dataclass
class GitHubConnection:
    """GitHub接続設定"""
    # Personal Access Token認証
    token: str | None = None

    # GitHub Apps認証
    app_id: int | None = None
    installation_id: int | None = None
    private_key: str | None = None
    private_key_path: str | None = None

    # 共通設定
    base_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> "GitHubConnection":
        """環境変数から生成"""
        return cls(
            token=os.getenv("GITHUB_TOKEN"),
            app_id=int(os.getenv("GITHUB_APP_ID", "0")) or None,
            # ...
        )

    def validate(self) -> bool:
        """接続情報の検証"""
        if self.token:
            return True
        if self.app_id and self.installation_id:
            return bool(self.private_key or self.private_key_path)
        return False
```

#### 2. ConnectionRegistry（一元管理）

```python
class ConnectionRegistry:
    """Connection設定を一元管理"""
    _github: GitHubConnection | None = None
    _gitlab: GitLabConnection | None = None
    _database: DatabaseConnection | None = None

    @classmethod
    def get_github(cls) -> GitHubConnection:
        if cls._github is None:
            cls._github = GitHubConnection.from_env()
        return cls._github

    @classmethod
    def set_github(cls, conn: GitHubConnection) -> None:
        """テスト時のモック注入"""
        cls._github = conn

    @classmethod
    def reset_all(cls) -> None:
        """全リセット（テスト用）"""
        cls._github = None
        cls._gitlab = None
        cls._database = None
```

#### 3. Factory統合

```python
class ClientFactory:
    @staticmethod
    def create_github_client(
        connection: GitHubConnection | None = None
    ) -> GitHubClientProtocol:
        if connection is None:
            connection = ConnectionRegistry.get_github()
        return GitHubClient(connection=connection)
```

#### 4. Client修正（後方互換性維持）

```python
class GitHubClient:
    def __init__(
        self,
        connection: GitHubConnection | None = None,
        # 後方互換性のため既存引数も残す
        app_id: int | None = None,
        token: str | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        # Connection優先
        if connection is None:
            # 既存の引数から生成（後方互換性）
            connection = GitHubConnection(
                token=token,
                app_id=app_id,
                base_url=base_url,
            )
            # 引数が全てNoneなら環境変数から
            if not connection.validate():
                connection = GitHubConnection.from_env()

        # 検証
        if not connection.validate():
            raise ValueError("GitHub authentication not configured")

        # 既存の初期化処理
        # ...
```

#### 5. 設定ファイル対応（オプション）

```yaml
# connections.yml
github:
  token: ${GITHUB_TOKEN}
  base_url: https://api.github.com

gitlab:
  token: ${GITLAB_TOKEN}
  base_url: https://gitlab.com

database:
  host: localhost
  port: 5432
  database: nagare
  user: nagare_user
  password: ${DATABASE_PASSWORD}
```

```python
# 使用例
ConnectionRegistry.from_file("connections.yml")
```

### 実装場所

- `src/nagare/utils/connections.py` - Connection定義とRegistry（新規）
- `src/nagare/utils/factory.py` - Factory修正
- `src/nagare/utils/github_client.py` - Client修正
- `src/nagare/utils/database.py` - Client修正
- `src/nagare/admin_app.py` - 重複コード削減
- `connections.yml` - 設定ファイル（環境変数参照のみ、gitコミット可能）

---

## 結果（Consequences）

### ポジティブな影響 ✅

1. **拡張性の向上**
   - 新プラットフォーム追加が3ステップ
     1. Connection定義追加
     2. Client実装
     3. Factory登録
   - プラグインアーキテクチャの基盤

2. **保守性の向上**
   - 接続情報管理が一元化
   - DRY原則遵守（URL構築等）
   - コード重複の削減

3. **型安全性の向上**
   - @dataclassによる厳密な型定義
   - 実行時検証（validate()）
   - 型ヒントによる補完

4. **テスト容易性の維持**
   ```python
   # テストでのモック注入
   ConnectionRegistry.set_github(
       GitHubConnection(token="test_token")
   )
   ```

5. **設定の柔軟性**
   - 環境変数（デフォルト）
   - 設定ファイル（YAML/JSON）
   - プログラムからの直接設定

6. **ADR-001準拠**
   - Pure DI + Factoryパターン継続
   - 依存性数: 4個（GitHub, GitLab, CircleCI, Database）< 5個

### ネガティブな影響 ⚠️

1. **新規レイヤー追加**
   - 学習コスト: 約1-2時間
   - 新しい概念（ConnectionRegistry）

2. **既存コード修正**
   - 4ファイルの修正が必要
   - テストの更新が必要

3. **実装コスト**
   - 新規実装: 約300行
   - テスト追加: 約150行

### 緩和策

1. **学習コスト**
   - ADR文書の整備
   - 実装例の提供
   - コメントによる説明

2. **後方互換性**
   - 既存の引数を残す
   - 段階的な移行を許可
   - 非推奨警告を段階的に導入

---

## 新プラットフォーム追加手順

### 例: GitLab追加

#### Step 1: Connection定義（10行）
```python
# connections.pyに追加
@dataclass
class GitLabConnection:
    token: str | None = None
    base_url: str = "https://gitlab.com"

    @classmethod
    def from_env(cls):
        return cls(
            token=os.getenv("GITLAB_TOKEN"),
            base_url=os.getenv("GITLAB_URL", "https://gitlab.com"),
        )

    def validate(self) -> bool:
        return bool(self.token)
```

#### Step 2: Client実装（50-100行）
```python
# gitlab_client.py（新規）
class GitLabClient:
    def __init__(self, connection: GitLabConnection):
        if not connection.validate():
            raise ValueError("GitLab authentication not configured")

        self.token = connection.token
        self.base_url = connection.base_url
        # ...

    def get_pipelines(self, ...):
        # 実装
        pass
```

#### Step 3: Factory登録（5行）
```python
# factory.pyに追加
@staticmethod
def create_gitlab_client(
    connection: GitLabConnection | None = None
) -> GitLabClientProtocol:
    if connection is None:
        connection = ConnectionRegistry.get_gitlab()
    return GitLabClient(connection=connection)
```

**合計**: 約70行で新プラットフォーム追加可能

---

## 今後の見直し条件

以下のいずれかに該当した場合、Airflow Connection統合を再検討する：

| # | 条件 | 現在値 | 閾値 |
|---|------|--------|------|
| 1 | プラットフォーム数 | 2個 | 5個以上 |
| 2 | 環境変数の数 | 7個 | 30個以上 |
| 3 | 暗号化要件 | なし | 必須 |
| 4 | UI管理要件 | なし | 必須 |
| 5 | マルチテナント | なし | 必要 |

### 次回レビュー予定
- **定期レビュー**: 2026年1月26日（3ヶ月後）
- **トリガーレビュー**: 上記条件に該当した時点

---

## 参考資料

### 実装（実装後に追加）
- [src/nagare/utils/connections.py](../../src/nagare/utils/connections.py)
- [connections.yml](../../../connections.yml)
- [tests/utils/test_connections.py](../../tests/utils/test_connections.py)

### 関連ADR
- [ADR-001: 依存性注入戦略](./001-dependency-injection-strategy.md)

### 設計資料
- [アーキテクチャ設計](../architecture.md)
- [実装ガイド](../implementation_guide.md)

---

## 実装計画

### Phase 1: Connection抽象化層の実装（優先度: 高）
- [ ] `connections.py`の作成
- [ ] `ConnectionRegistry`の実装
- [ ] `GitHubConnection`, `DatabaseConnection`の実装
- [ ] 単体テストの作成

### Phase 2: 既存コードのリファクタリング（優先度: 高）
- [ ] `factory.py`の修正
- [ ] `github_client.py`の修正
- [ ] `database.py`の修正
- [ ] `admin_app.py`の重複コード削減

### Phase 3: 設定ファイル対応（優先度: 中）
- [x] `connections.yml`の作成（環境変数参照形式でgitコミット可能）
- [ ] `ConnectionRegistry.from_file()`の実装
- [ ] YAMLパース処理の実装

### Phase 4: 管理画面統合（優先度: 低）
- [ ] Streamlitに設定確認ページ追加
- [ ] Connection検証機能の追加

### Phase 5: 将来の拡張準備（優先度: 低）
- [ ] `GitLabConnection`の骨格実装
- [ ] `CircleCIConnection`の骨格実装
- [ ] プラグインアーキテクチャの検討

---

## 変更履歴

| 日付 | 変更内容 | 変更者 |
|------|---------|--------|
| 2025-10-26 | 初版作成 | Development Team |

---

## 承認

- **提案者**: Development Team
- **承認者**: Project Owner
- **承認日**: 2025年10月26日
