#!/bin/bash
# .envファイルに強力なランダムパスワードを生成するスクリプト

set -e

ENV_FILE=".env"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "Nagare Secrets Setup"
echo "=================================="
echo

# .envファイルの存在確認
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error:${NC} .env file not found"
    echo "Please create .env first:"
    echo "  cp .env.sample .env"
    exit 1
fi

# openssl の存在確認
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Error:${NC} openssl is not installed"
    echo "Please install openssl first"
    exit 1
fi

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
        echo -e "${GREEN}✓${NC} Updated ${key}"
    else
        # 新しい行を追加
        echo "${key}=${value}" >> "$file"
        echo -e "${GREEN}✓${NC} Added ${key}"
    fi
}

# パスワード生成
echo "Generating secure random passwords..."
echo

DATABASE_PASSWORD=$(openssl rand -base64 32)
AIRFLOW_SECRET_KEY=$(openssl rand -base64 32)
SUPERSET_SECRET_KEY=$(openssl rand -base64 32)

update_env_var "DATABASE_PASSWORD" "$DATABASE_PASSWORD" "$ENV_FILE"
update_env_var "AIRFLOW_SECRET_KEY" "$AIRFLOW_SECRET_KEY" "$ENV_FILE"
update_env_var "SUPERSET_SECRET_KEY" "$SUPERSET_SECRET_KEY" "$ENV_FILE"

echo
echo "=================================="
echo -e "${GREEN}Setup completed!${NC}"
echo "=================================="
echo
echo "Generated secure passwords in .env:"
echo "  - DATABASE_PASSWORD"
echo "  - AIRFLOW_SECRET_KEY"
echo "  - SUPERSET_SECRET_KEY"
echo
echo "Next steps:"
echo "  1. Edit .env and set GITHUB_TOKEN and AIRFLOW_ADMIN_PASSWORD"
echo "  2. Run: docker compose up -d"
echo
echo -e "${RED}IMPORTANT:${NC} Do not commit .env to version control!"
echo ".env is included in .gitignore"
echo
