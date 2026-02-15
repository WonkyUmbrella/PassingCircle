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

### 3. Orphaned Objects After Blueprint Changes (CRITICAL)

**Symptom:**
- Blueprint updated and re-applied successfully
- Old behavior still occurs despite removing configuration from blueprint
- Logs show old policies/stages executing that are no longer in blueprint
- Multiple systems running simultaneously causing conflicts

**Example:** Updated enrollment flow to use Prompt Stages, but old Expression Policy still generates usernames, causing duplicate values and IntegrityErrors.

**Root Cause:**

**Authentik blueprints DO NOT delete objects when you remove them from the blueprint file.** Blueprint application only creates or updates objects - it never deletes them.

When you refactor a blueprint by:
- Removing a policy
- Removing a stage
- Removing a binding
- Changing implementation approach

...the OLD objects remain in the database and continue to execute.

**Detection:**

Check logs for unexpected policies or stages executing:
```bash
docker compose logs passingcircle-authentik-server --tail 200 | grep -E "P_ENG.*Running policy|Stage.*stage"
```

Look for policies/stages that are no longer defined in your blueprint.

**Example Detection:**
```json
{"event": "P_ENG(proc): Running policy",
 "policy": "<ExpressionPolicy: passingcircle-generate-username>"}
```

If `passingcircle-generate-username` is not in your blueprint but appears in logs, it's orphaned.

**Verification in Database:**

Check if policy exists:
```bash
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
SELECT p.name, p.policy_uuid
FROM authentik_policies_policy p
WHERE p.name = 'your-policy-name';
"
```

Check if policy is bound:
```bash
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
SELECT pb.order, pb.policy_id, pb.target_id
FROM authentik_policies_policybinding pb
WHERE pb.policy_id = 'policy-uuid-from-above';
"
```

**Solution:**

**Option 1: Use Authentik API (Recommended)**

```bash
# Get bootstrap token from config
TOKEN=$(grep authentik_bootstrap_token config/passingcircle.yml | awk '{print $2}')

# Delete policy via API (handles cascades automatically)
curl -k -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "https://auth.chat.local/api/v3/policies/expression/{policy-uuid}/"

# Restart Authentik to clear caches
docker compose restart passingcircle-authentik-server passingcircle-authentik-worker
```

**Option 2: Direct Database (Use with Caution)**

Only use if API is unavailable. Must delete in correct order due to foreign keys:

```bash
# 1. Delete policy bindings first
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
DELETE FROM authentik_policies_policybinding
WHERE policy_id = 'policy-uuid';
"

# 2. Delete from specific policy type table
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
DELETE FROM authentik_policies_expression_expressionpolicy
WHERE policy_ptr_id = 'policy-uuid';
"

# 3. Delete from base policy table
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
DELETE FROM authentik_policies_policy
WHERE policy_uuid = 'policy-uuid';
"

# 4. Restart Authentik to clear caches
docker compose restart passingcircle-authentik-server passingcircle-authentik-worker
```

**Prevention:**

When refactoring blueprints:
1. Identify objects being removed (policies, stages, bindings)
2. Document their UUIDs from the database
3. Apply new blueprint
4. Manually delete old objects
5. Restart Authentik services
6. Verify old behavior is gone

**Alternative: Use Authentik Admin UI**

Navigate to the specific object (Policy, Stage, etc.) in the admin UI and delete it manually. This handles foreign key cascades automatically.

---

### 4. Duplicate Stage Bindings After Flow Refactoring

**Symptom:**
- Flow stages execute in wrong order
- Same stage appears multiple times in flow execution
- Multiple stages bound to same order number

**Example Issue:**
After refactoring enrollment flow from 4 stages to 5 stages with different orders, the old bindings remained, resulting in 8 total bindings instead of 5.

**Detection:**

Check current stage bindings for a flow via SQL:

```bash
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
SELECT
  fsb.order,
  s.name as stage_name,
  fsb.fsb_uuid as binding_id,
  fsb.re_evaluate_policies
FROM authentik_flows_flowstagebinding fsb
JOIN authentik_flows_stage s ON fsb.stage_id = s.stage_uuid
JOIN authentik_flows_flow f ON fsb.target_id = f.flow_uuid
WHERE f.slug = 'passingcircle-enrollment'
ORDER BY fsb.order, s.name;
"
```

**Expected Output (for enrollment flow):**
```
 order |           stage_name           | re_evaluate_policies
-------+--------------------------------+----------------------
    10 | passingcircle-prompt           | f
    20 | passingcircle-prompt-2         | t
    30 | passingcircle-user-write       | f
    40 | passingcircle-webauthn-setup   | f
    50 | passingcircle-enrollment-login | f
(5 rows)
```

**Problem Output (duplicate bindings):**
```
 order |           stage_name
-------+--------------------------------
    10 | passingcircle-prompt
    20 | passingcircle-prompt-2
    20 | passingcircle-user-write       ← DUPLICATE at order 20
    30 | passingcircle-user-write
    30 | passingcircle-webauthn-setup   ← DUPLICATE at order 30
    40 | passingcircle-enrollment-login ← DUPLICATE at order 40
    40 | passingcircle-webauthn-setup
    50 | passingcircle-enrollment-login
(8 rows)
```

**Solution:**

Delete the orphaned bindings by their UUID:

```bash
# 1. Identify the UUIDs of duplicate bindings (the ones at wrong orders)
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
SELECT
  fsb.order,
  s.name as stage_name,
  fsb.fsb_uuid as binding_id
FROM authentik_flows_flowstagebinding fsb
JOIN authentik_flows_stage s ON fsb.stage_id = s.stage_uuid
JOIN authentik_flows_flow f ON fsb.target_id = f.flow_uuid
WHERE f.slug = 'passingcircle-enrollment'
ORDER BY fsb.order, s.name;
"

# 2. Delete specific duplicate bindings
# Replace UUIDs with the actual binding_ids from step 1
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
DELETE FROM authentik_flows_flowstagebinding
WHERE fsb_uuid IN (
  'uuid-of-duplicate-1',
  'uuid-of-duplicate-2',
  'uuid-of-duplicate-3'
);
"

# 3. Verify cleanup
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
SELECT
  fsb.order,
  s.name as stage_name
FROM authentik_flows_flowstagebinding fsb
JOIN authentik_flows_stage s ON fsb.stage_id = s.stage_uuid
JOIN authentik_flows_flow f ON fsb.target_id = f.flow_uuid
WHERE f.slug = 'passingcircle-enrollment'
ORDER BY fsb.order;
"

# 4. Restart Authentik to clear flow cache
docker compose restart passingcircle-authentik-server passingcircle-authentik-worker
```

**Verified Working Example:**

During enrollment flow refactoring (February 2026), we had 8 bindings instead of 5. The following cleanup worked:

```bash
# Identified duplicates at wrong orders:
# - user-write at order 20 (should be 30): cc4c39a7-d5e7-4925-a752-887eb663b56c
# - webauthn at order 30 (should be 40): c63c4d65-cc04-4c51-a080-8d7b76e2766c
# - login at order 40 (should be 50): 034e3f3a-331e-4b78-a829-1b15d87a0997

# Deleted them:
docker compose exec passingcircle-authentik-db psql -U authentik -d authentik -c "
DELETE FROM authentik_flows_flowstagebinding
WHERE fsb_uuid IN (
  'cc4c39a7-d5e7-4925-a752-887eb663b56c',
  'c63c4d65-cc04-4c51-a080-8d7b76e2766c',
  '034e3f3a-331e-4b78-a829-1b15d87a0997'
);
"
# Result: DELETE 3

# Verification showed exactly 5 bindings at correct orders ✅
```

**Prevention:**

When changing stage order numbers in blueprints:
1. Document current binding state before blueprint changes
2. Apply new blueprint
3. Immediately verify bindings via SQL
4. Delete orphaned bindings if detected
5. Restart services to clear caches

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
