# Troubleshooting Authentik Blueprints

This document covers debugging techniques and common issues when working with Authentik blueprints in Passing Circle.

## Table of Contents
- [Quick Debugging Commands](#quick-debugging-commands)
- [Enable Debug Logging](#enable-debug-logging)
- [Validate Blueprints](#validate-blueprints)
- [Common Issues](#common-issues)
- [Blueprint Validation Error](#blueprint-validation-error-identification-stage)
- [NGINX DNS Caching](#nginx-dns-caching-issue)
- [References](#references)

---

## Quick Debugging Commands

### Check Blueprint Status
```bash
curl -k -s -H "Authorization: Bearer $(python3 -c "import yaml; print(yaml.safe_load(open('config/passingcircle.yml'))['secrets']['authentik_bootstrap_token'])")" \
  https://auth.chat.local/api/v3/managed/blueprints/ | \
  python3 -c "import sys,json; [print(f\"{b['name']}: {b['status']}\") for b in json.load(sys.stdin)['results'] if 'Passing Circle' in b['name']]"
```

### Apply Blueprint Manually (Shows Validation Errors)
```bash
docker compose exec passingcircle-authentik-server ak apply_blueprint /blueprints/custom/01-flow-auth.yaml 2>&1 | tail -100
```

### Check Authentik Worker Logs
```bash
docker compose logs passingcircle-authentik-worker --tail 100 2>&1 | grep -i "passing.*circle\|blueprint.*error"
```

---

## Enable Debug Logging

Debug logging reveals detailed blueprint validation and application steps.

### Method 1: Environment Variable (Persistent)

Add to `docker-compose.yml` under both `passingcircle-authentik-server` and `passingcircle-authentik-worker`:

```yaml
environment:
  AUTHENTIK_LOG_LEVEL: debug
```

Then restart:
```bash
docker compose up -d passingcircle-authentik-server passingcircle-authentik-worker
```

### Method 2: Runtime (Temporary)
```bash
docker compose exec passingcircle-authentik-server sh -c 'export AUTHENTIK_LOG_LEVEL=debug && kill -HUP 1'
```

### View Debug Logs
```bash
docker compose logs passingcircle-authentik-worker --tail 200 --follow
```

Look for:
- `"Starting blueprint import validation"`
- `"Finished blueprint import validation"`
- `"Entry invalid"` (contains the actual error)
- `"Blueprint validation failed"`

---

## Validate Blueprints

### Using Authentik CLI

The `ak apply_blueprint` command validates AND shows detailed errors:

```bash
docker compose exec passingcircle-authentik-server ak apply_blueprint /blueprints/custom/01-flow-auth.yaml
```

**Example Error Output:**
```
Blueprint invalid
	authentik.blueprints.v1.importer: Entry invalid: Serializer errors
	{'non_field_errors': [ErrorDetail(string='When no user fields are selected,
	at least one source must be selected', code='invalid')]}
```

### Using JSON Schema (IDE Validation)

Add to the top of your `.yaml` blueprint files:

```yaml
# yaml-language-server: $schema=https://goauthentik.io/blueprints/schema.json
```

With VS Code + YAML extension, this provides:
- Real-time syntax validation
- Auto-completion
- Field documentation

**Version-specific schema:**
```yaml
# yaml-language-server: $schema=https://version-2025-2.goauthentik.io/blueprints/schema.json
```

---

## Common Issues

### 1. Blueprint Shows "error" Status But No Logs

**Symptom:** Blueprint has `status: "error"` in API, but no error messages in logs.

**Cause:** Known Authentik bug ([Issue #10481](https://github.com/goauthentik/authentik/issues/10481)) - validation errors not displayed in UI before v2024.8.4.

**Solution:** Use `ak apply_blueprint` CLI command to see actual validation errors.

### 2. Blueprints Applied But Objects Don't Exist

**Symptom:** Worker logs show `"state": "SUCCESS"` but no applications/flows exist in Authentik.

**Cause:** Validation passes but application logic fails silently during object creation.

**Debug Steps:**
1. Enable debug logging
2. Check for `"Entry invalid"` messages in worker logs
3. Validate blueprint with CLI: `ak apply_blueprint`
4. Check for circular dependencies between blueprints

---

## Blueprint Validation Error: Identification Stage

### The Error

```
Entry invalid: Serializer errors
{'non_field_errors': [ErrorDetail(string='When no user fields are selected,
at least one source must be selected', code='invalid')]}
```

### Root Cause

The `authentik_stages_identification.identificationstage` model requires either:
- **user_fields** (username, email, etc.) — at least one field, OR
- **sources** (OAuth/SAML providers) — at least one source

Our initial passkey-only configuration had both empty:
```yaml
attrs:
  user_fields: []  # Empty!
  passwordless_flow: !Find [authentik_flows.flow, [slug, passingcircle-auth]]
  sources: []      # Empty!
```

### Why This Happens

Authentik's identification stage is designed to collect user identity information. With no user fields and no OAuth sources, there's no way for users to identify themselves, making the stage invalid.

### Solution Options

**Option 1: Add WebAuthn Stage Without Identification**
Skip the identification stage entirely for passwordless flows. Use WebAuthn authenticator validate stage directly.

**Option 2: Use Minimal User Field**
Keep username field but hide it / auto-populate it:
```yaml
user_fields:
  - username
```

**Option 3: Add Dummy Source**
Configure a placeholder source (not recommended).

**Option 4: Use Authentication Type "None"**
Let the passwordless flow handle identification entirely through WebAuthn.

---

## NGINX DNS Caching Issue

### Symptom

After restarting Authentik containers:
- NGINX returns `502 Bad Gateway`
- Logs show: `connect() failed (113: Host is unreachable) while connecting to upstream`
- NGINX is trying to reach old container IP

### Root Cause

Docker assigns new IPs to containers on restart. NGINX resolves container names (`passingcircle-authentik-server`) to IPs at startup and caches them.

**Example:**
- Authentik starts with IP `172.18.0.8`
- NGINX resolves and caches `passingcircle-authentik-server` → `172.18.0.8`
- Authentik restarts, gets new IP `172.18.0.6`
- NGINX still tries `172.18.0.8` (cached) → connection fails

### Solution

Restart NGINX after any Authentik restart to refresh DNS:

```bash
docker compose restart passingcircle-nginx
```

### Prevention

Use Docker's internal DNS with resolver directives (advanced):
```nginx
resolver 127.0.0.11 valid=10s;
set $authentik passingcircle-authentik-server:9000;
proxy_pass http://$authentik;
```

This forces NGINX to re-resolve on every request.

---

## References

### Official Documentation
- [Blueprints | authentik](https://docs.goauthentik.io/customize/blueprints/)
- [Working with blueprints | authentik](https://docs.goauthentik.io/customize/blueprints/working_with_blueprints/)
- [File structure | authentik](https://docs.goauthentik.io/customize/blueprints/v1/structure/)
- [Models | authentik](https://docs.goauthentik.io/customize/blueprints/v1/models/)

### Blueprint Schema
- Current version: https://goauthentik.io/blueprints/schema.json
- Specific version: https://version-2025-2.goauthentik.io/blueprints/schema.json

### Known Issues
- [Blueprint validation failures not returned to web UI · Issue #10481](https://github.com/goauthentik/authentik/issues/10481)
  - Fixed in v2024.8.4
  - Before this version, validation errors only visible via CLI

### CLI Commands
```bash
# List available blueprint commands
docker compose exec passingcircle-authentik-server ak help | grep -i blue

# Available commands:
# - apply_blueprint       Apply a blueprint file
# - blueprint_shell       Interactive blueprint shell
# - export_blueprint      Export objects as blueprint
# - make_blueprint_schema Generate blueprint JSON schema
```

---

## Debugging Workflow

When blueprints fail to apply:

1. **Check status via API**
   ```bash
   curl -k -H "Authorization: Bearer TOKEN" https://auth.chat.local/api/v3/managed/blueprints/
   ```

2. **Enable debug logging** (see above)

3. **Apply blueprint via CLI** to see validation errors
   ```bash
   docker compose exec passingcircle-authentik-server ak apply_blueprint /blueprints/custom/01-flow-auth.yaml
   ```

4. **Check worker logs** for detailed application steps
   ```bash
   docker compose logs passingcircle-authentik-worker --tail 200
   ```

5. **Validate YAML syntax** using schema in IDE or online validator

6. **Check for circular dependencies** between blueprints (Flow A references Flow B which doesn't exist yet)

7. **Restart NGINX** if getting 502 errors after Authentik restarts
   ```bash
   docker compose restart passingcircle-nginx
   ```
