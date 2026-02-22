# Local Development

## Development Architecture

In development, a Cloudflare Tunnel provides valid TLS for passkey (WebAuthn) compatibility, since `.local` domains with self-signed certs fail browser security checks.

```
                        +---------------------+
                        |   CLOUDFLARE EDGE   |
                        |  (External Service) |
                        +----------+----------+
                                   Ʌ 
                                   | HTTPS (public internet)
                                   | chat.passingcircle.com
                                   | chat-auth.passingcircle.com
                                   | chat-mobile.passingcircle.com
                                   |
=================================  |  ==================================
LOCAL DOCKER STACK                 | (outbound tunnel connection)
                                   |
                       +-----------+-----------+
                       |  CLOUDFLARE TUNNEL    |
                       |  (Tunnel Client)      |
                       +-----------+-----------+
                                   |
                                   | Frontend Network
                                   |
                                   |
       +--------------------------------------------------------------+
       |                    NGINX (Reverse Proxy)                     |
       +---------------------+-------------------+--------------------+
       | chat.pc.com         | chat-auth.pc.com  | chat-mobile.pc.com |
       |                     |                   |                    |
       | /        -> Landing | / -> Authentik    | / -> SSO redirect  |
       | /_matrix -> Synapse |                   | /* -> FluffyChat   |
       +--------+------------+--------+----------+---------+----------+
                |                     |                   |
                |              Backend Network            |
                |                     |                   |
                v                     v                   v
          +-----------+        +------------+       +------------+
          |  Synapse  |        | AUTHENTIK  |       | fluffychat |
          |  (Matrix) |        | (Identity) |       |  (Chat ui) |
          +-----------+        +-----+------+       +------------+
                                     |
                               +-----v------+
                               |  Postgres  |
                               +------------+

See [Cloudflare Tunnel Setup](cloudflare-tunnel.md) for configuration details.

## Prerequisites

- Docker and Docker Compose
- A domain with Cloudflare DNS (for passkey/WebAuthn — self-signed certs on `.local` domains fail browser security checks)
- Cloudflare Tunnel configured (see [Cloudflare Tunnel Setup](cloudflare-tunnel.md))

## Quick Start

```bash
# 1. Generate configs and secrets
./scripts/setup.sh

# 2. Start services
docker compose up -d

# 3. Access (local, self-signed — WebAuthn will not work)
# Landing: https://chat.local
# FluffyChat: https://chat-mobile.local
# Element: https://chat.local/element/
# Authentik: https://auth.chat.local
```

For working passkey authentication, use Cloudflare Tunnel:

```bash
# 1. Set up Cloudflare Tunnel (see docs/setup/cloudflare-tunnel.md)

# 2. Update config/passingcircle.yml with production domains

# 3. Generate configs
./scripts/setup.sh

# 4. Start services with tunnel
source .env.cloudflare
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 5. Access
# Landing: https://chat.passingcircle.com
# FluffyChat: https://chat-mobile.passingcircle.com
# Element: https://chat.passingcircle.com/element/
# Authentik: https://chat-auth.passingcircle.com
```

## Configuration Changes

All configuration flows through `config/passingcircle.yml`. After editing:

```bash
# Regenerate all configs
./scripts/setup.sh

# Restart affected services
docker compose up -d
```

`setup.sh` is idempotent — safe to re-run at any time. Secrets are auto-generated on first run and persisted back to the YAML file.

## Applying Blueprint Changes

After modifying Authentik blueprint templates:

```bash
# Regenerate templates
./scripts/setup.sh

# Apply specific blueprint
docker compose exec passingcircle-authentik-server ak apply_blueprint /blueprints/custom/01-flow-auth.yaml

# Or restart worker to re-apply all blueprints
docker compose restart passingcircle-authentik-worker
```

See [Authentik Blueprints](../operations/authentik-blueprints.md) for debugging and orphaned object cleanup.

## Common Issues

### Synapse can't reach Authentik OIDC endpoint

**Cause:** Network aliases not configured or DNS routing externally.

**Fix:** Ensure NGINX has backend network aliases for both domains in `docker-compose.yml`:

```yaml
networks:
  backend:
    aliases:
      - chat-auth.passingcircle.com
      - chat.passingcircle.com
      - chat-mobile.passingcircle.com
```

### WebAuthn fails with "operation is insecure"

**Cause:** Using `.local` TLD with self-signed cert.

**Fix:** Use Cloudflare Tunnel with a valid domain. WebAuthn requires a secure context (HTTPS with a valid certificate from a trusted CA).

### NGINX 502 Bad Gateway after restarting Authentik

**Cause:** Docker assigns new IPs to containers on restart. NGINX caches the old IP.

**Fix:** Restart NGINX after restarting any backend service:

```bash
docker compose restart passingcircle-nginx
```

### Synapse crash loop on domain change

**Cause:** `server_name` is immutable after Synapse initialisation.

**Fix:** Wipe the Synapse database:

```bash
docker compose exec passingcircle-synapse-db psql -U synapse -d synapse -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker compose restart passingcircle-synapse
```

### Duplicate stage bindings in Authentik

**Cause:** Blueprints don't delete old objects when removed from the YAML.

**Fix:** Delete orphaned bindings via the Authentik admin UI or SQL. See [Authentik Blueprints](../operations/authentik-blueprints.md).

## Logs

```bash
# All services
docker compose logs --tail 100

# Specific service
docker compose logs passingcircle-synapse --tail 100 --follow

# Authentik debug logging (enabled by default in development)
docker compose logs passingcircle-authentik-worker --tail 200 --follow

# Blueprint status via API
TOKEN=$(grep authentik_bootstrap_token config/passingcircle.yml | awk '{print $2}')
curl -k -s -H "Authorization: Bearer $TOKEN" \
  https://auth.chat.local/api/v3/managed/blueprints/ | python3 -m json.tool
```

## Cleanup

To reset the local environment:

```bash
# Stop all services
docker compose down

# Remove data (databases, media, etc.)
rm -rf data/

# Remove generated configs
rm -f .env
rm -f services/nginx/conf.d/*.conf
rm -f services/nginx/certs/*
rm -f services/synapse/homeserver.yaml
rm -f services/synapse/log.config
rm -f services/synapse/*.signing.key
rm -f services/element/config.json
rm -f services/fluffychat/config.json
rm -f services/authentik/blueprints/*.yaml
rm -f landing/dist/index.html

# Start fresh
./scripts/setup.sh
docker compose up -d
```
