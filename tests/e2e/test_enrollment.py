"""
E2E test: new-user enrollment via passkey.

Flow:
  landing page  ->  "Start Chatting"  ->  NGINX 302  ->  Synapse SSO
  ->  Authentik identification  ->  "Sign up"  ->  username prompt
  ->  WebAuthn passkey registration (virtual)  ->  OIDC callback
  ->  auth.html  ->  FluffyChat  ->  rooms visible
"""

import re


# ── Timeouts (ms) ─────────────────────────────────────────────────────────

AUTHENTIK_LOAD = 30_000
STAGE_TIMEOUT = 20_000
FLUFFYCHAT_LOAD = 90_000

# Username pattern: adjective-animal-NNNN
USERNAME_RE = re.compile(
    r"^(swift|bright|calm|bold|keen|warm|cool|fair|glad|wise)-"
    r"(fox|owl|bear|deer|hawk|wolf|lynx|hare|wren|dove)-\d{4}$"
)


# ── The test ──────────────────────────────────────────────────────────────


class TestNewUserEnrollment:
    """Full happy-path: enroll a new user and verify rooms are visible."""

    def test_enroll_and_see_rooms(self, page, domains, virtual_authenticator):
        chat = domains["chat"]
        auth = domains["auth"]
        fluffychat = domains["fluffychat"]

        # ── Step 1: Landing page ──────────────────────────────────────
        page.goto(f"https://{chat}/", wait_until="domcontentloaded")
        start_link = page.get_by_role("link", name="Start Chatting")
        start_link.wait_for(state="visible", timeout=10_000)

        # ── Step 2: Click "Start Chatting" ────────────────────────────
        # Follows: chat-mobile/ -> NGINX 302 -> Synapse SSO -> Authentik
        start_link.click()
        page.wait_for_url(
            re.compile(rf"https://{re.escape(auth)}/"),
            timeout=AUTHENTIK_LOAD,
        )

        # ── Step 3: Authentik identification — click "Sign up" ────────
        # Playwright's role/text locators pierce shadow DOM natively.
        # The link text is "Sign up." (hidden via font-size:0) but
        # Playwright still matches it.
        sign_up = page.get_by_role("link", name=re.compile("Sign up"))
        sign_up.wait_for(state="visible", timeout=AUTHENTIK_LOAD)
        sign_up.click()
        page.wait_for_url(
            re.compile(r"/if/flow/passingcircle-enrollment/"),
            timeout=STAGE_TIMEOUT,
        )

        # ── Step 4: Username prompt — accept generated name ──────────
        username_input = page.get_by_role(
            "textbox", name="Your Username"
        )
        username_input.wait_for(state="visible", timeout=STAGE_TIMEOUT)
        generated_username = username_input.input_value()
        assert USERNAME_RE.match(generated_username), (
            f"Expected adjective-animal-NNNN, got: {generated_username!r}"
        )
        page.get_by_role("button", name="Continue").click()

        # ── Step 5: WebAuthn registration (virtual authenticator) ─────
        # After username submit Authentik runs: user-write (no UI) then
        # WebAuthn setup stage.  The stage may show a "Register" button.
        # The virtual authenticator auto-responds to the credentials.create()
        # call once triggered.  If a button appears, click it.
        try:
            register_btn = page.get_by_role("button", name=re.compile(
                "Register|Continue|Submit"
            ))
            register_btn.wait_for(state="visible", timeout=STAGE_TIMEOUT)
            register_btn.click()
        except Exception:
            pass  # Stage may auto-complete without a button click

        # Wait for the entire Authentik flow to complete and redirect
        # back through the OIDC callback chain.
        page.wait_for_url(
            re.compile(rf"https://{re.escape(fluffychat)}/"),
            timeout=AUTHENTIK_LOAD,
        )

        # ── Step 6: auth.html -> FluffyChat ──────────────────────────
        # auth.html stores loginToken in localStorage then redirects to
        # /index.html.  FluffyChat reads it, exchanges for access_token.
        page.wait_for_url(
            re.compile(rf"https://{re.escape(fluffychat)}/(index\.html)?$"),
            timeout=30_000,
        )

        # ── Step 7: Verify rooms are visible ─────────────────────────
        page.get_by_text("General").wait_for(
            state="visible", timeout=FLUFFYCHAT_LOAD
        )
        page.get_by_text("Announcements").wait_for(
            state="visible", timeout=FLUFFYCHAT_LOAD
        )
