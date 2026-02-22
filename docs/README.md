# Passing Circle Documentation

## Architecture

How the system works and why it's built this way.

- **[System Overview](architecture/system-overview.md)** — Components, networks, data flow, configuration management, security model. Start here.
- **[Authentication Flows](architecture/authentication-flows.md)** — Passkey enrollment and login via Authentik OIDC, Synapse integration, blueprint management.
- **[FluffyChat Auto-SSO](architecture/fluffychat-auto-sso.md)** — Custom fork for automatic SSO redirect, auth.html callback, NGINX integration, known issues.

## Setup

Getting a development environment running.

- **[Local Development](setup/local-development.md)** — Quick start, configuration workflow, common issues.
- **[Cloudflare Tunnel](setup/cloudflare-tunnel.md)** — Demo/development only. Required for passkey/WebAuthn to work (needs valid TLS). Production will need a different solution.
- **[FluffyChat Build Pipeline](setup/fluffychat-build-pipeline.md)** — GHCR image, GitHub Actions workflow, Flutter version pinning, rebuilding after upstream changes.

## Operations

Day-to-day configuration and troubleshooting.

- **[NGINX Configuration](operations/nginx-configuration.md)** — Reverse proxy architecture, per-domain routing, FluffyChat caching strategy, Cloudflare interaction.
- **[Authentik Blueprints](operations/authentik-blueprints.md)** — Debugging blueprint failures, orphaned objects, duplicate bindings, validation errors.
- **[Authentik Branding](operations/authentik-branding.md)** — Custom CSS in shadow DOMs, logo serving via NGINX, scoping rules to specific pages.

## Archive

Superseded documents kept for historical context.

- **[Element SSO Login Flow](archive/element-sso-login-flow.md)** — How Element Web processes loginToken. Relevant if re-enabling Element.
- **[Mobile Client Options](archive/mobile-client-options.md)** — Evaluation of FluffyChat vs Element Web for mobile. FluffyChat was subsequently adopted via a custom fork.
- **[FluffyChat Auto-SSO Requirements](archive/fluffychat-auto-sso-requirements.md)** — Feature analysis that led to the fork. The feature is now implemented.
- **[FluffyChat Incognito Delay](archive/fluffychat-incognito-delay.md)** — Root cause analysis of the ~60s delay in incognito mode. Summary in [FluffyChat Auto-SSO](architecture/fluffychat-auto-sso.md#known-issues).

## Suggested Reading Order

1. [System Overview](architecture/system-overview.md) — understand the components
2. [Authentication Flows](architecture/authentication-flows.md) — understand the auth model
3. [FluffyChat Auto-SSO](architecture/fluffychat-auto-sso.md) — understand the primary client
4. [NGINX Configuration](operations/nginx-configuration.md) — understand the proxy layer
5. [Local Development](setup/local-development.md) — get it running
