# Element Web SSO Login Flow

## Overview

This document explains how Element Web processes SSO authentication (via loginToken), the architectural requirements for it to work correctly, and the bugs we encountered and fixed.

---

## How the Login Token Flow Works

When a user authenticates via SSO (Authentik → Synapse → Element), the final step is Synapse redirecting the browser to Element with a short-lived token:

```
GET /element/?loginToken=syl_xxxxx
```

Element's `attemptTokenLogin()` function handles this. The critical requirement is:

**Element must be the one that initiated the SSO flow.**

When Element initiates SSO, it writes the homeserver URL to localStorage under the key `mx_sso_hs_url` *before* redirecting the browser away. When the loginToken callback arrives, Element reads this key to know which homeserver to exchange the token with:

```
POST /_matrix/client/v3/login
{ "type": "m.login.token", "token": "<loginToken>" }
```

If `mx_sso_hs_url` is missing from localStorage, `attemptTokenLogin()` logs:
> "Cannot log in with token: can't determine HS URL to use"

...and shows the welcome/login page with no useful error message to the user.

---

## The Bug: Landing Page Bypassed Element

The original landing page "Start Chatting" button linked directly to the Synapse SSO endpoint:

```html
<!-- WRONG: Bypasses Element entirely -->
<a href="https://chat.passingcircle.com/_matrix/client/v3/login/sso/redirect?redirectUrl=.../element/">
    Start Chatting
</a>
```

This sent the user through the entire auth flow (Synapse → Authentik → back to `/element/?loginToken=xxx`) without Element ever running. Since Element never ran, `mx_sso_hs_url` was never written to localStorage. Element received the loginToken cold and couldn't process it.

**Symptom**: After successful passkey authentication, Element showed the welcome/sign-in page instead of logging the user in.

**Fix**: Point the button to `/element/` and let Element initiate SSO itself:

```html
<!-- CORRECT: Element initiates SSO, sets localStorage first -->
<a href="https://chat.passingcircle.com/element/">
    Start Chatting
</a>
```

Combined with `sso_redirect_options.immediate: true` in Element's `config.json`, Element auto-redirects unauthenticated users to SSO without showing the login form.

---

## The "Continue to your account" Confirmation Page

After Synapse completes the OIDC flow with Authentik, it shows a confirmation page:

> *"Continuing will grant chat.passingcircle.com access to your account @username:chat.passingcircle.com"*

This is a Synapse security measure to prevent phishing — it confirms the user trusts the redirect target before issuing the loginToken. It shows whenever the redirect URL is **not** in Synapse's `sso.client_whitelist`.

Without whitelisting, this page added friction and could cause token expiry if the user took too long to click Continue (loginTokens are short-lived).

**Fix**: Add Element's URL to `sso.client_whitelist` in `homeserver.yaml`:

```yaml
sso:
  client_whitelist:
    - "https://chat.passingcircle.com/element/"
```

The trailing slash is important — without it, `https://chat.passingcircle.com/element/` would also match `https://chat.passingcircle.com/element/.evil.site`.

---

## What `sso_redirect_options.immediate` Does (and Doesn't Do)

`sso_redirect_options.immediate: true` in Element's `config.json`:

- **Does**: When Element loads with no active session and no loginToken in the URL, it immediately redirects to SSO instead of showing the login/welcome page.
- **Does not**: Affect loginToken processing in any way. The loginToken path runs before any view is rendered, completely independently of this setting.

This setting is required for the fixed landing page flow to work smoothly — without it, users would see Element's login page for a moment before being redirected to Authentik.

---

## Element Web Startup Sequence (with loginToken)

When Element loads at `/element/?loginToken=xxx`:

1. App bootstraps in `LOADING` state
2. `attemptDelegatedAuthLogin()` called with URL query params
3. Checks for `code` + `state` params → not present (that's the native OIDC/MAS path)
4. Falls through to `attemptTokenLogin(loginToken)`
5. Reads `mx_sso_hs_url` from localStorage
6. If found: `POST /_matrix/client/v3/login` with token → login succeeds → strip token from URL via `history.replaceState()`
7. If not found: error dialog → welcome page

The `/_matrix/client/unstable/org.matrix.msc2965/auth_metadata` (404) requests seen in logs are from a **separate** post-login discovery pass. They have no effect on loginToken processing.

---

## Correct Element `config.json` for SSO-Only Deployments

```json
{
    "default_server_config": {
        "m.homeserver": {
            "base_url": "https://chat.passingcircle.com",
            "server_name": "chat.passingcircle.com"
        }
    },
    "disable_guests": true,
    "disable_login_language_selector": true,
    "disable_3pid_login": true,
    "sso_redirect_options": {
        "immediate": true
    }
}
```

**Do not add** `disable_custom_urls: true` — this was tested previously and caused loginToken processing to break (Element loaded `welcome.html` instead of logging in).

---

## Summary of Changes Made

| File | Change | Reason |
|------|--------|--------|
| `landing/templates/index.html.j2` | "Start Chatting" links to `/element/` instead of SSO endpoint | Element must initiate SSO to write `mx_sso_hs_url` to localStorage |
| `services/synapse/templates/homeserver.yaml.j2` | Added `sso.client_whitelist` with Element URL | Skip "Continue to your account" confirmation page |
| `services/element/templates/config.json.j2` | Added `sso_redirect_options.immediate: true` | Auto-redirect unauthenticated users to SSO without showing login form |
