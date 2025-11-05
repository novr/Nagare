# ADR-006: 一時テーブル方式によるDAG間データ転送

## ステータス

**Accepted** - 2025年11月4日

## コンテキスト

現在のAirflow DAG実装では、タスク間のデータ転送にXCom（Airflowの内部メカニズム）を使用している。しかし、実運用において深刻なパフォーマンス問題とスケーラビリティ問題が発生している。

### 現状の問題点

1. **XComテーブルの肥大化**
   - 実測値：XComテーブルが**81MB**に達した（1,179エントリ）
   - 最大エントリ：`workflow_runs`キーが**40MB × 2 = 80MB**
   - `collect_bitrise_data`: 833エントリで232MB（圧縮前）
   - `collect_github_actions_data`: 243エントリで48MB（圧縮前）

2. **DAG設計原則との乖離**
   ```python
   # dag_design.md:70-74 の推奨
   # ✅ 許可: 軽量なメタデータ（10KB以下）
   # ❌ 禁止: 大きなデータセット（100KB以上）

   # 実際の実装（問題あり）
   ti.xcom_push(key="workflow_runs", value=all_workflow_runs)  # 40MB!
   ti.xcom_push(key="transformed_runs", value=transformed_runs)  # 10MB!
   ```

3. **データフローの非効率性**
   ```
   fetch_repositories
     → XComにリポジトリリスト保存
       → fetch_*_batch (並列バッチ)
         → 各バッチが全データをXComに保存 ⚠️ (2-4MB × 多数)
           → transform_data
             → 全バッチからXComでデータ収集 ⚠️
             → 変換後のデータもXComに保存 ⚠️ (10MB)
               → load_to_database
   ```

4. **スケーラビリティの限界**
   - リポジトリ数が増えるとXComサイズが線形に増加
   - Airflow UI (`/xcom/list/`) のアクセスが**78MB**のレスポンスを返す
   - PostgreSQLのメモリ圧迫とI/Oボトルネック

5. **メンテナンス負荷**
   - 定期的なXComクリーンアップが必要
   - 古いデータの自動削除メカニズムが未実装

### プロジェクト要件

- **パフォーマンス**: XComテーブルのサイズを**10KB以下**に削減
- **スケーラビリティ**: リポジトリ数が増えても安定動作
- **データ整合性**: トランザクション保証
- **保守性**: 自動クリーンアップ
- **後方互換性**: 既存のDAGロジックへの影響を最小化

### 検討した選択肢

#### 選択肢A: XComサイズ削減（ID参照のみ）

```python
# XComには最小限のメタデータのみ
ti.xcom_push(key="workflow_run_ids", value=[123, 456, 789])  # 数KB
# 次のタスクでDBから再取得
run_ids = ti.xcom_pull(key="workflow_run_ids")
runs = db.get_runs_by_ids(run_ids)
```

**メリット**:
- ✅ XComサイズが劇的に削減
- ✅ 実装が比較的シンプル

**デメリット**:
- ❌ DBへの追加クエリが必要（N+1問題）
- ❌ データ取得タスクで既にDBに保存する必要がある
- ❌ タスク間のデータフローが複雑化

---

#### 選択肢B: XCom Backend をS3/GCSに変更

```python
# カスタムXCom Backend
class S3XComBackend(BaseXComBackend):
    def serialize_value(self, value):
        # S3に保存し、参照を返す
        s3_key = upload_to_s3(value)
        return {"s3_key": s3_key}
```

**メリット**:
- ✅ PostgreSQLの負荷削減
- ✅ スケーラブル
- ✅ 既存のコード変更が最小限

**デメリット**:
- ❌ 外部依存（S3/GCS）が必要
- ❌ コスト増加（ストレージ、API呼び出し）
- ❌ ローカル開発環境が複雑化
- ❌ レイテンシ増加

---

#### 選択肢C: 一時テーブル方式（推奨）

```python
# 1. fetch_*_batchタスク: 一時テーブルに保存
def fetch_workflow_runs_batch(...):
    runs = github_client.get_workflow_runs(...)
    db.insert_temp_workflow_runs(runs, task_id=task_id)
    ti.xcom_push(key="batch_count", value=len(runs))  # メタデータのみ

# 2. transformタスク: 一時テーブルから読み込み
def transform_data(...):
    runs = db.get_temp_workflow_runs()  # 一時テーブルから全件取得
    transformed = [transform(run) for run in runs]
    db.insert_temp_transformed_runs(transformed)
    ti.xcom_push(key="transform_count", value=len(transformed))

# 3. loadタスク: 一時テーブルから本番テーブルへ移動
def load_to_database(...):
    db.move_temp_to_production()  # 一時→本番（トランザクション内）
    db.cleanup_temp_tables()  # 一時テーブルをクリア
```

**メリット**:
- ✅ XComは最小限のメタデータのみ（数KB）
- ✅ PostgreSQLのトランザクション機能を活用
- ✅ 外部依存なし（既存のPostgreSQL）
- ✅ ローカル開発環境でも動作
- ✅ データ整合性が保証される
- ✅ 自動クリーンアップが容易

**デメリット**:
- △ 一時テーブルのスキーマ定義が必要
- △ データ移動のロジックが必要
- △ 実装の変更範囲が大きい

---

#### 選択肢D: Airflow Dataset機能を使用

```python
# Airflow 2.4+ のDataset機能
from airflow.datasets import Dataset

dataset = Dataset("postgres://nagare/temp_workflow_runs")

with DAG(...) as dag:
    fetch_task = PythonOperator(..., outlets=[dataset])
    transform_task = PythonOperator(..., inlets=[dataset])
```

**メリット**:
- ✅ Airflow標準機能
- ✅ データ系譜の可視化

**デメリット**:
- ❌ まだ実験的な機能（安定性不明）
- ❌ ドキュメントが少ない
- ❌ 一時テーブル方式と本質的に同じ実装が必要

---

## 決定

**選択肢C（一時テーブル方式）を採用する。**

### 実装方針

#### 1. 一時テーブルの設計

```sql
-- ワークフロー実行データの一時テーブル
CREATE TABLE temp_workflow_runs (
    task_id VARCHAR(250) NOT NULL,      -- バッチタスクID（識別用）
    run_id VARCHAR(250) NOT NULL,        -- DAG run ID
    source_run_id VARCHAR(255) NOT NULL, -- GitHub/BitriseのRun ID
    source VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,                 -- 生データ（JSONB形式）
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (task_id, run_id, source_run_id)
);

-- 変換済みデータの一時テーブル
CREATE TABLE temp_transformed_runs (
    run_id VARCHAR(250) NOT NULL,        -- DAG run ID
    source_run_id VARCHAR(255) NOT NULL,
    data JSONB NOT NULL,                 -- 変換済みデータ
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (run_id, source_run_id)
);

-- ジョブデータの一時テーブル
CREATE TABLE temp_workflow_jobs (
    run_id VARCHAR(250) NOT NULL,
    source_job_id VARCHAR(255) NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (run_id, source_job_id)
);

-- インデックス（クエリパフォーマンス用）
CREATE INDEX idx_temp_workflow_runs_run_id ON temp_workflow_runs(run_id);
CREATE INDEX idx_temp_transformed_runs_run_id ON temp_transformed_runs(run_id);
CREATE INDEX idx_temp_workflow_jobs_run_id ON temp_workflow_jobs(run_id);
```

#### 2. DatabaseClientへのメソッド追加

```python
class DatabaseClientProtocol(Protocol):
    """データベースクライアントのプロトコル"""

    # 既存メソッド
    def get_repositories(self, source: str | None = None) -> list[dict[str, Any]]: ...
    def upsert_pipeline_runs(self, runs: list[dict[str, Any]]) -> None: ...

    # 新規メソッド（一時テーブル用）
    def insert_temp_workflow_runs(
        self, runs: list[dict[str, Any]], task_id: str, run_id: str
    ) -> None:
        """一時テーブルにワークフロー実行データを保存"""
        ...

    def get_temp_workflow_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから全ワークフロー実行データを取得"""
        ...

    def insert_temp_transformed_runs(
        self, runs: list[dict[str, Any]], run_id: str
    ) -> None:
        """一時テーブルに変換済みデータを保存"""
        ...

    def get_temp_transformed_runs(self, run_id: str) -> list[dict[str, Any]]:
        """一時テーブルから変換済みデータを取得"""
        ...

    def move_temp_to_production(self, run_id: str) -> None:
        """一時テーブルから本番テーブルへデータを移動（トランザクション内）"""
        ...

    def cleanup_temp_tables(self, run_id: str | None = None, days: int = 7) -> None:
        """一時テーブルをクリーンアップ（古いデータを削除）"""
        ...
```

#### 3. タスクの修正

**fetch_workflow_runs_batch の修正**:
```python
def fetch_workflow_runs_batch(
    github_client: GitHubClientProtocol,
    db: DatabaseClientProtocol,
    batch_repos: list[dict[str, str]],
    since: str | None = None,
    until: str | None = None,
    **context: Any
) -> None:
    ti: TaskInstance = context["ti"]
    run_id = context["run_id"]
    task_id = ti.task_id

    # データ取得
    all_workflow_runs = []
    for repo in batch_repos:
        runs = github_client.get_workflow_runs(...)
        all_workflow_runs.extend(runs)

    # 一時テーブルに保存（XComは使わない）
    db.insert_temp_workflow_runs(all_workflow_runs, task_id=task_id, run_id=run_id)

    # XComには統計情報のみ
    ti.xcom_push(key=f"batch_stats_{task_id}", value={
        "count": len(all_workflow_runs),
        "task_id": task_id,
    })
```

**transform_data の修正**:
```python
def transform_data(**context: Any) -> None:
    ti: TaskInstance = context["ti"]
    run_id = context["run_id"]

    # 一時テーブルから全データを取得
    workflow_runs = db.get_temp_workflow_runs(run_id)

    # 変換処理
    transformed_runs = [_transform_workflow_run(run) for run in workflow_runs]

    # 一時テーブルに保存
    db.insert_temp_transformed_runs(transformed_runs, run_id=run_id)

    # XComには統計情報のみ
    ti.xcom_push(key="transform_stats", value={
        "input_count": len(workflow_runs),
        "output_count": len(transformed_runs),
    })
```

**load_to_database の修正**:
```python
def load_to_database(db: DatabaseClientProtocol, **context: Any) -> None:
    run_id = context["run_id"]

    # トランザクション内で一時テーブルから本番テーブルへ移動
    with db.transaction():
        db.move_temp_to_production(run_id)

    # 成功後、一時テーブルをクリーンアップ
    db.cleanup_temp_tables(run_id=run_id)
```

#### 4. 自動クリーンアップDAGの追加

```python
# dags/cleanup_temp_tables.py
with DAG(
    dag_id="cleanup_temp_tables",
    schedule_interval="0 2 * * *",  # 毎日2:00 UTC
    catchup=False,
) as dag:
    cleanup_task = PythonOperator(
        task_id="cleanup_old_temp_data",
        python_callable=with_database_client(cleanup_old_temp_data),
    )

def cleanup_old_temp_data(db: DatabaseClientProtocol, **context: Any) -> None:
    """7日より古い一時テーブルデータを削除"""
    deleted_count = db.cleanup_temp_tables(days=7)
    logger.info(f"Deleted {deleted_count} old temporary records")
```

## 影響

### プラス影響

1. **パフォーマンスの劇的改善**
   - XComテーブル: **81MB → 数KB**（99%以上削減）
   - Airflow UI のレスポンスタイムが改善
   - PostgreSQLのメモリ使用量削減

2. **スケーラビリティの向上**
   - リポジトリ数が増えてもXComサイズは一定
   - 一時テーブルは自動クリーンアップで肥大化しない

3. **データ整合性の保証**
   - PostgreSQLのトランザクション機能を活用
   - ACID特性による確実なデータ移動

4. **運用の自動化**
   - 自動クリーンアップDAGで保守不要
   - 一時テーブルの寿命管理が明確

5. **デバッグの容易性**
   - 一時テーブルのデータをSQL直接確認可能
   - XComのバイナリデータより可読性が高い

### マイナス影響

1. **実装の複雑性**
   - 一時テーブルのスキーマ管理が必要
   - データ移動ロジックの追加

2. **マイグレーション作業**
   - 既存のタスクコードを修正
   - DatabaseClientに新規メソッド追加
   - 包括的なテストが必要

3. **ディスクI/O増加**
   - データを複数回読み書き（XComより多い）
   - ただし、PostgreSQLの効率的なI/Oで緩和

### 緩和策

1. **段階的な移行**
   - まずGitHub Actions DAGで実装・検証
   - 次にBitrise DAGに展開
   - 並行して旧実装も維持（フォールバック可能）

2. **パフォーマンステスト**
   - 一時テーブルへの書き込み速度を計測
   - インデックスの効果を検証
   - 必要に応じてJSONB→正規化テーブルに変更

3. **包括的なテスト**
   - 単体テスト: 各DatabaseClientメソッド
   - 統合テスト: DAG全体のデータフロー
   - エラーケース: トランザクションロールバック

4. **明確なドキュメント**
   - 一時テーブルの寿命と管理方法
   - トラブルシューティングガイド
   - SQL直接操作のベストプラクティス

## 使用例

### 一時テーブルのデータ確認（デバッグ用）

```sql
-- 現在のDAG runの一時データを確認
SELECT
    task_id,
    COUNT(*) as record_count,
    pg_size_pretty(SUM(octet_length(data::text))::bigint) as data_size
FROM temp_workflow_runs
WHERE run_id = 'manual__2025-11-04T10:00:00'
GROUP BY task_id;

-- 特定のワークフロー実行データを確認
SELECT data->>'name' as workflow_name, data->>'status' as status
FROM temp_workflow_runs
WHERE run_id = 'manual__2025-11-04T10:00:00'
LIMIT 10;
```

### 手動クリーンアップ（緊急時）

```sql
-- 特定のDAG runの一時データを削除
DELETE FROM temp_workflow_runs WHERE run_id = 'manual__2025-11-04T10:00:00';
DELETE FROM temp_transformed_runs WHERE run_id = 'manual__2025-11-04T10:00:00';
DELETE FROM temp_workflow_jobs WHERE run_id = 'manual__2025-11-04T10:00:00';

-- 7日より古いデータを削除
DELETE FROM temp_workflow_runs WHERE created_at < NOW() - INTERVAL '7 days';
DELETE FROM temp_transformed_runs WHERE created_at < NOW() - INTERVAL '7 days';
DELETE FROM temp_workflow_jobs WHERE created_at < NOW() - INTERVAL '7 days';
```

## 実装タスク

- [ ] マイグレーションファイル作成（一時テーブルのCREATE TABLE）
- [ ] DatabaseClientProtocolにメソッド追加
- [ ] DatabaseClient（PostgreSQL実装）にメソッド実装
- [ ] MockDatabaseClientにメソッド実装（テスト用）
- [ ] fetch_workflow_runs_batch の修正
- [ ] transform_data の修正
- [ ] load_to_database の修正
- [ ] cleanup_temp_tables DAGの作成
- [ ] 単体テスト作成
- [ ] 統合テスト作成
- [ ] ドキュメント更新（dag_design.md, implementation_guide.md）
- [ ] 本番環境でのパフォーマンステスト

## 関連資料

- [DAG設計原則](../dag_design.md) - XComの使用ルール
- [データモデル](../data_model.md) - 本番テーブルのスキーマ
- [PostgreSQL JSONB](https://www.postgresql.org/docs/current/datatype-json.html)
- [Airflow XCom Documentation](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/xcoms.html)

## 変更履歴

- 2025-11-04: 初版作成・承認
