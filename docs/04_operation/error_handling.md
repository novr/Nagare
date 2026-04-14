# エラーハンドリングガイド

Nagareのエラーハンドリング機能とトラブルシューティング方法。

## 概要

Nagareは以下の3つの主要なエラーハンドリング機能を実装しています：

1. **GitHub API Rate Limit対策**
2. **自動リトライ処理（指数バックオフ）**
3. **部分的失敗時の継続処理**

## GitHub API Rate Limit対策

### Rate Limit の仕組み

GitHub APIには以下のRate Limitがあります：

| 認証タイプ | Core API | Search API |
|-----------|----------|------------|
| **認証なし** | 60 req/hour | 10 req/min |
| **Personal Access Token** | 5,000 req/hour | 30 req/min |
| **GitHub App** | 5,000 req/hour | 30 req/min |

### 実装されている対策

#### 1. Rate Limit監視

```python
# GitHubClientでrate limitを自動チェック
rate_info = github_client.check_rate_limit()
# {
#   "core": {"limit": 5000, "remaining": 4523, "reset": "2025-10-24T14:00:00Z"},
#   "search": {"limit": 30, "remaining": 25, "reset": "2025-10-24T13:01:00Z"}
# }
```

**自動ログ出力**:
- 正常時: INFO レベルで残数をログ
- 残り10%未満: WARNING レベルでアラート

#### 2. 自動待機

Rate Limitが枯渇した場合、自動的にリセット時刻まで待機します：

```python
# Rate limit超過時の自動処理
if rate_info["core"]["remaining"] < 10:
    logger.warning("Rate limit low, waiting for reset...")
    github_client.wait_for_rate_limit_reset("core")
```

**待機ログ例**:
```
WARNING - Rate limit exceeded for core. Waiting 1247 seconds until reset at 2025-10-24T14:00:00Z
```

#### 3. リクエスト前の事前チェック

各GitHub API呼び出しの前に自動的にrate limitをチェックし、必要に応じて待機します。

## 自動リトライ処理

### リトライ対象のエラー

以下のエラーは自動的にリトライされます：

| エラー | 説明 | リトライ戦略 |
|--------|------|------------|
| **RateLimitExceededException** | Rate limit超過 | リセットまで待機後リトライ |
| **502 Bad Gateway** | 一時的なサーバーエラー | 指数バックオフでリトライ |
| **503 Service Unavailable** | サービス一時停止 | 指数バックオフでリトライ |
| **504 Gateway Timeout** | タイムアウト | 指数バックオフでリトライ |

### 指数バックオフ

リトライ間隔は指数的に増加します：

```
リトライ1回目: 1秒待機 (2^0)
リトライ2回目: 2秒待機 (2^1)
リトライ3回目: 4秒待機 (2^2)
```

**最大リトライ回数**: 3回

### 実装例

```python
retry_count = 0
max_retries = 3

while retry_count <= max_retries:
    try:
        # API呼び出し
        return github_client.get_workflow_runs(owner, repo)
    except GithubException as e:
        if e.status in [502, 503, 504] and retry_count < max_retries:
            wait_time = 2 ** retry_count
            logger.warning(f"Temporary error {e.status}, retrying in {wait_time}s")
            time.sleep(wait_time)
            retry_count += 1
            continue
        raise
```

## 部分的失敗時の継続処理

### 基本方針

複数のリポジトリやワークフロー実行からデータを取得する際、**1つが失敗しても他の処理は継続**します。

### エラー統計情報

各タスクは以下の統計情報を記録します：

```python
{
    "total_items": 10,           # 処理対象の総数
    "successful": 8,             # 成功数
    "failed": 2,                 # 失敗数
    "errors": [                  # 個別エラー詳細
        {
            "item": "owner/repo",
            "error_type": "GithubException",
            "status": 404,
            "message": "Not Found"
        },
        ...
    ]
}
```

### ログ出力例

**処理開始時**:
```
INFO - Fetching workflow runs for owner/repo1...
INFO - Fetched 15 items from owner/repo1
INFO - Fetching workflow runs for owner/repo2...
ERROR - GitHub API error while fetching workflow runs for owner/repo2: Status 404, Message: Not Found
INFO - Fetching workflow runs for owner/repo3...
INFO - Fetched 8 items from owner/repo3
```

**サマリー**:
```
INFO - Fetching workflow runs summary: 2/3 successful (66.7%), 1 failed
WARNING - Fetching workflow runs completed with 1 failures. Check logs for details.
```

### 全失敗時の動作

全てのアイテムで失敗した場合の動作：

- **ワークフロー実行取得**: RuntimeError を投げてタスク失敗
- **ジョブ取得**: エラーログのみ、空リストで継続

```python
# 全失敗時の処理例
if error_stats["successful"] == 0 and error_stats["total_items"] > 0:
    # ワークフロー実行取得の場合
    raise RuntimeError("All repositories failed")

    # ジョブ取得の場合
    logger.error("All workflow runs failed, continuing with empty list")
```

## エラー種別と対処法

### 1. 認証エラー (401 Unauthorized)

**原因**:
- GitHub Tokenが無効または期限切れ
- GitHub Appの設定ミス

**対処法**:
```bash
# .envファイルを確認
cat .env | grep GITHUB

# トークンを再生成
# GitHub → Settings → Developer settings → Personal access tokens
```

**必要な権限**:
- `repo` (プライベートリポジトリの場合)
- `actions:read` (Actions ワークフロー読み取り)

### 2. アクセス拒否 (403 Forbidden)

**原因**:
- Rate limit超過
- リポジトリへのアクセス権限がない

**対処法**:
```python
# Rate limitを確認
rate_info = github_client.check_rate_limit()
print(rate_info)

# リポジトリのアクセス権限を確認
# GitHub UI → Repository → Settings → Manage access
```

### 3. リポジトリ未発見 (404 Not Found)

**原因**:
- リポジトリ名が間違っている
- リポジトリが削除された
- アクセス権限がない

**対処法**:
```sql
-- データベースでリポジトリ名を確認
SELECT id, repository_name, active FROM repositories;

-- 無効化して除外
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py disable owner/repo
```

### 4. サーバーエラー (502, 503, 504)

**原因**:
- GitHub APIの一時的な障害

**対処法**:
- **自動リトライ機能が働きます**（手動対応不要）
- 継続的に発生する場合: [GitHub Status](https://www.githubstatus.com/) を確認

### 5. データ処理エラー (KeyError, ValueError)

**原因**:
- GitHub APIレスポンス形式の変更
- 予期しないデータ形式

**対処法**:
```bash
# エラーログを確認
docker logs nagare-airflow-scheduler | grep "Data processing error"

# 該当リポジトリを一時無効化
docker exec nagare-airflow-scheduler python /opt/airflow/scripts/manage_repositories.py disable owner/repo

# Issue報告
# https://github.com/your-repo/nagare/issues
```

## モニタリング

### Airflow UIでの確認

1. **DAG実行状況**: http://localhost:8080
   - タスク成功/失敗の確認
   - ログの確認

2. **タスクログ**:
   - 各タスクの詳細ログ
   - エラースタックトレース

### エラー統計の確認

AirflowのXComに保存されている統計情報を確認：

```python
# Airflow UIのXCom画面で確認
# Key: workflow_runs_error_stats
# Value: {"total_items": 5, "successful": 4, "failed": 1, ...}
```

### Streamlit管理画面での確認

http://localhost:8501 → **📈 実行履歴**

- 失敗したパイプライン実行
- エラーステータスの確認

## ベストプラクティス

### 1. Rate Limit対策

PAT はユーザ単位の上限が効きやすい。リポジトリ数・ポーリングが増えたら GitHub App（Installation 単位）へ切り替える（`.env` / `connections.yml` は README の GitHub 節を参照）。

### 2. リポジトリ数の調整

```python
# 監視リポジトリが多い場合、バッチサイズを調整
# src/nagare/constants.py
class FetchConfig:
    LOOKBACK_HOURS = 24  # デフォルト: 24時間
    # より短い間隔で実行して負荷分散
```

### 3. エラーアラート設定

```python
# DAGにメール通知を設定
default_args = {
    'email': ['admin@example.com'],
    'email_on_failure': True,
    'email_on_retry': False,
}
```

### 4. ログレベルの調整

```bash
# 詳細ログが必要な場合
# docker-compose.ymlに追加
environment:
  AIRFLOW__LOGGING__LOGGING_LEVEL: DEBUG
```

## トラブルシューティングフローチャート

```
エラー発生
  ↓
認証エラー (401) ?
  → YES: GitHub Token確認・再生成
  → NO: ↓

Rate Limit (403) ?
  → YES: 自動待機（対応不要）
  → NO: ↓

Not Found (404) ?
  → YES: リポジトリ名確認・無効化
  → NO: ↓

サーバーエラー (502/503/504) ?
  → YES: 自動リトライ（対応不要）
  → NO: ↓

データ処理エラー ?
  → YES: Issue報告・リポジトリ無効化
  → NO: ↓

予期しないエラー
  → ログ確認・Issue報告
```

## 関連ドキュメント

- [GitHub API Rate Limiting](https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting)
- [Airflow Logging](https://airflow.apache.org/docs/apache-airflow/stable/logging-monitoring/logging-tasks.html)
- [データベースセットアップ](../03_setup/database_setup.md)
- [Streamlit管理画面](../03_setup/streamlit_admin.md)
