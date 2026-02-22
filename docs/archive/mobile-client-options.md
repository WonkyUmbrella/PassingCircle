# Mobile Client Options

## Element Web on Mobile

### The Problem

Element Web detects mobile browsers and redirects users to `/element/mobile_guide`, a page prompting them to download a native app. If ignored, the app works but presents a cramped desktop layout.

### Config Options

`mobile_guide_toast: false` is the documented way to disable the redirect. **It is currently broken** — [GitHub issue #21616](https://github.com/element-hq/element-web/issues/21616) has been open since 2022 and the config key is silently ignored. Setting it anyway documents intent and may be honoured in a future version.

`mobile_builds` with all entries set to `null` removes app store download links from the guide page if it is reached:

```json
"mobile_guide_toast": false,
"mobile_builds": {
    "ios": null,
    "android": null,
    "fdroid": null
}
```

### NGINX Workaround

Because the config option is broken, the NGINX config intercepts `/element/mobile_guide` before Element's JavaScript can act on it and redirects back to `/element/`:

```nginx
location = /element/mobile_guide {
    return 302 /element/;
}
```

This must sit above the `/element/` proxy block so NGINX matches it first.

### Mobile UX Reality

There are no config options for improving the mobile layout. Element Web is a desktop-first app — on mobile it is a squeezed desktop UI. It is functional for basic chat but not optimised. There is no supported workaround short of a custom build.

---

## FluffyChat — Evaluated, Not Recommended

[FluffyChat](https://github.com/krille-chan/fluffychat) is a Flutter-based Matrix client with a web build. It was evaluated as a mobile-friendly alternative.

### Why It Was Rejected for This Stack

**No automatic SSO redirect.** Our flow depends on Element's `sso_redirect_options.immediate: true` to send unauthenticated users straight to Authentik without showing a login form. FluffyChat has no equivalent — users would see a homeserver input field and an SSO button.

**No homeserver lockdown.** `defaultHomeserver` pre-populates the field but users can change it. There is no `disable_custom_urls` equivalent. Feature request [#554](https://github.com/krille-chan/fluffychat/issues/554) was closed as stale.

**No official Docker image.** Requires building from source or using an unofficial community image. Element Web publishes official images.

**Open SSO bug on Android** ([#1560](https://github.com/krille-chan/fluffychat/issues/1560), January 2025) — SSO redirect loop, unresolved.

### Where FluffyChat Would Win

- Better mobile browser experience: proper PWA, no "download the app" prompt, consistent Flutter rendering
- Installable as a home screen app on Android and iOS
- Active development (latest: v2.4.1, January 2025), AGPL-3.0

### Verdict

Not a viable replacement without significant rework to the landing page and auth flow. If the mobile UX becomes a hard requirement and Element Web's limitations are unacceptable, the landing page could potentially construct and POST the SSO redirect directly (bypassing FluffyChat's login screen entirely) — but this would replicate the bug we just fixed in our own stack and is not recommended.

---

## Other Options Noted

**Hydrogen Web** ([element-hq/hydrogen-web](https://github.com/element-hq/hydrogen-web)) — lightweight Matrix client from the Element team, explicitly designed for mobile browser support. Still marked "work in progress" by maintainers (latest: v0.5.1, October 2024). Lacks many features. Worth monitoring as it matures.
