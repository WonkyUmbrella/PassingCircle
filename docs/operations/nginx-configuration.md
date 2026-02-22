# NGINX Configuration

## Overview

NGINX is the single entry point for all traffic. It runs as a reverse proxy with three server blocks, each handling a different domain. All configuration is generated from Jinja2 templates by `scripts/generate.py`.

**Templates and output:**

| Template | Output | Domain |
|---|---|---|
| `services/nginx/templates/chat.conf.j2` | `services/nginx/conf.d/chat.conf` | `chat.passingcircle.com` |
| `services/nginx/templates/auth.conf.j2` | `services/nginx/conf.d/auth.conf` | `chat-auth.passingcircle.com` |
| `services/nginx/templates/fluffychat.conf.j2` | `services/nginx/conf.d/fluffychat.conf` | `chat-mobile.passingcircle.com` |

## Chat Domain (`chat.passingcircle.com`)

The main domain serves the landing page, Element Web (optional), Synapse Matrix API, and discovery endpoints.

### Routes

| Location | Target | Notes |
|---|---|---|
| `= /` | `/var/www/landing/index.html` | Static landing page |
| `/static/` | `/var/www/landing/` | Landing page assets (logos) |
| `= /element/mobile_guide` | `302 /element/` | Workaround for broken `mobile_guide_toast` config in Element Web |
| `/element/` | `passingcircle-element:80` | Element Web client (optional) |
| `/_matrix/` | `passingcircle-synapse:8008` | Matrix client and federation API |
| `/_synapse/` | `passingcircle-synapse:8008` | Synapse OIDC callback and admin |
| `/.well-known/matrix/` | `/var/www/well-known/matrix/` | Matrix discovery files (static JSON with CORS headers) |

### WebSocket Support

The `/_matrix/` location includes WebSocket upgrade headers for Matrix sync:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### Upload Size

`client_max_body_size` is set from `passingcircle.yml` → `synapse.max_upload_size_mb` (default: 50 MB).

## Auth Domain (`chat-auth.passingcircle.com`)

Proxies all traffic to the Authentik server with a custom branding path.

### Routes

| Location | Target | Notes |
|---|---|---|
| `/branding/` | `/var/www/branding/` | Custom logo files served by NGINX (Authentik doesn't serve arbitrary media files at `/media/` URLs) |
| `/` | `passingcircle-authentik-server:9000` | Authentik application server |

### Branding Volume

Custom logos are served from the landing page static directory, mounted into NGINX:

```yaml
# docker-compose.yml
volumes:
  - ./landing/static:/var/www/branding:ro
```

Referenced in Authentik brand blueprint as `https://chat-auth.passingcircle.com/branding/logo-text-dark.svg`.

## FluffyChat Domain (`chat-mobile.passingcircle.com`)

The FluffyChat domain has the most complex configuration due to the auto-SSO flow and Flutter-specific caching requirements.

### Routes

| Location | Target | Notes |
|---|---|---|
| `= /` | `302` to Synapse SSO | Auto-redirect to SSO on first visit |
| `= /auth.html` | Inline HTML response | SSO callback handler (served by NGINX, not proxied) |
| `~* \.(js\|wasm)$` | `passingcircle-fluffychat:80` | Versioned chunk files with 1-day cache |
| `~* \.(otf\|ttf\|woff\|woff2\|png\|...)$` | `passingcircle-fluffychat:80` | Static assets with 7-day cache |
| `/` | `passingcircle-fluffychat:80` | Everything else with `no-cache` |

### SSO Redirect on Root

The root path redirects directly to the Synapse SSO endpoint:

```nginx
location = / {
    return 302 https://chat.passingcircle.com/_matrix/client/v3/login/sso/redirect
               ?redirectUrl=https%3A%2F%2Fchat-mobile.passingcircle.com%2Fauth.html;
}
```

This sends unauthenticated users straight to Authentik without them ever seeing a login form. After authentication, Synapse redirects to `/auth.html` with a `loginToken` parameter.

### Inline `auth.html` Handler

NGINX serves the auth callback handler directly rather than proxying it from the FluffyChat container:

```nginx
location = /auth.html {
    default_type text/html;
    return 200 "<!DOCTYPE html><title>Auth</title><script>
      var k='flutter-web-auth-2';
      if(window.opener){
        var o={};
        o[k]=location.href;
        window.opener.postMessage(o,location.origin);
        window.close();
      } else {
        localStorage.setItem(k,location.href);
        location.replace('/index.html');
      }
    </script>";
}
```

**Why inline?** The stock FluffyChat `auth.html` calls `window.close()` in all cases, which only works in popup mode. This inline handler adds redirect-mode support: it stores the callback URL (including `loginToken`) in localStorage and redirects to `/index.html`, where FluffyChat picks up the token. See [FluffyChat Auto-SSO](../architecture/fluffychat-auto-sso.md) for the full flow.

### Caching Strategy

Flutter web apps have specific caching requirements:

| File type | Cache-Control | Rationale |
|---|---|---|
| `.js`, `.wasm` | `public, max-age=86400` (1 day) | Content-hashed filenames — safe to cache, but 1 day limits stale assets after redeployment |
| Fonts, images, icons (`.otf`, `.ttf`, `.woff2`, `.png`, `.svg`, etc.) | `public, max-age=604800` (7 days) | Static assets that rarely change |
| Everything else (HTML, manifests, `config.json`) | `no-cache` | Must always revalidate — these files bootstrap the app and reference hashed chunk filenames |

### Proxy Buffer Sizes

Flutter web apps produce large WASM and JS files. Increased proxy buffers prevent NGINX from writing to temp files:

```nginx
proxy_buffer_size 128k;
proxy_buffers 8 256k;
proxy_busy_buffers_size 512k;
```

## TLS Configuration

All three server blocks share the same self-signed certificate and key:

```nginx
ssl_certificate /etc/nginx/certs/chat.passingcircle.com.crt;
ssl_certificate_key /etc/nginx/certs/chat.passingcircle.com.key;
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
```

The certificate includes SANs for all three domains. Generated by `scripts/generate.py` on first run.

In production, Cloudflare handles TLS termination at the edge. The tunnel connects to NGINX using these self-signed certs with TLS verification disabled.

## Cloudflare Interaction

When Cloudflare Tunnel is in use:

```
Browser -> Cloudflare Edge (valid TLS) -> Tunnel (encrypted) -> NGINX (self-signed TLS) -> Service
```

Cloudflare's CDN caching layer sits in front of NGINX. The `Cache-Control` headers set by NGINX are respected by Cloudflare:
- `no-cache` on HTML/bootstrap files ensures Cloudflare always revalidates
- Long `max-age` on hashed assets allows Cloudflare to cache them at the edge

HTTP-to-HTTPS redirect (`listen 80; return 301 https://...`) is present in all server blocks for direct access. When behind Cloudflare, this redirect typically doesn't trigger because Cloudflare handles it at the edge.

## DNS Caching Issue

NGINX resolves container hostnames to IPs at startup and caches them. If a backend container restarts and gets a new IP, NGINX continues trying the old IP, resulting in `502 Bad Gateway`.

**Fix:** Restart NGINX after any backend container restart:

```bash
docker compose restart passingcircle-nginx
```

**Advanced prevention:** Use Docker's internal DNS resolver with a short TTL:

```nginx
resolver 127.0.0.11 valid=10s;
set $backend passingcircle-authentik-server:9000;
proxy_pass http://$backend;
```

This forces NGINX to re-resolve on every request. Not currently implemented — manual NGINX restart is sufficient for event-scoped deployments.
