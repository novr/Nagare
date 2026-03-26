"""setup_superset_dashboard.py の position_json 構造テスト（Superset 非依存）。"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_SETUP_PATH = Path(__file__).resolve().parents[2] / "scripts" / "setup_superset_dashboard.py"


@pytest.fixture(scope="module")
def setup_mod():
    spec = importlib.util.spec_from_file_location("setup_superset_dashboard", _SETUP_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _slices_by_name(mod) -> dict[str, SimpleNamespace]:
    by: dict[str, SimpleNamespace] = {}
    for i, name in enumerate(mod.MANAGED_CHARTS):
        by[name] = SimpleNamespace(slice_name=name, id=10_000 + i)
    return by


def test_position_json_grid_has_four_rows(setup_mod) -> None:
    pj = json.loads(
        setup_mod._build_cicd_metrics_position_json(_slices_by_name(setup_mod))
    )
    grid_children = pj["GRID_ID"]["children"]
    assert len(grid_children) == 4


def test_position_json_first_tab_stack_has_only_l1_row(setup_mod) -> None:
    pj = json.loads(
        setup_mod._build_cicd_metrics_position_json(_slices_by_name(setup_mod))
    )
    row_tabs_id = pj["GRID_ID"]["children"][0]
    tabs_id = pj[row_tabs_id]["children"][0]
    first_tab_id = pj[tabs_id]["children"][0]
    outer_row_id = pj[first_tab_id]["children"][0]
    stack_col_id = pj[outer_row_id]["children"][0]
    stack = pj[stack_col_id]
    assert len(stack["children"]) == 1
    inner_l1_id = stack["children"][0]
    assert pj[inner_l1_id]["type"] == "ROW"


def test_managed_charts_count_matches_layout_slices(setup_mod) -> None:
    """タブ内 L1×4 + ヘルス2 + L2×6 = 16 チャートが MANAGED に含まれる。"""
    assert len(setup_mod.MANAGED_CHARTS) == 16
    assert len(setup_mod.MAIN_TAB_SPECS) == 4
