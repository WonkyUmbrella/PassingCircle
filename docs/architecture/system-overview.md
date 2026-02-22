# System Overview

## What is Passing Circle?

Passing Circle is a temporary, privacy-focused chat system for events. It provides secure, passkey-only authentication with auto-generated usernames and ephemeral chat rooms. The system is designed to be deployed quickly for events and decommissioned afterward.

**Key features:**
- Passkey-only authentication (no passwords)
- Auto-generated usernames (editable during enrollment)
- Matrix-based chat via [FluffyChat](https://github.com/krille-chan/fluffychat) (default) with optional [Element Web](https://element.io/) support
- OIDC-based SSO via [Authentik](https://goauthentik.io/)
- Self-hosted Docker stack (8 containers)
- Cloudflare Tunnel available for development TLS (WebAuthn requires valid certs)

## System Architecture

```
                           Users
                             |
                             | HTTPS
                             | chat.passingcircle.com
                             | chat-auth.passingcircle.com
                             | chat-mobile.passingcircle.com
                             |
                             v
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
```

For development with Cloudflare Tunnel (needed for WebAuthn with self-signed certs), see the [development architecture](../setup/local-development.md#development-architecture).

## Component Details

### 1. NGINX (`passingcircle-nginx`)

**Purpose:** Reverse proxy and TLS termination for all services.

**Networks:** Exposed (ports 80/443), Backend (internal)

**Three server blocks:**

| Domain | Routes |
|---|---|
| `chat.passingcircle.com` | `/` landing page, `/element/` Element Web (optional), `/_matrix/*` Synapse, `/.well-known/*` Matrix discovery |
| `chat-auth.passingcircle.com` | `/*` Authentik identity provider, `/branding/` custom logo files |
| `chat-mobile.passingcircle.com` | `/` SSO redirect, `/auth.html` inline callback handler, `/*` FluffyChat app |

**Network aliases** on the backend network allow internal services (like Synapse) to reach HTTPS endpoints via Docker networking instead of routing through Cloudflare:
- `chat.passingcircle.com` resolves to NGINX internally
- `chat-auth.passingcircle.com` resolves to NGINX internally
- `chat-mobile.passingcircle.com` resolves to NGINX internally

See [NGINX Configuration](../operations/nginx-configuration.md) for detailed proxy and caching rules.

### 2. Synapse (`passingcircle-synapse`)

**Purpose:** Matrix homeserver — manages chat rooms, messages, and user accounts.

**Networks:** Backend only

**Key configuration:**
- Server name: `chat.passingcircle.com`
- OIDC authentication via Authentik
- Auto-join rooms: `#general`, `#announcements`
- Federation disabled (event-only use)
- Media storage: 50 MB limit per file
- `skip_verification: true` for OIDC (self-signed certs)
- SSO client whitelist includes both FluffyChat and Element URLs
- `ui_auth.session_timeout: 5m` — allows FluffyChat cross-signing key upload after SSO login

**OIDC configuration:**
- Issuer: `https://chat-auth.passingcircle.com/application/o/passingcircle-matrix/`
- Discovery: enabled (auto-fetches endpoints)
- Username mapping: `{{ user.preferred_username }}`
- Uses NGINX network alias to avoid external routing for OIDC discovery

### 3. FluffyChat (`passingcircle-fluffychat`) — Default Client

**Purpose:** Matrix web client — the primary user-facing chat interface. Flutter-based with PWA support for mobile browsers.

**Image:** `ghcr.io/swherdman/fluffychat:swherdman-auto-sso-redirect` — a custom fork with auto-SSO redirect support.

**Networks:** Backend only (served via NGINX on its own domain)

**Configuration (`config.json`):**
- `defaultHomeserver`: `chat.passingcircle.com`
- `autoSsoRedirect`: `true` — immediately redirects unauthenticated users to SSO
- Privacy settings: typing notifications and read receipts disabled

**User experience:**
- User navigates to `chat-mobile.passingcircle.com`
- NGINX redirects `/` to Synapse SSO endpoint
- After authentication, `auth.html` callback stores the token and redirects to FluffyChat
- FluffyChat picks up the token from localStorage and completes login

See [FluffyChat Auto-SSO](fluffychat-auto-sso.md) for details on the fork and auth flow.

### 4. Element Web (`passingcircle-element`) — Optional Client

**Purpose:** Alternative Matrix web client, desktop-optimised. Currently in the stack but will be disabled. Code is retained for future re-enablement.

**Image:** `vectorim/element-web:latest`

**Networks:** Backend only (served via NGINX at `/element/` on the main domain)

**Configuration:**
- `sso_redirect_options.immediate: true` — auto-redirects to SSO
- `mobile_guide_toast: false` + NGINX redirect workaround for mobile users
- Branding set to event name

### 5. Authentik (`passingcircle-authentik-server` + `passingcircle-authentik-worker`)

**Purpose:** Identity provider with passkey-only authentication.

**Image:** `ghcr.io/goauthentik/server:2025.12` (no longer requires a separate Redis container)

**Networks:** Backend only (served via NGINX on the auth domain)

**Components:**
- **Server:** Main application server (port 9000)
- **Worker:** Background task processor
- **Postgres:** User data, flows, policies

**Custom flows:** See [Authentication Flows](authentication-flows.md) for details.

**Blueprint management:**
- Blueprints: declarative YAML configs for flows, stages, policies
- Location: `services/authentik/blueprints/*.yaml`
- Generated from: `services/authentik/templates/*.yaml.j2`
- Blueprints create/update objects but **do not delete** — manual cleanup required
- See [Authentik Blueprints](../operations/authentik-blueprints.md) for troubleshooting

### 6. Cloudflare Tunnel (development only)

In development, a Cloudflare Tunnel sits in front of NGINX to provide valid TLS for passkey (WebAuthn) compatibility, since `.local` domains with self-signed certs fail browser security checks.

See [Local Development](../setup/local-development.md#development-architecture) for the development architecture diagram and [Cloudflare Tunnel Setup](../setup/cloudflare-tunnel.md) for configuration.

## Network Architecture

NGINX is the only externally exposed service. All other containers communicate on an internal backend network.

**Backend Network** — internal services, databases, and inter-service communication:
- NGINX (public-facing, bridges to backend)
- Synapse
- FluffyChat
- Element Web (optional)
- Authentik Server + Worker
- Synapse Postgres
- Authentik Postgres

NGINX has backend network aliases for all three domains, allowing internal services (e.g. Synapse OIDC discovery) to resolve domain names to NGINX without leaving the Docker network.

## Data Flow

### Message Flow

```
User A types message in FluffyChat
  -> FluffyChat -> NGINX -> Synapse (POST /_matrix/client/v3/rooms/{roomId}/send)
  -> Synapse stores in Postgres, distributes to room members
  -> Synapse -> NGINX -> FluffyChat (User B) via sync endpoint
  -> User B sees message
```

### Media Upload Flow

```
User uploads image in FluffyChat
  -> FluffyChat -> NGINX -> Synapse (POST /_matrix/media/v3/upload)
  -> Synapse stores in /data/media_store (Docker volume)
  -> Returns mxc:// URL
  -> Other users fetch via GET /_matrix/media/v3/download
```

## Configuration Management

### Single Source of Truth

**File:** `config/passingcircle.yml`

Contains:
- Event name and branding
- Domain configuration (main, auth, FluffyChat)
- Secrets (auto-generated or provided)
- Room configuration
- Admin settings

### Generation Process

```
config/passingcircle.yml
  |
  v
scripts/generate.py (Jinja2 rendering)
  |
  +-> .env (Docker Compose environment)
  +-> services/nginx/conf.d/chat.conf
  +-> services/nginx/conf.d/auth.conf
  +-> services/nginx/conf.d/fluffychat.conf
  +-> services/synapse/homeserver.yaml
  +-> services/synapse/log.config
  +-> services/synapse/{domain}.signing.key
  +-> services/element/config.json
  +-> services/fluffychat/config.json
  +-> services/authentik/blueprints/*.yaml
  +-> services/nginx/certs/*.{crt,key} (self-signed)
  +-> landing/dist/index.html
```

**Command:** `./scripts/setup.sh`
- Runs `generate.py` in a Docker container
- Generates all configs and secrets
- Persists secrets back to `passingcircle.yml`
- Idempotent: safe to re-run

## Security Considerations

### Passkey-Only Authentication
- **No passwords:** reduces credential theft risk
- **Phishing-resistant:** passkeys are domain-bound
- **Biometric/PIN:** local device security
- **WebAuthn:** industry-standard protocol

### End-to-End Encryption
- **Private rooms and DMs:** encrypted by default (`encryption_enabled_by_default_for_room_type: invite` in Synapse)
- **Public rooms (general, announcements):** unencrypted so that late joiners can see full message history
- **Irreversible:** once a room is encrypted it cannot be unencrypted — this is a Matrix protocol constraint

### TLS & Network Security
- **NGINX TLS termination:** handles HTTPS directly for all domains
- **No exposed ports:** all backend services accessible only via NGINX reverse proxy
- **Docker network isolation:** backend services not reachable from outside the Docker network

### Data Privacy
- **Temporary:** system designed for decommission after event
- **No federation:** messages stay within this homeserver
- **Auto-generated usernames:** no PII required
- **Event-scoped:** not a permanent chat system

### Secrets Management
- **Auto-generated:** secrets created on first `setup.sh` run
- **Persisted:** stored in `config/passingcircle.yml`
- **Docker secrets:** passed via `.env` file (600 permissions)
- **Not committed:** `.env` and sensitive configs in `.gitignore`

## File Structure

```
passingcircle/
+-- config/
|   +-- passingcircle.yml          # Single source of truth
+-- docs/                          # This documentation
+-- scripts/
|   +-- generate.py                # Config generator
|   +-- setup.sh                   # Wrapper script
+-- services/
|   +-- authentik/
|   |   +-- blueprints/            # Generated from templates
|   |   +-- templates/             # Jinja2 templates
|   +-- element/
|   |   +-- config.json            # Generated
|   |   +-- templates/
|   +-- fluffychat/
|   |   +-- config.json            # Generated
|   |   +-- templates/
|   +-- landing/
|   |   +-- dist/index.html        # Generated
|   |   +-- templates/
|   |   +-- static/                # Logo SVGs
|   +-- nginx/
|   |   +-- certs/                 # Generated self-signed certs
|   |   +-- conf.d/                # Generated configs
|   |   +-- templates/
|   +-- synapse/
|       +-- homeserver.yaml        # Generated
|       +-- log.config             # Generated
|       +-- *.signing.key          # Generated
+-- landing/                       # Landing page source
|   +-- templates/index.html.j2
|   +-- dist/index.html            # Generated
|   +-- static/                    # Logo SVGs
+-- data/                          # Docker volumes (gitignored)
+-- .env                           # Generated (gitignored)
+-- .env.cloudflare                # Manual (gitignored)
+-- docker-compose.yml             # Main stack
+-- docker-compose.dev.yml         # Cloudflare Tunnel (gitignored)
```

## Performance & Scaling

**Expected capacity:**
- **Users:** 50-200 concurrent per event
- **Messages:** 1,000-5,000 per event
- **Media:** 50 MB per file, ~1 GB total per event

**Hardware requirements:**
- **CPU:** 4 cores minimum
- **RAM:** 8 GB minimum
- **Disk:** 20 GB minimum (more for media storage)

**Not designed for:**
- Permanent installations
- Large-scale deployments (1,000+ users)
- Federation with other Matrix homeservers
- Long-term message retention

## Future Considerations

- Admin dashboard for room management
- Event-specific branding customisation UI
- Message expiry / auto-deletion
- Read-only archive mode after event
- Multiple event instances on same host
- Disable Element Web service and landing page button (code retained for re-enablement)

## References

- [Matrix Specification](https://spec.matrix.org/)
- [Synapse Documentation](https://matrix-org.github.io/synapse/)
- [FluffyChat Repository](https://github.com/krille-chan/fluffychat)
- [Authentik Documentation](https://docs.goauthentik.io/)
- [Element Documentation](https://element.io/user-guide)
- [WebAuthn Guide](https://webauthn.guide/)
- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
