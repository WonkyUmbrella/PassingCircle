#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==========================================="
echo "  Passing Circle - Event Reset"
echo "==========================================="
echo ""
echo "This will DELETE all user data:"
echo "  - Synapse database + media"
echo "  - Authentik database + data"
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

echo "==> Removing data volumes..."
docker volume rm passingcircle_synapse-db passingcircle_synapse-media \
  passingcircle_authentik-db passingcircle_authentik-data 2>/dev/null || true

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
