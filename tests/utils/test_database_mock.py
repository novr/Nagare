"""database_mock.pyのユニットテスト（開発用MockDatabaseClient）"""

import json
from typing import Any

import pytest


def test_mock_database_client_init() -> None:
    """MockDatabaseClientが初期化されることを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()
    assert client is not None


def test_get_repositories_from_env_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数(JSON)からリポジトリを取得"""
    from nagare.utils.database_mock import MockDatabaseClient

    repositories_json = json.dumps(
        [
            {"owner": "env-org", "repo": "env-repo1"},
            {"owner": "env-org", "repo": "env-repo2"},
        ]
    )

    # 環境変数設定
    monkeypatch.setenv("REPOSITORIES_JSON", repositories_json)

    client = MockDatabaseClient()
    repositories = client.get_repositories()

    assert len(repositories) == 2
    assert repositories[0]["owner"] == "env-org"
    assert repositories[0]["repo"] == "env-repo1"


def test_get_repositories_fallback_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """設定なしの場合は空リストを返す"""
    from nagare.utils.database_mock import MockDatabaseClient

    # 環境変数クリア
    monkeypatch.delenv("REPOSITORIES_JSON", raising=False)

    client = MockDatabaseClient()
    repositories = client.get_repositories()

    assert repositories == []


def test_upsert_pipeline_runs() -> None:
    """upsert_pipeline_runs()がログ出力のみ行うことを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()

    runs: list[dict[str, Any]] = [
        {
            "source_run_id": "123",
            "repository_owner": "test-org",
            "repository_name": "test-repo",
            "status": "SUCCESS",
        },
        {
            "source_run_id": "456",
            "repository_owner": "test-org",
            "repository_name": "test-repo2",
            "status": "FAILURE",
        },
    ]

    # エラーなく実行されることを確認（ログ出力のみ）
    client.upsert_pipeline_runs(runs)


def test_upsert_jobs() -> None:
    """upsert_jobs()がログ出力のみ行うことを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()

    jobs: list[dict[str, Any]] = [
        {
            "source_job_id": "789",
            "source_run_id": "123",
            "repository_owner": "test-org",
            "repository_name": "test-repo",
            "job_name": "build",
            "status": "SUCCESS",
        },
        {
            "source_job_id": "790",
            "source_run_id": "456",
            "repository_owner": "test-org",
            "repository_name": "test-repo2",
            "job_name": "test",
            "status": "FAILURE",
        },
    ]

    # エラーなく実行されることを確認（ログ出力のみ）
    client.upsert_jobs(jobs)


def test_close() -> None:
    """close()が正常に実行されることを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()

    # エラーなく実行されることを確認
    client.close()


def test_context_manager() -> None:
    """Context managerとして動作することを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    with MockDatabaseClient() as client:
        assert client is not None

    # with文を抜けた後もエラーが発生しないことを確認


def test_transaction_commit() -> None:
    """トランザクションが正常にコミットされることを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()

    with client.transaction():
        # トランザクション内で操作実行
        client.upsert_pipeline_runs([{"source_run_id": "123", "status": "SUCCESS"}])

    # トランザクションが正常に終了することを確認
    # MockDatabaseClientではログ出力のみで実際のトランザクションは行わない


def test_transaction_rollback_on_exception() -> None:
    """例外発生時にトランザクションがロールバックされることを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()

    with pytest.raises(ValueError, match="Test error"):
        with client.transaction():
            # トランザクション内で例外を発生させる
            raise ValueError("Test error")

    # 例外が正しく伝播することを確認


def test_transaction_with_operations() -> None:
    """トランザクション内で複数の操作が実行できることを確認"""
    from nagare.utils.database_mock import MockDatabaseClient

    client = MockDatabaseClient()

    runs = [{"source_run_id": "123", "status": "SUCCESS"}]
    jobs = [{"source_job_id": "456", "source_run_id": "123", "status": "SUCCESS"}]

    with client.transaction():
        client.upsert_pipeline_runs(runs)
        client.upsert_jobs(jobs)

    # エラーなく実行されることを確認（ログ出力のみ）
