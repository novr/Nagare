"""モックデータベースクライアント

開発環境で使用するモック実装。
環境変数からリポジトリ情報を読み込む。
"""

import json
import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class MockDatabaseClient:
    """モックデータベースクライアント

    PostgreSQL未接続時に使用する開発用モック。
    環境変数REPOSITORIES_JSONからリポジトリ情報を読み込む。
    """

    def __init__(self) -> None:
        """モックDatabaseClientを初期化する"""
        logger.info("MockDatabaseClient initialized (development mode)")

    def get_repositories(self) -> list[dict[str, str]]:
        """監視対象リポジトリのリストを取得する（モック実装）

        環境変数REPOSITORIES_JSONから読み込む。

        Returns:
            リポジトリ情報のリスト（owner, repoを含む辞書）
        """
        # 環境変数から読み込み (JSON形式)
        repositories_json = os.getenv("REPOSITORIES_JSON")
        if repositories_json:
            repositories = json.loads(repositories_json)
            logger.info(
                f"[MOCK] Loaded {len(repositories)} repositories from REPOSITORIES_JSON"
            )
            return repositories

        # デフォルト（空リスト）
        logger.warning("[MOCK] No repositories configured. Set REPOSITORIES_JSON")
        return []

    def upsert_pipeline_runs(self, runs: list[dict[str, Any]]) -> None:
        """pipeline_runsテーブルにデータをUPSERTする（モック実装）

        実際にはデータを保存せず、ログ出力のみ行う。

        Args:
            runs: ワークフロー実行データのリスト
        """
        logger.info(f"[MOCK] Would upsert {len(runs)} pipeline runs")
        for run in runs:
            logger.debug(
                f"[MOCK] Would upsert run: {run.get('source_run_id')} "
                f"({run.get('repository_owner')}/{run.get('repository_name')}) "
                f"- Status: {run.get('status')}"
            )

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """jobsテーブルにデータをUPSERTする（モック実装）

        実際にはデータを保存せず、ログ出力のみ行う。

        Args:
            jobs: ジョブデータのリスト
        """
        logger.info(f"[MOCK] Would upsert {len(jobs)} jobs")
        for job in jobs:
            logger.debug(
                f"[MOCK] Would upsert job: {job.get('source_job_id')} "
                f"({job.get('repository_owner')}/{job.get('repository_name')}) "
                f"- Job: {job.get('job_name')} - Status: {job.get('status')}"
            )

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """トランザクションを開始する（モック実装）

        Context managerとして使用。実際のトランザクションは行わず、
        ログ出力のみ行う。

        Yields:
            None

        Example:
            with db.transaction():
                db.upsert_pipeline_runs(runs)
                db.upsert_jobs(jobs)
        """
        logger.debug("[MOCK] Transaction started")
        try:
            yield
            logger.info("[MOCK] Transaction committed (no-op)")
        except Exception as e:
            logger.warning(f"[MOCK] Transaction rolled back (no-op): {e}")
            raise

    def close(self) -> None:
        """データベース接続をクローズする（モック実装）

        モック実装では何もしない。
        """
        logger.debug("[MOCK] MockDatabaseClient closed (no-op)")

    def __enter__(self) -> "MockDatabaseClient":
        """Context manager: with文でのエントリーポイント

        Returns:
            MockDatabaseClientインスタンス自身
        """
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理

        Args:
            *args: 例外情報（型、値、トレースバック）
        """
        self.close()
