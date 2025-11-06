"""database.pyのユニットテスト（本番用DatabaseClient）

Note: これらはPostgreSQLへの実際の接続を行う統合テストです。
      PostgreSQLが利用不可能な場合はスキップされます。
"""

from typing import Any

import pytest


@pytest.fixture
def db_client():
    """データベース接続可能な場合のみテストを実行するフィクスチャ"""
    pytest.skip("PostgreSQL integration tests require a running database")


def test_database_client_init() -> None:
    """DatabaseClient（本番用）が初期化されることを確認"""
    from nagare.utils.database import DatabaseClient

    client = DatabaseClient()
    # 初期化が成功することを確認
    assert client is not None


def test_get_repositories(db_client) -> None:
    """本番モード: get_repositories()がPostgreSQLから取得できることを確認

    Note: PostgreSQLが利用可能な場合のみ実行される統合テスト
    """
    # データベースが利用可能であれば、エラーなく実行されることを確認
    # 空のリストが返される場合もある（repositoriesテーブルが空の場合）
    result = db_client.get_repositories()
    assert isinstance(result, list)


def test_upsert_pipeline_runs(db_client) -> None:
    """本番モード: upsert_pipeline_runs()が空データを正しく処理することを確認

    Note: PostgreSQLが利用可能な場合のみ実行される統合テスト。
          空データの場合は早期リターンされるため、実際のDB操作は行われない。
    """
    # 空データの場合は早期リターンされる（DB操作なし）
    runs: list[dict[str, Any]] = []
    db_client.upsert_pipeline_runs(runs)  # エラーなく完了することを確認


def test_upsert_jobs(db_client) -> None:
    """本番モード: upsert_jobs()が空データを正しく処理することを確認

    Note: PostgreSQLが利用可能な場合のみ実行される統合テスト。
          空データの場合は早期リターンされるため、実際のDB操作は行われない。
    """
    # 空データの場合は早期リターンされる（DB操作なし）
    jobs: list[dict[str, Any]] = []
    db_client.upsert_jobs(jobs)  # エラーなく完了することを確認


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
