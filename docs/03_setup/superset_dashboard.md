# Superset ダッシュボード（メトリクス v2）

CI/CD メトリクスは **`vw_l1_*` / `vw_l2_*` ビュー**とマート（`refresh_cicd_metrics_marts`）を前提とする。ダッシュボード slug は **`cicd-metrics-v2`**。

- URL: http://localhost:8088（認証は `.env` の `SUPERSET_ADMIN_*`）
- 設計の文脈: [cicd_metrics_dashboard.md](../02_design/cicd_metrics_dashboard.md)

## クイックセットアップ

1. **`airflow-init`** で `scripts/metrics_dashboard_v2_*.sql` が適用され、初回は `refresh_cicd_metrics_marts(TRUE)` が走る（手動適用は設計ドキュメントの SQL パス参照）。

2. **ダッシュボード生成**（Superset コンテナ内）:

```bash
docker cp scripts/setup_superset_dashboard.py nagare-superset:/tmp/setup_superset_dashboard.py
docker compose up -d superset
docker exec nagare-superset python3 /tmp/setup_superset_dashboard.py
```

`setup_superset_dashboard.py` は **Nagare アプリ DB の接続が無ければ** `.env` の `DATABASE_*` から登録する（Compose の `superset` サービスで `DATABASE_HOST=postgres` に上書き済み）。表示名の候補は `NAGARE_SUPERSET_DATABASE_NAME` → `Nagare PostgreSQL` → `nagare`。URI を直で渡す場合は `NAGARE_APP_SQLALCHEMY_URI`。

スクリプトは **Dataset 作成・カラム同期・チャート・`position_json`** まで行う。増分データ更新は DAG `refresh_cicd_metrics_marts` または `SELECT refresh_cicd_metrics_marts();`（修復時は `TRUE`）。

**L1 / L2 の読み方（可読性）**

1. **上からの並び**: **タブ**（L1 の成功率・実行数のみ）→ **L1リポジトリヘルス / L1悪化リポジトリ** → **L2**（リポジトリトレンド・ワークフロー系・失敗理由・再実行・アクション）。タブで切り替わるのは L1 の2枚だけ。
2. **L2** はタブの外に **1ブロック**（全タブ共通の同じスライス・リポジトリ粒度 `vw_l2_*`）。
3. Native Filter は **初期は空欄（＝絞りなし）**。**L1 Platform** / **L1 Tag** は対応する L1 タブ用。**Project** は L2（リポジトリ系）と L1 プロジェクト別に効く。**L1 Tag** は凡例が増えやすいので **1〜3 個程度**の選択を推奨。
4. **L1 Platform** はタブ「プラットフォーム別」の L1 のみ。タブ「All」の L1 は `platform` 列が無いため **対象外**。
5. L2 の凡例が多いときは **Repository** で絞り込み。

`--reset` で既存管理チャートの再作成など（詳細はスクリプト先頭の用法）。

## 再適用

```bash
./scripts/reapply_metrics_dashboard_v2.sh
./scripts/reapply_metrics_dashboard_v2.sh --with-superset   # Superset 側も作り直す場合
```

## 手動で DB 接続だけ足す場合

スクリプトが失敗するとき用。**Connect database** → PostgreSQL → ホスト `postgres`、DB `nagare`、ユーザー `.env` の `DATABASE_USER` / `DATABASE_PASSWORD`。表示名は上記候補のいずれか。

## トラブルシューティング

| 症状 | 見るところ |
|------|------------|
| `Could not load database driver: PostgresEngineSpec` | Superset イメージ再ビルド（`docker compose build superset`） |
| `Nagare 用 Database が見つかりません` | コンテナに `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME` が渡っているか（`env_file: .env`） |
| `no such service: #` | `docker compose up -d superset` と **同じ行に `#` コメントを付けない**（シェルによって `#` が引数になる） |
| チャートが空 | マート更新・`pipeline_runs` の有無、設計ドキュメントの検証チェックリスト |
| レイアウトが変わらない / ログの `GRID 行数` が 4 以外 | ホストの **`docker cp scripts/setup_superset_dashboard.py nagare-superset:/tmp/...` をやり直してから** スクリプト再実行（`/tmp` が古いままだと position_json が旧レイアウトのまま） |

接続・ネットワークの切り分け: `docker ps`、`docker network inspect nagare-network`、コンテナから `postgres` への到達。

## 関連

- [データモデル](../02_design/data_model.md)
- [データベースセットアップ](database_setup.md)
- [メトリクス検証チェックリスト](../04_operation/metrics_dashboard_validation.md)
- [Superset 公式](https://superset.apache.org/docs/intro)
