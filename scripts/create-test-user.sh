#!/usr/bin/env bash
set -euo pipefail

# Registers a test user via Synapse's shared-secret registration API.
# Usage: ./scripts/create-test-user.sh [username] [password]

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$PROJECT_DIR/config/passingcircle.yml"

USERNAME="${1:-testuser}"
PASSWORD="${2:-testpassword}"

# Extract domain and shared secret from config
DOMAIN=$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c['network']['domain'])")
SHARED_SECRET=$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c['secrets']['synapse_registration_shared_secret'])")

# Generate HMAC for registration
generate_mac() {
    local nonce="$1"
    printf '%s\0%s\0%s\0%s' "$nonce" "$USERNAME" "$PASSWORD" "notadmin" \
        | openssl dgst -sha1 -hmac "$SHARED_SECRET" -hex | awk '{print $NF}'
}

echo "Registering user '$USERNAME' on $DOMAIN..."

# Get nonce
NONCE=$(curl -sk "https://$DOMAIN/_synapse/admin/v1/register" | python3 -c "import sys,json; print(json.load(sys.stdin)['nonce'])")

MAC=$(generate_mac "$NONCE")

# Register
curl -sk -X POST "https://$DOMAIN/_synapse/admin/v1/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"nonce\": \"$NONCE\",
        \"username\": \"$USERNAME\",
        \"password\": \"$PASSWORD\",
        \"mac\": \"$MAC\",
        \"admin\": false
    }"

echo ""
echo "Done. User '$USERNAME' registered."
