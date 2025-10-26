#!/bin/bash
# =============================================================================
# Nagare Secrets Setup Script
# =============================================================================
#
# このスクリプトは.envファイルに強力なランダムパスワードを自動生成します。
#
# 生成される項目:
#   - DATABASE_PASSWORD     : PostgreSQLパスワード
#   - AIRFLOW_SECRET_KEY    : Airflow暗号化キー
#   - SUPERSET_SECRET_KEY   : Superset暗号化キー
#
# 使用方法:
#   ./scripts/setup-secrets.sh
#
# オプション:
#   --verify    : 設定の検証のみ実行（生成しない）
#   --help      : ヘルプを表示
#
# =============================================================================

set -e

ENV_FILE=".env"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Nagare Secrets Setup Script       ║${NC}"
echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo ""

# ヘルプ表示
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Generate secure random passwords for Nagare secrets."
    echo ""
    echo "Options:"
    echo "  --verify    Verify configuration only (do not generate)"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Generate secrets"
    echo "  $0 --verify           # Verify .env configuration"
    echo ""
    exit 0
}

# オプション解析
VERIFY_ONLY=false
for arg in "$@"; do
    case $arg in
        --help|-h)
            show_help
            ;;
        --verify)
            VERIFY_ONLY=true
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# .envファイルの存在確認
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error:${NC} .env file not found"
    echo ""
    echo "Please create .env first:"
    echo -e "  ${CYAN}cp .env.sample .env${NC}"
    echo ""
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

# 検証モードの場合はパスワード生成をスキップ
if [ "$VERIFY_ONLY" = false ]; then
    # パスワード生成
    echo -e "${BLUE}Generating secure random passwords...${NC}"
    echo ""

    DATABASE_PASSWORD=$(openssl rand -base64 32)
    AIRFLOW_SECRET_KEY=$(openssl rand -base64 32)
    SUPERSET_SECRET_KEY=$(openssl rand -base64 32)

    update_env_var "DATABASE_PASSWORD" "$DATABASE_PASSWORD" "$ENV_FILE"
    update_env_var "AIRFLOW_SECRET_KEY" "$AIRFLOW_SECRET_KEY" "$ENV_FILE"
    update_env_var "SUPERSET_SECRET_KEY" "$SUPERSET_SECRET_KEY" "$ENV_FILE"
else
    echo -e "${BLUE}Verification mode - skipping password generation${NC}"
    echo ""
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════${NC}"
if [ "$VERIFY_ONLY" = false ]; then
    echo -e "${GREEN}✅ Setup completed successfully!${NC}"
    echo -e "${CYAN}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✓${NC} Generated secure passwords in .env:"
    echo "  • DATABASE_PASSWORD     (32 characters)"
    echo "  • AIRFLOW_SECRET_KEY    (32 characters)"
    echo "  • SUPERSET_SECRET_KEY   (32 characters)"
    echo ""
else
    echo -e "${BLUE}Configuration Verification Report${NC}"
    echo -e "${CYAN}════════════════════════════════════════${NC}"
    echo ""
fi

# 設定の検証
echo -e "${BLUE}Verifying configuration...${NC}"
echo ""

# GitHub Token のチェック
if grep -q "^GITHUB_TOKEN=.\+" "$ENV_FILE"; then
    echo -e "${GREEN}✓${NC} GITHUB_TOKEN is set"
else
    echo -e "${YELLOW}⚠${NC} GITHUB_TOKEN is not set (required)"
    GITHUB_TOKEN_MISSING=true
fi

# Airflow Admin Password のチェック
if grep -q "^AIRFLOW_ADMIN_PASSWORD=.\+" "$ENV_FILE"; then
    echo -e "${GREEN}✓${NC} AIRFLOW_ADMIN_PASSWORD is set"
else
    echo -e "${YELLOW}⚠${NC} AIRFLOW_ADMIN_PASSWORD is not set (required)"
    AIRFLOW_PASSWORD_MISSING=true
fi

# Database Password のチェック（今生成したので必ずある）
if grep -q "^DATABASE_PASSWORD=.\+" "$ENV_FILE"; then
    echo -e "${GREEN}✓${NC} DATABASE_PASSWORD is set"
fi

# Airflow Secret Key のチェック（今生成したので必ずある）
if grep -q "^AIRFLOW_SECRET_KEY=.\+" "$ENV_FILE"; then
    echo -e "${GREEN}✓${NC} AIRFLOW_SECRET_KEY is set"
fi

# Superset Secret Key のチェック（今生成したので必ずある）
if grep -q "^SUPERSET_SECRET_KEY=.\+" "$ENV_FILE"; then
    echo -e "${GREEN}✓${NC} SUPERSET_SECRET_KEY is set"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo -e "${BLUE}Next Steps:${NC}"
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo ""

# まだ設定が必要な項目がある場合
if [ "$GITHUB_TOKEN_MISSING" = true ] || [ "$AIRFLOW_PASSWORD_MISSING" = true ]; then
    echo -e "${YELLOW}⚠  Additional configuration required:${NC}"
    echo ""

    if [ "$GITHUB_TOKEN_MISSING" = true ]; then
        echo -e "${YELLOW}1. Set GITHUB_TOKEN${NC}"
        echo "   • Open: https://github.com/settings/tokens"
        echo "   • Click: Generate new token (classic)"
        echo "   • Select scopes: repo, read:org, workflow"
        echo "   • Copy the token and add to .env:"
        echo -e "     ${CYAN}GITHUB_TOKEN=your_token_here${NC}"
        echo ""
    fi

    if [ "$AIRFLOW_PASSWORD_MISSING" = true ]; then
        echo -e "${YELLOW}2. Set AIRFLOW_ADMIN_PASSWORD${NC}"
        echo "   • Choose a strong password (16+ characters)"
        echo "   • Add to .env:"
        echo -e "     ${CYAN}AIRFLOW_ADMIN_PASSWORD=your_secure_password${NC}"
        echo ""
    fi

    echo -e "${BLUE}Then run:${NC}"
    echo "   docker compose up -d"
else
    echo -e "${GREEN}✅ All required settings are configured!${NC}"
    echo ""
    echo -e "${BLUE}You can now start the services:${NC}"
    echo "   docker compose up -d"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo -e "${BLUE}📚 Documentation:${NC}"
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo ""
echo "  • README.md - Full setup guide"
echo "  • .env.sample - Environment variables reference"
echo "  • connections.yml.sample - Alternative configuration"
echo "  • docs/02_design/adr/002-connection-management-architecture.md"
echo ""

echo -e "${CYAN}════════════════════════════════════════${NC}"
echo -e "${RED}⚠  Security Reminder:${NC}"
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo ""
echo -e "${RED}✗ Do NOT commit .env to version control!${NC}"
echo "  .env is already in .gitignore"
echo ""
echo "  Rotate secrets regularly (recommended: every 90 days)"
echo ""
