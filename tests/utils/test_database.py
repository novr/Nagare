"""database.pyのユニットテスト（本番用DatabaseClient）"""

from typing import Any

import pytest


def test_database_client_init() -> None:
    """DatabaseClient（本番用）が初期化されることを確認"""
    from nagare.utils.database import DatabaseClient

    client = DatabaseClient()
    # 初期化が成功することを確認
    assert client is not None


def test_get_repositories_not_implemented() -> None:
    """本番モード: PostgreSQL実装が未完了のためNotImplementedErrorが発生"""
    from nagare.utils.database import DatabaseClient

    client = DatabaseClient()

    with pytest.raises(NotImplementedError, match="PostgreSQL repository fetching"):
        client.get_repositories()


def test_upsert_pipeline_runs_not_implemented() -> None:
    """本番モード: PostgreSQL実装が未完了のためNotImplementedErrorが発生"""
    from nagare.utils.database import DatabaseClient

    client = DatabaseClient()

    runs: list[dict[str, Any]] = [{"source_run_id": "123", "status": "SUCCESS"}]

    with pytest.raises(NotImplementedError, match="PostgreSQL upsert"):
        client.upsert_pipeline_runs(runs)


def test_upsert_jobs_not_implemented() -> None:
    """本番モード: PostgreSQL実装が未完了のためNotImplementedErrorが発生"""
    from nagare.utils.database import DatabaseClient

    client = DatabaseClient()

    jobs: list[dict[str, Any]] = [{"source_job_id": "789", "status": "SUCCESS"}]

    with pytest.raises(NotImplementedError, match="PostgreSQL upsert for jobs"):
        client.upsert_jobs(jobs)


def test_close() -> None:
    """close()が正常に実行されることを確認"""
    from nagare.utils.database import DatabaseClient

    client = DatabaseClient()

    # エラーなく実行されることを確認（TODO: 実際の接続プールクローズは未実装）
    client.close()


def test_context_manager() -> None:
    """Context managerとして動作することを確認"""
    from nagare.utils.database import DatabaseClient

    with DatabaseClient() as client:
        assert client is not None

    # with文を抜けた後もエラーが発生しないことを確認
