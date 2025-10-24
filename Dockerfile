# ベースイメージ: Apache Airflow 2.10.0 with Python 3.11
FROM apache/airflow:2.10.0-python3.11

# ユーザーをrootに切り替え（パッケージインストール用）
USER root

# システムパッケージの更新とクリーンアップ
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ユーザーをairflowに戻す
USER airflow

# 作業ディレクトリを設定
WORKDIR /opt/airflow

# アプリケーションコードと依存関係ファイルをコピー
COPY --chown=airflow:root pyproject.toml README.md ./
COPY --chown=airflow:root src/ ./src/
COPY --chown=airflow:root scripts/ ./scripts/

# 追加の依存関係をインストール（本番環境用、editable installなし）
# Airflowは既にベースイメージに含まれているため、
# pyproject.tomlのdependenciesには本番環境に必要な依存関係のみを記載
RUN pip install --no-cache-dir .

# PYTHONPATH設定（srcディレクトリをインポートパスに追加）
ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow/src"

# Airflowのホームディレクトリ
ENV AIRFLOW_HOME=/opt/airflow

# DAGsディレクトリのパス（srcディレクトリ内を直接指定）
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/src/nagare/dags

# ヘルスチェック用のエントリーポイント
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD airflow jobs check --job-type SchedulerJob --hostname "$${HOSTNAME}" || exit 1

# デフォルトコマンド（docker-compose.ymlでオーバーライド可能）
CMD ["airflow", "webserver"]
