# 05. 汎用データモデル

本システムで利用するデータベースのテーブル設計。特定のCI/CDツールに依存しない汎用的なカラム名で定義する。

## 1. `pipeline_runs` テーブル

パイプライン全体の実行1回分に相当するデータを格納する。

| 汎用項目名 | データ型 | 説明 |
| :--- | :--- | :--- |
| `id` | `BIGINT` | 主キー。システム全体で一意なID。 |
| `source_run_id` | `VARCHAR(255)` | CI/CDツール側での実行ID。`source`と合わせて複合ユニーク。 |
| `source` | `VARCHAR(50)` | データソース名（例：`github_actions`, `gitlab_ci`）。 |
| `pipeline_name` | `VARCHAR(255)` | 実行されたパイプライン/ワークフローの名称。 |
| `status` | `VARCHAR(50)` | 実行の最終結果 (`SUCCESS`, `FAILURE`, `CANCELLED`等)。 |
| `trigger_event` | `VARCHAR(50)` | 実行のきっかけ (`PUSH`, `PULL_REQUEST`等)。 |
| `repository_id` | `BIGINT` | `repositories`テーブルへの外部キー。 |
| `branch_name` | `VARCHAR(255)` | 実行対象のブランチ名。 |
| `commit_sha` | `VARCHAR(255)` | 実行対象のコミットハッシュ。 |
| `started_at` | `TIMESTAMP` | 開始日時。 |
| `completed_at` | `TIMESTAMP` | 完了日時。 |
| `duration_ms` | `BIGINT` | 実行時間（ミリ秒）。 |
| `url` | `TEXT` | CI/CDツール上の実行結果画面へのURL。 |
| `created_at` | `TIMESTAMP` | このレコードが作成された日時。 |
| `updated_at` | `TIMESTAMP` | このレコードが更新された日時。 |

## 2. `jobs` テーブル

パイプラインを構成する個別のジョブ実行データを格納する。ボトルネック分析に利用。

| 汎用項目名 | データ型 | 説明 |
| :--- | :--- | :--- |
| `id` | `BIGINT` | 主キー。 |
| `run_id` | `BIGINT` | `pipeline_runs`テーブルへの外部キー。 |
| `source_job_id` | `VARCHAR(255)` | CI/CDツール側でのジョブID。 |
| `job_name` | `VARCHAR(255)` | ジョブの名称 (`build`, `unit-test`等)。 |
| `status` | `VARCHAR(50)` | ジョブの最終結果 (`SUCCESS`, `FAILURE`等)。 |
| `started_at` | `TIMESTAMP` | 開始日時。 |
| `completed_at` | `TIMESTAMP` | 完了日時。 |
| `duration_ms` | `BIGINT` | 実行時間（ミリ秒）。 |
| `created_at` | `TIMESTAMP` | このレコードが作成された日時。 |
| `updated_at` | `TIMESTAMP` | このレコードが更新された日時。 |

## 3. `repositories` テーブル

分析対象のリポジトリ情報を管理する。

| 汎用項目名 | データ型 | 説明 |
| :--- | :--- | :--- |
| `id` | `BIGINT` | 主キー。 |
| `source_repository_id`|`VARCHAR(255)` | CI/CDツール側でのリポジトリID。 |
| `source` | `VARCHAR(50)` | データソース名。 |
| `repository_name`| `VARCHAR(255)` | リポジトリ名（例：`org/repo`）。 |
| `project_id` | `BIGINT` | `projects`テーブルへの外部キー（NULL許容）。 |
| `created_at` | `TIMESTAMP` | このレコードが作成された日時。 |
| `updated_at` | `TIMESTAMP` | このレコードが更新された日時。 |

## 4. `projects` テーブル

リポジトリをグルーピングするためのプロジェクト情報を管理する。

| 汎用項目名 | データ型 | 説明 |
| :--- | :--- | :--- |
| `id` | `BIGINT` | 主キー。 |
| `project_name` | `VARCHAR(255)` | プロジェクト名。 |
| `created_at` | `TIMESTAMP` | このレコードが作成された日時。 |
| `updated_at` | `TIMESTAMP` | このレコードが更新された日時。 |
