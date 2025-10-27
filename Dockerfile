# ベースイメージ: Apache Airflow 2.10.0 with Python 3.11
FROM apache/airflow:2.10.0-python3.11

# ユーザーをrootに切り替え（パッケージインストール用）
USER root

# ランタイムに必要な最小限のパッケージのみインストール
# libpq5: PostgreSQL接続用（ランタイムライブラリ）
# curl: ヘルスチェック用
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ユーザーをairflowに戻す
USER airflow

# 作業ディレクトリを設定
WORKDIR /opt/airflow

# アプリケーションコードと依存関係ファイルをコピー
COPY --chown=airflow:root pyproject.toml README.md ./
COPY --chown=airflow:root src/ ./src/

# ビルド環境の指定（production or development）
# デフォルトは production（安全側に倒す）
ARG BUILD_ENV=production

# 追加の依存関係をインストール
# psycopg2-binaryを使用するため、build-essentialは不要
# Airflowは既にベースイメージに含まれている
# BUILD_ENV=development の場合のみ開発依存関係（pytest, ruff, pyright）をインストール
RUN if [ "$BUILD_ENV" = "development" ]; then \
        echo "🔧 Installing development dependencies (pytest, ruff, pyright)..." && \
        pip install --no-cache-dir ".[dev]"; \
    else \
        echo "🚀 Installing production dependencies only..." && \
        pip install --no-cache-dir .; \
    fi

# PYTHONPATH設定（srcディレクトリをインポートパスに追加）
ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow/src"

# Airflowのホームディレクトリ
ENV AIRFLOW_HOME=/opt/airflow

# デフォルトコマンド（docker-compose.ymlでオーバーライド可能）
CMD ["airflow", "webserver"]
