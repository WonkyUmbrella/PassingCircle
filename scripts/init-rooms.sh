#!/usr/bin/env bash
set -euo pipefail

# Initializes rooms after Synapse is running:
# 1. Registers the admin user via shared secret
# 2. Promotes admin to Synapse server admin
# 3. Sets power levels for announce_only rooms

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$PROJECT_DIR/config/passingcircle.yml"

DOMAIN=$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c['network']['domain'])")
SHARED_SECRET=$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c['secrets']['synapse_registration_shared_secret'])")
ADMIN_USERNAME=$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c['admins'][0]['username'])")
ADMIN_PASSWORD=$(python3 -c "
import yaml, secrets, string
c = yaml.safe_load(open('$CONFIG'))
# Use a deterministic password derived from the shared secret for the admin
print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))
")

BASE_URL="https://$DOMAIN"

echo "==> Waiting for Synapse to be ready..."
for i in $(seq 1 30); do
    if curl -sk "$BASE_URL/_matrix/client/v3/login" >/dev/null 2>&1; then
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

# --- Register admin user ---
echo "==> Registering admin user '$ADMIN_USERNAME'..."
NONCE=$(curl -sk "$BASE_URL/_synapse/admin/v1/register" | python3 -c "import sys,json; print(json.load(sys.stdin)['nonce'])")

MAC=$(printf '%s\0%s\0%s\0%s' "$NONCE" "$ADMIN_USERNAME" "$ADMIN_PASSWORD" "admin" \
    | openssl dgst -sha1 -hmac "$SHARED_SECRET" -hex | awk '{print $NF}')

REGISTER_RESULT=$(curl -sk -X POST "$BASE_URL/_synapse/admin/v1/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"nonce\": \"$NONCE\",
        \"username\": \"$ADMIN_USERNAME\",
        \"password\": \"$ADMIN_PASSWORD\",
        \"mac\": \"$MAC\",
        \"admin\": true
    }" 2>&1)

echo "  $REGISTER_RESULT"

# --- Get admin access token ---
echo "==> Logging in as admin..."
LOGIN_RESULT=$(curl -sk -X POST "$BASE_URL/_matrix/client/v3/login" \
    -H "Content-Type: application/json" \
    -d "{
        \"type\": \"m.login.password\",
        \"identifier\": {\"type\": \"m.id.user\", \"user\": \"$ADMIN_USERNAME\"},
        \"password\": \"$ADMIN_PASSWORD\"
    }")

ACCESS_TOKEN=$(echo "$LOGIN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# --- Configure announce_only rooms ---
echo "==> Configuring announce-only rooms..."

# Parse rooms from config
python3 -c "
import yaml, json
c = yaml.safe_load(open('$CONFIG'))
for room in c.get('rooms', []):
    if room.get('announce_only', False):
        print(room['id'])
" | while read -r ROOM_ID; do
    FULL_ROOM_ALIAS="#${ROOM_ID}:${DOMAIN}"
    echo "  Setting announce-only for $FULL_ROOM_ALIAS"

    # Resolve room alias to room ID
    ENCODED_ALIAS=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$FULL_ROOM_ALIAS', safe=''))")
    ROOM_RESOLVE=$(curl -sk "$BASE_URL/_matrix/client/v3/directory/room/$ENCODED_ALIAS" \
        -H "Authorization: Bearer $ACCESS_TOKEN")
    MATRIX_ROOM_ID=$(echo "$ROOM_RESOLVE" | python3 -c "import sys,json; print(json.load(sys.stdin)['room_id'])")

    if [ -z "$MATRIX_ROOM_ID" ] || [ "$MATRIX_ROOM_ID" = "None" ]; then
        echo "  WARNING: Could not resolve room $FULL_ROOM_ALIAS, skipping"
        continue
    fi

    # Get current power levels
    POWER_LEVELS=$(curl -sk "$BASE_URL/_matrix/client/v3/rooms/$MATRIX_ROOM_ID/state/m.room.power_levels" \
        -H "Authorization: Bearer $ACCESS_TOKEN")

    # Update power levels: set events_default to 50 (only moderators+ can send)
    UPDATED=$(echo "$POWER_LEVELS" | python3 -c "
import sys, json
pl = json.load(sys.stdin)
pl['events_default'] = 50
print(json.dumps(pl))
")

    curl -sk -X PUT "$BASE_URL/_matrix/client/v3/rooms/$MATRIX_ROOM_ID/state/m.room.power_levels" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$UPDATED" >/dev/null

    echo "  Done: $FULL_ROOM_ALIAS is now announce-only"
done

echo ""
echo "==> Room initialization complete."
echo "    Admin user: $ADMIN_USERNAME"
