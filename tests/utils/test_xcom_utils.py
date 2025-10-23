"""xcom_utils.pyのユニットテスト"""

import pytest


def test_get_data_size() -> None:
    """データのシリアライズ後のサイズを取得できることを確認"""
    from nagare.utils.xcom_utils import get_data_size

    # 小さいデータ
    small_data = {"key": "value"}
    size = get_data_size(small_data)
    assert size > 0

    # 大きいデータ
    large_data = [{"id": i, "data": "x" * 1000} for i in range(100)]
    large_size = get_data_size(large_data)
    assert large_size > size


def test_check_xcom_size_normal() -> None:
    """正常なサイズのデータがチェックをパスすることを確認"""
    from nagare.utils.xcom_utils import check_xcom_size

    small_data = [{"id": i} for i in range(10)]
    size, exceeded = check_xcom_size(small_data, "test_key")

    assert size > 0
    assert not exceeded


def test_check_xcom_size_warning() -> None:
    """警告閾値を超えるデータで警告が出ることを確認"""
    from nagare.utils.xcom_utils import check_xcom_size

    # 約40KBのデータ（警告閾値約38KBを超える）
    large_data = [{"id": i, "data": "x" * 1000} for i in range(40)]
    size, exceeded = check_xcom_size(large_data, "test_key")

    assert size > 0
    # 警告は出るが、まだ制限は超えていない
    assert not exceeded


def test_check_xcom_size_exceeded() -> None:
    """制限を超えるデータでフラグが立つことを確認"""
    from nagare.utils.xcom_utils import check_xcom_size

    # 約60KBのデータ（制限48KBを超える）
    huge_data = [{"id": i, "data": "x" * 1000} for i in range(60)]
    size, exceeded = check_xcom_size(huge_data, "test_key", raise_on_exceed=False)

    assert size > 0
    assert exceeded


def test_check_xcom_size_raise_on_exceed() -> None:
    """raise_on_exceed=Trueで制限超過時に例外が発生することを確認"""
    from nagare.utils.xcom_utils import check_xcom_size

    # 約60KBのデータ（制限48KBを超える）
    huge_data = [{"id": i, "data": "x" * 1000} for i in range(60)]

    with pytest.raises(ValueError, match="exceeds limit"):
        check_xcom_size(huge_data, "test_key", raise_on_exceed=True)


def test_split_data_for_xcom_no_split() -> None:
    """小さいデータが分割されないことを確認"""
    from nagare.utils.xcom_utils import split_data_for_xcom

    small_data = [{"id": i} for i in range(10)]
    chunks = split_data_for_xcom(small_data, "test_key")

    assert len(chunks) == 1
    assert chunks[0][0] == "test_key"
    assert chunks[0][1] == small_data


def test_split_data_for_xcom_with_split() -> None:
    """大きいデータが複数のチャンクに分割されることを確認"""
    from nagare.utils.xcom_utils import split_data_for_xcom

    # 約60KBのデータ（複数チャンクに分割される）
    large_data = [{"id": i, "data": "x" * 1000} for i in range(60)]
    chunks = split_data_for_xcom(large_data, "test_key", max_chunk_size=20 * 1024)

    assert len(chunks) > 1
    # すべてのチャンクの合計がオリジナルデータと同じ
    total_items = sum(len(chunk[1]) for chunk in chunks)
    assert total_items == len(large_data)


def test_split_data_for_xcom_empty() -> None:
    """空データの処理を確認"""
    from nagare.utils.xcom_utils import split_data_for_xcom

    empty_data: list[dict[str, str]] = []
    chunks = split_data_for_xcom(empty_data, "test_key")

    assert len(chunks) == 1
    assert chunks[0][0] == "test_key"
    assert chunks[0][1] == []
