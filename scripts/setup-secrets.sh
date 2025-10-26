#!/bin/bash
# Dockerコンテナ用のSecretsファイルを生成するスクリプト

set -e

SECRETS_DIR="./secrets"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "Nagare Docker Secrets Setup"
echo "=================================="
echo

# secretsディレクトリの作成
if [ ! -d "$SECRETS_DIR" ]; then
    echo "Creating secrets directory..."
    mkdir -p "$SECRETS_DIR"
    chmod 700 "$SECRETS_DIR"
    echo -e "${GREEN}✓${NC} Secrets directory created"
else
    echo -e "${YELLOW}⚠${NC} Secrets directory already exists"
fi

# データベースパスワード
DB_PASSWORD_FILE="$SECRETS_DIR/db_password.txt"
if [ ! -f "$DB_PASSWORD_FILE" ]; then
    echo
    echo "Enter database password (or press Enter to generate a random one):"
    read -s DB_PASSWORD
    if [ -z "$DB_PASSWORD" ]; then
        DB_PASSWORD=$(openssl rand -base64 32)
        echo -e "${GREEN}✓${NC} Generated random database password"
    fi
    echo -n "$DB_PASSWORD" > "$DB_PASSWORD_FILE"
    chmod 600 "$DB_PASSWORD_FILE"
    echo -e "${GREEN}✓${NC} Database password saved to $DB_PASSWORD_FILE"
else
    echo -e "${YELLOW}⚠${NC} Database password file already exists"
fi

# Airflow Secret Key
AIRFLOW_KEY_FILE="$SECRETS_DIR/airflow_secret_key.txt"
if [ ! -f "$AIRFLOW_KEY_FILE" ]; then
    AIRFLOW_KEY=$(openssl rand -base64 32)
    echo -n "$AIRFLOW_KEY" > "$AIRFLOW_KEY_FILE"
    chmod 600 "$AIRFLOW_KEY_FILE"
    echo -e "${GREEN}✓${NC} Airflow secret key generated and saved"
else
    echo -e "${YELLOW}⚠${NC} Airflow secret key file already exists"
fi

# Superset Secret Key
SUPERSET_KEY_FILE="$SECRETS_DIR/superset_secret_key.txt"
if [ ! -f "$SUPERSET_KEY_FILE" ]; then
    SUPERSET_KEY=$(openssl rand -base64 32)
    echo -n "$SUPERSET_KEY" > "$SUPERSET_KEY_FILE"
    chmod 600 "$SUPERSET_KEY_FILE"
    echo -e "${GREEN}✓${NC} Superset secret key generated and saved"
else
    echo -e "${YELLOW}⚠${NC} Superset secret key file already exists"
fi

echo
echo "=================================="
echo "Updating .env file..."
echo "=================================="

ENV_FILE=".env"

# .envファイルが存在しない場合は.env.sampleからコピー
if [ ! -f "$ENV_FILE" ]; then
    if [ -f ".env.sample" ]; then
        cp .env.sample "$ENV_FILE"
        echo -e "${GREEN}✓${NC} Created .env from .env.sample"
    else
        echo -e "${RED}✗${NC} .env.sample not found, creating new .env"
        touch "$ENV_FILE"
    fi
fi

# 生成されたパスワード/キーを読み込み
DB_PASSWORD=$(cat "$DB_PASSWORD_FILE")
AIRFLOW_KEY=$(cat "$AIRFLOW_KEY_FILE")
SUPERSET_KEY=$(cat "$SUPERSET_KEY_FILE")

# .envファイルを更新（既存の値があれば置換、なければ追加）
update_env_var() {
    local key=$1
    local value=$2
    local file=$3

    # エスケープ処理（/や特殊文字をエスケープ）
    local escaped_value=$(printf '%s\n' "$value" | sed 's/[\/&]/\\&/g')

    if grep -q "^${key}=" "$file"; then
        # 既存の行を置換（macOS/Linux互換）
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^${key}=.*|${key}=${escaped_value}|" "$file"
        else
            sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"
        fi
        echo -e "${GREEN}✓${NC} Updated ${key} in .env"
    else
        # 新しい行を追加
        echo "${key}=${value}" >> "$file"
        echo -e "${GREEN}✓${NC} Added ${key} to .env"
    fi
}

update_env_var "DATABASE_PASSWORD" "$DB_PASSWORD" "$ENV_FILE"
update_env_var "SUPERSET_SECRET_KEY" "$SUPERSET_KEY" "$ENV_FILE"

echo
echo "=================================="
echo -e "${GREEN}Setup completed!${NC}"
echo "=================================="
echo
echo "Secret files created in $SECRETS_DIR:"
echo "  - db_password.txt"
echo "  - airflow_secret_key.txt"
echo "  - superset_secret_key.txt"
echo
echo ".env file updated with:"
echo "  - DATABASE_PASSWORD"
echo "  - SUPERSET_SECRET_KEY"
echo
echo -e "${RED}IMPORTANT:${NC} Do not commit these files to version control!"
echo "Both $SECRETS_DIR and .env are included in .gitignore"
echo
