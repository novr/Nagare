# ADR-001 付録: DIコンテナ実装例

> このドキュメントは [ADR-001: 依存性注入戦略の選択](./001-dependency-injection-strategy.md) の付録です。

## 目的

将来的にdependency-injectorを導入する場合の具体的な実装例を提供する。

**⚠️ 注意**: これらは参考実装であり、実際には使用されていない。

---

## 1. Container定義

### ファイル: `src/nagare/utils/container.py` (参考実装)

```python
"""依存性注入コンテナ（参考実装）

このファイルは将来的にdependency-injectorを導入する際の参考として保存。
実際には使用されていない。
"""

from dependency_injector import containers, providers


class Container(containers.DeclarativeContainer):
    """依存性注入コンテナ

    全ての依存性を一元管理する。
    """

    # ========================================
    # 設定プロバイダー
    # ========================================
    config = providers.Configuration()

    # 環境変数から読み込み（NAGARE_で始まる変数）
    # 例: NAGARE_GITHUB_TOKEN → config.github.token
    config.from_env("NAGARE", as_=config)

    # YAMLファイルから読み込み（オプション）
    # 存在しない場合はスキップ
    config.from_yaml('config/settings.yaml', required=False)

    # ========================================
    # データベースクライアント（Singleton）
    # ========================================
    # アプリケーション全体で1つのインスタンスを共有
    database_client = providers.Singleton(
        "nagare.utils.database.DatabaseClient",
        # 設定から読み込む場合（例）:
        # use_mock=config.database.use_mock.as_bool()
    )

    # ========================================
    # GitHubクライアント（Resource）
    # ========================================
    # Resourceプロバイダーは自動でclose()を呼ぶ
    github_client = providers.Resource(
        "nagare.utils.github_client.GitHubClient",
        token=config.github.token,
        base_url=config.github.base_url.as_(
            str,
            default="https://api.github.com"
        ),
    )

    # ========================================
    # 将来的な拡張例
    # ========================================

    # GitLabクライアント
    # gitlab_client = providers.Resource(
    #     "nagare.utils.gitlab_client.GitLabClient",
    #     token=config.gitlab.token,
    #     base_url=config.gitlab.base_url.as_(str),
    # )

    # CircleCIクライアント
    # circleci_client = providers.Resource(
    #     "nagare.utils.circleci_client.CircleCIClient",
    #     token=config.circleci.token,
    # )


# グローバルコンテナインスタンス
container = Container()
```

---

## 2. タスク関数（自動配線）

### ファイル: `src/nagare/tasks/fetch.py` (修正版)

```python
"""データ取得タスク（DI版）"""

from typing import Any
from dependency_injector.wiring import inject, Provide
from nagare.utils.protocols import DatabaseClientProtocol, GitHubClientProtocol

# ========================================
# 方法1: Provideデフォルト引数（推奨）
# ========================================

@inject
def fetch_repositories(
    db: DatabaseClientProtocol = Provide["container.database_client"],
    **context: Any
) -> list[dict[str, str]]:
    """監視対象のリポジトリリストを取得する（DI版）

    @injectデコレータにより、dbが自動注入される。

    Args:
        db: DatabaseClientインスタンス（自動注入）
        **context: Airflowのコンテキスト

    Returns:
        リポジトリ情報のリスト
    """
    repositories = db.get_repositories()

    # XComで次のタスクに渡す
    ti = context["ti"]
    ti.xcom_push(key="repositories", value=repositories)

    return repositories


@inject
def fetch_workflow_runs(
    github_client: GitHubClientProtocol = Provide["container.github_client"],
    **context: Any
) -> None:
    """各リポジトリのワークフロー実行データを取得する（DI版）

    Args:
        github_client: GitHubClientインスタンス（自動注入）
        **context: Airflowのコンテキスト
    """
    ti = context["ti"]

    # 前のタスクからリポジトリリストを取得
    repositories = ti.xcom_pull(
        task_ids="fetch_repositories",
        key="repositories"
    )

    if not repositories:
        return

    # ワークフロー実行データ取得
    all_workflow_runs = []
    for repo in repositories:
        runs = github_client.get_workflow_runs(
            owner=repo["owner"],
            repo=repo["repo"],
        )
        for run in runs:
            run["_repository_owner"] = repo["owner"]
            run["_repository_name"] = repo["repo"]
        all_workflow_runs.extend(runs)

    # XComで次のタスクに渡す
    ti.xcom_push(key="workflow_runs", value=all_workflow_runs)


# ========================================
# 方法2: 明示的な注入（参考）
# ========================================

def fetch_repositories_explicit(
    container: Container,
    **context: Any
) -> list[dict[str, str]]:
    """明示的にContainerから取得する方法（参考）"""
    with container.database_client() as db:
        return fetch_repositories_impl(db, **context)


def fetch_repositories_impl(
    db: DatabaseClientProtocol,
    **context: Any
) -> list[dict[str, str]]:
    """実装（Pure DI）"""
    repositories = db.get_repositories()
    # ...
    return repositories
```

---

## 3. DAG定義

### ファイル: `src/nagare/dags/collect_github_actions_data_di.py` (参考実装)

```python
"""GitHub Actionsデータ収集DAG（DI版・参考実装）

⚠️ 注意: この実装は参考であり、実際には使用されていない。
"""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

from nagare.tasks.fetch import (
    fetch_repositories,
    fetch_workflow_runs,
)
from nagare.tasks.load import load_to_database
from nagare.tasks.transform import transform_data
from nagare.utils.container import container


# ========================================
# Containerの初期化
# ========================================

# 環境変数から設定を読み込み
container.config.from_env("NAGARE")

# Wiringを有効化（自動配線）
# このモジュール内の@inject関数に依存性が注入される
container.wire(modules=[
    "nagare.tasks.fetch",
    "nagare.tasks.load",
])


# ========================================
# DAG定義
# ========================================

default_args = {
    "owner": "nagare",
    "depends_on_past": False,
    "email": os.getenv("AIRFLOW_ALERT_EMAIL", "admin@example.com"),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
}

with DAG(
    dag_id="collect_github_actions_data_di",
    default_args=default_args,
    description="GitHub Actionsのワークフロー実行データを収集する（DI版）",
    schedule_interval="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["github", "data-collection", "di"],
) as dag:

    # ========================================
    # タスク定義
    # ========================================

    # @injectにより、自動的に依存性が注入される
    # ラッパー関数不要！

    task_fetch_repositories = PythonOperator(
        task_id="fetch_repositories",
        python_callable=fetch_repositories,
    )

    task_fetch_workflow_runs = PythonOperator(
        task_id="fetch_workflow_runs",
        python_callable=fetch_workflow_runs,
    )

    task_transform_data = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    task_load_to_database = PythonOperator(
        task_id="load_to_database",
        python_callable=load_to_database,
    )

    # タスクの依存関係
    (
        task_fetch_repositories
        >> task_fetch_workflow_runs
        >> task_transform_data
        >> task_load_to_database
    )


# ========================================
# クリーンアップ（重要）
# ========================================

def cleanup():
    """DAG実行後のクリーンアップ"""
    container.unwire()

# Airflow 2.x以降はon_success_callbackで呼び出し
dag.on_success_callback = cleanup
```

---

## 4. テストでのオーバーライド

### ファイル: `tests/conftest.py` (修正版)

```python
"""Pytest設定（DI版）"""

import pytest
from dependency_injector import providers
from nagare.utils.container import Container
from tests.conftest import MockDatabaseClient, MockGitHubClient


@pytest.fixture
def di_container():
    """テスト用のDIコンテナを生成

    モッククライアントをオーバーライドする。
    """
    container = Container()

    # モックでオーバーライド
    container.database_client.override(
        providers.Singleton(MockDatabaseClient)
    )
    container.github_client.override(
        providers.Factory(MockGitHubClient)
    )

    # Wiring有効化
    container.wire(modules=[
        "nagare.tasks.fetch",
        "nagare.tasks.load",
    ])

    yield container

    # クリーンアップ
    container.unwire()
    container.reset_singletons()


def test_fetch_repositories_with_di(di_container, mock_airflow_context):
    """fetch_repositories関数のテスト（DI版）"""
    from nagare.tasks.fetch import fetch_repositories

    # @injectにより、自動的にMockDatabaseClientが注入される
    result = fetch_repositories(**mock_airflow_context)

    assert len(result) == 2
    assert result[0]["owner"] == "test-org"
```

---

## 5. 設定ファイル

### ファイル: `config/settings.yaml` (例)

```yaml
# Nagare設定ファイル（例）

database:
  use_mock: false
  connection_string: "${DATABASE_URL}"  # 環境変数から読み込み
  pool_size: 10
  timeout: 30

github:
  token: "${GITHUB_TOKEN}"  # 環境変数から読み込み
  base_url: "https://api.github.com"
  timeout: 30
  max_retries: 3

# 将来的な拡張例
gitlab:
  token: "${GITLAB_TOKEN}"
  base_url: "https://gitlab.com/api/v4"

circleci:
  token: "${CIRCLECI_TOKEN}"
  base_url: "https://circleci.com/api/v2"

# 監視対象リポジトリ（YAMLで管理する場合）
repositories:
  - owner: "test-org"
    repo: "test-repo-1"
  - owner: "test-org"
    repo: "test-repo-2"
```

### 環境変数の読み込み

```bash
# .env
NAGARE_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
NAGARE_DATABASE_USE_MOCK=true
NAGARE_REPOSITORIES='[{"owner":"test-org","repo":"test-repo"}]'
```

```python
# Pythonコード
from nagare.utils.container import container

# 環境変数から自動読み込み
container.config.from_env("NAGARE", as_=container.config)

# アクセス
token = container.config.github.token()
use_mock = container.config.database.use_mock.as_bool()
```

---

## 6. 段階的移行プラン

### Phase 1: Container定義（1日）

```python
# 1. Containerクラスを作成
# src/nagare/utils/container.py

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    database_client = providers.Singleton(DatabaseClient)
    github_client = providers.Resource(GitHubClient)
```

### Phase 2: 既存Factoryとの共存（1日）

```python
# 2. Factoryから段階的に移行
# src/nagare/utils/factory.py

from nagare.utils.container import container

class ClientFactory:
    @staticmethod
    def create_database_client():
        # Containerから取得（段階的移行）
        return container.database_client()
```

### Phase 3: タスク関数の変更（2日）

```python
# 3. @injectデコレータ追加
# src/nagare/tasks/fetch.py

@inject
def fetch_repositories(
    db: DatabaseClientProtocol = Provide["container.database_client"],
    **context: Any
):
    # 実装は変更不要
    ...
```

### Phase 4: DAG統合（1日）

```python
# 4. Wiring有効化
# src/nagare/dags/collect_github_actions_data.py

from nagare.utils.container import container

container.wire(modules=["nagare.tasks.fetch"])

# ラッパー関数不要に！
task = PythonOperator(
    task_id="fetch_repositories",
    python_callable=fetch_repositories,  # 直接指定
)
```

### Phase 5: テスト更新（1日）

```python
# 5. テストでオーバーライド
# tests/conftest.py

@pytest.fixture
def di_container():
    container = Container()
    container.database_client.override(
        providers.Singleton(MockDatabaseClient)
    )
    yield container
    container.unwire()
```

---

## 7. メリット・デメリット再確認

### dependency-injector導入のメリット ✅

1. **ラッパー関数不要**
   ```python
   # Before（現在）
   def fetch_repositories_with_di(**context):
       factory = get_factory()
       with factory.create_database_client() as db:
           return fetch_repositories(db=db, **context)

   # After（dependency-injector）
   @inject
   def fetch_repositories(
       db = Provide[Container.database_client],
       **context
   ):
       # @injectで自動注入、ラッパー不要！
       ...
   ```

2. **設定の一元管理**
   ```python
   # Before（現在）
   # 各クライアントで環境変数を読む
   token = os.getenv("GITHUB_TOKEN")

   # After（dependency-injector）
   # Container定義で一元管理
   config.from_env("NAGARE")
   github = providers.Resource(
       GitHubClient,
       token=config.github.token
   )
   ```

3. **ライフサイクル明示**
   ```python
   # SingletonかFactoryかが明確
   database = providers.Singleton(DatabaseClient)  # アプリ全体で1つ
   github = providers.Factory(GitHubClient)  # 毎回新規作成
   ```

4. **YAMLファイル統合**
   ```python
   # YAMLから設定読み込み
   container.config.from_yaml('settings.yaml')
   ```

### dependency-injector導入のデメリット ❌

1. **学習コスト**
   - Provider、Container、Wiringなどの概念
   - 2-4時間の学習時間

2. **ボイラープレート**
   - Container定義が必要（+50行程度）
   - wiring()の呼び出しが必要

3. **デバッグ難易度**
   - 自動配線により依存関係が見えにくい
   - スタックトレースが長くなる

4. **外部依存**
   - dependency-injectorへの依存
   - 将来的な破壊的変更のリスク

---

## 8. 実際の導入判断基準（再掲）

以下のいずれかに該当した場合、導入を検討:

| # | 条件 | 現在値 | 閾値 | 状態 |
|---|------|--------|------|------|
| 1 | 依存性の数 | 3個 | 5個以上 | 🟢 |
| 2 | 環境変数の数 | 7個 | 20個以上 | 🟢 |
| 3 | チームサイズ | 1-2人 | 3人以上 | 🟢 |
| 4 | 設定ファイル | なし | YAML必要 | 🟢 |
| 5 | ライフサイクル管理 | 単純 | 複雑 | 🟢 |

**現時点の判断**: 導入不要（Factoryパターンで十分）

---

## 参考リンク

- [dependency-injector公式ドキュメント](https://python-dependency-injector.ets-labs.org/)
- [dependency-injectorチュートリアル](https://python-dependency-injector.ets-labs.org/tutorials/index.html)
- [Airflow統合のベストプラクティス](https://python-dependency-injector.ets-labs.org/examples/index.html)

---

**作成日**: 2025年10月22日
**最終更新**: 2025年10月22日
**使用状況**: 参考実装（実際には未使用）
