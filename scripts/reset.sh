#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==========================================="
echo "  Passing Circle - Event Reset"
echo "==========================================="
echo ""
echo "This will DELETE all user data:"
echo "  - Synapse database + media"
echo "  - Authentik database + media"
echo "  - Redis data"
echo ""
echo "PRESERVED:"
echo "  - config/passingcircle.yml"
echo "  - Generated secrets (in config)"
echo "  - TLS certificates"
echo "  - Synapse signing key"
echo ""
read -rp "Type 'RESET' to confirm: " CONFIRM

if [ "$CONFIRM" != "RESET" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "==> Stopping containers..."
cd "$PROJECT_DIR"
docker compose down 2>/dev/null || true

echo "==> Removing data directories..."
rm -rf "$PROJECT_DIR/data/synapse-db"
rm -rf "$PROJECT_DIR/data/synapse-media"
rm -rf "$PROJECT_DIR/data/authentik-db"
rm -rf "$PROJECT_DIR/data/authentik-media"
rm -rf "$PROJECT_DIR/data/redis"

echo "==> Recreating empty data directories..."
mkdir -p "$PROJECT_DIR/data/synapse-db"
mkdir -p "$PROJECT_DIR/data/synapse-media"
mkdir -p "$PROJECT_DIR/data/authentik-db"
mkdir -p "$PROJECT_DIR/data/authentik-media"
mkdir -p "$PROJECT_DIR/data/redis"

echo ""
echo "==========================================="
echo "  Reset complete."
echo ""
echo "  Start fresh with:"
echo "    docker compose up -d"
echo ""
echo "  Then initialize rooms:"
echo "    ./scripts/init-rooms.sh"
echo "==========================================="
