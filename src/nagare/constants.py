"""定数定義

このモジュールはプロジェクト全体で使用される定数を一元管理する（SSoT）。
"""

from enum import Enum


class XComKeys:
    """Airflow XComで使用するキー名

    タスク間でデータを受け渡す際のキー名を定義。
    """

    REPOSITORIES = "repositories"
    WORKFLOW_RUNS = "workflow_runs"
    WORKFLOW_RUN_JOBS = "workflow_run_jobs"
    TRANSFORMED_RUNS = "transformed_runs"
    TRANSFORMED_JOBS = "transformed_jobs"


class TaskIds:
    """DAGのタスクID

    タスクIDをハードコードせず、定数として管理。
    """

    FETCH_REPOSITORIES = "fetch_repositories"
    FETCH_WORKFLOW_RUNS = "fetch_workflow_runs"
    FETCH_WORKFLOW_RUN_JOBS = "fetch_workflow_run_jobs"
    TRANSFORM_DATA = "transform_data"
    LOAD_TO_DATABASE = "load_to_database"


class PipelineStatus(str, Enum):
    """パイプライン・ジョブのステータス

    汎用データモデルで使用するステータス値。
    str継承により、文字列として直接使用可能。
    """

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"
    IN_PROGRESS = "IN_PROGRESS"
    QUEUED = "QUEUED"
    UNKNOWN = "UNKNOWN"


class GitHubConclusion(str, Enum):
    """GitHub Actionsのconclusion値"""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class GitHubStatus(str, Enum):
    """GitHub Actionsのstatus値"""

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    QUEUED = "queued"


# ステータスマッピング（GitHub Actions -> 汎用モデル）
GITHUB_CONCLUSION_TO_STATUS = {
    GitHubConclusion.SUCCESS: PipelineStatus.SUCCESS,
    GitHubConclusion.FAILURE: PipelineStatus.FAILURE,
    GitHubConclusion.CANCELLED: PipelineStatus.CANCELLED,
    GitHubConclusion.SKIPPED: PipelineStatus.SKIPPED,
    GitHubConclusion.TIMED_OUT: PipelineStatus.TIMEOUT,
}


# データ取得設定
class FetchConfig:
    """データ取得に関する設定値"""

    # GitHub API取得時のルックバック時間（時間）
    LOOKBACK_HOURS = 2

    # GitHub API取得時のデフォルト最大件数
    MAX_WORKFLOW_RUNS = 1000
    MAX_JOBS = 1000


# GitHub API設定
class GitHubConfig:
    """GitHub API関連の設定値"""

    # リトライ設定
    RETRY_TOTAL = 3
    RETRY_BACKOFF_FACTOR = 1.0  # 1秒、2秒、4秒と指数バックオフ
    # 403: Forbidden (レート制限などで使用)
    # 429: Too Many Requests (レート制限超過)
    # 500-504: サーバーエラー
    RETRY_STATUS_FORCELIST = [403, 429, 500, 502, 503, 504]

    # ページネーション
    PER_PAGE = 100

    # レポジトリキャッシュ有効化
    ENABLE_REPO_CACHE = True
