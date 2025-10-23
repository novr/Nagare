"""日時処理ユーティリティ

日時文字列の変換や実行時間計算の共通ロジックを提供する。
"""

from datetime import datetime


def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    """ISO形式の日時文字列をdatetimeオブジェクトに変換する

    GitHub APIのレスポンスに含まれるISO 8601形式の日時文字列
    （例: "2024-01-01T12:00:00Z"）をdatetimeオブジェクトに変換する。

    Args:
        dt_str: ISO 8601形式の日時文字列（末尾が"Z"のUTC時刻）

    Returns:
        変換されたdatetimeオブジェクト（タイムゾーン情報付き）
        入力がNoneの場合はNoneを返す

    Example:
        >>> parse_iso_datetime("2024-01-01T12:00:00Z")
        datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        >>> parse_iso_datetime(None)
        None
    """
    if dt_str is None:
        return None

    # "Z"を"+00:00"に置換してISO形式としてパース
    # これによりタイムゾーン情報付きのdatetimeオブジェクトが得られる
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def calculate_duration_ms(
    start: datetime | None, end: datetime | None
) -> int | None:
    """開始時刻と終了時刻から実行時間をミリ秒単位で計算する

    Args:
        start: 開始時刻
        end: 終了時刻

    Returns:
        実行時間（ミリ秒）
        いずれかの引数がNoneの場合はNoneを返す

    Example:
        >>> from datetime import datetime, timezone
        >>> start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        >>> end = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        >>> calculate_duration_ms(start, end)
        5000
        >>> calculate_duration_ms(None, end)
        None
    """
    if start is None or end is None:
        return None

    # timedeltaの秒数を取得し、ミリ秒に変換
    return int((end - start).total_seconds() * 1000)
