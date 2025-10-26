# Docker構成 批判的レビュー

**レビュー日**: 2025-10-26
**対象ファイル**: `Dockerfile`, `Dockerfile.superset`, `docker-compose.yml`

---

## 🚨 重大な問題（Critical Issues）

### 1. **Dockerfile.superset: latestタグ使用**
**深刻度**: 🔴 Critical

**問題点**:
```dockerfile
FROM apache/superset:latest
```

**影響**:
- 再現性がない（ビルドごとに異なるバージョン）
- 予期しない破壊的変更のリスク
- CI/CDの不安定化

**推奨対策**:
```dockerfile
FROM apache/superset:3.1.0  # 具体的なバージョンを指定
```

### 2. **airflow-init: デフォルトパスワードが"admin"**
**深刻度**: 🔴 Critical

**問題点**:
```yaml
# docker-compose.yml line 157
--password ${AIRFLOW_ADMIN_PASSWORD:-admin}
```

`.env`で`AIRFLOW_ADMIN_PASSWORD`が未設定の場合、パスワードが"admin"になる。

**推奨対策**:
```yaml
# デフォルト値を削除
--password ${AIRFLOW_ADMIN_PASSWORD}

# または.envでエラーチェック
if [ -z "$AIRFLOW_ADMIN_PASSWORD" ]; then
  echo "Error: AIRFLOW_ADMIN_PASSWORD is not set"
  exit 1
fi
```

---

## ⚠️ 高優先度の問題（High Priority Issues）

### 3. **Dockerfile: build-essentialがランタイムに残る**
**深刻度**: 🟡 High

**問題点**:
```dockerfile
# Dockerfile line 8-13
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```

`build-essential`はビルド時のみ必要、ランタイムでは不要。

**影響**:
- イメージサイズ増加（約200MB）
- 攻撃面の拡大

**推奨対策**:
```dockerfile
# マルチステージビルド
FROM apache/airflow:2.10.0-python3.11 AS builder
RUN apt-get update && apt-get install -y build-essential

FROM apache/airflow:2.10.0-python3.11
# libpq-devのみインストール（ランタイムに必要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```

または、`psycopg2-binary`を使用する場合は不要：
```dockerfile
# build-essential不要
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && apt-get clean
```

### 4. **Dockerfile: HEALTHCHECKがSchedulerJob固定**
**深刻度**: 🟡 High

**問題点**:
```dockerfile
# Dockerfile line 41-42
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD airflow jobs check --job-type SchedulerJob --hostname "$${HOSTNAME}" || exit 1
```

このDockerfileは`airflow-webserver`と`streamlit-admin`でも使用されるが、SchedulerJobチェックは不適切。

**推奨対策**:
```dockerfile
# Dockerfileからhealthcheckを削除
# docker-compose.ymlで各サービスに適切なhealthcheckを定義（既に実装済み）
```

### 5. **streamlit-admin: Airflow Dockerfileを流用**
**深刻度**: 🟡 High

**問題点**:
```yaml
# docker-compose.yml line 203-209
streamlit-admin:
  build:
    context: .
    dockerfile: Dockerfile  # Airflow用Dockerfile
  entrypoint: []
  command: ["streamlit", "run", ...]
```

**影響**:
- Airflowの依存関係を含む（不要）
- イメージサイズ増加
- 責務の分離違反

**推奨対策**:
専用のDockerfileを作成：
```dockerfile
# Dockerfile.streamlit
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .[streamlit]

COPY src/ ./src/
ENV PYTHONPATH=/app/src

CMD ["streamlit", "run", "/app/src/nagare/admin_app.py"]
```

### 6. **docker-compose.yml: 環境変数の大量重複**
**深刻度**: 🟡 High

**問題点**:
`airflow-webserver`と`airflow-scheduler`で同じ環境変数を重複定義（約30行）。

**推奨対策**:
```yaml
# YAML anchorsを使用
x-airflow-common: &airflow-common
  build:
    context: .
    dockerfile: Dockerfile
  environment: &airflow-common-env
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
    # ... 共通環境変数
  volumes:
    - ./src:/opt/airflow/src:ro
    - airflow_logs:/opt/airflow/logs

services:
  airflow-webserver:
    <<: *airflow-common
    command: airflow webserver
    environment:
      <<: *airflow-common-env
      AIRFLOW__WEBSERVER__SECRET_KEY: ${AIRFLOW_SECRET_KEY}

  airflow-scheduler:
    <<: *airflow-common
    command: airflow scheduler
```

### 7. **AIRFLOW__CORE__DAGS_FOLDERの重複定義**
**深刻度**: 🟡 High

**問題点**:
```dockerfile
# Dockerfile line 38
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/src/nagare/dags

# docker-compose.yml line 40, 104
AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/src/nagare/dags
```

**推奨対策**:
Dockerfileの定義を削除し、docker-compose.ymlでのみ定義。

---

## 📝 中優先度の問題（Medium Priority Issues）

### 8. **Dockerfile: scripts/ディレクトリのコピー**
**深刻度**: 🟠 Medium

**問題点**:
```dockerfile
# Dockerfile line 24
COPY --chown=airflow:root scripts/ ./scripts/
```

`scripts/setup-secrets.sh`はホストで実行するスクリプト、イメージに含める必要なし。

**推奨対策**:
```dockerfile
# scriptsディレクトリのコピーを削除
# または、必要なスクリプトのみコピー（現在は不要）
```

### 9. **PostgreSQL: パスワードが未設定時のエラーハンドリング不足**
**深刻度**: 🟠 Medium

**問題点**:
```yaml
POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
```

`DATABASE_PASSWORD`が空の場合、PostgreSQLは起動するが認証なし。

**推奨対策**:
```yaml
# entrypointでチェック
entrypoint: /bin/bash
command:
  - -c
  - |
    if [ -z "$POSTGRES_PASSWORD" ]; then
      echo "Error: DATABASE_PASSWORD is not set"
      exit 1
    fi
    docker-entrypoint.sh postgres
```

### 10. **Superset: 初期化処理がない**
**深刻度**: 🟠 Medium

**問題点**:
Supersetのデータベース初期化（`superset db upgrade`, `superset init`）が不足。

**推奨対策**:
```yaml
superset-init:
  build:
    context: .
    dockerfile: Dockerfile.superset
  command: |
    superset db upgrade
    superset fab create-admin \
      --username admin \
      --firstname Admin \
      --lastname User \
      --email admin@example.com \
      --password ${SUPERSET_ADMIN_PASSWORD}
    superset init
  depends_on:
    postgres:
      condition: service_healthy
```

---

## 💡 低優先度の改善提案（Low Priority Improvements）

### 11. **イメージサイズ最適化**

**現状推定サイズ**:
- Airflowイメージ: ~1.5GB（build-essential含む）
- Supersetイメージ: ~1.2GB

**最適化後**:
- Airflowイメージ: ~1.3GB（-200MB）
- Streamlitイメージ: ~500MB（専用イメージ作成）

### 12. **.dockerignore追加**

```gitignore
# .dockerignore
.git
.venv
__pycache__
*.pyc
*.egg-info
.pytest_cache
.ruff_cache
.env
secrets/
tests/
docs/
REVIEW.md
DOCKER_REVIEW.md
```

### 13. **ビルドキャッシュの活用**

```dockerfile
# 依存関係を先にインストール（キャッシュ活用）
COPY --chown=airflow:root pyproject.toml ./
RUN pip install --no-cache-dir .

# コードは後でコピー（変更頻度が高い）
COPY --chown=airflow:root src/ ./src/
```

### 14. **ヘルスチェックのタイムアウト統一**

現在、サービスごとに異なる設定。統一を検討。

### 15. **ネットワーク設定の明示化**

```yaml
networks:
  nagare-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

---

## ✅ 良い点（Strengths）

1. **バージョン固定**: PostgreSQL、Airflowは明示的なバージョン指定
2. **ヘルスチェック**: 全サービスに適切なhealthcheck定義
3. **最小権限の原則**: USER切り替えで不要な権限削除
4. **depends_on条件**: service_healthy使用で順序制御
5. **ボリューム管理**: 名前付きボリュームで永続化
6. **restart設定**: unless-stoppedで自動復旧
7. **リソース制限**: メモリ制限で暴走防止
8. **読み取り専用マウント**: src:roでセキュリティ向上

---

## 🎯 優先度別アクションプラン

### 即座に対応すべき（Critical）
1. [ ] Dockerfile.supersetのlatestタグをバージョン固定
2. [ ] airflow-initのデフォルトパスワード削除またはエラーチェック

### 1週間以内（High Priority）
3. [ ] Dockerfileからbuild-essential削除（マルチステージビルドor psycopg2-binary）
4. [ ] DockerfileからHEALTHCHECK削除（docker-composeで定義済み）
5. [ ] streamlit-admin用の専用Dockerfile作成
6. [ ] docker-compose.ymlでYAML anchors使用（環境変数重複削減）
7. [ ] AIRFLOW__CORE__DAGS_FOLDERの重複削除

### 1ヶ月以内（Medium Priority）
8. [ ] scripts/ディレクトリのコピー削除
9. [ ] PostgreSQLパスワードエラーチェック追加
10. [ ] Superset初期化処理追加

### 継続的に（Low Priority）
11. [ ] .dockerignore追加
12. [ ] ビルドキャッシュ最適化
13. [ ] イメージサイズ監視

---

## 📊 総合評価

| カテゴリ | スコア | コメント |
|---------|--------|----------|
| セキュリティ | 6/10 | デフォルトパスワード、latestタグ使用が問題 |
| 最適化 | 5/10 | build-essential残存、イメージサイズ肥大化 |
| 保守性 | 6/10 | 環境変数重複、責務分離不足 |
| 再現性 | 7/10 | latestタグ以外はバージョン固定 |
| ベストプラクティス | 7/10 | 基本は押さえているが改善余地あり |

**総合スコア**: 6.2/10

**コメント**:
基本的なDocker構成は適切だが、細かい問題が積み重なっている。
特にセキュリティ（デフォルトパスワード、latestタグ）と最適化（build-essential、イメージサイズ）の改善が必要。
YAML anchorsを使用すれば保守性は大幅に向上する。

**重点改善領域**:
1. セキュリティ強化（Critical）
2. イメージ最適化（High）
3. 環境変数の整理（High）
4. 責務の分離（High）
