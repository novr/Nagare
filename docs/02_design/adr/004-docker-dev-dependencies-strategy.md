# ADR-004: Docker環境での開発依存関係管理戦略

## ステータス

採用 (2025-10-28)

## コンテキスト

Nagareは Docker Compose で開発・本番環境を管理している。現在のDockerfileではテスト実行のために開発依存関係（pytest, ruff, pyright）を常にインストールしているが、これは本番環境では不要である。

### 現状の問題

```dockerfile
# 現在: 本番環境にも開発依存関係をインストール
RUN pip install --no-cache-dir ".[dev]"
```

**問題点**:
- ❌ pytest, ruff, pyright が本番環境に含まれる（不要）
- ❌ Dockerイメージサイズが増加（約50-100MB）
- ❌ セキュリティ上のベストプラクティスに反する
- ❌ 攻撃面が増加（不要なパッケージが含まれる）

### 要件

1. **ローカル開発**: Docker内でテスト実行可能
2. **本番環境**: 開発依存関係を含まない軽量イメージ
3. **シンプルさ**: 複雑な構成を避ける
4. **メンテナンス性**: 将来の変更が容易

## 検討した選択肢

### 選択肢1: 環境変数で条件分岐

**実装方法**:
```dockerfile
ARG BUILD_ENV=production

RUN if [ "$BUILD_ENV" = "development" ]; then \
        pip install --no-cache-dir ".[dev]"; \
    else \
        pip install --no-cache-dir .; \
    fi
```

```yaml
# docker-compose.yml
services:
  airflow-scheduler:
    build:
      args:
        BUILD_ENV: development
```

**メリット**:
- ✅ シンプルで理解しやすい
- ✅ docker-compose.ymlで簡単に制御
- ✅ 単一のDockerfileで管理
- ✅ CI/CDで本番用ビルドが容易（`--build-arg BUILD_ENV=production`）

**デメリット**:
- ⚠️ ビルド時に環境を指定する必要がある
- ⚠️ レイヤーキャッシュが環境ごとに分かれる

**判断**: ✅ 採用 - メリットがデメリットを上回る

### 選択肢2: マルチステージビルド

**実装方法**:
```dockerfile
FROM apache/airflow:2.10.0-python3.11 as development
RUN pip install --no-cache-dir ".[dev]"

FROM apache/airflow:2.10.0-python3.11 as production
RUN pip install --no-cache-dir .

# docker-compose.yml で target を指定
```

**メリット**:
- ✅ 環境を完全に分離
- ✅ Dockerのベストプラクティス

**デメリット**:
- ⚠️ docker-compose.ymlで`target`指定が必要
- ⚠️ ステージ間でコードを共有する場合の複雑さ
- ⚠️ ビルド時間が若干増加

**判断**: ❌ 不採用 - 現時点では過剰

### 選択肢3: 別のDockerfile作成

**実装方法**:
- `Dockerfile` - 本番用
- `Dockerfile.dev` - 開発/テスト用

**メリット**:
- ✅ 完全に独立した構成
- ✅ 各環境で最適化しやすい

**デメリット**:
- ❌ 2つのDockerfileのメンテナンス負担
- ❌ 設定の重複（DRY原則に反する）
- ❌ docker-compose.ymlで複数のdockerfileを管理

**判断**: ❌ 不採用 - メンテナンス負担が大きい

## 決定

**選択肢1（環境変数で条件分岐）を採用する**

### 実装方針

1. **Dockerfile**: `BUILD_ENV` ARGで条件分岐
2. **docker-compose.yml**: 開発環境では `BUILD_ENV=development` を指定
3. **本番デプロイ**: `docker build` 時にARGを指定しない（デフォルト: production）

### 実装例

```dockerfile
# Dockerfile
ARG BUILD_ENV=production

RUN if [ "$BUILD_ENV" = "development" ]; then \
        echo "Installing development dependencies..." && \
        pip install --no-cache-dir ".[dev]"; \
    else \
        echo "Installing production dependencies only..." && \
        pip install --no-cache-dir .; \
    fi
```

```yaml
# docker-compose.yml
x-airflow-common: &airflow-common
  build:
    context: .
    dockerfile: Dockerfile
    args:
      BUILD_ENV: development  # ローカル開発用
```

```bash
# 本番デプロイ時
docker build -t nagare:latest .  # デフォルトでproduction
# または明示的に
docker build --build-arg BUILD_ENV=production -t nagare:latest .
```

## 理由

### 1. シンプルさを重視

- 単一のDockerfileで管理
- docker-compose.ymlでの制御が直感的
- チーム全体が理解しやすい

### 2. 開発体験を損なわない

- ローカル開発でテスト実行可能
- CI/CDでも同じDockerfileを使用
- 環境の切り替えが簡単

### 3. セキュリティの向上

- 本番環境に不要なパッケージを含まない
- 攻撃面の削減
- イメージサイズの削減（50-100MB）

### 4. CI/CD との統合

```yaml
# CI/CD 例（GitHub Actions）
- name: Build test image
  run: docker build --build-arg BUILD_ENV=development -t nagare:test .

- name: Run tests
  run: docker run nagare:test pytest

- name: Build production image
  run: docker build --build-arg BUILD_ENV=production -t nagare:latest .
```

## 結果

### ポジティブな影響

- ✅ 本番イメージサイズ削減: 約50-100MB
- ✅ セキュリティ向上: 不要なパッケージの除外
- ✅ 開発体験維持: Docker内でテスト実行可能
- ✅ メンテナンス性: 単一のDockerfile

### ネガティブな影響

- ⚠️ ビルド時に環境指定が必要
- ⚠️ レイヤーキャッシュが環境ごとに分かれる（ビルド時間への影響は軽微）

### 軽減策

- **ドキュメント**: README.mdにビルド方法を明記
- **デフォルト値**: production をデフォルトに設定（安全側に倒す）
- **CI/CD**: 明示的に環境を指定するワークフロー

## 将来の見直し

以下の場合は、マルチステージビルド（選択肢2）への移行を検討:
- 開発環境と本番環境で大きく異なる依存関係が必要になった場合
- ビルド時間の最適化が重要になった場合
- 複数の環境（development, staging, production）を管理する必要が出た場合

## 関連ADR

- [ADR-001: Dependency Injection Strategy](001-dependency-injection-strategy.md)
- [ADR-002: Connection Management Architecture](002-connection-management-architecture.md)
- [ADR-003: Bitrise Client Implementation Strategy](003-bitrise-client-implementation-strategy.md)

## 参考資料

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker ARG and ENV](https://docs.docker.com/engine/reference/builder/#arg)
