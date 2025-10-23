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

# Pythonの依存関係ファイルをコピー（キャッシュ最適化のため先にコピー）
COPY --chown=airflow:root pyproject.toml uv.lock ./

# uvをインストール
RUN pip install --no-cache-dir uv

# 依存関係をインストール（本番環境用）
# uvを使用してロックファイルから正確な依存関係をインストール
RUN uv pip install --system --no-cache -r uv.lock

# アプリケーションコードをコピー
COPY --chown=airflow:root src/ ./src/

# Airflow DAGsディレクトリへのシンボリックリンクを作成
RUN ln -s /opt/airflow/src/nagare/dags /opt/airflow/dags

# PYTHONPATH設定（srcディレクトリをインポートパスに追加）
ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow/src"

# Airflowのホームディレクトリ
ENV AIRFLOW_HOME=/opt/airflow

# DAGsディレクトリのパス
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags

# ヘルスチェック用のエントリーポイント
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD airflow jobs check --job-type SchedulerJob --hostname "$${HOSTNAME}" || exit 1

# デフォルトコマンド（docker-compose.ymlでオーバーライド可能）
CMD ["airflow", "webserver"]
