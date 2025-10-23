"""DAGタスク用のヘルパー関数

DAGラッパー関数の共通ロジックを提供し、DRY原則を守る。
"""

from collections.abc import Callable
from typing import Any, TypeVar

from nagare.utils.factory import ClientFactory, get_factory

# 型変数の定義
T = TypeVar("T")


def with_database_client(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
) -> Callable[..., T]:
    """DatabaseClientを注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: DatabaseClientを第一引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(db: DatabaseClientProtocol, **context: Any) -> None:
            repositories = db.get_repositories()
            ...

        # DAGで使用
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_database_client(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_database_client() as db:
            return task_func(db=db, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper


def with_github_client(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
) -> Callable[..., T]:
    """GitHubClientを注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: GitHubClientを第一引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(github_client: GitHubClientProtocol, **context: Any) -> None:
            runs = github_client.get_workflow_runs(...)
            ...

        # DAGで使用
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_github_client(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_github_client() as github_client:
            return task_func(github_client=github_client, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper
