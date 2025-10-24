#!/usr/bin/env python3
"""リポジトリ管理CLI

PostgreSQLデータベースに監視対象リポジトリを追加・削除・一覧表示する。

Usage:
    # 一覧表示
    python scripts/manage_repositories.py list

    # 追加
    python scripts/manage_repositories.py add owner/repo

    # 無効化
    python scripts/manage_repositories.py disable owner/repo

    # 有効化
    python scripts/manage_repositories.py enable owner/repo
"""

import argparse
import os
import sys
from pathlib import Path

# プロジェクトルートをPYTHONPATHに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import create_engine, text


def get_db_connection():
    """データベース接続を取得する"""
    db_host = os.getenv("DATABASE_HOST", "localhost")
    db_port = os.getenv("DATABASE_PORT", "5432")
    db_name = os.getenv("DATABASE_NAME", "nagare")
    db_user = os.getenv("DATABASE_USER", "nagare_user")
    db_password = os.getenv("DATABASE_PASSWORD", "")

    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(db_url)


def list_repositories(engine):
    """リポジトリ一覧を表示する"""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, repository_name, source, active, created_at
                FROM repositories
                ORDER BY active DESC, repository_name
                """
            )
        )
        print("\n監視対象リポジトリ:")
        print("-" * 80)
        print(f"{'ID':<6} {'リポジトリ名':<30} {'ソース':<20} {'状態':<8} {'作成日時'}")
        print("-" * 80)
        for row in result:
            status = "有効" if row.active else "無効"
            print(
                f"{row.id:<6} {row.repository_name:<30} {row.source:<20} "
                f"{status:<8} {row.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        print()


def add_repository(engine, repo_name: str, source: str = "github_actions"):
    """リポジトリを追加する"""
    # repository_nameから source_repository_id を生成（簡易版）
    # 実際のGitHub APIから取得する場合は別途実装が必要
    source_repo_id = repo_name.replace("/", "_")

    with engine.begin() as conn:
        # 既存チェック
        result = conn.execute(
            text(
                """
                SELECT id, active FROM repositories
                WHERE repository_name = :repo_name AND source = :source
                """
            ),
            {"repo_name": repo_name, "source": source},
        )
        existing = result.fetchone()

        if existing:
            if existing.active:
                print(f"❌ リポジトリ '{repo_name}' は既に登録されています")
                return
            else:
                # 無効状態のリポジトリを有効化
                conn.execute(
                    text(
                        """
                        UPDATE repositories
                        SET active = TRUE, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": existing.id},
                )
                print(f"✓ リポジトリ '{repo_name}' を有効化しました (ID: {existing.id})")
                return

        # 新規追加
        result = conn.execute(
            text(
                """
                INSERT INTO repositories (source_repository_id, source, repository_name, active)
                VALUES (:source_repo_id, :source, :repo_name, TRUE)
                RETURNING id
                """
            ),
            {
                "source_repo_id": source_repo_id,
                "source": source,
                "repo_name": repo_name,
            },
        )
        repo_id = result.fetchone()[0]
        print(f"✓ リポジトリ '{repo_name}' を追加しました (ID: {repo_id})")


def disable_repository(engine, repo_name: str, source: str = "github_actions"):
    """リポジトリを無効化する"""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE repositories
                SET active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE repository_name = :repo_name AND source = :source AND active = TRUE
                RETURNING id
                """
            ),
            {"repo_name": repo_name, "source": source},
        )
        row = result.fetchone()
        if row:
            print(f"✓ リポジトリ '{repo_name}' を無効化しました (ID: {row[0]})")
        else:
            print(f"❌ 有効なリポジトリ '{repo_name}' が見つかりませんでした")


def enable_repository(engine, repo_name: str, source: str = "github_actions"):
    """リポジトリを有効化する"""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE repositories
                SET active = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE repository_name = :repo_name AND source = :source AND active = FALSE
                RETURNING id
                """
            ),
            {"repo_name": repo_name, "source": source},
        )
        row = result.fetchone()
        if row:
            print(f"✓ リポジトリ '{repo_name}' を有効化しました (ID: {row[0]})")
        else:
            print(f"❌ 無効なリポジトリ '{repo_name}' が見つかりませんでした")


def main():
    parser = argparse.ArgumentParser(description="リポジトリ管理CLI")
    subparsers = parser.add_subparsers(dest="command", help="サブコマンド")

    # listコマンド
    subparsers.add_parser("list", help="リポジトリ一覧を表示")

    # addコマンド
    add_parser = subparsers.add_parser("add", help="リポジトリを追加")
    add_parser.add_argument("repository", help="リポジトリ名 (例: owner/repo)")
    add_parser.add_argument("--source", default="github_actions", help="ソース名")

    # disableコマンド
    disable_parser = subparsers.add_parser("disable", help="リポジトリを無効化")
    disable_parser.add_argument("repository", help="リポジトリ名 (例: owner/repo)")
    disable_parser.add_argument("--source", default="github_actions", help="ソース名")

    # enableコマンド
    enable_parser = subparsers.add_parser("enable", help="リポジトリを有効化")
    enable_parser.add_argument("repository", help="リポジトリ名 (例: owner/repo)")
    enable_parser.add_argument("--source", default="github_actions", help="ソース名")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        engine = get_db_connection()

        if args.command == "list":
            list_repositories(engine)
        elif args.command == "add":
            add_repository(engine, args.repository, args.source)
        elif args.command == "disable":
            disable_repository(engine, args.repository, args.source)
        elif args.command == "enable":
            enable_repository(engine, args.repository, args.source)

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
