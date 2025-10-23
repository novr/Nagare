"""XCom関連のユーティリティ

Airflow XComのサイズ制限やデータ処理に関するヘルパー関数を提供する。
"""

import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# XComのデフォルトサイズ制限（バイト）
# Airflowのデフォルト設定は約48KB
XCOM_SIZE_LIMIT_BYTES = 48 * 1024  # 48KB

# 警告を出すサイズ閾値（制限の80%）
XCOM_SIZE_WARNING_THRESHOLD = int(XCOM_SIZE_LIMIT_BYTES * 0.8)


def get_data_size(data: Any) -> int:
    """データのシリアライズ後のサイズを取得する

    Args:
        data: サイズを測定するデータ

    Returns:
        シリアライズ後のバイトサイズ
    """
    try:
        # JSONシリアライズしてサイズを測定
        json_str = json.dumps(data, default=str)
        return sys.getsizeof(json_str)
    except Exception as e:
        logger.warning(f"Failed to calculate data size: {e}")
        return 0


def check_xcom_size(
    data: Any, key: str, raise_on_exceed: bool = False
) -> tuple[int, bool]:
    """XComデータのサイズをチェックする

    Args:
        data: チェックするデータ
        key: XComのキー名（ログ出力用）
        raise_on_exceed: サイズ超過時に例外を発生させるかどうか

    Returns:
        (データサイズ, 制限超過フラグ)のタプル

    Raises:
        ValueError: raise_on_exceed=Trueでサイズ制限を超えた場合
    """
    size_bytes = get_data_size(data)
    size_kb = size_bytes / 1024

    # サイズ制限超過チェック
    if size_bytes > XCOM_SIZE_LIMIT_BYTES:
        error_msg = (
            f"XCom data size for '{key}' exceeds limit: "
            f"{size_kb:.1f}KB > {XCOM_SIZE_LIMIT_BYTES/1024:.1f}KB"
        )
        logger.error(error_msg)
        if raise_on_exceed:
            raise ValueError(error_msg)
        return size_bytes, True

    # 警告閾値チェック
    if size_bytes > XCOM_SIZE_WARNING_THRESHOLD:
        logger.warning(
            f"XCom data size for '{key}' is approaching limit: "
            f"{size_kb:.1f}KB (threshold: {XCOM_SIZE_WARNING_THRESHOLD/1024:.1f}KB)"
        )
    else:
        logger.debug(f"XCom data size for '{key}': {size_kb:.1f}KB")

    return size_bytes, False
