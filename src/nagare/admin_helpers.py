"""Streamlit管理画面のヘルパー関数

リソース管理、入力検証などの汎用的なユーティリティ関数を提供する。
"""

import os
from contextlib import contextmanager


@contextmanager
def temporary_env_var(key: str, value: str):
    """環境変数を一時的に設定するコンテキストマネージャー

    Args:
        key: 環境変数名
        value: 設定する値

    Yields:
        None

    Note:
        終了時に元の値に復元する。元の値がない場合は削除する。

    Example:
        >>> with temporary_env_var("MY_VAR", "test_value"):
        ...     print(os.environ["MY_VAR"])  # "test_value"
        >>> # MY_VARは元の値に戻る（または削除される）
    """
    original = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if original is not None:
            os.environ[key] = original
        else:
            os.environ.pop(key, None)


def validate_repository_name(repo_name: str) -> tuple[bool, str]:
    """リポジトリ名の形式を検証する

    Args:
        repo_name: リポジトリ名（owner/repo形式）

    Returns:
        (is_valid, error_message): 検証結果とエラーメッセージのタプル

    Example:
        >>> validate_repository_name("owner/repo")
        (True, "")
        >>> validate_repository_name("invalid")
        (False, "リポジトリ名は 'owner/repo' 形式で入力してください")
    """
    if not repo_name or not repo_name.strip():
        return False, "リポジトリ名を入力してください"

    repo_name = repo_name.strip()

    if "/" not in repo_name:
        return False, "リポジトリ名は 'owner/repo' 形式で入力してください"

    parts = repo_name.split("/")
    if len(parts) != 2:
        return False, "リポジトリ名は 'owner/repo' 形式で入力してください"

    owner, repo = parts
    if not owner or not repo:
        return False, "所有者名とリポジトリ名の両方を入力してください"

    # 不正な文字チェック（GitHubの命名規則に基づく）
    invalid_chars = set('<>:"|?*\\')
    if any(c in invalid_chars for c in repo_name):
        return (
            False,
            f"リポジトリ名に使用できない文字が含まれています: {', '.join(invalid_chars)}",
        )

    return True, ""


def validate_connection_id(conn_id: str) -> tuple[bool, str]:
    """接続IDの形式を検証する

    Args:
        conn_id: 接続ID

    Returns:
        (is_valid, error_message): 検証結果とエラーメッセージのタプル

    Example:
        >>> validate_connection_id("github_default")
        (True, "")
        >>> validate_connection_id("123invalid")
        (False, "接続IDは英字で始める必要があります")
    """
    if not conn_id or not conn_id.strip():
        return False, "接続IDを入力してください"

    conn_id = conn_id.strip()

    # 英数字、アンダースコア、ハイフンのみ許可
    if not all(c.isalnum() or c in ("_", "-") for c in conn_id):
        return False, "接続IDは英数字、アンダースコア、ハイフンのみ使用できます"

    # 先頭は英字のみ
    if not conn_id[0].isalpha():
        return False, "接続IDは英字で始める必要があります"

    # 長さチェック
    if len(conn_id) > 64:
        return False, "接続IDは64文字以内にしてください"

    return True, ""
