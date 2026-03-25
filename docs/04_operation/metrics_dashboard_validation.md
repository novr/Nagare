# CI/CD メトリクスダッシュボード検証チェックリスト

日次レビュー想定の確認手順。詳細は [cicd_metrics_dashboard.md](../02_design/cicd_metrics_dashboard.md) を参照。

## 事前条件

- [ ] `scripts/metrics_dashboard_v2_schema.sql` / `*_refresh.sql` / `*_views.sql` が適用済み
- [ ] DAG `refresh_cicd_metrics_marts`（増分）または `SELECT refresh_cicd_metrics_marts();` が成功している（初回・修復時は `TRUE`）
- [ ] `pipeline_runs` に対象期間のデータがある

## L1（全体把握）

- [ ] 最終日の総実行数・成功率・失敗数が妥当
- [ ] 成功率・実行数のトレンドが日付昇順で読める
- [ ] リポジトリヘルス表に直近7日の指標が出る
- [ ] `deterioration_flag` が期待どおり（急落・失敗増・p95悪化）で立つ

## L2（リポジトリ詳細）

- [ ] リポジトリ選択で日次トレンドが切り替わる
- [ ] 失敗ワークフロー Top と実行時間 Top が矛盾なく読める
- [ ] 失敗理由・ステップ表が空でない（失敗実行がある場合）
- [ ] アクション候補に優先度が付いている

## Superset（任意）

- [ ] ダッシュボード `cicd-metrics-v2` が開ける
- [ ] Native Filter「Repository」で L2 系チャートが絞り込める
- [ ] Native Filter「L1 Platform」で L1 系（`vw_l1_daily_overview_by_platform` 由来）が期待どおり絞り込める

## 記録

| 日付 | 実施者 | 結果 | メモ |
|------|--------|------|------|
|      |        |      |      |
