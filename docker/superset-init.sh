#!/bin/bash
# Superset初期化スクリプト
# docker-compose up時に自動実行され、管理者ユーザーの作成とDB初期化を行う

set -e

# 環境変数からSuperset管理者の認証情報を取得（デフォルト値付き）
ADMIN_USERNAME=${SUPERSET_ADMIN_USERNAME:-admin}
ADMIN_PASSWORD=${SUPERSET_ADMIN_PASSWORD:-admin}
ADMIN_EMAIL=${SUPERSET_ADMIN_EMAIL:-admin@example.com}
ADMIN_FIRSTNAME=${SUPERSET_ADMIN_FIRSTNAME:-Admin}
ADMIN_LASTNAME=${SUPERSET_ADMIN_LASTNAME:-User}

echo "Starting Superset initialization..."

# Superset設定ファイルを作成（環境変数からデータベース接続を読み取る）
echo "Creating Superset configuration..."
cat > /app/pythonpath/superset_config.py <<EOF
import os

# データベース接続設定（環境変数から取得）
SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')

# セキュリティキー
SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY')

# サンプルデータのロード無効化
SUPERSET_LOAD_EXAMPLES = os.getenv('SUPERSET_LOAD_EXAMPLES', 'no').lower() in ('yes', 'true', '1')
EOF

# データベースのマイグレーション
echo "Running database migrations..."
superset db upgrade

# 管理者ユーザーが既に存在するかチェック
if superset fab list-users | grep -q "$ADMIN_USERNAME"; then
    echo "Admin user '$ADMIN_USERNAME' already exists, skipping creation"
else
    echo "Creating admin user '$ADMIN_USERNAME'..."
    superset fab create-admin \
        --username "$ADMIN_USERNAME" \
        --firstname "$ADMIN_FIRSTNAME" \
        --lastname "$ADMIN_LASTNAME" \
        --email "$ADMIN_EMAIL" \
        --password "$ADMIN_PASSWORD"
    echo "Admin user created successfully"
fi

# Supersetの初期化（ロールとパーミッションの設定）
echo "Initializing Superset..."
superset init

echo "Superset initialization completed!"
echo "You can login with:"
echo "  Username: $ADMIN_USERNAME"
echo "  Password: $ADMIN_PASSWORD"
echo "  URL: http://localhost:8088"

# 元のentrypointを実行
exec /usr/bin/run-server.sh
