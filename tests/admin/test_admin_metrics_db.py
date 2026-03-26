"""admin_metrics_db の純粋ロジック・DB モックテスト。"""

from unittest.mock import MagicMock, patch

import pytest

from nagare import admin_metrics_db as mdb


class TestTagSlugsSet:
    def test_empty_and_none(self) -> None:
        assert mdb._tag_slugs_set(None) == set()
        assert mdb._tag_slugs_set("") == set()
        assert mdb._tag_slugs_set("   ") == set()

    def test_splits_and_trims(self) -> None:
        assert mdb._tag_slugs_set("ios, backend") == {"ios", "backend"}
        assert mdb._tag_slugs_set("a,, b") == {"a", "b"}

    def test_nan_like(self) -> None:
        assert mdb._tag_slugs_set(float("nan")) == set()


class TestListRepoNamesForMetrics:
    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        mdb.list_repo_names_for_metrics.clear()

    @staticmethod
    def _mock_engine(rows: list[tuple]) -> MagicMock:
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        cm = MagicMock()
        cm.__enter__.return_value = mock_conn
        cm.__exit__.return_value = None
        eng = MagicMock()
        eng.connect.return_value = cm
        return eng

    @patch.object(mdb, "get_database_engine")
    def test_no_filters_returns_all(self, mock_ge: MagicMock) -> None:
        mock_ge.return_value = self._mock_engine(
            [
                ("org/a", "Proj1", "ios,backend"),
                ("org/b", None, "ios"),
            ]
        )
        names = mdb.list_repo_names_for_metrics()
        assert names == ["org/a", "org/b"]

    @patch.object(mdb, "get_database_engine")
    def test_filter_project_assigned(self, mock_ge: MagicMock) -> None:
        mock_ge.return_value = self._mock_engine(
            [
                ("org/a", "Proj1", None),
                ("org/b", "Other", "x"),
            ]
        )
        names = mdb.list_repo_names_for_metrics(project_label="Proj1")
        assert names == ["org/a"]

    @patch.object(mdb, "get_database_engine")
    def test_filter_unassigned(self, mock_ge: MagicMock) -> None:
        mock_ge.return_value = self._mock_engine(
            [
                ("org/a", "Proj1", None),
                ("org/b", None, ""),
                ("org/c", "  ", None),
            ]
        )
        names = mdb.list_repo_names_for_metrics(project_label="(未所属)")
        assert names == ["org/b", "org/c"]

    @patch.object(mdb, "get_database_engine")
    def test_tag_or(self, mock_ge: MagicMock) -> None:
        mock_ge.return_value = self._mock_engine(
            [
                ("r1", None, "ios,android"),
                ("r2", None, "backend"),
            ]
        )
        names = mdb.list_repo_names_for_metrics(
            tag_slugs=["ios"], tag_match_all=False
        )
        assert names == ["r1"]

    @patch.object(mdb, "get_database_engine")
    def test_tag_and(self, mock_ge: MagicMock) -> None:
        mock_ge.return_value = self._mock_engine(
            [
                ("r1", None, "ios,backend"),
                ("r2", None, "ios"),
            ]
        )
        names = mdb.list_repo_names_for_metrics(
            tag_slugs=["ios", "backend"], tag_match_all=True
        )
        assert names == ["r1"]
