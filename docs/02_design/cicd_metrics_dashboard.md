# CI/CD メトリクスダッシュボード（設計・運用）

## 目的と成功条件

- **目的**: 日次レビューでパイプラインの悪化傾向を検知し、改善アクションを決める。
- **成功条件（PoC）**
  - 悪化したリポジトリを **3分以内** に候補として挙げられる。
  - リポジトリ詳細から、失敗の偏り（ワークフロー / ステップ）を **5分以内** に把握できる。
  - 各画面に **データ対象日・最終集計時刻** が明示されている。

## L1 / L2 の役割

| 層 | 役割 | 遷移条件 |
|----|------|----------|
| **L1 全体把握** | 全体KPI、日次トレンド、リポジトリ別ヘルス・悪化ランキング | 常に起点 |
| **L2 リポジトリ詳細** | 対象repoの時系列、失敗ワークフロー、実行時間、ステップヒートマップ、再実行傾向 | L1でrepo選択または行クリック |

## KPI とシグナル

| 種別 | 指標 | 備考 |
|------|------|------|
| KPI | 成功率 | `SUCCESS` / 全完了実行 |
| KPI | デイリー失敗件数 | `FAILURE` 等の集計 |
| KPI | 総実行数 | フィルタ内 |
| シグナル | 実行時間 p50 / p95 | `duration_ms` ベース |
| シグナル | 再実行率 | `is_retry` の割合（MVPはヒューリスティック） |
| シグナル | flake 疑い率 | MVP: 0 または簡易（将来拡張） |

**閾値（推奨）**: 固定閾値に加え、前日比・直近7日平均からの乖離で警告（実装は集計テーブル＋ビュー）。

## ワイヤー（配置順）

### L1

1. グローバルフィルタ: 期間（7/14/30日）、ブランチ種別、イベント種別、最終更新時刻
2. KPI 4枚: 総実行数、成功率、失敗件数、中央値実行時間
3. トレンド: 成功率・実行時間（p50/p95）
4. repoヘルス、悪化repoランキング
5. repo一覧テーブル → L2 へ

### L2

1. コンテキストバー: repo名、期間、前日比サマリー
2. KPI 4枚: repo成功率、失敗件数、p95、再実行率
3. Top failing / Longest workflows
4. 失敗理由内訳、ステップ失敗ヒートマップ
5. 再実行・flake傾向、アクション候補
6. 実行一覧テーブル

## 検証（日次レビュー想定）

- [ ] 任意の「悪化日」を想定し、L1で該当repoがランキングに載るか。
- [ ] L2で失敗ワークフローTopとステップヒートマップが矛盾なく読めるか。
- [ ] フィルタ変更後も指標の単位・日付境界（JST）が一貫しているか。
- [ ] `refresh_cicd_metrics_marts` 実行後、Superset / Streamlit の数値が一致するか。

## 関連ファイル

- スキーマ: [scripts/metrics_dashboard_v2_schema.sql](../../scripts/metrics_dashboard_v2_schema.sql)
- リフレッシュ: [scripts/metrics_dashboard_v2_refresh.sql](../../scripts/metrics_dashboard_v2_refresh.sql)
- ビュー: [scripts/metrics_dashboard_v2_views.sql](../../scripts/metrics_dashboard_v2_views.sql)
- DAG: `src/nagare/dags/refresh_cicd_metrics_marts.py`

## スケールとパーティション（将来）

- **増分同期**: `refresh_cicd_metrics_marts(FALSE)` は `pipeline_runs.updated_at` / `jobs.updated_at` と `metrics_mart_sync_state` のウォーターマークで差分のみ反映する。初回・修復は `refresh_cicd_metrics_marts(TRUE)`。
- **パーティション**: `fact_pipeline_run` を `started_at` の月次 RANGE で切る案は、保持期間が長く行数・refresh 時間が閾値を超えた段階で検討する（移行コストが大きいため MVP では未実施）。
