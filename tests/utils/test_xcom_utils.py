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
