# 07. Airflow DAG設計原則

本ドキュメントでは、Nagareにおけるデータ収集バッチ処理のAirflow DAG設計ルールを定義する。

## 1. DAG設計の基本原則

### 1.1. 設計原則

- **決定性 (Deterministic):** 同じ入力に対して常に同じ出力を生成する
- **シンプルさ:** DAGの複雑さを最小限に抑え、分析とデバッグを容易にする
- **冪等性 (Idempotency):** 同じタスクを複数回実行しても結果が変わらない（UPSERTを活用）
- **単一責任:** 各タスクは1つの明確な責任のみを持つ
- **疎結合:** タスク間のデータ受け渡しを最小限にする

### 1.2. 必須設定

**DAG定義**
- `catchup=False`: 過去の実行をスキップ
- `start_date`: 固定値を使用（動的な`datetime.now()`は禁止）
- `schedule_interval`: cron形式で明示的に指定
- DAG IDは明確で一意な名前

**default_args**
```python
default_args = {
    "owner": "nagare",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,           # 1-4回を推奨
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
}
```

## 2. タスク設計ルール

### 2.1. タスク分割の原則

**責務の分離**
- データ取得、変換、読み込みを別タスクに分割
- 各タスクは独立してテスト可能であること
- 1つのタスクで複数のリソース種別を扱わない

**タスクの命名規則**
- 動詞で始まる（例: `fetch_`, `transform_`, `load_`）
- 何を処理するか明確にする（例: `fetch_workflow_runs`）
- 過度に長い名前は避ける（最大40文字程度）

### 2.2. タスクの依存関係

**線形フロー**
```python
task1 >> task2 >> task3 >> task4
```

**並列実行の制限**
- MVP版では並列実行を行わない
- `max_active_runs_per_dag=1` を設定

**ExternalTaskSensorの使用**
- 他のDAGに依存する場合のみ使用
- MVP版では使用しない

## 3. データハンドリングルール

### 3.1. XComの使用ルール（更新: ADR-006）

**✅ 使用が許可される場合**
- 軽量なメタデータ（統計情報、エラーカウントなど、10KB以下）
- タスク間の制御情報（run_id、task_idなど）
- バッチ処理の統計情報（count, error_stats）

**❌ 使用が禁止される場合**
- 大きなデータセット（100KB以上）
- APIレスポンスの全体（GitHub/Bitrise APIレスポンス）
- 変換済みデータ（pipeline_runs, jobs）
- バイナリデータ

**✅ 推奨される代替手段（ADR-006: 一時テーブル方式）**

タスク間のデータ転送には**一時テーブル**を使用する：

```python
# ❌ 悪い例: XComに大きなデータを保存
ti.xcom_push(key="workflow_runs", value=all_workflow_runs)  # 40MB!

# ✅ 良い例: 一時テーブルに保存、XComは統計のみ
db.insert_temp_workflow_runs(all_workflow_runs, task_id, run_id)
ti.xcom_push(key="batch_stats", value={"count": len(all_workflow_runs)})  # 数KB
```

**一時テーブルの利点**:
- XComテーブルの肥大化防止（81MB → 数KB、99%削減達成）
- PostgreSQLのトランザクション機能を活用
- データ整合性の保証（ACID特性）
- 自動クリーンアップ（7日で自動削除）

**一時テーブルの使用パターン**:
1. **fetchタスク**: APIレスポンスを一時テーブルに保存
2. **transformタスク**: 一時テーブルから読み込み、変換後も一時テーブルに保存
3. **loadタスク**: 一時テーブルから本番テーブルへ移動、完了後クリーンアップ

### 3.2. データの永続化

**一時データ（ADR-006: 一時テーブル方式）**
- タスク間のデータ転送: **一時テーブル**（temp_workflow_runs, temp_transformed_runs, temp_workflow_jobs）
- 各DAG run用にrun_idで識別
- 成功時: load_to_databaseタスクで自動クリーンアップ
- 失敗時: cleanup_temp_tablesDAGで7日後に自動削除

**永続データ**
- データベースに保存（pipeline_runs, jobs テーブル）
- トランザクションを適切に管理
- UPSERTで冪等性を保証

**一時テーブルのライフサイクル**:
```
1. fetchタスク: temp_workflow_runs に保存
2. transformタスク: temp_workflow_runs から読込 → temp_transformed_runs に保存
3. loadタスク: temp_transformed_runs から本番テーブルへ移動 → 一時テーブルをクリーンアップ
4. 失敗時: cleanup_temp_tablesDAG（毎日2:00 UTC）が7日より古いデータを削除
```

## 4. エラーハンドリングルール

### 4.1. GitHub API Rate Limit対策

**Rate Limit監視（実装済み）**
- GitHub API呼び出し前に自動的にRate Limitを確認
- 残数が10%未満の場合、WARNINGログを出力
- 残数が10リクエスト未満の場合、自動的にリセット時刻まで待機

**自動待機処理（実装済み）**
```python
# Rate Limit情報の取得
rate_info = github_client.check_rate_limit()
# {
#   "core": {"limit": 5000, "remaining": 4523, "reset": "2025-10-24T14:00:00Z"},
#   "search": {"limit": 30, "remaining": 25, "reset": "2025-10-24T13:01:00Z"}
# }

# 残数が少ない場合は自動待機
if rate_info["core"]["remaining"] < 10:
    github_client.wait_for_rate_limit_reset("core")
```

**Rate Limit超過時の動作**
- リセット時刻までの待機時間を計算し、ログに記録
- 自動的にスリープし、リセット後に処理を再開
- リトライカウントは消費しない（Rate Limit待機は通常動作）

### 4.2. リトライ戦略

**リトライ設定の基準（実装済み）**

| 処理内容 | リトライ回数 | 間隔 | バックオフ |
|---------|------------|------|----------|
| DBアクセス | 3回 | 5分 | なし |
| GitHub API（一時的エラー） | 3回 | 1秒 | 指数（1,2,4秒） |
| Rate Limit超過 | 無制限 | リセットまで | なし |
| データ変換 | 0回 | - | - |

**指数バックオフの実装（実装済み）**
```python
retry_count = 0
max_retries = 3

while retry_count <= max_retries:
    try:
        return github_client.get_workflow_runs(owner, repo)
    except GithubException as e:
        if e.status in [502, 503, 504] and retry_count < max_retries:
            wait_time = 2 ** retry_count  # 1秒、2秒、4秒
            logger.warning(f"Temporary error {e.status}, retrying in {wait_time}s")
            time.sleep(wait_time)
            retry_count += 1
            continue
        raise
```

**リトライ対象エラー**
- 502 Bad Gateway（サーバー一時的エラー）
- 503 Service Unavailable（サービス一時停止）
- 504 Gateway Timeout（タイムアウト）
- RateLimitExceededException（Rate Limit超過）

**リトライの例外**
- 401 Unauthorized（認証エラー）: 即座に失敗
- 404 Not Found（リソース未発見）: 即座に失敗、ログ記録
- データ変換エラー: リトライしない（ログ記録のみ）

### 4.3. 部分的な失敗の許容

**原則（実装済み）**
- 1つのリソース（リポジトリ、ワークフロー実行）の失敗が全体に影響しない
- エラーは詳細に記録し、処理を継続
- エラー統計をXComに保存し、モニタリングに活用

**実装パターン（実装済み）**
```python
results = []
error_stats = {
    "total_items": len(items),
    "successful": 0,
    "failed": 0,
    "errors": [],
}

for item in items:
    try:
        result = process(item)
        results.extend(result)
        error_stats["successful"] += 1
    except GithubException as e:
        logger.error(f"GitHub API error: {e}")
        error_stats["failed"] += 1
        error_stats["errors"].append({
            "item": item,
            "error_type": "GithubException",
            "status": e.status,
            "message": str(e.data),
        })
        continue  # 他のリソースは処理継続

# エラー統計をXComに保存
ti.xcom_push(key=f"{key}_error_stats", value=error_stats)
```

**全失敗時の動作**
- ワークフロー実行取得: RuntimeErrorを投げてタスク失敗
- ジョブ取得: エラーログのみ、空リストで継続

### 4.4. アラート条件

- DAGが連続3回失敗: メール/Slack通知
- タスク実行時間が通常の2倍超過: 警告
- Rate Limitが10%未満: WARNINGログ（自動対応）
- 部分的失敗率が50%超過: WARNINGログ

詳細は[エラーハンドリングガイド](../04_operation/error_handling.md)を参照。

## 5. パフォーマンス設計ルール

### 5.1. API呼び出しの制約

**GitHub API制約（実装済み）**
- Personal Access Token: 5,000リクエスト/時間（Core API）
- GitHub Apps: 5,000リクエスト/時間（Core API）
- Search API: 30リクエスト/分
- 自動的にRate Limit監視と待機処理を実施
- `check_rate_limit()`で残数を確認
- `wait_for_rate_limit_reset()`で自動待機

**並列度の制限**
- MVP版では並列処理を行わない
- 将来的にも並列度は5以下に制限

### 5.2. データベースアクセス

**必須事項**
- バルクINSERT/UPDATEを使用（1件ずつは禁止）
- トランザクションサイズ: 最大1000レコード/トランザクション
- 適切なインデックスの設定（`data_model.md`参照）

**禁止事項**
- N+1クエリ
- SELECT *（必要なカラムのみ指定）
- ループ内でのINSERT

### 5.3. メモリ管理

**制限**
- 1タスクあたりのメモリ使用: 最大1GB
- 大きなデータセットはストリーム処理またはバッチ分割

**推奨**
- ジェネレータの使用
- 適切なデータのチャンク分割

## 6. セキュリティルール

### 6.1. 認証情報の管理

**必須**
- GitHub App tokenは環境変数から取得
- データベース接続情報は環境変数またはSecrets Manager
- コードに認証情報を埋め込まない

**環境変数命名規則**
```
GITHUB_APP_TOKEN
DATABASE_HOST
DATABASE_USER
DATABASE_PASSWORD
```

### 6.2. ログ出力の制限

**禁止事項**
- トークンやパスワードのログ出力
- ユーザーの個人情報
- 完全なAPIレスポンス（要約のみ）

**推奨**
- エラーメッセージは具体的に
- デバッグ情報は適切なログレベルで

## 7. テスト要件

### 7.1. 必須テスト

**DAG検証**
- DAGが正しく読み込まれること
- タスク依存関係が正しいこと
- 循環依存がないこと

**タスクのユニットテスト**
- 各タスク関数の単体テスト
- モックを使用した外部依存の分離
- エッジケースのテスト

### 7.2. テストデータの原則

- 本番データを使用しない
- モックまたはフィクスチャを使用
- テスト用のリポジトリは最小限（1-2個）

## 8. スケジューリングルール

### 8.1. 実行頻度

**メインDAG (`collect_github_actions_data`)**
- 頻度: 1時間に1回
- cron: `0 * * * *` （毎時0分）
- タイムゾーン: UTC

**制約**
- API制約により、これより頻繁な実行は不可
- 1回の実行時間: 30分以内を目標

### 8.2. メンテナンスウィンドウ

- 日本時間の深夜2-3時（UTC 17-18時）はメンテナンス可能時間
- この時間帯のDAG実行は避けることが望ましい

## 9. コード品質ルール

コーディング規約の基本は [AGENT.md](../../../AGENT.md) を参照。

**DAG固有の推奨事項**
- 関数は50行以内
- クラスは200行以内
- 複雑度（Cyclomatic Complexity）は10以下
- Docstring（Google Style）

## 10. 監視・運用ルール

### 10.1. ログレベル

| レベル | 用途 |
|-------|------|
| ERROR | タスク失敗、データ損失の可能性 |
| WARNING | 部分的な失敗、パフォーマンス劣化 |
| INFO | 処理の開始/完了、重要な統計情報 |
| DEBUG | デバッグ情報（本番では無効化） |

### 10.2. メトリクス

**必須メトリクス**
- DAG実行成功率
- タスク実行時間
- API呼び出し数
- 処理したリポジトリ数

**収集方法**
- Airflowのメタデータから自動収集
- カスタムメトリクスはログから抽出

## 11. 拡張性の考慮

### 11.1. 汎用性の原則

**データモデル**
- GitHub Actions固有の名称を避ける
- 汎用的なカラム名（`source`, `source_run_id`）
- 他のCI/CDツール追加を考慮

**コード設計**
- CI/CDツール固有のロジックは分離
- インターフェースの定義
- プラグイン可能な設計

### 11.2. 制限事項の明示

**MVP版の制限**
- GitHub Actionsのみサポート
- 並列実行なし
- 高度な権限管理なし

**将来の拡張**
- GitLab CI、CircleCIのサポート
- 並列処理による高速化
- Row Level Securityによる権限管理

## 12. 参考資料

### 12.1. 関連ドキュメント

- [実装ガイド](./implementation_guide.md) - 具体的な実装方法
- [アーキテクチャ設計](./architecture.md) - システム全体構成
- [データモデル](./data_model.md) - データベーススキーマ

### 12.2. 外部ドキュメント

- [Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
- [PyGithub Documentation](https://pygithub.readthedocs.io/)
- [GitHub REST API - Actions](https://docs.github.com/en/rest/actions/workflow-runs)
