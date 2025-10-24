"""データベースユーティリティ

PostgreSQL接続とデータアクセス機能を提供する。
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class DatabaseClient:
    """本番用データベースクライアント

    PostgreSQLへの接続とデータアクセス機能を提供する。
    開発環境ではMockDatabaseClientを使用すること。
    """

    def __init__(self) -> None:
        """DatabaseClientを初期化する"""
        logger.info("DatabaseClient initialized (production mode)")

        # 環境変数から接続情報を取得
        db_host = os.getenv("DATABASE_HOST", "localhost")
        db_port = os.getenv("DATABASE_PORT", "5432")
        db_name = os.getenv("DATABASE_NAME", "nagare")
        db_user = os.getenv("DATABASE_USER", "nagare_user")
        db_password = os.getenv("DATABASE_PASSWORD", "")

        # 接続URL構築
        db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        # PostgreSQL接続プールの初期化
        self.engine: Engine = create_engine(
            db_url,
            pool_pre_ping=True,  # 接続の有効性を確認
            pool_size=5,
            max_overflow=10,
        )
        self.session_factory = sessionmaker(bind=self.engine)
        logger.info(f"Connected to PostgreSQL: {db_host}:{db_port}/{db_name}")

    def get_repositories(self) -> list[dict[str, str]]:
        """監視対象リポジトリのリストを取得する

        PostgreSQLから監視対象リポジトリを取得する。

        Returns:
            リポジトリ情報のリスト（owner, repoを含む辞書）
        """
        session = self.session_factory()
        try:
            # repository_name形式は"owner/repo"を想定
            query = text(
                """
                SELECT id, repository_name
                FROM repositories
                WHERE active = TRUE
                """
            )
            result = session.execute(query)
            repositories = []
            for row in result:
                # repository_nameを"owner/repo"から分割
                parts = row.repository_name.split("/", 1)
                if len(parts) == 2:
                    repositories.append({"owner": parts[0], "repo": parts[1]})
                else:
                    logger.warning(f"Invalid repository_name format: {row.repository_name}")
            logger.info(f"Retrieved {len(repositories)} active repositories")
            return repositories
        finally:
            session.close()

    def upsert_pipeline_runs(self, runs: list[dict[str, Any]]) -> None:
        """pipeline_runsテーブルにデータをUPSERTする

        Args:
            runs: ワークフロー実行データのリスト
        """
        if not runs:
            return

        session = self.session_factory()
        try:
            for run in runs:
                query = text(
                    """
                    INSERT INTO pipeline_runs (
                        source_run_id, source, pipeline_name, status, trigger_event,
                        repository_id, branch_name, commit_sha, started_at,
                        completed_at, duration_ms, url
                    )
                    VALUES (
                        :source_run_id, :source, :pipeline_name, :status, :trigger_event,
                        :repository_id, :branch_name, :commit_sha, :started_at,
                        :completed_at, :duration_ms, :url
                    )
                    ON CONFLICT (source_run_id, source) DO UPDATE SET
                        pipeline_name = EXCLUDED.pipeline_name,
                        status = EXCLUDED.status,
                        trigger_event = EXCLUDED.trigger_event,
                        branch_name = EXCLUDED.branch_name,
                        commit_sha = EXCLUDED.commit_sha,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at,
                        duration_ms = EXCLUDED.duration_ms,
                        url = EXCLUDED.url,
                        updated_at = CURRENT_TIMESTAMP
                    """
                )
                session.execute(query, run)
            session.commit()
            logger.info(f"Upserted {len(runs)} pipeline runs")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """jobsテーブルにデータをUPSERTする

        Args:
            jobs: ジョブデータのリスト
        """
        if not jobs:
            return

        session = self.session_factory()
        try:
            for job in jobs:
                query = text(
                    """
                    INSERT INTO jobs (
                        run_id, source_job_id, job_name, status,
                        started_at, completed_at, duration_ms
                    )
                    VALUES (
                        :run_id, :source_job_id, :job_name, :status,
                        :started_at, :completed_at, :duration_ms
                    )
                    ON CONFLICT (source_job_id, run_id) DO UPDATE SET
                        job_name = EXCLUDED.job_name,
                        status = EXCLUDED.status,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at,
                        duration_ms = EXCLUDED.duration_ms,
                        updated_at = CURRENT_TIMESTAMP
                    """
                )
                session.execute(query, job)
            session.commit()
            logger.info(f"Upserted {len(jobs)} jobs")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        """トランザクションを開始する

        Context managerとして使用し、正常終了時はコミット、例外発生時はロールバック。

        Yields:
            Session: SQLAlchemyセッション

        Example:
            with db.transaction() as session:
                db.upsert_pipeline_runs(runs)
                db.upsert_jobs(jobs)
                # 両方成功した場合のみコミット
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            session.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise
        finally:
            session.close()

    def close(self) -> None:
        """データベース接続をクローズする"""
        self.engine.dispose()
        logger.info("DatabaseClient closed")

    def __enter__(self) -> "DatabaseClient":
        """Context manager: with文でのエントリーポイント

        Returns:
            DatabaseClientインスタンス自身
        """
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager: with文での終了処理

        Args:
            *args: 例外情報（型、値、トレースバック）
        """
        self.close()
