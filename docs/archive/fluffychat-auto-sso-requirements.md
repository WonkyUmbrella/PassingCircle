# Feature Request: Auto-SSO Redirect on Page Load (FluffyChat Web)

## Summary

Add a `config.json` option that causes FluffyChat web to immediately redirect unauthenticated users to SSO on page load, bypassing the homeserver picker UI. This is equivalent to the `sso_redirect_options.immediate` option available in [Element Web](https://github.com/element-hq/element-web/blob/develop/docs/config.md).

---

## Motivation

Single-tenant Matrix deployments — where the homeserver is fixed and SSO is the only login method — do not benefit from the homeserver picker UI. In these deployments the user experience on first load is:

1. Homeserver picker renders with a pre-filled server address (via `defaultHomeserver`)
2. User clicks "Sign in"
3. Confirmation dialog appears
4. Browser opens the SSO provider
5. User authenticates

Steps 1–3 are avoidable friction. The homeserver is known and the user has navigated to the URL intentionally. The desired experience is:

> User navigates to the FluffyChat URL → immediately redirected to the SSO provider → authenticates → enters chat.

---

## Prior Art: Element Web

Element Web solves this with [`sso_redirect_options`](https://github.com/element-hq/element-web/blob/develop/docs/config.md) in its `config.json`:

```json
{
  "sso_redirect_options": {
    "immediate": true
  }
}
```

When `immediate: true`, Element Web redirects all unauthenticated users straight to the SSO/OIDC provider without rendering any login UI. The full set of options is:

| Option | Type | Description |
|--------|------|-------------|
| `immediate` | boolean | Redirect all unauthenticated users to SSO immediately on load |
| `on_welcome_page` | boolean | Redirect when landing on the welcome page |
| `on_login_page` | boolean | Redirect when landing on the login page |

This is documented at [web-docs.element.dev](https://web-docs.element.dev/Element%20Web/config.html) and is part of Element Web's standard deployment configuration for SSO-only environments.

---

## Why This Cannot Be Solved Outside FluffyChat

FluffyChat web uses [`flutter_web_auth_2`](https://pub.dev/packages/flutter_web_auth_2) to handle SSO authentication. This package requires the Flutter app itself to call `FlutterWebAuth2.authenticate()` before any SSO redirect occurs — it sets up a listener that processes the callback when the user returns.

The consequence is:

- If the SSO redirect is initiated externally (e.g. from a reverse proxy) before FluffyChat has loaded, `authenticate()` is never called, and the callback (`auth.html` → `localStorage['flutter-web-auth-2']`) has no listener to deliver the `loginToken` to
- FluffyChat does not inspect `?loginToken` as a URL parameter on startup, and does not poll `localStorage['flutter-web-auth-2']` at initialisation — it only reads these during an active `authenticate()` call
- The result is that the `loginToken` goes unprocessed and the user is shown the homeserver picker

This is a fundamental difference from Element Web, which is a React application that can inspect URL parameters and `localStorage` at any point during startup.

---

## Proposed Feature

### Config option: `autoSsoRedirect`

```json
{
  "defaultHomeserver": "matrix.example.com",
  "autoSsoRedirect": true
}
```

**Behaviour when `autoSsoRedirect: true`:**

- On app initialisation, if no existing session is present in storage:
  1. Require `defaultHomeserver` to be set — if absent, log a warning and fall back to the normal homeserver picker
  2. Skip the homeserver picker UI
  3. Immediately initiate the SSO flow against `defaultHomeserver` using the same code path as the existing "Sign in with SSO" button
- If an existing session is found in storage, skip the redirect and load normally
- If SSO authentication fails or is cancelled by the user, fall back to the normal homeserver picker

**Behaviour when `autoSsoRedirect: false` or not set (default):**

No change from current behaviour.

---

## Relevant Source Locations (v2.4.1)

| File | Relevance |
|------|-----------|
| `web/config.sample.json` | Config schema — add `autoSsoRedirect` here |
| `lib/config/app_config.dart` | Static config values read from `config.json`; add field here |
| `lib/pages/homeserver_picker/homeserver_picker.dart` | Controller for the homeserver picker page; trigger point for the auto-redirect |
| `lib/pages/homeserver_picker/homeserver_picker_view.dart` | View layer; would be bypassed entirely when auto-redirect is active |

The trigger should be in `HomeserverPickerController.initState()` (or equivalent):

```dart
if (AppConfig.autoSsoRedirect &&
    AppConfig.defaultHomeserver.isNotEmpty &&
    !Matrix.of(context).client.isLogged()) {
  // invoke the same SSO redirect logic used by the "Sign in with SSO" button
  // with AppConfig.defaultHomeserver as the homeserver
}
```

---

## Acceptance Criteria

1. A fresh visit to the FluffyChat web URL immediately redirects to the SSO provider — no user interaction required before the SSO prompt
2. A returning user with an existing session (non-incognito browser, persistent storage) loads directly into their chat without triggering SSO again
3. If SSO fails or is aborted, the user is shown the normal homeserver picker
4. The feature is **opt-in** — deployments that do not set `autoSsoRedirect` see no behaviour change
5. The feature is a no-op if `defaultHomeserver` is not also set, with a console warning

---

## References

- [Element Web `sso_redirect_options` documentation](https://web-docs.element.dev/Element%20Web/config.html)
- [Element Web `config.md` on GitHub](https://github.com/element-hq/element-web/blob/develop/docs/config.md)
- [FluffyChat repository](https://github.com/krille-chan/fluffychat)
- [FluffyChat `config.sample.json`](https://github.com/krille-chan/fluffychat/blob/main/web/config.sample.json)
- [`flutter_web_auth_2` package](https://pub.dev/packages/flutter_web_auth_2)
- [`flutter_web_auth_2` source on GitHub](https://github.com/SongbookPro/flutter_web_auth_2)
