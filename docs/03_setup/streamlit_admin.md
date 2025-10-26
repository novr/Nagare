# Streamlit管理画面セットアップガイド

リポジトリ管理とデータ監視のためのWeb UI。

## 概要

Streamlit管理画面は、以下の機能を提供します：

- **リポジトリ管理**: Web UIでの追加・有効化・無効化
- **ダッシュボード**: リポジトリ統計、パイプライン実行状況
- **実行履歴**: パイプライン実行履歴の閲覧とフィルタリング

## アクセス方法

```bash
# ブラウザでアクセス
http://localhost:8501
```

デフォルトポート: `8501` (`.env`の`STREAMLIT_PORT`で変更可能)

## 起動・停止

### Docker環境での起動

```bash
# 全サービス起動（Streamlit含む）
docker-compose up -d

# Streamlit管理画面のみ起動
docker-compose up -d streamlit-admin

# ステータス確認
docker-compose ps streamlit-admin
```

### 再起動

```bash
# 設定変更後の再起動
docker-compose restart streamlit-admin

# ログ確認
docker-compose logs -f streamlit-admin
```

### 停止

```bash
# Streamlit管理画面のみ停止
docker-compose stop streamlit-admin

# 完全削除（コンテナとイメージ）
docker-compose down
docker-compose build streamlit-admin
```

## 機能紹介

### 1. ダッシュボード 📊

システム全体の状況を一目で確認：

- **登録リポジトリ数**: 全体と有効リポジトリ数
- **パイプライン実行統計**: 直近24時間の実行回数と成功率
- **平均実行時間**: パフォーマンス指標
- **最近の実行履歴**: 最新20件の実行結果（色分け表示）

### 2. リポジトリ管理 📦

#### リポジトリの追加

1. 「➕ リポジトリを追加」を展開
2. `owner/repo` 形式でリポジトリ名を入力
3. 「追加」ボタンをクリック

**例**: `novr/CIPette`

#### リポジトリの有効化・無効化

- **有効化**: データ収集対象に含める
- **無効化**: データ収集を一時停止（データは保持）

各リポジトリの行にある「有効化」「無効化」ボタンで切り替え可能。

#### フィルタリング

- **すべて**: 全リポジトリ表示
- **有効のみ**: アクティブなリポジトリのみ
- **無効のみ**: 無効化されたリポジトリのみ

### 3. 実行履歴 📈

パイプライン実行履歴の詳細表示：

- **表示件数調整**: スライダーで10〜100件
- **ステータスフィルタ**: success、failure、その他
- **色分け表示**:
  - 🟢 成功: 緑背景
  - 🔴 失敗: 赤背景

## 開発時のデバッグ

コードを修正した後、変更を反映させる方法:

```bash
# Streamlitコンテナを再起動
docker-compose restart streamlit-admin

# コードを大幅に変更した場合は再ビルド
docker-compose build streamlit-admin
docker-compose up -d streamlit-admin
```

## トラブルシューティング

### 接続エラーが表示される

**症状**: "データ取得エラー" メッセージ

**確認事項**:
1. PostgreSQLコンテナが起動しているか
   ```bash
   docker-compose ps postgres
   ```

2. データベース接続情報が正しいか
   ```bash
   # .envファイルを確認
   grep DATABASE .env
   ```

3. データベースが初期化されているか
   ```bash
   # テーブルが存在するか確認
   docker exec -it nagare-postgres psql -U nagare_user -d nagare -c "\dt"
   ```

### コンテナが起動しない

```bash
# ログ確認
docker-compose logs streamlit-admin

# コンテナ再ビルド
docker-compose build --no-cache streamlit-admin
docker-compose up -d streamlit-admin
```

### ページが表示されない（404エラー）

**原因**: Streamlitの起動が完了していない

**解決方法**:
```bash
# ヘルスチェック確認
docker-compose ps streamlit-admin

# STATUS が "healthy" になるまで待つ（最大30秒）
```

### リポジトリ追加ができない

**症状**: "追加エラー" メッセージ

**確認事項**:
1. リポジトリ名が `owner/repo` 形式か
2. データベース接続が正常か
3. 既に同じリポジトリが登録されていないか

### 画面が更新されない

**解決方法**:
- ブラウザをリロード（Ctrl+R / Cmd+R）
- Streamlitの「Rerun」ボタンをクリック
- コンテナを再起動

## 環境変数

`.env`ファイルで設定可能：

```bash
# Streamlitポート（デフォルト: 8501）
STREAMLIT_PORT=8501

# データベースパスワード（必須）
DATABASE_PASSWORD=your_secure_password_here
```

**設定の管理方針**:
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER` は`docker-compose.yml`で管理
- `.env`には機密情報（パスワード、トークン）のみ記載
- カスタマイズする場合は`docker-compose.yml`を編集

## セキュリティ注意事項

### 本番環境での運用

1. **アクセス制限**
   ```yaml
   # docker-compose.ymlでポート公開を制限
   ports:
     - "127.0.0.1:8501:8501"  # ローカルホストのみ
   ```

2. **認証の追加**（将来的な拡張）
   - Streamlit Cloud認証
   - OAuth統合
   - リバースプロキシでの認証

3. **データベースパスワード**
   - `.env`ファイルを`.gitignore`に追加（既に設定済み）
   - 強固なパスワードを使用

## パフォーマンス最適化

### キャッシュ設定

Streamlitは`@st.cache_resource`でデータベース接続をキャッシュしています。

キャッシュクリア:
- UIの右上メニュー → "Clear cache"
- または`Ctrl+Shift+R` (Cmd+Shift+R)

### 大量データの表示

実行履歴の表示件数を調整してパフォーマンスを最適化：
- 少量（10-20件）: 高速表示
- 大量（50-100件）: データ分析向け

## 参考情報

- **Streamlitドキュメント**: https://docs.streamlit.io/
- **ソースコード**: `src/nagare/admin_app.py`
- **Docker設定**: `docker-compose.yml`
- **データベーススキーマ**: `docs/02_design/data_model.md`
