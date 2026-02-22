# FluffyChat Auto-SSO

## Why a Fork Exists

Stock FluffyChat does not support automatic SSO redirect on page load. In a single-tenant deployment where the homeserver is fixed and SSO is the only login method, users would see:

1. Homeserver picker with a pre-filled server address
2. "Sign in" button
3. Confirmation dialog
4. SSO provider opens

Steps 1-3 are unnecessary friction. The desired experience is:

> Navigate to the FluffyChat URL -> immediately redirected to the SSO provider -> authenticate -> enter chat.

### Why This Cannot Be Solved Outside FluffyChat

FluffyChat web uses [`flutter_web_auth_2`](https://pub.dev/packages/flutter_web_auth_2) for SSO authentication. This package requires the Flutter app itself to call `FlutterWebAuth2.authenticate()` before any SSO redirect — it sets up a listener for the callback.

If the SSO redirect is initiated externally (e.g. from a reverse proxy) before FluffyChat has loaded:
- `authenticate()` is never called, so no listener exists for the callback
- FluffyChat does not inspect `?loginToken` as a URL parameter on startup
- FluffyChat does not poll `localStorage['flutter-web-auth-2']` at initialisation
- The loginToken goes unprocessed and the user sees the homeserver picker

This is different from Element Web, which is a React app that inspects URL parameters and localStorage at any point during startup.

### Prior Art: Element Web

Element Web solves this with `sso_redirect_options.immediate: true` in its `config.json`. There is no equivalent in stock FluffyChat.

## The Fork

**Repository:** [github.com/swherdman/fluffychat](https://github.com/swherdman/fluffychat)

**Branch:** `swherdman/auto-sso-redirect`

**Docker image:** `ghcr.io/swherdman/fluffychat:swherdman-auto-sso-redirect`

### What It Changes

The fork adds an `autoSsoRedirect` config option. When enabled, FluffyChat immediately initiates SSO login for unauthenticated users on the web platform.

**Files changed from upstream:**

| File | Change |
|---|---|
| `web/config.sample.json` | Added `autoSsoRedirect: false` option |
| `lib/config/setting_keys.dart` | Added `autoSsoRedirect` to AppSettings enum |
| `lib/config/routes.dart` | Route unauthenticated users to `/home/sign_in` when auto-SSO enabled |
| `lib/pages/sign_in/sign_in_page.dart` | Call `autoSsoIfEnabled()` on page creation |
| `lib/pages/sign_in/view_model/sign_in_view_model.dart` | Core auto-SSO logic (+74 lines) |
| `lib/widgets/view_model_builder.dart` | Added `onCreated` callback for post-creation init |
| `web/auth.html` | Updated callback for redirect mode (non-popup) |

### How `autoSsoIfEnabled()` Works

1. **Guards:** Only runs on web (`kIsWeb`), not during sign-up, and only when `autoSsoRedirect` is `true`
2. **Requires `defaultHomeserver`:** Logs a warning and falls back to normal login if not set
3. **Checks localStorage:** Looks for a pending `flutter-web-auth-2` token from a previous redirect
4. **If token found:** Exchanges it with Synapse via `LoginType.mLoginToken` — login complete
5. **If no token:** Verifies SSO support (`m.login.sso` in login flows), then redirects browser to `/_matrix/client/v3/login/sso/redirect` with `auth.html` as the callback URL
6. **On failure:** Falls back to normal homeserver picker with an error snackbar

### `auth.html` Callback

The fork modifies `web/auth.html` to handle both popup and redirect modes:

```html
<script>
  var key = 'flutter-web-auth-2';
  if (window.opener) {
    // Popup mode: post message back to opener window
    window.opener.postMessage({
      [key]: window.location.href
    }, window.location.origin);
    window.close();
  } else {
    // Redirect mode: store in localStorage and redirect to app
    localStorage.setItem(key, window.location.href);
    window.location.replace('/');
  }
</script>
```

**Key difference from stock auth.html:** The stock version calls `window.close()` in all cases, which only works in popup mode. The fork adds `localStorage.setItem()` + `window.location.replace('/')` for the redirect (non-popup) flow, so FluffyChat can pick up the token on the next page load.

## NGINX Integration

The auto-SSO flow works with NGINX to provide a seamless experience. The FluffyChat NGINX server block (`fluffychat.conf`) includes:

**Root redirect** — sends unauthenticated visitors directly to Synapse SSO:

```nginx
location = / {
    return 302 https://chat.passingcircle.com/_matrix/client/v3/login/sso/redirect
                ?redirectUrl=https%3A%2F%2Fchat-mobile.passingcircle.com%2Fauth.html;
}
```

**Inline auth.html** — NGINX serves the callback handler directly (not from the FluffyChat container), ensuring the correct redirect-mode behaviour:

```nginx
location = /auth.html {
    default_type text/html;
    return 200 "<!DOCTYPE html><title>Auth</title><script>...</script>";
}
```

This inline handler is served by NGINX rather than proxied from the FluffyChat container because the fork's `auth.html` may differ from what's built into the Docker image. Serving it from NGINX ensures the redirect-mode logic is always present.

## Configuration

### `config.json`

```json
{
    "defaultHomeserver": "chat.passingcircle.com",
    "autoSsoRedirect": true
}
```

Both options are required for auto-SSO. `autoSsoRedirect` without `defaultHomeserver` logs a console warning and falls back to the normal flow.

### Synapse SSO Whitelist

The FluffyChat domain must be in Synapse's SSO client whitelist to skip the "Continue to your account" confirmation page:

```yaml
sso:
  client_whitelist:
    - "https://chat-mobile.passingcircle.com/"
```

### Synapse UIA Timeout

FluffyChat triggers cross-signing key upload 30-60 seconds after login. Without a UIA session timeout, this requires re-authentication:

```yaml
ui_auth:
  session_timeout: "5m"
```

## Known Issues

### Incognito / Fresh Session Delay (~60 seconds)

When an **existing user** logs in via incognito/private browsing, FluffyChat shows "Waiting for server..." at the key backup screen for approximately 60 seconds.

**Cause:** In incognito mode, IndexedDB is blank. FluffyChat's bootstrap dialog waits for `prevBatch` (sync state) which is `null`. It sits in a `while` loop through two 30-second long-poll timeouts before proceeding.

**New accounts are not affected** — they take the key setup path (generating new keys) rather than the recovery path.

**Workarounds:**
1. **Lower Synapse sync timeout** (recommended): Set `sync_long_poll_timeout_ms: 5000` in `homeserver.yaml` to reduce the delay from ~60s to ~10s. Trade-off: all clients poll more frequently.
2. **Use PWA / regular browser**: IndexedDB persists between visits, so `prevBatch` is cached and the loop exits immediately.
3. **Accept the delay**: ~60 seconds, once per incognito session.

**Status:** Partially fixed on FluffyChat `main` branch (Dec 2025 commits) but no stable release yet.

See [archived incognito delay doc](../archive/fluffychat-incognito-delay.md) for detailed root cause analysis and network-level evidence.

## References

- [FluffyChat fork](https://github.com/swherdman/fluffychat) — `swherdman/auto-sso-redirect` branch
- [`flutter_web_auth_2` package](https://pub.dev/packages/flutter_web_auth_2)
- [Element Web `sso_redirect_options` documentation](https://web-docs.element.dev/Element%20Web/config.html)
- [Archived: FluffyChat Auto-SSO Requirements](../archive/fluffychat-auto-sso-requirements.md) — original feature analysis
- [Archived: Incognito Delay](../archive/fluffychat-incognito-delay.md) — detailed root cause
