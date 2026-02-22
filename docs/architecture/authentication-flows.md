# Authentication Flows

## End-to-End Flow

```
+----------+
|  User    |
| (Browser)|
+----+-----+
     |
     | 1. Navigate to chat-mobile.passingcircle.com (FluffyChat)
     v
+-------------+
| NGINX       |
| (/ redirect)|
+----+--------+
     |
     | 2. 302 redirect to Synapse SSO endpoint
     v
+-------------+
|   Synapse   |
| (redirects) |
+----+--------+
     |
     | 3. OIDC redirect to Authentik
     v
+--------------------------------------------+
|              AUTHENTIK                     |
|                                            |
|  If NEW USER (Register):                   |
|    +----------------------------------+    |
|    |  Enrollment Flow                 |    |
|    |  1. Generate/edit username       |    |
|    |  2. Derive email/name (policy)   |    |
|    |  3. Create account               |    |
|    |  4. Register passkey             |    |
|    |  5. Auto-login                   |    |
|    +----------------------------------+    |
|                                            |
|  If EXISTING USER (Sign In):               |
|    +----------------------------------+    |
|    |  Auth Flow                       |    |
|    |  1. Click "Sign in" (passkey)    |    |
|    |  2. Authenticate with passkey    |    |
|    |  3. Login                        |    |
|    +----------------------------------+    |
|                                            |
+----+---------------------------------------+
     |
     | 4. OIDC callback with loginToken
     v
+-------------+
| NGINX       |
| /auth.html  |
+----+--------+
     |
     | 5. auth.html stores token in localStorage, redirects to /
     v
+-------------+
|  FluffyChat |
| (reads      |
|  localStorage)
+----+--------+
     |
     | 6. FluffyChat exchanges loginToken with Synapse
     | 7. Synapse creates Matrix user (if first time)
     |    @keen-deer-8495:chat.passingcircle.com
     | 8. Auto-join rooms: #general, #announcements
     v
+-------------+
|    Chat!    |
+-------------+
```

**Note:** When using Element Web (optional), the flow is simpler — Element initiates SSO itself via `sso_redirect_options.immediate: true`, and Synapse redirects back to `/element/?loginToken=xxx` directly. See [archived Element SSO doc](../archive/element-sso-login-flow.md) for details.

## Authentication Flow (`passingcircle-auth`)

The authentication flow handles returning users who already have a passkey registered.

```
+---------------------------------------------+
|  1. Identification Stage                    |
|     - Shows "Sign in" button (passkey)      |
|     - Username field present but hidden     |
|       via CSS (passkey identifies user)     |
|     - "Need an account?" link to enrollment |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  2. Passkey Authentication                  |
|     - Browser prompts for passkey selection |
|     - Validates passkey credential          |
|     - Verifies user identity via biometric  |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  3. Create SSO Session                      |
|     - Establishes Authentik SSO session     |
|     - Generates OIDC authorisation token    |
|     - Redirects back to application         |
+---------------------------------------------+
```

The identification stage UI is customised via Authentik's `branding_custom_css` to hide the username field, the "Or" divider, and the submit button — leaving only the passkey "Sign in" button and enrollment link. See [Authentik Branding](../operations/authentik-branding.md) for CSS details.

## Enrollment Flow (`passingcircle-enrollment`)

The enrollment flow creates new user accounts with auto-generated usernames and passkey-only authentication.

```
+---------------------------------------------+
|  1. Prompt Stage 1 (Username)               |
|     - Auto-generates username               |
|       (e.g. "swift-fox-1234")               |
|     - User can edit the generated name      |
|     - Submits chosen username               |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  Expression Policy (between stages)         |
|     - Reads submitted username              |
|     - Derives email: {username}@domain      |
|     - Derives display name = username       |
|     - Injects into prompt_data              |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  2. Prompt Stage 2 (Hidden)                 |
|     - Email field (hidden, from policy)     |
|     - Name field (hidden, from policy)      |
|     - Auto-submits (no user interaction)    |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  3. User Write Stage                        |
|     - Reads prompt_data                     |
|     - Creates user: always_create mode      |
|     - Sets username, email, display name    |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  4. WebAuthn Setup Stage                    |
|     - Registers passkey for new user        |
|     - User provides biometric/security key  |
|     - Stores passkey credential             |
+----------------------+----------------------+
                       |
                       v
+---------------------------------------------+
|  5. User Login Stage                        |
|     - Logs in the newly created user        |
|     - Creates Authentik SSO session         |
|     - Generates OIDC token for application  |
|     - Redirects to complete login           |
+---------------------------------------------+
```

### Why Two Prompt Stages?

The enrollment flow uses two separate prompt stages with an expression policy between them. This is a deliberate architectural choice driven by how Authentik evaluates expressions:

1. **`initial_value_expression` evaluates during form rendering** (the GET request), before the user has submitted anything.
2. **At rendering time, `prompt_context` is empty** — all field expressions execute in parallel, so fields cannot reference each other's values.
3. **Expression policies run during flow execution** (after stage submission), so they have access to submitted data.

This means:
- **Stage 1** collects the username (with an auto-generated default the user can edit)
- **The policy** reads the submitted username and derives the email and display name
- **Stage 2** has hidden fields that read the policy-injected values and auto-submits

**Common mistake:** Trying to derive email/name from username within a single prompt stage using `prompt_context.get('username')`. This always returns the default value because the username hasn't been submitted yet when the expression runs.

**Source:** [Authentik GitHub Discussion #2107](https://github.com/goauthentik/authentik/discussions/2107) — "Policies are only run upon stage completion, you could break the flow up into two separate prompt stages and use the policies in between to generate data."

### Expression Evaluation Timing

```
HTTP GET (Stage 1 render)
  +-- initial_value_expression runs -> generates username
  +-- prompt_context is EMPTY at this point
  +-- User sees form with generated username (editable)

HTTP POST (Stage 1 submit)
  +-- Username submitted -> stored in prompt_data

POLICY EXECUTION (between Stage 1 and Stage 2)
  +-- Reads prompt_data['username'] (submitted value)
  +-- Derives email = f"{username}@domain"
  +-- Derives name = username
  +-- Injects into prompt_data

HTTP GET (Stage 2 render)
  +-- Email field reads prompt_data['email'] (from policy)
  +-- Name field reads prompt_data['name'] (from policy)
  +-- Hidden fields with derived values, auto-submits

User Write Stage
  +-- Reads prompt_data (has all fields)
  +-- Creates user
```

### Username Generation

The username field uses an `initial_value_expression` to generate random names:

```python
import random
adjectives = ["swift", "bright", "calm", "bold", "keen", "warm", "cool", "fair", "glad", "wise"]
animals = ["fox", "owl", "bear", "deer", "hawk", "wolf", "lynx", "hare", "wren", "dove"]
adj = random.choice(adjectives)
animal = random.choice(animals)
num = random.randint(1000, 9999)
return f"{adj}-{animal}-{num}"
```

The field type is `text` (not `text_read_only`) so users can customise their username before submitting.

## Synapse OIDC Configuration

Synapse connects to Authentik as an OIDC provider:

```yaml
oidc_providers:
  - idp_id: authentik
    idp_name: "Passkey Login"
    discover: true
    issuer: "https://chat-auth.passingcircle.com/application/o/passingcircle-matrix/"
    client_id: "<from secrets>"
    client_secret: "<from secrets>"
    scopes: ["openid", "profile", "email"]
    skip_verification: true  # self-signed certs
    user_mapping_provider:
      config:
        localpart_template: "{{ user.preferred_username }}"
        display_name_template: "{{ user.preferred_username }}"
        confirm_localpart: false
```

The `skip_verification: true` setting is required because internal OIDC discovery goes through NGINX with self-signed certificates. Synapse trusts the certificate via a CA cert volume mount.

The SSO client whitelist allows both clients to receive login tokens without a confirmation page:

```yaml
sso:
  client_whitelist:
    - "https://chat.passingcircle.com/element/"
    - "https://chat-mobile.passingcircle.com/"
```

## Blueprint Management

Authentik flows and stages are defined in blueprint YAML files, generated from Jinja2 templates:

| Template | Blueprint | Purpose |
|---|---|---|
| `00-brand.yaml.j2` | `00-brand.yaml` | Brand customisation (logo, title, CSS) |
| `01-flow-auth.yaml.j2` | `01-flow-auth.yaml` | Authentication flow |
| `02-flow-enrollment.yaml.j2` | `02-flow-enrollment.yaml` | Enrollment flow |
| `03-provider.yaml.j2` | `03-provider.yaml` | OIDC provider for Synapse |

**Applying blueprints:**

```bash
# Regenerate from templates
./scripts/setup.sh

# Apply a specific blueprint
docker compose exec passingcircle-authentik-server ak apply_blueprint /blueprints/custom/01-flow-auth.yaml
```

**Critical:** Blueprints create and update objects but **never delete** them. When refactoring flows (removing stages, policies, or bindings), the old objects remain in the database and continue to execute. See [Authentik Blueprints](../operations/authentik-blueprints.md) for cleanup procedures.

## Patterns to Avoid

### Do not use expression policies to inject user data

```yaml
# WRONG: Policy runs during planning phase, data is lost by execution
- model: authentik_policies_expression.expressionpolicy
  attrs:
    expression: |
      request.context["prompt_data"]["username"] = "value"
```

Policies run during flow **planning**; stages execute later. Data set during planning is not accessible during execution.

### Do not reference other fields in `initial_value_expression`

```yaml
# WRONG: prompt_context is empty during rendering
initial_value: |
  return prompt_context.get('username', 'default')
initial_value_expression: true
```

All field expressions run in parallel during the GET request. Use the two-stage pattern with an expression policy instead.

### Do use prompt stages for data generation

```yaml
# CORRECT: Prompt stages are the Authentik-native way to inject data
- model: authentik_stages_prompt.prompt
  attrs:
    initial_value: "return generated_value()"
    initial_value_expression: true
```

## Troubleshooting

**Synapse can't reach Authentik OIDC endpoint:**
Ensure NGINX has backend network aliases for both domains. Internal OIDC discovery routes through Docker networking, not Cloudflare.

**WebAuthn fails with "operation is insecure":**
Using `.local` TLD with self-signed cert. Use Cloudflare Tunnel with a valid domain.

**Duplicate stage bindings in Authentik:**
Blueprints don't delete old objects. Check and clean up via Authentik admin UI or SQL. See [Authentik Blueprints](../operations/authentik-blueprints.md).

**User Write stage says "No Pending Data":**
Ensure a Prompt stage comes before the User Write stage in the flow. User Write reads from `prompt_data` which is populated by Prompt stages.

## References

- [Authentik Prompt Stage](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/prompt/)
- [Authentik User Write Stage](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/user_write/)
- [Authentik Flow Context](https://docs.goauthentik.io/add-secure-apps/flows-stages/flow/context/)
- [Authentik Expression Policies](https://docs.goauthentik.io/customize/policies/expression)
- [Default Enrollment Blueprint](https://github.com/goauthentik/authentik/blob/main/blueprints/default/flow-default-source-enrollment.yaml)
