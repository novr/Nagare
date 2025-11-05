# ADR-005: 環境変数展開機能の実装

## ステータス

**Accepted** - 2025年10月28日

## コンテキスト

ADR-002で導入したConnection管理アーキテクチャにおいて、`connections.yml`ファイルからの設定読み込み機能が実装されている。しかし、現状の実装では以下の問題が存在する。

### 現状の問題点

1. **セキュリティリスク**
   ```yaml
   # ❌ 悪い例：機密情報を直接記載
   github:
     token: ghp_xxxxxxxxxxxxxxxxxxxx  # トークンが平文で保存
   database:
     password: my_secret_password     # パスワードが漏洩リスク
   ```
   - `connections.yml`に機密情報を直接記載する必要がある
   - Git履歴に残るリスクがある
   - ファイルシステム上に平文で保存される

2. **複数環境での管理が煩雑**
   ```bash
   # 環境ごとに異なるファイルが必要
   connections.yml.dev
   connections.yml.staging
   connections.yml.production
   ```
   - 環境ごとに異なる`connections.yml`が必要
   - 構造的な設定と機密情報が混在
   - ファイルの重複管理が発生

3. **12 Factor Appの原則違反**
   - 設定を環境変数で管理するベストプラクティスに反する
   - Docker/Kubernetesとの統合が非効率
   - CI/CDパイプラインでの設定注入が困難

4. **柔軟性の欠如**
   ```yaml
   # デフォルト値を設定できない
   database:
     host: localhost  # 開発環境用
     # 本番環境ではどうする？
   ```
   - デフォルト値の指定ができない
   - 環境依存の値を動的に設定できない

### プロジェクト要件

- **セキュリティ**: 機密情報を安全に管理
- **柔軟性**: 複数環境への対応
- **保守性**: `.env`ファイルとの統合
- **後方互換性**: 既存の`connections.yml`が動作
- **標準準拠**: 業界標準のパターンを採用

### 検討した選択肢

#### 選択肢A: 現状維持（connections.ymlに直接記載）

```yaml
github:
  token: ghp_xxxxxxxxxxxxxxxxxxxx
database:
  password: my_secret_password
```

**メリット**:
- 変更不要
- シンプル

**デメリット**:
- ❌ セキュリティリスク
- ❌ Git管理が困難
- ❌ 環境ごとに異なるファイルが必要

---

#### 選択肢B: 環境変数のみを使用（connections.ymlを廃止）

```python
# 環境変数から直接読み込み
ConnectionRegistry.get_github()  # GITHUB_TOKENを読み取り
```

**メリット**:
- ✅ セキュリティが高い
- ✅ 12 Factor App準拠
- ✅ シンプル

**デメリット**:
- ❌ 複数のConnection定義ができない
- ❌ 構造的な設定が環境変数に散在
- ❌ デフォルト値の管理が困難

---

#### 選択肢C: 環境変数展開機能（推奨）

```yaml
# connections.yml: 構造的な設定
github_default:
  token: ${GITHUB_TOKEN}  # 環境変数から読み込み
  base_url: ${GITHUB_API_URL:-https://api.github.com}  # デフォルト値付き

github_enterprise:
  token: ${GITHUB_ENTERPRISE_TOKEN}
  base_url: ${GITHUB_ENTERPRISE_URL}

database:
  host: ${DATABASE_HOST:-localhost}
  port: ${DATABASE_PORT:-5432}
  password: ${DATABASE_PASSWORD}
```

```bash
# .env: 機密情報のみ
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_ENTERPRISE_TOKEN=ghp_yyyyyyyyyyyy
DATABASE_PASSWORD=secure_password
```

**メリット**:
- ✅ セキュリティ：機密情報を`.env`で管理
- ✅ 柔軟性：複数のConnection定義が可能
- ✅ 保守性：構造と機密情報の分離
- ✅ デフォルト値のサポート
- ✅ 業界標準のパターン（Docker Compose等）
- ✅ 後方互換性：既存ファイルも動作

**デメリット**:
- △ 実装が必要（正規表現パース）
- △ わずかな複雑性の増加

---

#### 選択肢D: テンプレートエンジン（Jinja2等）

```yaml
github:
  token: {{ GITHUB_TOKEN }}
```

**メリット**:
- ✅ 強力な機能（条件分岐、ループ等）

**デメリット**:
- ❌ 過剰な複雑性
- ❌ 新しい依存関係（Jinja2）
- ❌ 学習コストが高い

---

## 決定

**選択肢C（環境変数展開機能）を採用する。**

### 実装方針

1. **環境変数展開の構文**
   - `${VAR_NAME}`: 環境変数の値を展開（未設定の場合は空文字）
   - `${VAR_NAME:-default}`: デフォルト値をサポート
   - 文字列の一部としても使用可能: `https://${HOST}/api/v1`

2. **実装箇所**
   - `ConnectionRegistry._expand_env_vars()`: 再帰的な環境変数展開
   - `ConnectionRegistry.from_file()`: YAMLロード後に環境変数を展開

3. **サポート対象**
   - 文字列値: `${VAR_NAME}`を展開
   - 辞書: 再帰的に処理
   - リスト: 再帰的に処理
   - その他の型（int, bool, None）: そのまま維持

4. **正規表現パターン**
   ```python
   pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}"
   # マッチ例:
   # ${VAR_NAME}         → group(1)=VAR_NAME, group(3)=None
   # ${VAR_NAME:-default} → group(1)=VAR_NAME, group(3)=default
   ```

### 実装コード

```python
@classmethod
def _expand_env_vars(cls, value: Any) -> Any:
    """環境変数を展開する"""
    if isinstance(value, str):
        pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}"

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(3) if match.group(3) is not None else ""
            return os.getenv(var_name, default_value)

        return re.sub(pattern, replacer, value)

    elif isinstance(value, dict):
        return {k: cls._expand_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [cls._expand_env_vars(item) for item in value]

    else:
        return value

@classmethod
def from_file(cls, path: str | Path) -> None:
    """設定ファイルから読み込み（環境変数展開付き）"""
    # ...
    config = yaml.safe_load(f)

    # 環境変数を展開
    config = cls._expand_env_vars(config)

    # Connectionを生成
    # ...
```

## 影響

### プラス影響

1. **セキュリティの向上**
   - 機密情報を`.env`ファイルで管理
   - `connections.yml`をGitで管理可能（構造定義のみ）
   - トークン漏洩リスクの低減

2. **柔軟性の向上**
   - 複数のConnection定義が可能
   - 環境ごとに異なる`.env`で対応
   - デフォルト値のサポート

3. **開発効率の向上**
   - Docker Composeと統合しやすい
   - CI/CDパイプラインでの設定注入が容易
   - ローカル開発環境の構築が簡単

4. **保守性の向上**
   - 構造的な設定と機密情報の分離
   - 設定の可読性が向上
   - DRYの原則に準拠

### マイナス影響

1. **わずかな複雑性の増加**
   - 環境変数展開のロジックが追加
   - ユーザーが2つのファイルを管理
   - ドキュメント整備が必要

2. **デバッグの複雑化**
   - 展開後の値が不明瞭になる可能性
   - 環境変数の設定ミスの検出が困難

### 緩和策

1. **明確なドキュメント**
   - `connections.yml`に豊富な例を記載
   - セキュリティベストプラクティスを明示
   - トラブルシューティングガイドを提供

2. **エラーハンドリング**
   - 環境変数が未設定の場合の明確なエラーメッセージ
   - デフォルト値を積極的に推奨

3. **テストの充実**
   - 環境変数展開の包括的なテスト
   - エッジケース（空文字、特殊文字）のカバー

## 使用例

### Docker環境での使い方（推奨）

**設計方針**:
- **固定値**（host, port）は`docker-compose.yml`または`connections.yml`で管理
- **機密情報**（password, token）のみ`.env`で管理
- 重複を避け、Single Source of Truth（単一の真実の情報源）を維持

```yaml
# connections.yml
github_default:
  token: ${GITHUB_TOKEN}

database:
  # Docker環境では固定値を使用（docker-compose.ymlのサービス名）
  host: postgres  # 環境変数ではなく固定値
  port: 5432      # 環境変数ではなく固定値
  database: ${DATABASE_NAME:-nagare}
  user: ${DATABASE_USER:-nagare_user}
  password: ${DATABASE_PASSWORD}  # 機密情報のみ環境変数
```

```bash
# .env（機密情報のみ）
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
DATABASE_PASSWORD=secure_password
# DATABASE_HOSTとDATABASE_PORTは不要（docker-compose.ymlで管理）
```

```yaml
# docker-compose.yml（抜粋）
services:
  postgres:
    container_name: nagare-postgres
    environment:
      POSTGRES_USER: ${DATABASE_USER:-nagare_user}
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
      POSTGRES_DB: ${DATABASE_NAME:-nagare}
```

### ローカル開発環境（docker-compose.yml不使用）

```yaml
# connections.yml
database:
  # すべて環境変数から読み込み
  host: ${DATABASE_HOST:-localhost}
  port: ${DATABASE_PORT:-5432}
  password: ${DATABASE_PASSWORD}
```

```bash
# .env
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_PASSWORD=secure_password
```

### 複数のConnection定義

```yaml
# connections.yml
github_prod:
  token: ${GITHUB_PROD_TOKEN}

github_dev:
  token: ${GITHUB_DEV_TOKEN}

github_readonly:
  token: ${GITHUB_READONLY_TOKEN}
```

```bash
# .env
GITHUB_PROD_TOKEN=ghp_prod_xxxxx
GITHUB_DEV_TOKEN=ghp_dev_xxxxx
GITHUB_READONLY_TOKEN=ghp_readonly_xxxxx
```

### GitHub Enterprise

```yaml
# connections.yml
github_enterprise:
  token: ${GITHUB_ENTERPRISE_TOKEN}
  base_url: ${GITHUB_ENTERPRISE_URL}
```

```bash
# .env
GITHUB_ENTERPRISE_TOKEN=ghp_enterprise_xxxxx
GITHUB_ENTERPRISE_URL=https://github.example.com/api/v3
```

## 実装タスク

- [x] `ConnectionRegistry._expand_env_vars()`の実装
- [x] 環境変数展開の包括的なテスト
- [x] `connections.yml`の更新（環境変数参照形式）
- [x] ADRドキュメントの作成
- [x] 全テストの実行と検証

## 関連資料

- [ADR-002: Connection管理アーキテクチャ](./002-connection-management-architecture.md)
- [12 Factor App - Config](https://12factor.net/config)
- [Docker Compose - Environment Variable Substitution](https://docs.docker.com/compose/environment-variables/)
- [Kubernetes - ConfigMaps and Secrets](https://kubernetes.io/docs/concepts/configuration/)

## 変更履歴

- 2025-10-28: 初版作成・承認
