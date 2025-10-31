"""データベースユーティリティ

PostgreSQL接続とデータアクセス機能を提供する。

ADR-002: Connection管理アーキテクチャに準拠し、
DatabaseConnectionから接続情報を受け取る。
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from nagare.constants import SourceType
from nagare.utils.connections import DatabaseConnection

logger = logging.getLogger(__name__)


class DatabaseClient:
    """本番用データベースクライアント

    PostgreSQLへの接続とデータアクセス機能を提供する。
    開発環境ではMockDatabaseClientを使用すること。
    """

    def __init__(self, connection: DatabaseConnection | None = None) -> None:
        """DatabaseClientを初期化する

        Args:
            connection: データベース接続設定
                       （省略時は環境変数から生成）
        """
        logger.info("DatabaseClient initialized (production mode)")

        # Connection優先、なければ環境変数から生成
        if connection is None:
            connection = DatabaseConnection.from_env()

        # 接続情報の検証
        if not connection.validate():
            raise ValueError(
                "Database connection not configured properly. "
                "Check DATABASE_HOST, DATABASE_NAME, and DATABASE_USER."
            )

        # PostgreSQL接続プールの初期化
        self.engine: Engine = create_engine(
            connection.url,
            pool_pre_ping=connection.pool_pre_ping,
            pool_size=connection.pool_size,
            max_overflow=connection.max_overflow,
        )
        self.session_factory = sessionmaker(bind=self.engine)
        logger.info(
            f"Connected to PostgreSQL: {connection.host}:{connection.port}"
            f"/{connection.database}"
        )

    def get_repositories(self, source: str | None = None) -> list[dict[str, str]]:
        """監視対象リポジトリのリストを取得する

        PostgreSQLから監視対象リポジトリを取得する。

        Args:
            source: ソースタイプでフィルタ（オプション）。例: "github_actions", "bitrise"

        Returns:
            リポジトリ情報のリスト
            - GitHub/デフォルト: {"owner": str, "repo": str}
            - Bitrise: {"id": int, "repository_name": str, "source_repository_id": str}
        """
        session = self.session_factory()
        try:
            # repository_name形式は"owner/repo"を想定
            if source:
                query = text(
                    """
                    SELECT id, repository_name, source, source_repository_id
                    FROM repositories
                    WHERE active = TRUE AND source = :source
                    """
                )
                result = session.execute(query, {"source": source})
            else:
                query = text(
                    """
                    SELECT id, repository_name, source, source_repository_id
                    FROM repositories
                    WHERE active = TRUE
                    """
                )
                result = session.execute(query)

            repositories = []
            for row in result:
                # ソースタイプで判定（GitHub ActionsとBitriseで異なる構造を返す）
                if row.source == SourceType.GITHUB_ACTIONS:
                    # GitHub形式: owner/repoに分割
                    parts = row.repository_name.split("/", 1)
                    if len(parts) == 2:
                        repositories.append({"owner": parts[0], "repo": parts[1]})
                    else:
                        logger.warning(
                            f"Invalid repository_name format: {row.repository_name}"
                        )
                elif row.source == SourceType.BITRISE:
                    # Bitrise形式: id/repository_name/source_repository_idを返す
                    # source_repository_idはBitriseのapp_slug（UUID）
                    repositories.append({
                        "id": row.id,
                        "repository_name": row.repository_name,
                        "source_repository_id": row.source_repository_id
                    })
                else:
                    # デフォルト: GitHub形式として扱う
                    parts = row.repository_name.split("/", 1)
                    if len(parts) == 2:
                        repositories.append({"owner": parts[0], "repo": parts[1]})
                    else:
                        logger.warning(
                            f"Unknown source type '{row.source}' for repository: {row.repository_name}"
                        )

            source_msg = f" for source '{source}'" if source else ""
            logger.info(f"Retrieved {len(repositories)} active repositories{source_msg}")
            return repositories
        finally:
            session.close()

    def get_latest_run_timestamp(self, owner: str, repo: str) -> Any:
        """指定リポジトリの最新パイプライン実行タイムスタンプを取得する

        Args:
            owner: リポジトリオーナー
            repo: リポジトリ名

        Returns:
            最新の started_at タイムスタンプ。データがない場合はNone
        """
        session = self.session_factory()
        try:
            repository_name = f"{owner}/{repo}"
            query = text(
                """
                SELECT pr.started_at
                FROM pipeline_runs pr
                JOIN repositories r ON pr.repository_id = r.id
                WHERE r.repository_name = :repository_name
                ORDER BY pr.started_at DESC
                LIMIT 1
                """
            )
            result = session.execute(query, {"repository_name": repository_name})
            row = result.fetchone()
            if row and row[0]:
                # PostgreSQL TIMESTAMP列はnaiveなので、UTCとして明示的に設定
                timestamp = row[0].replace(tzinfo=timezone.utc)
                logger.debug(f"Latest run timestamp for {repository_name}: {timestamp}")
                return timestamp
            else:
                logger.debug(f"No runs found for {repository_name} (initial fetch)")
                return None
        finally:
            session.close()

    def get_oldest_run_timestamp(self, source: str | None = None) -> Any:
        """指定ソースの最も古いパイプライン実行タイムスタンプを取得する

        サンプリングではなく、SQLで全リポジトリの最小値を直接取得する。
        期間バッチング用の基準日時として使用。

        Args:
            source: ソースタイプでフィルタ（オプション）。例: "github_actions", "bitrise"

        Returns:
            最も古い started_at タイムスタンプ。データがない場合はNone
        """
        session = self.session_factory()
        try:
            if source:
                query = text(
                    """
                    SELECT MIN(pr.started_at)
                    FROM pipeline_runs pr
                    JOIN repositories r ON pr.repository_id = r.id
                    WHERE r.active = TRUE AND r.source = :source
                    """
                )
                result = session.execute(query, {"source": source})
            else:
                query = text(
                    """
                    SELECT MIN(pr.started_at)
                    FROM pipeline_runs pr
                    JOIN repositories r ON pr.repository_id = r.id
                    WHERE r.active = TRUE
                    """
                )
                result = session.execute(query)

            row = result.fetchone()
            if row and row[0]:
                # PostgreSQL TIMESTAMP列はnaiveなので、UTCとして明示的に設定
                timestamp = row[0].replace(tzinfo=timezone.utc)
                logger.debug(f"Oldest run timestamp for source '{source}': {timestamp}")
                return timestamp
            else:
                logger.debug(f"No runs found for source '{source}' (initial fetch)")
                return None
        finally:
            session.close()

    def upsert_pipeline_runs(self, runs: list[dict[str, Any]]) -> None:
        """pipeline_runsテーブルにデータをUPSERTする

        Args:
            runs: ワークフロー実行データのリスト
                  (repository_owner, repository_nameを含む)
        """
        if not runs:
            return

        session = self.session_factory()
        try:
            # 全てのrepository_nameを抽出（重複排除）
            repository_names = list(
                {f"{run['repository_owner']}/{run['repository_name']}" for run in runs}
            )

            # 一度のクエリで全てのrepository_idを取得（N+1問題の解決）
            repo_cache: dict[str, int] = {}
            if repository_names:
                placeholders = ", ".join(
                    [f":repo_{i}" for i in range(len(repository_names))]
                )
                repo_query = text(
                    f"""
                    SELECT repository_name, id FROM repositories
                    WHERE repository_name IN ({placeholders})
                    """
                )
                params = {f"repo_{i}": name for i, name in enumerate(repository_names)}
                result = session.execute(repo_query, params)
                repo_cache = {row[0]: row[1] for row in result}

            # スキップされたrun数をカウント
            skipped_count = 0

            for run in runs:
                repository_name = f"{run['repository_owner']}/{run['repository_name']}"
                repository_id = repo_cache.get(repository_name)

                if repository_id is None:
                    logger.warning(f"Repository {repository_name} not found, skipping")
                    skipped_count += 1
                    continue

                # repository_idを追加してINSERT
                query = text(
                    """
                    INSERT INTO pipeline_runs (
                        source_run_id, source, pipeline_name, status,
                        trigger_event, repository_id, branch_name, commit_sha,
                        started_at, completed_at, duration_ms, url
                    )
                    VALUES (
                        :source_run_id, :source, :pipeline_name, :status,
                        :trigger_event, :repository_id, :branch_name, :commit_sha,
                        :started_at, :completed_at, :duration_ms, :url
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
                session.execute(
                    query,
                    {
                        "source_run_id": run["source_run_id"],
                        "source": run["source"],
                        "pipeline_name": run["pipeline_name"],
                        "status": run["status"],
                        "trigger_event": run["trigger_event"],
                        "repository_id": repository_id,
                        "branch_name": run.get("branch_name"),
                        "commit_sha": run.get("commit_sha"),
                        "started_at": run.get("started_at"),
                        "completed_at": run.get("completed_at"),
                        "duration_ms": run.get("duration_ms"),
                        "url": run.get("url"),
                    },
                )

            # エラーログ出力
            if skipped_count > 0:
                logger.error(
                    f"Skipped {skipped_count} runs due to missing repositories"
                )

            session.commit()
            logger.info(
                f"Upserted {len(runs) - skipped_count} pipeline runs "
                f"({skipped_count} skipped)"
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> None:
        """jobsテーブルにデータをUPSERTする

        Args:
            jobs: ジョブデータのリスト
                  (source_run_id, repository_owner, repository_nameを含む)
        """
        if not jobs:
            return

        session = self.session_factory()
        try:
            # 全てのsource_run_idを抽出（重複排除）
            source_run_ids = list({job["source_run_id"] for job in jobs})

            # 一度のクエリで全てのrun_idを取得（N+1問題の解決）
            run_cache: dict[tuple[str, str, str], int] = {}
            if source_run_ids:
                placeholders = ", ".join(
                    [f":run_{i}" for i in range(len(source_run_ids))]
                )
                run_query = text(
                    f"""
                    SELECT pr.source_run_id, pr.source, r.repository_name, pr.id
                    FROM pipeline_runs pr
                    JOIN repositories r ON pr.repository_id = r.id
                    WHERE pr.source_run_id IN ({placeholders})
                    """
                )
                params = {f"run_{i}": run_id for i, run_id in enumerate(source_run_ids)}
                result = session.execute(run_query, params)
                # キー: (source_run_id, source, repository_name), 値: run_id
                for row in result:
                    run_cache[(row[0], row[1], row[2])] = row[3]

            # スキップされたjob数をカウント
            skipped_count = 0

            for job in jobs:
                repository_name = f"{job['repository_owner']}/{job['repository_name']}"
                cache_key = (
                    job["source_run_id"],
                    job["source"],
                    repository_name,
                )
                run_id = run_cache.get(cache_key)

                if run_id is None:
                    logger.warning(
                        f"Pipeline run not found for job {job['source_job_id']} "
                        f"(run_id={job['source_run_id']}, "
                        f"repo={repository_name}), skipping"
                    )
                    skipped_count += 1
                    continue

                # run_idを使用してINSERT
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
                session.execute(
                    query,
                    {
                        "run_id": run_id,
                        "source_job_id": job["source_job_id"],
                        "job_name": job["job_name"],
                        "status": job["status"],
                        "started_at": job.get("started_at"),
                        "completed_at": job.get("completed_at"),
                        "duration_ms": job.get("duration_ms"),
                    },
                )

            # エラーログ出力
            if skipped_count > 0:
                logger.error(
                    f"Skipped {skipped_count} jobs due to missing pipeline runs"
                )

            session.commit()
            logger.info(
                f"Upserted {len(jobs) - skipped_count} jobs ({skipped_count} skipped)"
            )
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
