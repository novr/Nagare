# ADR-003: Bitrise Client実装戦略

## ステータス

採用 (2025-10-27)

## コンテキスト

Nagareの対応CI/CDプラットフォームにBitriseを追加する必要がある。Bitrise APIは公式のOpenAPI仕様を提供しており、複数の実装アプローチが考えられる。

### Bitrise API概要

- **バージョン**: v0.1
- **ベースURL**: https://api.bitrise.io/v0.1
- **認証**: Personal Access Token
- **OpenAPI仕様**: https://api-docs.bitrise.io/docs/swagger.json

### 必要な機能

- アプリ一覧取得 (GET /apps)
- ビルド一覧取得 (GET /apps/{app-slug}/builds)
- ビルド詳細取得 (GET /apps/{app-slug}/builds/{build-slug})
- ビルドログ取得 (GET /apps/{app-slug}/builds/{build-slug}/log)

## 検討した選択肢

### 選択肢1: 既存のPythonパッケージを使用

**パッケージ**: `bitrise` (https://pypi.org/project/bitrise/)

**メリット**:
- 即座に利用可能
- PyPI経由でインストール可能

**デメリット**:
- **最終更新: 2018年6月（7年前）**
- メンテナンスされていない（17コミット、3 stars、2 forks）
- 機能が限定的（apps, builds, artifactsのみ）
- 活発度が非常に低い
- Bitrise APIのアップデートに追従していない可能性

**判断**: ❌ 使用不可 - メンテナンス放棄状態

### 選択肢2: OpenAPI仕様から自動生成

**ツール**: openapi-generator-cli, datamodel-code-generator, openapi-python-client

**メリット**:
- 完全なAPI対応
- 型安全な実装
- API変更時の自動更新

**デメリット**:
- ビルドプロセスの複雑化
- 生成コードのカスタマイズが困難
- 必要以上の機能が含まれる（オーバーキル）
- 生成コードの品質が保証されない
- プロジェクトの依存関係増加

**判断**: ⚠️ 現時点では過剰 - 必要な機能が限定的

### 選択肢3: 手動実装（GitHubClientパターン踏襲）

**実装方針**:
- `requests`ライブラリを使用
- GitHubClientと同じアーキテクチャパターン
- 必要な機能のみ実装

**メリット**:
- **GitHubClientとの一貫性** - 同じパターンでメンテナンスしやすい
- **シンプル** - 必要な機能のみ実装
- **依存関係が少ない** - requestsのみ（既存依存）
- **カスタマイズが容易** - Nagareの要件に最適化
- **学習コストが低い** - チーム内で既に使用しているパターン

**デメリット**:
- API変更時の手動更新が必要
- 新しいエンドポイント追加時の手動実装

**判断**: ✅ 採用

## 決定

**選択肢3（手動実装）を採用する**

### 実装方針

1. **BitriseConnection**: ADR-002に準拠した接続設定クラス
2. **BitriseClient**: requestsベースのAPIクライアント
3. **BitriseClientProtocol**: 型安全性のためのプロトコル定義
4. **エラーハンドリング**: GitHubClientと同様のリトライ・タイムアウト処理

### 実装ファイル

```
src/nagare/utils/
├── connections.py         # BitriseConnection追加
├── bitrise_client.py      # BitriseClient実装（新規）
└── factory.py             # ClientFactory更新
```

## 理由

### 1. 既存パッケージは使用不可

- 7年間メンテナンスなし
- Bitrise APIの最新機能に対応していない可能性
- セキュリティリスク

### 2. OpenAPI生成は現時点で過剰

- 必要な機能は4エンドポイントのみ
- 生成コードの複雑性 >> プロジェクトの要件
- ビルドプロセスの複雑化は避けたい

### 3. GitHubClientとの一貫性が重要

```python
# GitHubClient と BitriseClient で同じパターン
with GitHubClient(connection=github_conn) as client:
    runs = client.get_workflow_runs(owner, repo)

with BitriseClient(connection=bitrise_conn) as client:
    builds = client.get_builds(app_slug)
```

- **学習コストの削減**: 同じパターンで統一
- **メンテナンス性**: 同じアプローチで問題解決
- **コードレビュー**: レビュアーが理解しやすい

### 4. プロジェクトの規模に適している

- 小〜中規模プロジェクト
- シンプルさを重視
- 過度な抽象化を避ける

## 結果

### ポジティブな影響

- ✅ GitHubClientと同じパターンで統一された実装
- ✅ 必要最小限の依存関係（requestsのみ）
- ✅ カスタマイズが容易
- ✅ チーム内での理解・メンテナンスが容易

### ネガティブな影響

- ⚠️ API変更時の手動更新が必要
- ⚠️ 新規エンドポイント追加時の手動実装

### 軽減策

- **OpenAPI仕様の定期確認**: 四半期ごとにAPI変更をチェック
- **テストカバレッジ**: BitriseClientの動作を保証
- **将来の見直し**: 必要な機能が10エンドポイント以上になった場合、OpenAPI生成を再検討

## 関連ADR

- [ADR-001: Dependency Injection Strategy](001-dependency-injection-strategy.md) - DIパターンに準拠
- [ADR-002: Connection Management Architecture](002-connection-management-architecture.md) - Connection設計に準拠

## 参考資料

- [Bitrise API Documentation](https://api-docs.bitrise.io/)
- [Bitrise OpenAPI Specification](https://api-docs.bitrise.io/docs/swagger.json)
- [PyPI bitrise package](https://pypi.org/project/bitrise/) - 採用しなかったパッケージ
- [GitHub: BrandonBlair/bitrise](https://github.com/BrandonBlair/bitrise) - 最終更新2018年
