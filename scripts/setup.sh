#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building setup container..."
docker build -t passingcircle-setup -f "$PROJECT_DIR/scripts/Dockerfile.setup" "$PROJECT_DIR"

echo "==> Running setup (generate configs, certs, secrets)..."
docker run --rm \
    -v "$PROJECT_DIR:/project" \
    passingcircle-setup

echo ""
echo "==> Setup complete. Start services with:"
echo "    cd $PROJECT_DIR && docker compose up -d"
