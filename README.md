# Passing Circle

Temporary, privacy-focused chat for events. Self-hosted Docker stack with passkey-only authentication — no passwords, no accounts to manage.

## How It Works

Passing Circle runs a full Matrix chat stack behind a single reverse proxy. Users authenticate with passkeys (biometric or PIN) instead of passwords. Usernames are auto-generated (e.g. `swift-fox-7291`). All user data can be wiped between events while preserving configuration.

**User flow:**
1. Open `https://chat.local/` — see landing page
2. Click "Start Chatting" — redirected to passkey prompt
3. New users click "Register" — create a passkey, get an auto-generated username, land in chat
4. Returning users — browser prompts for existing passkey, straight into chat

## Architecture

8 containers, 2 DNS entries, zero external dependencies.

| Container | Purpose |
|-----------|---------|
| nginx | Reverse proxy + TLS termination |
| synapse | Matrix homeserver |
| synapse-db | Synapse PostgreSQL |
| element | Matrix web client |
| authentik-server | Identity provider (OIDC + passkeys) |
| authentik-worker | Authentik background tasks |
| authentik-db | Authentik PostgreSQL |
| authentik-redis | Authentik cache |

```
chat.local/            → Landing page
chat.local/element/    → Element Web client
chat.local/_matrix/*   → Synapse API
auth.chat.local/*      → Authentik IdP
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- DNS or `/etc/hosts` entries pointing `chat.local` and `auth.chat.local` to your host IP

### Setup

1. **Configure** — edit `config/passingcircle.yml` with your event name, host IP, and room list.

2. **Generate** — run setup to generate secrets, TLS certs, and all service configs:
   ```bash
   ./scripts/setup.sh
   ```

3. **Start** — bring up all 8 containers:
   ```bash
   docker compose up -d
   ```

4. **Initialize rooms** — register the admin user and configure room permissions:
   ```bash
   ./scripts/init-rooms.sh
   ```

5. **Open** `https://chat.local/` — your browser will warn about the self-signed certificate, which is expected.

## Configuration

All settings live in `config/passingcircle.yml`:

```yaml
event:
  name: "My Event 2026"
  tagline: "Connect. Collaborate."

network:
  domain: "chat.local"
  auth_domain: "auth.chat.local"
  host_ip: "192.168.1.100"

rooms:
  - id: "general"
    name: "General"
    topic: "Open discussion"
    auto_join: true
    announce_only: false
  - id: "announcements"
    name: "Announcements"
    topic: "Official announcements"
    auto_join: true
    announce_only: true

admins:
  - username: "eventadmin"
```

Secrets are auto-generated on first run and saved back to the config file.

## Event Reset

Wipe all user data between events while keeping your configuration:

```bash
./scripts/reset.sh
```

This removes all databases, media, and session data. Config, certificates, and signing keys are preserved. Run `docker compose up -d` and `./scripts/init-rooms.sh` to start fresh.

## Project Structure

```
config/passingcircle.yml          # Single source of truth
scripts/
  setup.sh                        # Generates everything from config
  init-rooms.sh                   # Post-startup room configuration
  reset.sh                        # Wipe user data between events
  create-test-user.sh             # Register a test user
services/
  nginx/templates/                # NGINX reverse proxy configs
  synapse/templates/              # Matrix homeserver config
  element/templates/              # Element Web client config
  authentik/templates/            # Authentik IdP blueprints
landing/templates/                # Landing page
```

Templates are Jinja2 files rendered by `scripts/generate.py` during setup. Generated output (configs, certs, `.env`) is gitignored.

## License

MIT
