# 実装タスク

## 1. 必須（MVP完成に必要）

- [x] Database接続ユーティリティ (`src/nagare/utils/database.py`) ✅
  - モックモード実装済み
  - PostgreSQL接続プール実装済み ✅
  - リポジトリ取得機能実装済み
  - UPSERT処理（冪等性の確保）実装済み ✅
  - トランザクション管理実装済み ✅
  - Context manager対応 ✅

- [x] load_to_databaseタスクの基本実装 (`src/nagare/tasks/load.py`) ✅
  - database.pyのメソッド呼び出し実装済み
  - バルクUPSERT実装済み ✅
  - トランザクション管理実装済み ✅

- [x] ジョブデータの取得・保存
  - `github_client.get_workflow_run_jobs()` の利用 ✅
  - jobsテーブルへのデータ保存 ✅
  - fetch_workflow_run_jobs()実装済み
  - transform_data()でジョブ変換対応
  - load_to_database()でupsert_jobs()呼び出し
  - DatabaseClientProtocolにupsert_jobs()追加
  - テストカバレッジ: 80% (52/52テスト成功)

- [x] ユニットテストの基本構造 (`tests/`)
  - モック用Protocol定義 (`src/nagare/utils/protocols.py`) ✅
  - モッククラスとフィクスチャ (`tests/conftest.py`) ✅
  - fetch.pyのテスト (`tests/tasks/test_fetch.py`) ✅
  - load.pyのテスト (`tests/tasks/test_load.py`) ✅
  - transform.pyのテスト (`tests/tasks/test_transform.py`) ✅
  - DAG読み込みテスト (`tests/dags/test_collect_github_actions_data.py`) ✅
  - 統合テスト（PostgreSQL接続込み）は今後の課題

- [x] Docker Compose環境 ✅
  - Airflow、Superset、PostgreSQLのローカル環境実装済み ✅
  - docker-compose.yml作成済み ✅
  - Dockerfile最適化（依存関係管理、PYTHONPATH設定）✅
  - 全サービスhealthy状態で稼働中 ✅

- [x] データベーススキーマ初期化 (`scripts/init_db.sql`) ✅
  - projects、repositories、pipeline_runs、jobsテーブル作成 ✅
  - 適切なインデックス設定 ✅
  - 外部キー制約とUNIQUE制約 ✅
  - 自動updated_atトリガー ✅

- [x] リポジトリ管理CLI (`scripts/manage_repositories.py`) ✅
  - リポジトリの追加・一覧・有効化・無効化機能 ✅
  - Docker環境での実行対応 ✅
  - セットアップドキュメント (`docs/03_setup/database_setup.md`) ✅

## 2. 推奨（運用改善）

- [ ] 統合テスト環境
  - PostgreSQL接続を含む統合テスト
  - Docker環境でのテスト自動化
  - テストデータのセットアップとクリーンアップ

- [ ] クリーンアップタスク（一時ファイル削除）
  - 古いワークフローデータの定期削除
  - ログファイルのローテーション

- [ ] 監視・アラート機能（Slack通知）
  - DAG実行失敗時の通知
  - データ収集エラーの通知
  - パフォーマンス異常検知

- [ ] エラーハンドリングの強化
  - GitHub API rate limit対策
  - リトライ処理の最適化
  - 部分的なデータ収集失敗時の継続処理

## 3. 将来的な拡張

- [ ] GitLab CI、CircleCI対応
  - 複数のCI/CDプラットフォーム統合
  - プラットフォーム共通のデータモデル

- [ ] 並列処理による高速化
  - リポジトリごとの並列データ収集
  - Airflow TaskGroup活用

- [ ] Row Level Securityによる権限管理
  - プロジェクト単位のアクセス制御
  - ユーザーロールベースの権限管理

- [ ] ダッシュボード機能の拡充
  - カスタムメトリクス表示
  - リアルタイムアラート
  - レポート自動生成

- [ ] データ分析機能
  - CI/CD実行トレンド分析
  - ボトルネック検出
  - コスト最適化提案
