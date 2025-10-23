# Architecture Decision Records (ADR)

このディレクトリには、Nagareプロジェクトの重要なアーキテクチャ決定を記録したADRが格納されています。

## ADRとは

Architecture Decision Record (ADR) は、アーキテクチャ上の重要な決定とその理由を文書化する軽量な記録方式です。

### ADRの目的

- **意思決定の透明性**: なぜその技術を選んだのかを明確化
- **知識の共有**: チームメンバー間での知識共有
- **将来の参考**: 同様の問題に直面した際の参考資料
- **変更の追跡**: 技術選定の変遷を記録

## ADRの構造

各ADRは以下の構造を持ちます：

```markdown
# ADR-XXX: タイトル

## ステータス
Accepted / Rejected / Deprecated / Superseded

## コンテキスト
- 問題の背景
- 制約条件
- プロジェクト特性

## 決定内容
- 選択した解決策
- 実装方針

## 結果（Consequences）
- ポジティブな影響
- ネガティブな影響
- トレードオフ

## 見直し条件
- 再評価のトリガー
- 次回レビュー日
```

---

## ADRの作成プロセス

### 1. 問題の特定
重要なアーキテクチャ決定が必要になった時

例:
- 新しいライブラリの導入
- アーキテクチャパターンの選択
- 技術スタックの変更

### 2. 選択肢の調査
- 複数の解決策を検討
- メリット・デメリットを比較
- プロジェクト特性との適合性を評価

### 3. ADRの作成
```bash
# 次のADR番号を確認
ls docs/02_design/adr/ | grep "^[0-9]" | tail -1

# 新しいADRファイルを作成
touch docs/02_design/adr/00X-title.md
```

### 4. レビューと承認
- チームメンバーによるレビュー
- プロジェクトオーナーの承認

### 5. 実装
ADRで決定した内容を実装

### 6. 定期的な見直し
- 四半期ごとに各ADRをレビュー
- 状況変化に応じて更新またはSupersede

---

## ADRのステータス

### ✅ Accepted
- 承認され、現在採用されている決定

### ❌ Rejected
- 検討されたが採用されなかった決定

### 🔄 Superseded
- 新しいADRによって置き換えられた決定
- 例: "Superseded by ADR-XXX"

### 🚫 Deprecated
- 非推奨となった決定
- 段階的に廃止予定

---

## 命名規則

```
[番号]-[タイトル].md
```

**例**:
- `001-dependency-injection-strategy.md`
- `002-database-migration-strategy.md`
- `003-api-versioning-approach.md`

### 番号付けルール
- 001から開始
- 3桁のゼロパディング
- 連番（欠番なし）

---

## 付録ファイルの管理

大量の詳細情報は付録ファイルに分離:

```
001-dependency-injection-strategy.md        # メイン
001-appendix-di-comparison-matrix.md        # 付録: 比較表
001-appendix-di-implementation-examples.md  # 付録: 実装例
```

**メリット**:
- メインADRが簡潔
- 詳細情報は必要に応じて参照
- 保守性向上

---

## レビュースケジュール

### 定期レビュー
- **頻度**: 四半期ごと
- **対象**: 全てのAcceptedステータスのADR
- **内容**:
  - 前提条件の変化確認
  - 再評価条件の確認
  - ステータス更新

### トリガーベースレビュー
以下のイベント発生時に即座にレビュー:
- 技術スタックの大幅変更
- チーム構成の変更
- プロジェクト規模の大幅変化
- 外部依存ライブラリの重大な更新

---

## 参考資料

### ADRについて
- [ADR GitHub](https://adr.github.io/)
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR Tools](https://github.com/npryce/adr-tools)

### テンプレート
- [Michael Nygard's ADR Template](https://github.com/joelparkerhenderson/architecture-decision-record/blob/main/templates/decision-record-template-by-michael-nygard/index.md)

---

## よくある質問（FAQ）

### Q1: どのような決定をADRに記録すべきか？

**A**: 以下のような重要な技術的決定:
- 技術スタックの選択
- アーキテクチャパターンの採用
- ライブラリ・フレームワークの選定
- データモデルの設計方針
- セキュリティ方針

**記録しないもの**:
- 軽微なコード変更
- バグ修正
- 一時的な実装の詳細

---

### Q2: ADRは変更できるか？

**A**: はい、ただし変更ではなく新しいADRで置き換える:
- 元のADRを "Superseded by ADR-XXX" に更新
- 新しいADRを作成し、理由を記載

---

### Q3: Rejectedの決定も記録すべきか？

**A**: はい、重要な決定は採用されなかった場合も記録:
- なぜ採用されなかったかを明記
- 将来同じ議論を繰り返さない
- チームの学習として残す

---

## 連絡先

ADRに関する質問やフィードバック:
- プロジェクトオーナーに連絡
- GitHubのIssueで議論

---

**作成日**: 2025年10月22日
**最終更新**: 2025年10月22日
**メンテナー**: プロジェクトオーナー
