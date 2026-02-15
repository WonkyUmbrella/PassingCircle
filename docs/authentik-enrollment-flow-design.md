# Authentik Enrollment Flow Design

## Problem Statement

We need a passwordless enrollment flow that:
1. Auto-generates random usernames (e.g., "swift-fox-1234")
2. Doesn't require password input
3. Uses WebAuthn/passkeys for authentication
4. Automatically creates user accounts

## ⚠️ Critical Correction: prompt_context Limitation

**IMPORTANT**: The pattern documented below (lines 136-159) where email/name fields derive from username using `prompt_context.get('username')` **does not work in practice**.

**Why**: `initial_value_expression` evaluates during form **rendering** (before user submission). At this point, `prompt_context` is empty because the form hasn't been submitted yet. All field expressions execute in parallel during the GET request, so fields cannot reference each other's values.

**Correct Pattern**: Use Expression Policies **between** prompt stages:
- Stage 1: Collects username (editable by user)
- Policy: Runs after Stage 1 submission, reads submitted username, derives email/name
- Stage 2: Hidden fields populated by policy-injected data
- User Write: Creates user with consistent data

See updated implementation in `/services/authentik/templates/02-flow-enrollment.yaml.j2`.

**Sources**:
- [Authentik GitHub Discussion #2107](https://github.com/goauthentik/authentik/discussions/2107): "Policies are only run upon stage completion, you could break the flow up into two separate prompt stages and use the policies in between to generate data."
- Official Authentik documentation confirms expression policies run during planning, not execution

## Initial (Failed) Approach

### What We Tried
We attempted to use **Expression Policies** bound to the User Write stage to inject `prompt_data`:

```yaml
# Expression policy bound to User Write stage binding
- model: authentik_policies_expression.expressionpolicy
  attrs:
    expression: |
      username = generate_random_username()
      request.context["flow_plan"].context["prompt_data"] = {
          "username": username,
          "email": f"{username}@domain"
      }
      return True
```

### Why It Failed
1. **Timing Mismatch**: Expression policies run during flow **planning** phase
2. **Data Doesn't Persist**: The User Write stage executes later in the **execution** phase
3. **Context Isolation**: Data set during planning isn't accessible during execution
4. **Wrong Pattern**: User Write stages expect data from **Prompt stages**, not policies

### Log Evidence
```
P_ENG(proc): Running policy - passing: true     ← Policy runs during planning
f(plan): finished building                      ← Planning completes
f(exec): Current stage: UserWriteStage          ← Stage executes later
No Pending data.                                ← Data not found!
```

The policy ran successfully 3 times, but when the User Write stage executed, the data was gone.

---

## Correct Approach: Prompt Stage with Expression-Based Fields

### Key Insight from Research

According to [Authentik documentation](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/prompt/):

> "If you enable 'Interpret initial value as expression,' the initial value will be evaluated as a Python expression. This happens in the same environment as Policies."

**Prompt stages** are the only way to inject data that User Write stages can consume.

### Architecture (Updated: Two-Stage Design)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Enrollment Flow                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Prompt Stage 1                                              │
│     └─ Username Field (Editable, Expression-generated)          │
│     │                                                            │
│     └─► User submits (can edit generated username)              │
│                                                                  │
│  ▼ Expression Policy (between Stage 1 and 2)                    │
│     ├─ Reads submitted username from prompt_data                │
│     ├─ Derives email = f"{username}@chat.local"                 │
│     ├─ Derives name = username                                  │
│     └─► Injects email and name into prompt_data                 │
│                                                                  │
│  2. Prompt Stage 2                                              │
│     ├─ Email Field (Hidden, reads from policy-injected data)    │
│     └─ Name Field (Hidden, reads from policy-injected data)     │
│     │                                                            │
│     └─► Auto-submits (no visible fields)                        │
│                                                                  │
│  3. User Write Stage                                            │
│     ├─ Reads prompt_data (username, email, name)                │
│     ├─ Creates user with: user_creation_mode: always_create     │
│     └─► Creates pending_user                                    │
│                                                                  │
│  4. WebAuthn Setup Stage                                        │
│     ├─ Registers passkey for pending_user                       │
│     └─► User now has passkey credential                         │
│                                                                  │
│  5. User Login Stage                                            │
│     └─► Logs in the newly created user                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Expression Evaluation Timing

```
HTTP GET (Stage 1 render)
  └─ initial_value_expression runs → generates username
  └─ prompt_context is EMPTY at this point
  └─ User sees form with generated username (editable)

HTTP POST (Stage 1 submit)
  └─ Username submitted → stored in prompt_data

POLICY EXECUTION (between Stage 1 and Stage 2)
  └─ Reads prompt_data['username'] (submitted value)
  └─ Derives email = f"{username}@chat.local"
  └─ Derives name = username
  └─ Injects into prompt_data

HTTP GET (Stage 2 render)
  └─ Email field expression reads prompt_data['email'] (from policy)
  └─ Name field expression reads prompt_data['name'] (from policy)
  └─ Hidden fields with derived values
  └─ Auto-submits (no user interaction)

User Write Stage Execution
  └─ Reads prompt_data (has all fields)
  └─ Creates user
```

### Data Flow

1. **Prompt Stage 1** executes → generates random username → user can edit → submits
2. **Expression Policy** runs → reads submitted username → derives email/name → injects into context
3. **Prompt Stage 2** renders → hidden fields read policy-injected data → auto-submits
4. **User Write Stage** reads complete `prompt_data` → creates user account
5. **WebAuthn Stage** registers passkey for the new user
6. **Login Stage** logs them in automatically

---

## Implementation Details

### Prompt Stage Configuration

The Prompt stage needs 3 fields:

#### 1. Username Field (Visible, Editable) - UPDATED

**Note**: Changed from `text_read_only` to `text` to allow user customization.

```yaml
- model: authentik_stages_prompt.prompt
  attrs:
    field_key: username
    label: Your Username (you can edit this if you want)
    type: text  # Changed from text_read_only
    required: true
    placeholder: Generating...
    order: 0
    initial_value: |
      import random
      adjectives = ["swift", "bright", "calm", "bold", "keen", "warm", "cool", "fair", "glad", "wise"]
      animals = ["fox", "owl", "bear", "deer", "hawk", "wolf", "lynx", "hare", "wren", "dove"]
      adj = random.choice(adjectives)
      animal = random.choice(animals)
      num = random.randint(1000, 9999)
      return f"{adj}-{animal}-{num}"
    initial_value_expression: true
```

**Why editable?**
- User sees their generated username
- Can customize it if desired
- Final value (original or edited) gets stored in `prompt_data`

#### 2. Email Field (Hidden) - ⚠️ INCORRECT PATTERN

**WARNING**: This implementation does NOT work as documented. See correction at top of this document.

```yaml
- model: authentik_stages_prompt.prompt
  attrs:
    field_key: email
    label: Email
    type: hidden
    required: true
    order: 1
    initial_value: |
      username = prompt_context.get('username', 'user')  # ❌ DOESN'T WORK
      return f"{username}@chat.local"
    initial_value_expression: true
```

**Why this fails:**
- `prompt_context` is empty during form rendering (GET request)
- All field expressions execute in parallel, cannot reference each other
- Always returns default value 'user@chat.local', not derived username

**Correct approach:** See two-stage architecture with expression policy above.

#### 3. Name Field (Hidden) - ⚠️ INCORRECT PATTERN

**WARNING**: This implementation does NOT work as documented. See correction at top of this document.

```yaml
- model: authentik_stages_prompt.prompt
  attrs:
    field_key: name
    label: Name
    type: hidden
    required: true
    order: 2
    initial_value: |
      return prompt_context.get('username', 'User')  # ❌ DOESN'T WORK
    initial_value_expression: true
```

**Why this fails:**
- Same issue as email field
- `prompt_context` is empty during rendering
- Always returns default value 'User', not the username

### User Write Stage Configuration

```yaml
- model: authentik_stages_user_write.userwritestage
  attrs:
    create_users_as_inactive: false
    user_creation_mode: always_create
    # No group assignment needed for basic enrollment
```

**Key settings:**
- `always_create` - Creates new user even if none exists
- Reads from `prompt_data["username"]`, `["email"]`, `["name"]`
- No special configuration needed - it just works!

---

## Why This Works

### 1. Correct Stage Order
Prompt → User Write follows the standard Authentik pattern shown in [default enrollment blueprint](https://github.com/goauthentik/authentik/blob/main/blueprints/default/flow-default-source-enrollment.yaml)

### 2. Expression Execution Timing
Prompt stage expressions run **during stage execution**, not during planning. The data is immediately available for subsequent stages.

### 3. Standard Data Flow
```
Prompt Stage (execution)
  ↓ sets prompt_data
User Write Stage (execution)
  ↓ reads prompt_data, creates user
WebAuthn Stage (execution)
  ↓ registers passkey
Login Stage (execution)
  ↓ logs in user
```

All stages execute in sequence with proper data handoff.

---

## Common Patterns to Avoid

### ❌ Expression Policies for Data Injection
```yaml
# DON'T DO THIS
- model: authentik_policies_expression.expressionpolicy
  attrs:
    expression: |
      request.context["prompt_data"]["username"] = "value"
      # This data won't be available to User Write stage!
```

**Why?** Policies run during planning; stages execute later.

### ❌ Binding Policies to Stage Bindings for Data
```yaml
# DON'T DO THIS
- model: authentik_policies.policybinding
  identifiers:
    target: !Find [user_write_stage_binding]
  attrs:
    policy: !Find [data_injection_policy]
```

**Why?** Policies control flow/access, they don't inject stage data.

### ✅ Use Prompt Stages with Expressions
```yaml
# DO THIS
- model: authentik_stages_prompt.prompt
  attrs:
    initial_value: "return generated_value()"
    initial_value_expression: true
```

**Why?** This is the Authentik-native way to generate/inject data.

---

## Troubleshooting

### User Write Stage Says "No Pending Data"

**Cause:** The stage can't find `prompt_data`

**Solution:** Ensure a Prompt stage comes BEFORE User Write stage

### Expressions Not Evaluating

**Cause:** `initial_value_expression: false` or not set

**Solution:** Set `initial_value_expression: true` on the prompt

### Username Not Generating

**Cause:** Expression syntax error or import missing

**Solution:** Test expression in Authentik admin → Expression Policy tester

---

## References

### Official Documentation
- [Prompt Stage](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/prompt/) - Field types and expressions
- [User Write Stage](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/user_write/) - How it consumes prompt_data
- [Flow Context](https://docs.goauthentik.io/add-secure-apps/flows-stages/flow/context/) - Data flow between stages
- [Expression Policies](https://docs.goauthentik.io/customize/policies/expression) - When/how policies execute

### Examples
- [Default Enrollment Blueprint](https://github.com/goauthentik/authentik/blob/main/blueprints/default/flow-default-source-enrollment.yaml) - Standard enrollment pattern
- [Custom User Attributes Discussion](https://github.com/goauthentik/authentik/discussions/4767) - Community insights

### Key Learnings
- Policies = flow control and validation
- Prompt stages = data collection and generation
- User Write stage = data consumer (reads prompt_data)
- Execution order matters: Prompt must come before User Write

---

## Summary

**Don't use expression policies to inject user data.**
**Do use Prompt stages with expression-based initial values.**

This follows Authentik's design philosophy where:
- **Stages** handle data and user interaction
- **Policies** handle access control and validation
- **Expressions** can be used in both, but serve different purposes
