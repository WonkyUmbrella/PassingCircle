# Authentik Branding & CSS Customization

## Overview

Authentik 2025.4+ supports custom CSS via the `branding_custom_css` field on the Brand model. This CSS is injected into all shadow DOMs via `adoptedStyleSheets`, meaning it propagates through the nested web component hierarchy.

## Brand Model Fields

Set in blueprint (`00-brand.yaml.j2`):

| Field | Description |
|-------|-------------|
| `branding_title` | Page title shown in browser tab |
| `branding_logo` | URL to logo image (must be full URL, not absolute path — `/path` is rejected) |
| `branding_custom_css` | Custom CSS applied globally to all pages |

**Logo path gotcha**: `branding_logo` rejects absolute paths like `/branding/logo.svg` with error `Absolute paths are not allowed`. Use a full URL: `https://domain/branding/logo.svg`.

## Shadow DOM Structure (Authentik 2025.12)

CSS propagates through these nested shadow DOMs:

```
ak-flow-executor (shadow root)
├── header.pf-c-login__header          (empty)
├── main.pf-c-login__main
│   ├── div.pf-c-login__main-header.pf-c-brand   ← LOGO lives here
│   └── ak-stage-identification (shadow root)
│       └── ak-flow-card (shadow root)
│           ├── div.pf-c-login__main-header       ← "Sign In" HEADING
│           ├── div.pf-c-login__main-body          ← form content slot
│           └── div.pf-c-login__main-footer        ← footer-band slot
└── slot[name="footer"]
```

**Key insight**: `.pf-c-login__main-header` exists at TWO levels:
1. In `ak-flow-executor` — has additional class `.pf-c-brand`, contains the logo
2. In `ak-flow-card` — contains the h1 heading text

To hide the heading without hiding the logo, use: `.pf-c-login__main-header:not(.pf-c-brand)`.

## Identification Stage DOM Elements

```html
<!-- Username field -->
<div class="pf-c-form__group">
  <input name="uidField" type="text" />
</div>

<!-- Log in button -->
<div class="pf-c-form__group pf-m-action">
  <button type="submit">Log in</button>
</div>

<!-- Or divider -->
<ak-divider>Or</ak-divider>

<!-- Passwordless / security key link -->
<a name="passwordless" class="pf-c-button pf-m-secondary pf-m-block"
   href="/if/flow/passingcircle-auth-passwordless/">
  Use a security key
</a>

<!-- Sign up link (in footer band) -->
<fieldset class="pf-c-login__main-footer-band">
  <div class="pf-c-login__main-footer-band-item">
    Need an account?
    <a name="enroll" href="/if/flow/passingcircle-enrollment/">Sign up.</a>
  </div>
</fieldset>
```

## Scoping CSS to Specific Pages

Since `branding_custom_css` applies globally to ALL pages/flows, you must scope rules that should only affect specific stages. Use `:has()` to scope to the identification stage:

```css
/* BAD — hides submit button on ALL pages including enrollment */
.pf-c-form__group.pf-m-action { display: none !important; }

/* GOOD — only hides on identification page (where uidField exists) */
.pf-c-form:has(input[name="uidField"]) > .pf-c-form__group.pf-m-action { display: none !important; }
```

Rules that are naturally scoped (target elements only on identification page):
- `input[name="uidField"]` — only exists on identification
- `a[name="passwordless"]` — only exists on identification
- `a[name="enroll"]` — only exists on identification
- `.pf-c-login__main-footer-band` — only exists on identification

Rules that need explicit scoping:
- `.pf-c-form__group.pf-m-action` — exists on ALL pages with forms
- `ak-divider` — could exist on other pages
- `.pf-c-form` layout overrides — affects ALL forms

## Hiding Text and Using ::after for Replacement

Pattern: set `font-size: 0` on the element, then use `::after` with `content` and explicit `font-size`.

**Vertical centering issue**: When using `font-size: 0` on an `<a>` tag, the original text node (e.g., "Use a security key") still exists as an invisible flex item. This can interfere with flexbox centering.

**Solution**: Use `position: absolute` on the `::after` to ignore the hidden text entirely:

```css
a[name="passwordless"] {
  font-size: 0 !important;
  position: relative !important;
  display: block !important;
  height: 70px !important;
}
a[name="passwordless"]::after {
  content: "Sign in" !important;
  font-size: 1.4rem !important;
  position: absolute !important;
  top: 50% !important;
  left: 50% !important;
  transform: translate(-50%, -50%) !important;
}
```

## Hover State Gotcha

The `<a>` tag gets `text-decoration: underline` on hover by default. Even with `font-size: 0`, this underline renders on the invisible text and can shift the `::after` content. Fix with:

```css
a[name="passwordless"] {
  text-decoration: none !important;
}
```

## Button Height Matching

When matching heights between buttons in different containers, use explicit `height` rather than `padding`:

- `padding` on `<a>` tags with `font-size: 0` behaves unpredictably because line-height collapses
- `min-height` doesn't cap elements whose content exceeds it
- `height: 70px` with `display: flex; align-items: center` is the most reliable approach

## Width Matching Across Containers

The identification page has buttons in two different container hierarchies:
- Sign in button: inside `.pf-c-login__main-body` (padding: 48px) → `.pf-c-form` (padding: 16px)
- Sign up button: inside `.pf-c-login__main-footer` → `.pf-c-login__main-footer-band`

To match widths, set the footer band padding to equal the combined padding chain: `padding: 0 64px` (48px + 16px).

## Serving Custom Logo Files

Authentik doesn't serve arbitrary files from its `/data/media/` directory at `/media/` URLs. Instead, serve logos through nginx:

1. Add a volume mount in `docker-compose.yml`: `./landing/static:/var/www/branding:ro`
2. Add a location block in `auth.conf.j2`:
   ```nginx
   location /branding/ {
       alias /var/www/branding/;
       expires 1d;
       add_header Cache-Control "public, immutable";
   }
   ```
3. Reference in blueprint: `branding_logo: https://{{ auth_domain }}/branding/logo-text-dark.svg`

## Applying Blueprint Changes

```bash
# Render template
bash scripts/setup.sh

# Apply blueprint
docker compose exec passingcircle-authentik-server ak apply_blueprint /blueprints/custom/00-brand.yaml

# If CSS changes don't appear, hard-refresh the browser (Ctrl+Shift+R)
```

## Debugging CSS in Shadow DOMs

Use browser evaluate to inspect shadow DOM elements:

```javascript
const executor = document.querySelector('ak-flow-executor');
const stage = executor.shadowRoot.querySelector('ak-stage-identification');
const card = stage.shadowRoot.querySelector('ak-flow-card');

// Inject test CSS into all shadow roots
const css = `/* test rules */`;
const sheet = new CSSStyleSheet();
sheet.replaceSync(css);
executor.shadowRoot.adoptedStyleSheets = [...executor.shadowRoot.adoptedStyleSheets, sheet];
stage.shadowRoot.adoptedStyleSheets = [...stage.shadowRoot.adoptedStyleSheets, sheet];
card.shadowRoot.adoptedStyleSheets = [...card.shadowRoot.adoptedStyleSheets, sheet];
```

Note: stacking multiple test stylesheets via browser evaluate can cause unexpected results from rule accumulation. Always do a clean page reload to verify final CSS from the blueprint.
