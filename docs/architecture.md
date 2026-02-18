# Passing Circle - Architecture Documentation

## Overview

Passing Circle is a temporary, privacy-focused chat system for events. It provides secure, passkey-only authentication with auto-generated usernames and ephemeral chat rooms. The system is designed to be deployed quickly for events and decommissioned afterward.

**Key Features:**
- Passkey-only authentication (no passwords)
- Auto-generated usernames (editable during enrollment)
- Matrix-based chat (Element Web client)
- OIDC-based SSO via Authentik
- Self-hosted Docker stack
- Cloudflare Tunnel for production TLS

## System Architecture

```
                        ┌─────────────────────┐
                        │   CLOUDFLARE EDGE   │
                        │  (External Service) │
                        └──────────┬──────────┘
                                   │
                                   │ HTTPS (public internet)
                                   │ chat.passingcircle.com
                                   │ chat-auth.passingcircle.com
                                   │
                                   ▲
                                   │
══════════════════════════════════ │ ═══════════════════════════════════
LOCAL DOCKER STACK                 │ (outbound tunnel connection)
                                   │
                       ┌───────────┴───────────┐
                       │  CLOUDFLARE TUNNEL    │
                       │  (Tunnel Client)      │
                       └───────────┬───────────┘
                                   │
                                   │ Frontend Network
                                   │
                                   ▼
       ┌───────────────────────────────────────────────────────────┐
       │                  NGINX (Reverse Proxy)                    │
       ├─────────────────────────────┬─────────────────────────────┤
       │  chat.passingcircle.com     │ chat-auth.passingcircle.com │
       │                             │                             │
       │  /         → Landing        │  /  → Authentik             │
       │  /element/ → Element        │                             │
       │  /_matrix/ → Synapse        │                             │
       └──────────────┬──────────────┴──────────────┬──────────────┘
                      │                             │
                      │        Backend Network      │ 
                      │                             │
                      │                             │
              ┌───────┴───────┐                     │
              │               │                     │
              ▼               ▼                     ▼
     ┌─────────────┐ ┌─────────────┐       ┌─────────────┐
     │   ELEMENT   │ │   SYNAPSE   │       │  AUTHENTIK  │
     │  (Chat UI)  │ │  (Matrix)   │◄──────┤  (Identity) │
     └─────────────┘ └──────┬──────┘       └──────┬──────┘
                            │                     │
                            │              ┌──────┴────────┐
                            │              │               │
                     ┌──────▼──────┐       │               │
                     │  Postgres   │       │               │
                     │  (Synapse)  │       │               │
                     └─────────────┘       │               │
                                    ┌──────▼──────┐  ┌─────▼───────┐
                                    │  Postgres   │  │    Redis    │
                                    │ (Authentik) │  │ (Authentik) │
                                    └─────────────┘  └─────────────┘

```

## Component Details

### 1. NGINX (passingcircle-nginx)
**Purpose:** Reverse proxy and TLS termination

**Networks:** Frontend (exposed), Backend (internal bridge)

**Routes:**
- `chat.passingcircle.com/` → Landing page (static HTML)
- `chat.passingcircle.com/element/` → Element Web
- `chat.passingcircle.com/_matrix/*` → Synapse (Matrix homeserver)
- `chat.passingcircle.com/.well-known/*` → Synapse (federation discovery)
- `chat-auth.passingcircle.com/*` → Authentik (identity provider)

**Network Aliases:**
- `chat.passingcircle.com` (backend network)
- `chat-auth.passingcircle.com` (backend network)

These aliases allow internal services (like Synapse) to reach HTTPS endpoints via internal Docker networking instead of routing through Cloudflare.

### 2. Synapse (passingcircle-synapse)
**Purpose:** Matrix homeserver - manages chat rooms, messages, and federation

**Networks:** Backend only

**Key Features:**
- Server name: `chat.passingcircle.com`
- OIDC authentication via Authentik
- Auto-join rooms: `#general`, `#announcements`
- Federation disabled (event-only use)
- Media storage: 50MB limit per file

**Authentication Flow:**
```
User clicks "Sign In" in Element
  ↓
Synapse redirects to OIDC provider (Authentik)
  ↓
Authentik prompts for passkey authentication
  ↓
User authenticates with passkey
  ↓
Authentik redirects back to Synapse with OIDC token
  ↓
Synapse validates token, creates Matrix user
  ↓
User logged into Element
```

**OIDC Configuration:**
- Issuer: `https://chat-auth.passingcircle.com/application/o/passingcircle-matrix/`
- Discovery: Enabled (auto-fetches endpoints)
- Username mapping: `{{ user.preferred_username }}`
- Internal connectivity: Uses NGINX network alias to avoid external routing

### 3. Element Web (passingcircle-element)
**Purpose:** Matrix web client - the user-facing chat interface

**Networks:** Frontend only

**Configuration:**
- Default homeserver: `https://chat.passingcircle.com`
- Branding: "My Event 2026"
- Mounted at `/element/` via NGINX

**User Experience:**
- Landing page → "Start Chatting" → Element
- SSO login → Authentik passkey flow
- Auto-join rooms after first login

### 4. Authentik (passingcircle-authentik-server + worker)
**Purpose:** Identity provider with passkey-only authentication

**Networks:** Frontend, Backend

**Components:**
- **Server:** Main application server (port 9000)
- **Worker:** Background task processor
- **Postgres:** User data, flows, policies
- **Redis:** Session cache, task queue

**Custom Flows:**

#### Authentication Flow (`passingcircle-auth`)
```
┌─────────────────────────────────────────────┐
│  1. Passkey Authentication                  │
│     - User clicks "Login with Passkey"      │
│     - Browser prompts for passkey selection │
│     - Validates passkey credential          │
│     - Verifies user identity via biometric  │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  2. Create SSO Session                      │
│     - Establishes Authentik SSO session     │
│     - Generates OIDC authorization token    │
│     - Redirects back to application         │
└─────────────────────────────────────────────┘
```

#### Enrollment Flow (`passingcircle-enrollment`)
```
┌─────────────────────────────────────────────┐
│  1. Collect Username                        │
│     - Auto-generates username (e.g.,        │
│       "swift-fox-1234")                     │
│     - User can edit/customize               │
│     - Submits chosen username               │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  2. Derive User Attributes                  │
│     - Reads submitted username              │
│     - Generates email: {username}@domain    │
│     - Sets display name to username         │
│     - Prepares data for account creation    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  3. Create User Account                     │
│     - Creates new user in Authentik         │
│     - Sets username, email, display name    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  4. Register Passkey                        │
│     - Prompts for passkey enrollment        │
│     - User provides biometric/security key  │
│     - Stores passkey credential             │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  5. Establish SSO Session                   │
│     - Logs in newly created user            │
│     - Creates Authentik SSO session         │
│     - Generates OIDC token for application  │
│     - Redirects to complete login           │
└─────────────────────────────────────────────┘
```

**Why Two-Stage Architecture?**

The enrollment flow uses two separate prompt stages with an expression policy in between because:
1. `initial_value_expression` in Authentik evaluates during form **rendering** (before submission)
2. At rendering time, other field values aren't available yet (all expressions run in parallel)
3. Expression policies run during flow **execution** (after stage submission)
4. This allows Stage 1 to collect username, then the policy derives email/name for Stage 2

**Blueprint Management:**
- Blueprints: Declarative YAML configs for flows, stages, policies
- Location: `services/authentik/blueprints/*.yaml`
- Generated from: `services/authentik/templates/*.yaml.j2`
- Important: Blueprints create/update objects but **don't delete** - manual cleanup required

### 5. Cloudflare Tunnel (passingcircle-cloudflare-tunnel)
**Purpose:** Secure tunnel for production access with proper TLS

**Networks:** Frontend only

**Configuration:**
- Routes traffic from Cloudflare edge to NGINX
- No TLS verification (NGINX uses self-signed certs internally)
- Domains:
  - `chat.passingcircle.com` → `https://passingcircle-nginx:443`
  - `chat-auth.passingcircle.com` → `https://passingcircle-nginx:443`

**Why Cloudflare Tunnel?**
- WebAuthn/Passkeys require secure context (HTTPS with valid cert)
- `.local` TLD with self-signed certs fails WebAuthn browser checks
- Cloudflare provides valid TLS at edge, tunnel connects to internal NGINX

**Dev Setup:**
- `docker-compose.dev.yml` adds tunnel to stack
- Excluded from git (contains secrets)
- Started with: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`

## Network Architecture

### Frontend Network
**Purpose:** Public-facing services and reverse proxy

**Services:**
- NGINX (exposed, bridge to backend)
- Element Web
- Authentik Server
- Cloudflare Tunnel (dev/prod)

### Backend Network
**Purpose:** Internal services, databases, and inter-service communication

**Services:**
- NGINX (bridge from frontend)
- Synapse
- Authentik Server
- Synapse Postgres
- Authentik Postgres
- Authentik Redis

**Network Aliases (Backend):**
NGINX has aliases allowing internal services to use domain names:
- `chat.passingcircle.com` → resolves to NGINX internally
- `chat-auth.passingcircle.com` → resolves to NGINX internally

This prevents internal services (like Synapse) from routing through Cloudflare when reaching Authentik for OIDC discovery.

## Authentication & Authorization Flow

```
┌──────────┐
│  User    │
│ (Browser)│
└────┬─────┘
     │
     │ 1. Navigate to chat.passingcircle.com
     ▼
┌─────────────┐
│   Landing   │
│    Page     │
└────┬────────┘
     │
     │ 2. Click "Start Chatting"
     ▼
┌─────────────┐
│   Element   │
│   Web UI    │
└────┬────────┘
     │
     │ 3. Click "Sign In" (First time: "Register")
     ▼
┌─────────────┐
│   Synapse   │
│ (redirects) │
└────┬────────┘
     │
     │ 4. OIDC redirect to Authentik
     ▼
┌─────────────────────────────────────────────┐
│              AUTHENTIK                      │
│                                             │
│  If NEW USER (Register):                   │
│    ┌─────────────────────────────────┐    │
│    │  Enrollment Flow                │    │
│    │  1. Generate/edit username      │    │
│    │  2. Derive email/name           │    │
│    │  3. Create account              │    │
│    │  4. Register passkey            │    │
│    │  5. Auto-login                  │    │
│    └─────────────────────────────────┘    │
│                                             │
│  If EXISTING USER (Sign In):               │
│    ┌─────────────────────────────────┐    │
│    │  Auth Flow                      │    │
│    │  1. Click "Login with Passkey"  │    │
│    │  2. Authenticate with passkey   │    │
│    │  3. Login                       │    │
│    └─────────────────────────────────┘    │
│                                             │
└────┬────────────────────────────────────────┘
     │
     │ 5. OIDC callback with token
     ▼
┌─────────────┐
│   Synapse   │
│ (validates) │
└────┬────────┘
     │
     │ 6. Create Matrix user (if first time)
     │    @keen-deer-8495:chat.passingcircle.com
     ▼
┌─────────────┐
│   Element   │
│  (Logged in)│
└────┬────────┘
     │
     │ 7. Auto-join rooms: #general, #announcements
     ▼
┌─────────────┐
│    Chat!    │
└─────────────┘
```

## Data Flow

### Message Flow
```
User A types message in Element
  ↓
Element → Synapse (POST /_matrix/client/v3/rooms/{roomId}/send)
  ↓
Synapse stores in postgres, distributes to room members
  ↓
Synapse → Element (User B) via sync endpoint
  ↓
User B sees message
```

### Media Upload Flow
```
User uploads image in Element
  ↓
Element → Synapse (POST /_matrix/media/v3/upload)
  ↓
Synapse stores in /data/media_store (Docker volume)
  ↓
Returns media_id (mxc:// URL)
  ↓
Element embeds image using mxc:// URL
  ↓
Other users fetch via GET /_matrix/media/v3/download
```

## Configuration Management

### Single Source of Truth
**File:** `config/passingcircle.yml`

Contains:
- Event name and branding
- Domain configuration
- Secrets (auto-generated or provided)
- Room configuration
- Admin settings

### Generation Process
```
config/passingcircle.yml
  ↓
scripts/generate.py (Jinja2 rendering)
  ↓
  ├─→ .env (Docker Compose environment)
  ├─→ services/nginx/conf.d/*.conf
  ├─→ services/synapse/homeserver.yaml
  ├─→ services/synapse/{domain}.signing.key
  ├─→ services/element/config.json
  ├─→ services/authentik/blueprints/*.yaml
  ├─→ services/nginx/certs/*.{crt,key} (self-signed)
  └─→ services/landing/dist/index.html
```

**Command:** `./scripts/setup.sh`
- Runs `generate.py` in Docker container
- Generates all configs and secrets
- Persists secrets back to `passingcircle.yml`
- Idempotent: safe to re-run

## Deployment

### Development (Local)
```bash
# 1. Generate configs
./scripts/setup.sh

# 2. Start services
docker compose up -d

# 3. Access
# - Landing: http://chat.local (add to /etc/hosts)
# - Element: http://chat.local/element/
# - Authentik: http://auth.chat.local (add to /etc/hosts)
```

### Production (Cloudflare Tunnel)
```bash
# 1. Set up Cloudflare Tunnel (see docs/cloudflare-tunnel-setup.md)

# 2. Update config/passingcircle.yml with production domains

# 3. Generate configs
./scripts/setup.sh

# 4. Start services with tunnel
export CLOUDFLARE_TUNNEL_TOKEN="your-token"
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 5. Access
# - Landing: https://chat.passingcircle.com
# - Element: https://chat.passingcircle.com/element/
# - Authentik: https://chat-auth.passingcircle.com
```

## Security Considerations

### Passkey-Only Authentication
- **No passwords:** Reduces credential theft risk
- **Phishing-resistant:** Passkeys are domain-bound
- **Biometric/PIN:** Local device security
- **WebAuthn:** Industry-standard protocol

### TLS & Network Security
- **Cloudflare Tunnel:** Secure tunnel with valid TLS at edge
- **Internal TLS:** Self-signed certs between tunnel and NGINX
- **No exposed ports:** Services only accessible via NGINX reverse proxy
- **Docker networks:** Isolation between frontend/backend

### Data Privacy
- **Temporary:** System designed for decommission after event
- **No federation:** Messages stay within this homeserver
- **Auto-generated usernames:** No PII required
- **Event-scoped:** Not a permanent chat system

### Secrets Management
- **Auto-generated:** Secrets created on first setup
- **Persisted:** Stored in `config/passingcircle.yml`
- **Docker secrets:** Passed via `.env` file (600 permissions)
- **Not committed:** `.env` and sensitive configs in `.gitignore`

## Troubleshooting

### Common Issues

**Issue:** Synapse can't reach Authentik OIDC endpoint
**Cause:** Network aliases not configured or DNS routing externally
**Fix:** Ensure NGINX has backend network aliases for both domains

**Issue:** WebAuthn fails with "operation is insecure"
**Cause:** Using `.local` TLD with self-signed cert
**Fix:** Use Cloudflare Tunnel with valid domain

**Issue:** Duplicate stage bindings in Authentik
**Cause:** Blueprints don't delete old objects
**Fix:** Delete via Authentik admin UI or SQL (see docs/troubleshooting-authentik-blueprints.md)

**Issue:** Synapse crash loop on domain change
**Cause:** `server_name` is immutable after initialization
**Fix:** Wipe Synapse database: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`

## File Structure

```
passingcircle/
├── config/
│   └── passingcircle.yml          # Single source of truth
├── docs/
│   ├── architecture.md             # This file
│   ├── authentik-enrollment-flow-design.md
│   ├── cloudflare-tunnel-setup.md
│   └── troubleshooting-authentik-blueprints.md
├── scripts/
│   ├── generate.py                 # Config generator
│   └── setup.sh                    # Wrapper script
├── services/
│   ├── authentik/
│   │   ├── blueprints/            # Generated from templates
│   │   └── templates/             # Jinja2 templates
│   ├── element/
│   │   └── config.json            # Generated
│   ├── landing/
│   │   └── dist/index.html        # Generated
│   ├── nginx/
│   │   ├── certs/                 # Generated self-signed certs
│   │   └── conf.d/                # Generated configs
│   └── synapse/
│       ├── homeserver.yaml        # Generated
│       ├── log.config             # Generated
│       └── *.signing.key          # Generated
├── data/                          # Docker volumes (gitignored)
├── .env                           # Generated (gitignored)
├── .env.cloudflare               # Manual (gitignored)
├── docker-compose.yml             # Main stack
└── docker-compose.dev.yml         # Cloudflare Tunnel (gitignored)
```

## Performance & Scaling

**Expected Capacity:**
- **Users:** 50-200 concurrent users per event
- **Messages:** 1000-5000 messages per event
- **Media:** 50MB per file, ~1GB total storage per event

**Hardware Requirements:**
- **CPU:** 4 cores minimum
- **RAM:** 8GB minimum
- **Disk:** 20GB minimum (more for media storage)

**Not designed for:**
- Permanent installations
- Large-scale deployments (1000+ users)
- Federation with other Matrix homeservers
- Long-term message retention

## Future Considerations

**Potential Enhancements:**
- Admin dashboard for room management
- Event-specific branding customization UI
- Message expiry/auto-deletion
- Read-only archive mode after event
- Multiple event instances on same host

**Maintenance:**
- Regular Docker image updates
- Cloudflare Tunnel token rotation
- Certificate renewal (production)
- Database backups (if persistence needed)
- Log rotation and monitoring

## References

- [Matrix Specification](https://spec.matrix.org/)
- [Synapse Documentation](https://matrix-org.github.io/synapse/)
- [Authentik Documentation](https://docs.goauthentik.io/)
- [Element Documentation](https://element.io/user-guide)
- [WebAuthn Guide](https://webauthn.guide/)
- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
