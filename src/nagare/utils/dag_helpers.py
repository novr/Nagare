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
    conn_id: str | None = None,
) -> Callable[..., T]:
    """GitHubClientを注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: GitHubClientを第一引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）
        conn_id: Airflow Connection ID（省略時は環境変数から取得）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(github_client: GitHubClientProtocol, **context: Any) -> None:
            runs = github_client.get_workflow_runs(...)
            ...

        # Airflow Connectionを使用（推奨）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_github_client(my_task, conn_id="github_default"),
        )

        # 環境変数を使用（後方互換性）
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

        with current_factory.create_github_client(conn_id=conn_id) as github_client:
            return task_func(github_client=github_client, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper


def with_bitrise_client(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
    conn_id: str | None = None,
) -> Callable[..., T]:
    """BitriseClientを注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: BitriseClientを第一引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）
        conn_id: Airflow Connection ID（省略時は環境変数から取得）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(bitrise_client: BitriseClientProtocol, **context: Any) -> None:
            builds = bitrise_client.get_builds(...)
            ...

        # Airflow Connectionを使用（推奨）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_bitrise_client(my_task, conn_id="bitrise_default"),
        )

        # 環境変数を使用（後方互換性）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_bitrise_client(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_bitrise_client(conn_id=conn_id) as bitrise_client:
            return task_func(bitrise_client=bitrise_client, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper


def with_github_and_database_clients(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
    conn_id: str | None = None,
) -> Callable[..., T]:
    """GitHubClientとDatabaseClientの両方を注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: GitHubClientとDatabaseClientを引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）
        conn_id: GitHub用のAirflow Connection ID（省略時は環境変数から取得）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(
            github_client: GitHubClientProtocol,
            db: DatabaseClientProtocol,
            **context: Any
        ) -> None:
            latest_timestamp = db.get_latest_run_timestamp("owner", "repo")
            runs = github_client.get_workflow_runs(..., created_after=latest_timestamp)
            ...

        # Airflow Connectionを使用（推奨）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_github_and_database_clients(
                my_task, conn_id="github_default"
            ),
        )

        # 環境変数を使用（後方互換性）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_github_and_database_clients(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_github_client(conn_id=conn_id) as github_client:
            with current_factory.create_database_client() as db:
                return task_func(github_client=github_client, db=db, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper


def with_bitrise_and_database_clients(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
    conn_id: str | None = None,
) -> Callable[..., T]:
    """BitriseClientとDatabaseClientの両方を注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: BitriseClientとDatabaseClientを引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）
        conn_id: Bitrise用のAirflow Connection ID（省略時は環境変数から取得）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(
            bitrise_client: BitriseClientProtocol,
            db: DatabaseClientProtocol,
            **context: Any
        ) -> None:
            latest_timestamp = db.get_latest_run_timestamp(repo_id, "bitrise")
            builds = bitrise_client.get_builds(app_slug, ...)
            ...

        # Airflow Connectionを使用（推奨）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_bitrise_and_database_clients(
                my_task, conn_id="bitrise_default"
            ),
        )

        # 環境変数を使用（後方互換性）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_bitrise_and_database_clients(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_bitrise_client(conn_id=conn_id) as bitrise_client:
            with current_factory.create_database_client() as db:
                return task_func(bitrise_client=bitrise_client, db=db, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper


def with_xcode_cloud_client(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
    conn_id: str | None = None,
) -> Callable[..., T]:
    """XcodeCloudClientを注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: XcodeCloudClientを第一引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）
        conn_id: Airflow Connection ID（省略時は環境変数から取得）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(xcode_cloud_client: XcodeCloudClientProtocol, **context: Any) -> None:
            builds = xcode_cloud_client.list_ci_builds_for_app(...)
            ...

        # Airflow Connectionを使用（推奨）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_xcode_cloud_client(my_task, conn_id="xcode_cloud_default"),
        )

        # 環境変数を使用（後方互換性）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_xcode_cloud_client(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_xcode_cloud_client(conn_id=conn_id) as xcode_cloud_client:
            return task_func(xcode_cloud_client=xcode_cloud_client, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper


def with_xcode_cloud_and_database_clients(
    task_func: Callable[..., T],
    factory: ClientFactory | None = None,
    conn_id: str | None = None,
) -> Callable[..., T]:
    """XcodeCloudClientとDatabaseClientの両方を注入してタスク関数を実行するラッパーを生成する

    Args:
        task_func: XcodeCloudClientとDatabaseClientを引数として受け取るタスク関数
        factory: ClientFactoryインスタンス（省略時はget_factory()を使用）
        conn_id: Xcode Cloud用のAirflow Connection ID（省略時は環境変数から取得）

    Returns:
        ラップされた関数（Airflowのコンテキストを受け取る）

    Example:
        ```python
        def my_task(
            xcode_cloud_client: XcodeCloudClientProtocol,
            db: DatabaseClientProtocol,
            **context: Any
        ) -> None:
            latest_timestamp = db.get_latest_run_timestamp(repo_id, "xcode_cloud")
            builds = xcode_cloud_client.list_ci_builds_for_app(app_id, ...)
            ...

        # Airflow Connectionを使用（推奨）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_xcode_cloud_and_database_clients(
                my_task, conn_id="xcode_cloud_default"
            ),
        )

        # 環境変数を使用（後方互換性）
        task = PythonOperator(
            task_id="my_task",
            python_callable=with_xcode_cloud_and_database_clients(my_task),
        )
        ```
    """

    def wrapper(**context: Any) -> T:
        """Airflowから呼ばれるラッパー関数"""
        if factory is None:
            current_factory = get_factory()
        else:
            current_factory = factory

        with current_factory.create_xcode_cloud_client(conn_id=conn_id) as xcode_cloud_client:
            with current_factory.create_database_client() as db:
                return task_func(xcode_cloud_client=xcode_cloud_client, db=db, **context)

    # 元の関数名とdocstringを保持
    wrapper.__name__ = task_func.__name__
    wrapper.__doc__ = task_func.__doc__

    return wrapper
