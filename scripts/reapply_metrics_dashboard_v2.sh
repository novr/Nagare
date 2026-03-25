#!/usr/bin/env bash
# メトリクス v2 の DDL・ビュー・マート同期を再適用する。
# 前提: docker compose で postgres が起動済み（コンテナ名 nagare-postgres）
#
# 使い方:
#   chmod +x scripts/reapply_metrics_dashboard_v2.sh
#   ./scripts/reapply_metrics_dashboard_v2.sh
#   ./scripts/reapply_metrics_dashboard_v2.sh --with-superset   # Superset チャートも --reset 再作成
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WITH_SUPERSET=false
for arg in "$@"; do
  case "$arg" in
    --with-superset) WITH_SUPERSET=true ;;
  esac
done

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DATABASE_USER="${DATABASE_USER:-nagare_user}"
DATABASE_NAME="${DATABASE_NAME:-nagare}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-nagare-postgres}"
SUPERSET_CONTAINER="${SUPERSET_CONTAINER:-nagare-superset}"

if ! docker ps --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
  echo "ERROR: コンテナ '$POSTGRES_CONTAINER' が起動していません。"
  echo "  cp .env.sample .env を行い必要な値を入れたうえで: docker compose up -d"
  exit 1
fi

echo "==> Applying metrics v2 SQL (schema, refresh function, views)..."
for f in metrics_dashboard_v2_schema.sql metrics_dashboard_v2_refresh.sql metrics_dashboard_v2_views.sql; do
  echo "    ... $f"
  docker exec -i "$POSTGRES_CONTAINER" psql -U "$DATABASE_USER" -d "$DATABASE_NAME" -v ON_ERROR_STOP=1 \
    <"$ROOT/scripts/$f"
done

echo "==> Running refresh_cicd_metrics_marts(TRUE) (full)..."
docker exec -i "$POSTGRES_CONTAINER" psql -U "$DATABASE_USER" -d "$DATABASE_NAME" -v ON_ERROR_STOP=1 \
  -c "SELECT refresh_cicd_metrics_marts(TRUE);"

if [[ "$WITH_SUPERSET" == true ]]; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$SUPERSET_CONTAINER"; then
    echo "WARN: Superset コンテナ '$SUPERSET_CONTAINER' が無いためスキップしました。"
    exit 0
  fi
  echo "==> Superset ダッシュボード再作成 (--reset)..."
  # ベースイメージに /app/scripts が無いことがあるため /tmp を使う
  docker cp "$ROOT/scripts/setup_superset_dashboard.py" "$SUPERSET_CONTAINER:/tmp/setup_superset_dashboard.py"
  docker exec "$SUPERSET_CONTAINER" python3 /tmp/setup_superset_dashboard.py --reset
fi

echo "==> 完了"
