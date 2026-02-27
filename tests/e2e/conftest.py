import pytest
import yaml
from pathlib import Path


# Path to the project-level config (two directories up from tests/e2e/)
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "passingcircle.yml"


# ── Domain / config fixtures ──────────────────────────────────────────────


@pytest.fixture(scope="session")
def pc_config():
    """Parsed contents of config/passingcircle.yml."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def domains(pc_config):
    """Dict with 'chat', 'auth', 'fluffychat' domain strings."""
    net = pc_config["network"]
    return {
        "chat": net["domain"],
        "auth": net["auth_domain"],
        "fluffychat": net["fluffychat_domain"],
    }


# ── Browser context: ignore self-signed TLS ───────────────────────────────


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Extend pytest-playwright's default context args for self-signed certs."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
    }


# ── Virtual WebAuthn authenticator (CDP) ──────────────────────────────────


@pytest.fixture
def virtual_authenticator(context, page):
    """Register a CTAP2 virtual authenticator that auto-responds to WebAuthn.

    Must be activated before any WebAuthn ceremony is triggered in the
    browser.  The authenticator persists across cross-domain navigations
    within the same browser context.
    """
    cdp = context.new_cdp_session(page)
    cdp.send("WebAuthn.enable", {"enableUI": False})
    result = cdp.send(
        "WebAuthn.addVirtualAuthenticator",
        {
            "options": {
                "protocol": "ctap2",
                "transport": "internal",
                "hasResidentKey": True,
                "hasUserVerification": True,
                "isUserVerified": True,
                "automaticPresenceSimulation": True,
            }
        },
    )
    authenticator_id = result["authenticatorId"]
    yield authenticator_id
    try:
        cdp.send(
            "WebAuthn.removeVirtualAuthenticator",
            {"authenticatorId": authenticator_id},
        )
    except Exception:
        pass
