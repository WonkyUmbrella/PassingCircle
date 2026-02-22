#!/usr/bin/env bash
set -euo pipefail

# Apply Authentik blueprints in dependency order, then restart Synapse.
# Run this after 'docker compose up -d' on first boot or after a reset.

echo "==> Waiting for Authentik to be healthy..."
until docker compose exec -T passingcircle-authentik-server ak healthcheck >/dev/null 2>&1; do
    printf "."
    sleep 5
done
echo " ready"

echo "==> Applying blueprints..."
for bp in 00-brand 01-flow-auth 02-flow-enrollment 03-provider; do
    echo "    ${bp}"
    docker compose exec -T passingcircle-authentik-server \
        ak apply_blueprint "/blueprints/custom/${bp}.yaml" >/dev/null 2>&1
done

echo "==> Restarting Synapse (needs OIDC provider)..."
docker compose restart passingcircle-synapse

echo ""
echo "==> Bootstrap complete."
