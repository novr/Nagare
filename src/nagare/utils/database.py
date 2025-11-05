"""データベースユーティリティ

PostgreSQL接続とデータアクセス機能を提供する。

ADR-002: Connection管理アーキテクチャに準拠し、
DatabaseConnectionから接続情報を受け取る。
"""

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from nagare.constants import SourceType


def _json_serializer(obj: Any) -> str:
    """JSON serializer for objects not serializable by default json encoder

    Args:
        obj: Object to serialize

    Returns:
        ISO format string for datetime objects

    Raises:
        TypeError: If object is not serializable
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")
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

    # 一時テーブル関連メソッド（ADR-006: XCom削減のため）

    def insert_temp_workflow_runs(
        self, runs: list[dict[str, Any]], task_id: str, run_id: str
    ) -> None:
        """一時テーブルにワークフロー実行データを保存する

        Args:
            runs: ワークフロー実行データのリスト（GitHub/Bitrise APIレスポンス）
            task_id: バッチタスクID（例: fetch_github_batch_0）
            run_id: DAG run ID（Airflow生成、例: manual__2025-11-04T10:00:00）
        """
        if not runs:
            return

        session = self.session_factory()
        try:
            for run in runs:
                # source_run_idとsourceを抽出
                source_run_id = str(run.get("id", run.get("slug")))  # GitHub: id, Bitrise: slug
                source = run.get("_source", "github_actions")

                query = text(
                    """
                    INSERT INTO temp_workflow_runs (
                        task_id, run_id, source_run_id, source, data
                    )
                    VALUES (
                        :task_id, :run_id, :source_run_id, :source, :data
                    )
                    ON CONFLICT (task_id, run_id, source_run_id) DO UPDATE SET
                        data = EXCLUDED.data,
                        created_at = NOW()
                    """
                )
                session.execute(
                    query,
                    {
                        "task_id": task_id,
                        "run_id": run_id,
                        "source_run_id": source_run_id,
                        "source": source,
                        "data": json.dumps(run, default=_json_serializer),
                    },
                )

            session.commit()
            logger.info(
                f"Inserted {len(runs)} workflow runs to temp table "
                f"(task_id={task_id}, run_id={run_id})"
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_temp_workflow_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから全ワークフロー実行データを取得する

        Args:
            run_id: DAG run ID

        Returns:
            ワークフロー実行データのリスト
        """
        session = self.session_factory()
        try:
            query = text(
                """
                SELECT data
                FROM temp_workflow_runs
                WHERE run_id = :run_id
                ORDER BY created_at
                """
            )
            result = session.execute(query, {"run_id": run_id})

            runs = []
            for row in result:
                # JSONBカラムは既にPython辞書として返される
                runs.append(row[0])

            logger.info(f"Retrieved {len(runs)} workflow runs from temp table (run_id={run_id})")
            return runs
        finally:
            session.close()

    def insert_temp_transformed_runs(
        self, runs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルに変換済みデータを保存する

        Args:
            runs: 変換済みワークフロー実行データのリスト（汎用データモデル形式）
            run_id: DAG run ID
        """
        if not runs:
            return

        session = self.session_factory()
        try:
            for run in runs:
                query = text(
                    """
                    INSERT INTO temp_transformed_runs (
                        run_id, source_run_id, source, data
                    )
                    VALUES (
                        :run_id, :source_run_id, :source, :data
                    )
                    ON CONFLICT (run_id, source_run_id) DO UPDATE SET
                        data = EXCLUDED.data,
                        created_at = NOW()
                    """
                )
                session.execute(
                    query,
                    {
                        "run_id": run_id,
                        "source_run_id": run["source_run_id"],
                        "source": run["source"],
                        "data": json.dumps(run, default=_json_serializer),
                    },
                )

            session.commit()
            logger.info(
                f"Inserted {len(runs)} transformed runs to temp table (run_id={run_id})"
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_temp_transformed_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから変換済みデータを取得する

        Args:
            run_id: DAG run ID

        Returns:
            変換済みワークフロー実行データのリスト
        """
        session = self.session_factory()
        try:
            query = text(
                """
                SELECT data
                FROM temp_transformed_runs
                WHERE run_id = :run_id
                ORDER BY created_at
                """
            )
            result = session.execute(query, {"run_id": run_id})

            runs = []
            for row in result:
                # JSONBカラムは既にPython辞書として返される
                runs.append(row[0])

            logger.info(f"Retrieved {len(runs)} transformed runs from temp table (run_id={run_id})")
            return runs
        finally:
            session.close()

    def insert_temp_workflow_jobs(
        self, jobs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルにジョブデータを保存する

        Args:
            jobs: ジョブデータのリスト
            run_id: DAG run ID
        """
        if not jobs:
            return

        session = self.session_factory()
        try:
            for job in jobs:
                query = text(
                    """
                    INSERT INTO temp_workflow_jobs (
                        run_id, source_job_id, source_run_id, data
                    )
                    VALUES (
                        :run_id, :source_job_id, :source_run_id, :data
                    )
                    ON CONFLICT (run_id, source_job_id) DO UPDATE SET
                        data = EXCLUDED.data,
                        created_at = NOW()
                    """
                )
                session.execute(
                    query,
                    {
                        "run_id": run_id,
                        "source_job_id": job["source_job_id"],
                        "source_run_id": job["source_run_id"],
                        "data": json.dumps(job, default=_json_serializer),
                    },
                )

            session.commit()
            logger.info(
                f"Inserted {len(jobs)} workflow jobs to temp table (run_id={run_id})"
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_temp_workflow_jobs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルからジョブデータを取得する

        Args:
            run_id: DAG run ID

        Returns:
            ジョブデータのリスト
        """
        session = self.session_factory()
        try:
            query = text(
                """
                SELECT data
                FROM temp_workflow_jobs
                WHERE run_id = :run_id
                ORDER BY created_at
                """
            )
            result = session.execute(query, {"run_id": run_id})

            jobs = []
            for row in result:
                # JSONBカラムは既にPython辞書として返される
                jobs.append(row[0])

            logger.info(f"Retrieved {len(jobs)} workflow jobs from temp table (run_id={run_id})")
            return jobs
        finally:
            session.close()

    def move_temp_to_production(self, run_id: str) -> None:
        """一時テーブルから本番テーブルへデータを移動する

        トランザクション内で呼び出すこと。
        temp_transformed_runs → pipeline_runs
        temp_workflow_jobs → jobs

        Args:
            run_id: DAG run ID
        """
        # 一時テーブルからデータを取得
        transformed_runs = self.get_temp_transformed_runs(run_id)
        transformed_jobs = self.get_temp_workflow_jobs(run_id)

        # 本番テーブルにUPSERT
        if transformed_runs:
            self.upsert_pipeline_runs(transformed_runs)

        if transformed_jobs:
            self.upsert_jobs(transformed_jobs)

        logger.info(
            f"Moved {len(transformed_runs)} runs and {len(transformed_jobs)} jobs "
            f"from temp to production tables (run_id={run_id})"
        )

    def cleanup_temp_tables(self, run_id: str | None = None, days: int = 7) -> int:
        """一時テーブルをクリーンアップする

        Args:
            run_id: 特定のDAG runのデータを削除（Noneの場合は古いデータを削除）
            days: 保持日数（run_idがNoneの場合のみ有効）

        Returns:
            削除されたレコード数の合計
        """
        session = self.session_factory()
        try:
            deleted_count = 0

            if run_id:
                # 特定のDAG runのデータを削除
                for table in ["temp_workflow_runs", "temp_transformed_runs", "temp_workflow_jobs"]:
                    query = text(f"DELETE FROM {table} WHERE run_id = :run_id")
                    result = session.execute(query, {"run_id": run_id})
                    deleted_count += result.rowcount

                logger.info(
                    f"Deleted {deleted_count} records from temp tables (run_id={run_id})"
                )
            else:
                # 古いデータを削除
                for table in ["temp_workflow_runs", "temp_transformed_runs", "temp_workflow_jobs"]:
                    query = text(
                        f"""
                        DELETE FROM {table}
                        WHERE created_at < NOW() - INTERVAL '{days} days'
                        """
                    )
                    result = session.execute(query)
                    deleted_count += result.rowcount

                logger.info(
                    f"Deleted {deleted_count} old records from temp tables (older than {days} days)"
                )

            session.commit()
            return deleted_count
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
