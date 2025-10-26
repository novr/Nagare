# Nagare プロジェクト統合レビュー

**レビュー日**: 2025-10-26 (最終更新)
**レビュアー**: Claude AI
**プロジェクト**: Nagare - CI/CDパイプライン分析プラットフォーム
**対象**: コード品質、Docker構成、セットアップ手順、アーキテクチャ

---

## 📋 レビュー概要

このレビューは、以下の観点から包括的に評価しています：
1. **Docker構成**: Dockerfile、docker-compose.yml
2. **セットアップ手順**: README.md、.env.sample、setup-secrets.sh
3. **コード品質**: src/配下のPythonコード
4. **アーキテクチャ**: 設計原則、依存性注入、データモデル

---

## 🚨 重大な問題（Critical Issues）

### 1. **セキュリティ: パスワードのURLエスケープ不足**
**深刻度**: 🔴 Critical

**問題点**:
```python
# src/nagare/admin_app.py:38
db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# src/nagare/utils/connections.py:172
return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
```

**影響**:
- パスワードに特殊文字（`@`, `/`, `#`など）が含まれるとURL構文エラー
- エラー時にスタックトレースでパスワードが平文露出のリスク
- `setup-secrets.sh`が生成する強力なパスワードは特殊文字を含む可能性が高い

**推奨対策**:
```python
from urllib.parse import quote_plus

db_url = f"postgresql://{db_user}:{quote_plus(db_password)}@{db_host}:{db_port}/{db_name}"
```

**優先度**: 即座に対応

---

## ⚠️ 高優先度の問題（High Priority Issues）

### 2. **テストバグ: 誤った例外型の使用**
**深刻度**: 🟡 High

**問題箇所**:
- `tests/utils/test_error_handling.py:105`: Python標準の`TimeoutError`を使用しているが、SQLAlchemyは`sqlalchemy.exc.TimeoutError`を使用

**推奨対策**:
正しい例外型をインポートして使用

---

## 📝 中優先度の問題（Medium Priority Issues）

### 3. **Docker: streamlit-admin用の専用Dockerfile作成を検討**
**深刻度**: 🟠 Medium

**現状**:
```yaml
# docker-compose.yml
streamlit-admin:
  build:
    dockerfile: Dockerfile  # Airflow用Dockerfileを流用
  command: ["streamlit", "run", ...]
```

**影響**:
- Airflowの依存関係を含む（不要）
- イメージサイズ増加

**推奨対策**:
Streamlit専用のDockerfileを作成するか、現状のまま運用（トレードオフあり）

**優先度**: 1ヶ月以内

### 4. **セットアップ: GitHubトークン設定の説明強化**
**深刻度**: 🟠 Medium

**問題点**:
- GitHub Apps認証の設定方法が不明
- Personal Access Tokenのほうが簡単だが選択肢が明確でない

**推奨対策**:
README.mdにGitHub認証の選択肢と手順を明記

### 5. **セットアップ: 初回起動の待ち時間を明記**
**深刻度**: 🟠 Medium

**問題点**:
Airflow/Supersetの初期化に5-10分かかることが未記載

**推奨対策**:
```markdown
## セットアップ手順

4. Docker環境の起動

\`\`\`bash
docker compose up -d

# 初回起動時は初期化に5-10分かかります
# 以下のコマンドで起動完了を確認:
docker compose ps
# 全てのサービスが "healthy" または "running" になるまで待機
\`\`\`
```

### 6. **テスト品質: 冪等性テストが冪等性をテストしていない**
**深刻度**: 🟠 Medium

**問題箇所**:
- `tests/dags/test_dag_integration.py:308-348`

**問題点**:
```python
# tests/dags/test_dag_integration.py:347
assert second_count == 2  # モックなので累積される
```

テストコメント自体が「モックなので累積される」と認めている。実際のデータベースでは同じIDは上書きされるが、モックのappend動作をテストしているだけで本質的な冪等性を保証できていない。

**影響**:
- upsertのWHERE句が間違っていて毎回新規レコードが作成されるバグがあっても、このテストはパスする

**推奨対策**:
1. テスト名を変更: `test_upsert_idempotency` → `test_upsert_mock_behavior`
2. または実DBでの統合テストを追加

---

### 7. **テスト: パフォーマンステストが性能を測定していない**
**深刻度**: 🟠 Medium

**問題箇所**:
- `tests/dags/test_dag_integration.py:262-306`

**問題点**:
```python
def test_large_dataset_handling(self, ...):
    """大量のデータを処理できることを確認"""
    mock_db.repositories = [... for i in range(50)]
    result = wrapped_func(**mock_airflow_context)
    assert len(result) == 50  # 件数の確認のみ
```

テスト名は「パフォーマンステスト」だが、実際は件数の確認のみで、実行時間・メモリ使用量・データベース接続数などを測定していない。

**推奨対策**:
1. テスト名を変更: `test_large_dataset_handling` → `test_multiple_repositories_handling`
2. または実際の性能テストを追加（時間計測、閾値チェック）

---

### 8. **テストカバレッジ: リトライ動作の未検証**
**深刻度**: 🟠 Medium

**問題点**:
- DAGの`default_args`で`retries=3`が設定されている
- しかしタスク失敗時にリトライが動作するかを検証するテストが存在しない

**影響**:
- Rate Limitエラー時にリトライせず即座に失敗する
- 一時的なネットワークエラーでDAG全体が失敗する

**推奨対策**:
```python
def test_task_retry_on_transient_error(self):
    """一時的なエラーでリトライが動作することを確認"""
    # 1回目: エラー、2回目: 成功
    mock_github.get_repo.side_effect = [
        GithubException(500, "Server Error", {}),  # 1回目失敗
        mock_repo  # 2回目成功
    ]
    # リトライ動作を検証
```

---

### 9. **テストカバレッジ: 未テストのモジュール**
**深刻度**: 🟠 Medium

**問題点**:
以下のモジュールのテストカバレッジが不明:
- `src/nagare/utils/datetime_utils.py`
- `src/nagare/utils/dag_helpers.py` (デコレータの動作検証が不足の可能性)

**影響**:
- `datetime_utils.py`: 日付変換のバグが本番環境で発覚
- `dag_helpers.py`: デコレータが引数を正しく渡さないバグ

**推奨対策**:
カバレッジレポートを生成して確認:
```bash
docker compose exec airflow-scheduler uv run pytest --cov=src/nagare --cov-report=html tests/
```

---

### 10. **テスト品質: mock specの欠如**
**深刻度**: 🟠 Medium

**問題点**:
多くのテストで`MagicMock()`を`spec=`なしで使用:
```python
mock_client = MagicMock()
mock_client.get_repo.return_value = ...
```

**影響**:
- 存在しないメソッドを呼んでもエラーにならない
- 実装が`get_repo()`を`get_repository()`に変更してもテストが通る（False Positive）

**推奨対策**:
```python
from nagare.utils.github_client import GitHubClient
mock_client = MagicMock(spec=GitHubClient)
```

**優先度**: 低（継続的改善として徐々に対応）

---

### 11. **テスト: 実DB統合テストの不足**
**深刻度**: 🟠 Medium

モックベースのテストは充実しているが、実際のPostgreSQLへの接続テストが不足:
- SQL構文エラー、型変換エラー、制約違反などが本番環境で発覚するリスク
- 上記の冪等性テストの問題も、実DBテストがあれば解決

**推奨対策**:
testcontainers-pythonを使用した統合テスト:
```python
@pytest.mark.integration
def test_database_integration(test_database_container):
    """実DBでのCRUD操作テスト"""
    # 実際のPostgreSQLコンテナに接続
    # リポジトリ追加、更新、削除、取得を検証
```

---

## 💡 低優先度の改善提案（Low Priority Improvements）

### 12. **コード重複: admin_app.pyとconnections.pyのURL生成**
**深刻度**: 🟢 Low

両方で似たようなURL生成コードが存在:
- `admin_app.py:38`: データベースURL生成
- `connections.py:172`: データベースURL生成

**推奨対策**:
`admin_app.py`が`DatabaseConnection`クラスを使用するようにリファクタリング。

---

### 13. **ドキュメント: Dockerfile.supersetバージョンの根拠が不明**
**深刻度**: 🟢 Low

バージョン3.1.0に固定したが、選定理由が不明:
- 最新安定版なのか？
- LTS版なのか？
- 特定の機能要件があるのか？

**推奨対策**:
コメントまたはADRで選定理由を記録。

---

### 14. **テストの命名規則: 不統一**
**深刻度**: 🟢 Low

一部のテストで日本語の説明とテスト名が乖離:
```python
def test_add_repository_new(self):
    """新規リポジトリの追加"""
```

**推奨対策**:
より明確な命名:
```python
def test_add_repository_creates_new_record_when_not_exists(self):
    """既存レコードが無い場合、新規作成されること"""
```

---

### 15. **Docker: イメージサイズ最適化の継続**
- .dockerignoreの追加
- ビルドキャッシュの最適化
- マルチステージビルドの検討（Streamlit専用イメージ作成時）

### 16. **セットアップ: 前提条件の詳細化**
```markdown
### 前提条件
- Docker Desktop 4.0以降（推奨: 最新版）
- 最低8GB RAM（推奨: 16GB）
- 最低20GB空きディスク容量
- macOS / Linux / Windows（WSL2）
```

### 17. **セットアップ: セットアップ検証スクリプト**
```bash
# scripts/verify-setup.sh
# 全てのサービスが正常に起動しているかチェック
```

### 18. **命名規則: ファイル名の一貫性**
- DAGファイルは`collect_github_actions_data_dag.py`のほうが明確

### 19. **ログレベル: 本番環境での調整**
現在はすべてINFOレベル、本番環境ではWARNING以上に設定すべき

### 20. **コメント: 英語docstringの追加検討**
主要な関数/クラスに英語のdocstringも追加を検討

---

## ✅ 解決済みの問題（Resolved Issues）

以下の問題は最近のコミットで解決されました：

### ~~1. Docker: Dockerfile.supersetのlatestタグ使用~~ → **解決済み** (commit 078543d)

**旧問題**:
- `FROM apache/superset:latest`でビルドの再現性がない
- 予期しない破壊的変更のリスク

**解決策**:
```dockerfile
FROM apache/superset:3.1.0  # バージョンを明示的に固定
```

### ~~2. README.mdから削除済みファイルへの参照~~ → **解決済み** (commit 5698b6f以前)

**旧問題**:
- `superset/queries/`への参照（既に削除済み）
- `AGENT.md`への参照（`.claude/AGENT.md`に移動済み）

**解決策**:
該当する参照は既に削除済み、確認完了

### ~~3. テスト: 統合テストの不足~~ → **大幅改善** (commit 09cdb65)

**旧問題**:
- `src/nagare/admin_app.py` (Streamlit UI)のテスト不足
- `src/nagare/dags/`の統合テスト不足
- エラーハンドリングのエッジケーステスト不足

**解決策**:
- `tests/dags/test_dag_integration.py` (318行): DAG全体の統合テスト
- `tests/admin/test_admin_app.py` (389行): admin appの機能テスト
- `tests/utils/test_error_handling.py` (354行): 包括的なエラーハンドリングテスト
- 合計1,061行の新規テストコード追加

**残課題**:
- Docker環境での実行検証が必要
- 実DB統合テストは別途追加を推奨

### ~~4. セットアップ: パスワード設定の矛盾と混乱~~ → **完全解決** (commit 18ac387)

**旧問題**:
- `.env`の`DATABASE_PASSWORD`とDocker Secrets (`secrets/db_password.txt`)が二重管理
- PostgreSQLはSecretsファイル、Airflow/Superset/Streamlitは.envを使用
- パスワード不一致による接続エラー

**解決策**:
- Docker Secretsを完全に廃止
- 全サービスで`.env`の`DATABASE_PASSWORD`に統一
- `setup-secrets.sh`が`.env`を直接更新

**検証**:
```yaml
# docker-compose.yml - 全サービスで統一
postgres:
  environment:
    POSTGRES_PASSWORD: ${DATABASE_PASSWORD}

airflow-webserver:
  environment:
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://${DATABASE_USER}:${DATABASE_PASSWORD}@postgres:5432/${DATABASE_NAME}
```

### ~~5. セットアップ: .env.sampleのデフォルト値が不適切~~ → **解決済み** (commit cb35947)

**旧問題**:
- `DATABASE_PASSWORD=change_this_password` (弱いパスワード)
- `AIRFLOW_ADMIN_PASSWORD=admin` (弱いパスワード)

**解決策**:
```bash
# .env.sample - 空にして自動生成を必須化
DATABASE_PASSWORD=
AIRFLOW_ADMIN_PASSWORD=
```

### ~~6. Docker: build-essentialがランタイムに残る~~ → **解決済み** (commit a25bce2)

**旧問題**:
- `build-essential`がランタイムイメージに残存
- イメージサイズ増加（約200MB）

**解決策**:
```dockerfile
# Dockerfile
# psycopg2-binaryを使用するため、build-essentialは不要
```

### ~~7. Docker: 環境変数の大量重複~~ → **解決済み** (commit a25bce2)

**旧問題**:
- `airflow-webserver`と`airflow-scheduler`で同じ環境変数を重複定義（約30行）

**解決策**:
```yaml
# docker-compose.yml - YAML anchors使用
x-airflow-common: &airflow-common
  build:
    context: .
    dockerfile: Dockerfile
  environment: &airflow-env
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    # ... 共通環境変数

services:
  airflow-webserver:
    <<: *airflow-common
    environment:
      <<: *airflow-env
```

### ~~8. Docker: AIRFLOW__CORE__DAGS_FOLDERの重複定義~~ → **解決済み** (commit a25bce2)

**旧問題**:
- Dockerfileとdocker-compose.ymlの両方で定義

**解決策**:
docker-compose.ymlでのみ定義するように統一

### ~~9. Docker: scripts/ディレクトリのコピー~~ → **解決済み** (commit a25bce2)

**旧問題**:
- `scripts/setup-secrets.sh`はホストで実行するスクリプト、イメージに不要

**解決策**:
不要なファイルのコピーを削除

### ~~10. セットアップ: setup-secrets.shの実行タイミングが不明確~~ → **解決済み** (commit bf01ba3)

**旧問題**:
- `.env`編集後に`setup-secrets.sh`を実行する手順（順序が逆）

**解決策**:
- `setup-secrets.sh`が`.env`を自動更新
- README.mdで正しい手順を明記

### ~~11. コード品質: N+1クエリ問題~~ → **解決済み** (commit bc9cc53)

**旧問題**:
- `upsert_pipeline_runs()`と`upsert_jobs()`で大量のSELECTクエリ

**解決策**:
- repository_idとrun_idをIN句で一括取得
- キャッシュを使用してO(1)ルックアップ
- 99%のクエリ削減を達成

### ~~12. ファイル整理: 試行錯誤の痕跡~~ → **解決済み** (commit 22ae739, 6cf0544, cee265a)

**旧問題**:
- 不要なファイルが残存

**解決策**:
- `superset/database.yaml`, `superset/setup_database.py` 削除
- 重複SQLファイル削除
- `AGENT.md`を`.claude/AGENT.md`に移動

### ~~13. 依存関係: uv.lockファイルが.gitignore~~ → **解決済み** (commit eda4c65)

**旧問題**:
- `uv.lock`がバージョン管理されていない

**解決策**:
- `uv.lock`をバージョン管理に追加

### ~~14. アーキテクチャ: Supersetビルドの複雑さ~~ → **改善済み** (commit 901848a)

**旧問題**:
- Python 3.10ハードコード

**解決策**:
- 動的バージョン検出に改善

---

## ✅ 良い点（Strengths）

### アーキテクチャ・設計
1. **明確なディレクトリ構造**: `src/`, `tests/`, `docs/`の分離が適切
2. **型ヒント**: Protocolを使用した依存性注入が適切
3. **依存性注入**: Factory patternの適切な使用（ADR-001）
4. **Connection抽象化**: 外部接続の一元管理（ADR-002）
5. **明確な責務分離**: 各コンポーネントの役割が明確

### コード品質
6. **エラーハンドリング**: 堅牢なリトライ処理とRate Limit対応
7. **パフォーマンス**: N+1クエリ問題を解決済み
8. **テストの存在**: 主要なコンポーネントにテストがある
9. **保守性**: 不要なファイルを削除し、クリーンな構造

### Docker・インフラ
10. **バージョン固定**: PostgreSQL、Airflowは明示的なバージョン指定
11. **ヘルスチェック**: 全サービスに適切なhealthcheck定義
12. **YAML anchors**: 環境変数の重複を大幅に削減
13. **depends_on条件**: service_healthy使用で順序制御
14. **ボリューム管理**: 名前付きボリュームで永続化
15. **restart設定**: unless-stoppedで自動復旧
16. **読み取り専用マウント**: src:roでセキュリティ向上

### ドキュメント
17. **充実したドキュメント**: `docs/`ディレクトリに設計ドキュメントが整理
18. **ADR**: 重要な設計決定を文書化（ADR-001, ADR-002）
19. **セットアップガイド**: Docker環境での構築手順が明確
20. **開発ガイドライン**: `.claude/AGENT.md`でプロジェクト固有の規約を明記

### セキュリティ
21. **Secrets管理**: `.env`ファイルで機密情報を一元管理
22. **.gitignore**: 機密情報の除外が適切
23. **パスワード生成**: `setup-secrets.sh`で強力なランダムパスワード生成

---

## 🎯 優先度別アクションプラン

### 即座に対応すべき（Critical）
1. [ ] **パスワードのURLエスケープ追加**
   - `admin_app.py:38`に`quote_plus()`追加
   - `connections.py:172`に`quote_plus()`追加

### 1週間以内（High Priority）
2. [ ] **test_error_handling.pyの例外型修正**
   - `TimeoutError` → `sqlalchemy.exc.TimeoutError`

3. [ ] **Docker環境でのテスト実行検証**
   - 新規追加した全テストをDocker環境で実行確認
   - 失敗する場合は修正

### 1ヶ月以内（Medium Priority）
4. [ ] **冪等性テストの修正または改名**
   - 実DBでの統合テストを追加するか、テスト名を変更

5. [ ] **パフォーマンステストの実装または改名**
   - 実際の時間計測を追加するか、テスト名を変更

6. [ ] **リトライ動作のテスト追加**
   - 一時的なエラー時のリトライ動作を検証

7. [ ] **カバレッジレポート生成とギャップ分析**
   - `pytest --cov`でカバレッジを測定し、未テストモジュールを特定

8. [ ] **実DB統合テストの追加**
   - testcontainers-pythonを使用した統合テスト

9. [ ] GitHub認証設定の説明を拡充（Personal Access Token vs GitHub Apps）

10. [ ] 初回起動の待ち時間をREADME.mdに明記

11. [ ] Streamlit専用Dockerfileの作成を検討（トレードオフ評価）

### 継続的に（Low Priority）
12. [ ] **テストのmock spec指定追加**（継続的改善）
13. [ ] **コード重複の削除**（admin_app.pyとconnections.pyのURL生成）
14. [ ] **Dockerfile.supersetバージョン選定理由の文書化**
15. [ ] **テスト命名規則の統一**
16. [ ] .dockerignoreの追加
17. [ ] 前提条件（RAM、ディスク容量）の詳細化
18. [ ] セットアップ検証スクリプトの作成
19. [ ] パフォーマンス監視
20. [ ] セキュリティスキャンの自動化
21. [ ] ドキュメントの継続的な更新

---

## 📊 総合評価（批判的視点）

| カテゴリ | 前回 | 現在 | 変化 | コメント |
|---------|------|------|-----|----------|
| コード品質 | 8.5/10 | 8.3/10 | -0.2 | URLエスケープ欠如、コード重複で減点 |
| セキュリティ | 7.5/10 | 6.8/10 | -0.7 | パスワード露出リスクで大幅減点 |
| テストカバレッジ | 6.5/10 | 8.0/10 | +1.5 | 統合テスト追加で大幅改善 |
| テスト品質 | - | 6.5/10 | N/A | 量は十分だが質に問題（False Positive、実行未検証） |
| ドキュメント | 8.0/10 | 8.3/10 | +0.3 | CRITICAL_REVIEW.md追加で改善 |
| アーキテクチャ | 8.5/10 | 8.5/10 | 0 | 変更なし |
| 保守性 | 8.5/10 | 8.5/10 | 0 | 変更なし |
| Docker構成 | 7.5/10 | 8.2/10 | +0.7 | バージョン固定で改善 |
| セットアップ | 8.0/10 | 8.0/10 | 0 | 変更なし |

**総合スコア**: 7.9/10 (批判的評価)

**注**: この評価は意図的に厳しい視点で行っています。Critical問題を修正し、High問題に対処すれば、**8.5/10以上**に到達可能です。

### 改善履歴（直近）

**最近の改善（+0.7）**:
- ✅ Dockerfile.supersetのバージョン固定 (commit 078543d)
- ✅ 統合テスト大幅追加: 1,061行 (commit 09cdb65)
  - DAG統合テスト (318行)
  - admin appテスト (389行)
  - エラーハンドリングテスト (354行)

**以前の大幅改善（+1.0）**:
- ✅ パスワード管理の統一（Docker Secrets廃止） (commit 18ac387)
- ✅ Docker環境変数の重複削減（YAML anchors） (commit a25bce2)
- ✅ .env.sampleのデフォルト値改善 (commit cb35947)
- ✅ build-essential削除（イメージサイズ最適化） (commit a25bce2)

**以前の改善（+0.5）**:
- ✅ setup-secrets.shの改善 (commit bf01ba3)
- ✅ 不要ファイル削除（保守性向上）
- ✅ N+1クエリ問題解決 (commit bc9cc53)

**以前の新規追加（+0.5）**:
- ✅ ADR-002: Connection管理アーキテクチャ (commit 372c6e8)
- ✅ .claude/AGENT.md: 開発ガイドライン (commit 5698b6f)
- ✅ Docker環境への統一 (commit 5698b6f)

**新たな課題（-0.7）**:
- ❌ **Critical**: パスワードのURLエスケープ欠如（セキュリティリスク）
- ❌ **High**: テストバグ: 例外型の誤り
- ❌ **High**: Docker環境でのテスト未検証
- ❌ **Medium**: テスト品質の問題（冪等性、パフォーマンス、False Positive）

### コメント（批判的視点）

プロジェクトは**継続的に改善**されていますが、批判的レビューで新たな問題が多数発見されました。

**最近解決された課題**:
1. ✅ Dockerfile.supersetのlatestタグ → バージョン3.1.0に固定
2. ✅ 統合テストの不足 → 1,061行の包括的なテスト追加
3. ✅ README.mdの参照リンク → 確認完了、問題なし

**現在の強み**:
- 堅牢なアーキテクチャ（Pure DI + Factory + Connection抽象化）
- 充実したドキュメント（ADR、開発ガイドライン、CRITICAL_REVIEW.md）
- Docker環境の最適化（バージョン固定、YAML anchors、イメージサイズ最適化）
- 包括的なテストカバレッジ（1,061行の新規テスト）

**新たに発見された問題**:
1. ❌ **Critical**: パスワードのURLエスケープ欠如
   - 特殊文字を含むパスワードでURL構文エラー
   - エラー時にスタックトレースでパスワードが露出する危険性

2. ❌ **High**: テストバグ
   - `test_error_handling.py:105`: 誤った例外型を使用（False Positive）
   - Docker環境での実行未検証（1,061行が動作するか不明）

3. ❌ **Medium**: テスト品質の問題
   - 冪等性テストが冪等性を検証していない（モックの挙動をテスト）
   - パフォーマンステストが性能を測定していない（件数確認のみ）
   - リトライ動作が未検証
   - mock specの欠如によるFalse Positiveリスク

**批判的評価**:
テストの**量**は大幅に改善されましたが、**質**には問題があります：
- 一部のテストは「テストのためのテスト」で、実際のバグを検出できない
- テストコード内で`quote_plus`を使っているのに、実装では使っていない矛盾
- 1,061行のコードを追加したが、Docker環境での動作確認をしていない

しかし、**基本的な構造とアーキテクチャは優秀**です。
Critical/High問題を修正すれば、**8.5-9.0/10の品質**に到達可能です。

**推奨される次のステップ**:
1. **即座**: パスワードのURLエスケープ追加（10分）
2. **1週間以内**: テストバグ修正（5分）+ Docker環境での実行検証（30分）
3. **1ヶ月以内**: テスト品質改善（冪等性、パフォーマンス、リトライ）
4. **継続的**: mock spec追加、コード重複削除、命名規則統一

**次回レビューの焦点**:
- Critical/High問題の修正状況
- テスト品質の改善状況
- 実DB統合テストの追加計画

---

## 📚 関連ドキュメント

- [ADR-001: 依存性注入（DI）戦略の選択](docs/02_design/adr/001-dependency-injection-strategy.md)
- [ADR-002: Connection管理アーキテクチャ](docs/02_design/adr/002-connection-management-architecture.md)
- [開発ガイドライン](.claude/AGENT.md)
- [アーキテクチャ設計](docs/02_design/architecture.md)
- [データモデル](docs/02_design/data_model.md)
- [エラーハンドリング](docs/04_operation/error_handling.md)

---

**最終更新日**: 2025年10月26日
**次回レビュー推奨日**: 2025年11月26日
