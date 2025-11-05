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

        # 一時テーブルのインメモリストレージ
        self._temp_workflow_runs: dict[str, list[dict[str, Any]]] = {}
        self._temp_transformed_runs: dict[str, list[dict[str, Any]]] = {}
        self._temp_workflow_jobs: dict[str, list[dict[str, Any]]] = {}

    def get_repositories(self, source: str | None = None) -> list[dict[str, str]]:
        """監視対象リポジトリのリストを取得する（モック実装）

        環境変数REPOSITORIES_JSONから読み込む。

        Args:
            source: ソースタイプでフィルタ（オプション）。モック実装ではフィルタリングは行わない。

        Returns:
            リポジトリ情報のリスト（owner, repoを含む辞書）
        """
        # 環境変数から読み込み (JSON形式)
        repositories_json = os.getenv("REPOSITORIES_JSON")
        if repositories_json:
            repositories = json.loads(repositories_json)
            source_msg = f" for source '{source}'" if source else ""
            logger.info(
                f"[MOCK] Loaded {len(repositories)} repositories from REPOSITORIES_JSON{source_msg}"
            )
            return repositories

        # デフォルト（空リスト）
        logger.warning("[MOCK] No repositories configured. Set REPOSITORIES_JSON")
        return []

    def get_latest_run_timestamp(self, owner: str, repo: str) -> Any:
        """指定リポジトリの最新パイプライン実行タイムスタンプを取得する（モック実装）

        モック環境ではデータが保存されないため、常にNoneを返す（初回取得として扱う）。

        Args:
            owner: リポジトリオーナー
            repo: リポジトリ名

        Returns:
            常にNone（初回取得をシミュレート）
        """
        logger.debug(
            f"[MOCK] get_latest_run_timestamp called for {owner}/{repo} - returning None (initial fetch)"
        )
        return None

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

    def get_oldest_run_timestamp(self, source: str | None = None) -> Any:
        """指定ソースの最も古いパイプライン実行タイムスタンプを取得する（モック実装）

        Args:
            source: ソースタイプでフィルタ（オプション）

        Returns:
            常にNone（初回取得をシミュレート）
        """
        logger.debug(f"[MOCK] get_oldest_run_timestamp called for source '{source}' - returning None")
        return None

    # 一時テーブル関連メソッド（ADR-006: XCom削減のため）

    def insert_temp_workflow_runs(
        self, runs: list[dict[str, Any]], task_id: str, run_id: str
    ) -> None:
        """一時テーブルにワークフロー実行データを保存する（モック実装）

        Args:
            runs: ワークフロー実行データのリスト
            task_id: バッチタスクID
            run_id: DAG run ID
        """
        if not runs:
            return

        key = f"{run_id}:{task_id}"
        if key not in self._temp_workflow_runs:
            self._temp_workflow_runs[key] = []

        self._temp_workflow_runs[key].extend(runs)
        logger.info(
            f"[MOCK] Inserted {len(runs)} workflow runs to temp storage "
            f"(task_id={task_id}, run_id={run_id})"
        )

    def get_temp_workflow_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから全ワークフロー実行データを取得する（モック実装）

        Args:
            run_id: DAG run ID

        Returns:
            ワークフロー実行データのリスト
        """
        # run_idで始まる全てのキーからデータを収集
        runs = []
        for key, data in self._temp_workflow_runs.items():
            if key.startswith(f"{run_id}:"):
                runs.extend(data)

        logger.info(f"[MOCK] Retrieved {len(runs)} workflow runs from temp storage (run_id={run_id})")
        return runs

    def insert_temp_transformed_runs(
        self, runs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルに変換済みデータを保存する（モック実装）

        Args:
            runs: 変換済みワークフロー実行データのリスト
            run_id: DAG run ID
        """
        if not runs:
            return

        if run_id not in self._temp_transformed_runs:
            self._temp_transformed_runs[run_id] = []

        self._temp_transformed_runs[run_id].extend(runs)
        logger.info(
            f"[MOCK] Inserted {len(runs)} transformed runs to temp storage (run_id={run_id})"
        )

    def get_temp_transformed_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから変換済みデータを取得する（モック実装）

        Args:
            run_id: DAG run ID

        Returns:
            変換済みワークフロー実行データのリスト
        """
        runs = self._temp_transformed_runs.get(run_id, [])
        logger.info(f"[MOCK] Retrieved {len(runs)} transformed runs from temp storage (run_id={run_id})")
        return runs

    def insert_temp_workflow_jobs(
        self, jobs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルにジョブデータを保存する（モック実装）

        Args:
            jobs: ジョブデータのリスト
            run_id: DAG run ID
        """
        if not jobs:
            return

        if run_id not in self._temp_workflow_jobs:
            self._temp_workflow_jobs[run_id] = []

        self._temp_workflow_jobs[run_id].extend(jobs)
        logger.info(
            f"[MOCK] Inserted {len(jobs)} workflow jobs to temp storage (run_id={run_id})"
        )

    def get_temp_workflow_jobs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルからジョブデータを取得する（モック実装）

        Args:
            run_id: DAG run ID

        Returns:
            ジョブデータのリスト
        """
        jobs = self._temp_workflow_jobs.get(run_id, [])
        logger.info(f"[MOCK] Retrieved {len(jobs)} workflow jobs from temp storage (run_id={run_id})")
        return jobs

    def move_temp_to_production(self, run_id: str) -> None:
        """一時テーブルから本番テーブルへデータを移動する（モック実装）

        Args:
            run_id: DAG run ID
        """
        transformed_runs = self.get_temp_transformed_runs(run_id)
        transformed_jobs = self.get_temp_workflow_jobs(run_id)

        if transformed_runs:
            self.upsert_pipeline_runs(transformed_runs)

        if transformed_jobs:
            self.upsert_jobs(transformed_jobs)

        logger.info(
            f"[MOCK] Moved {len(transformed_runs)} runs and {len(transformed_jobs)} jobs "
            f"from temp to production (run_id={run_id})"
        )

    def cleanup_temp_tables(self, run_id: str | None = None, days: int = 7) -> int:
        """一時テーブルをクリーンアップする（モック実装）

        Args:
            run_id: 特定のDAG runのデータを削除
            days: 保持日数（モック実装では未使用）

        Returns:
            削除されたレコード数の合計
        """
        deleted_count = 0

        if run_id:
            # 特定のDAG runのデータを削除
            for key in list(self._temp_workflow_runs.keys()):
                if key.startswith(f"{run_id}:"):
                    deleted_count += len(self._temp_workflow_runs[key])
                    del self._temp_workflow_runs[key]

            if run_id in self._temp_transformed_runs:
                deleted_count += len(self._temp_transformed_runs[run_id])
                del self._temp_transformed_runs[run_id]

            if run_id in self._temp_workflow_jobs:
                deleted_count += len(self._temp_workflow_jobs[run_id])
                del self._temp_workflow_jobs[run_id]

            logger.info(
                f"[MOCK] Deleted {deleted_count} records from temp storage (run_id={run_id})"
            )
        else:
            # 全データを削除
            for storage in [self._temp_workflow_runs, self._temp_transformed_runs, self._temp_workflow_jobs]:
                for data_list in storage.values():
                    deleted_count += len(data_list) if isinstance(data_list, list) else 1
                storage.clear()

            logger.info(
                f"[MOCK] Deleted {deleted_count} old records from temp storage (older than {days} days)"
            )

        return deleted_count

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
