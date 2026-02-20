#!/usr/bin/env python3
"""
Reads config/passingcircle.yml, generates secrets, renders all templates,
creates TLS certificates, and writes .env file.
"""

import os
import secrets
import string
import subprocess
import sys

import yaml
from jinja2 import Environment, FileSystemLoader

PROJECT_DIR = "/project"
CONFIG_PATH = os.path.join(PROJECT_DIR, "config", "passingcircle.yml")


def generate_secret(length=64):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_client_id():
    return secrets.token_hex(16)


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


def ensure_secrets(cfg):
    """Fill in any empty secret values and persist back to config."""
    changed = False
    sec = cfg["secrets"]

    secret_fields = [
        "synapse_registration_shared_secret",
        "synapse_macaroon_secret",
        "authentik_secret_key",
        "authentik_bootstrap_token",
        "authentik_bootstrap_password",
        "oidc_client_secret",
        "postgres_synapse_password",
        "postgres_authentik_password",
    ]

    for field in secret_fields:
        if not sec.get(field):
            sec[field] = generate_secret()
            changed = True

    if not sec.get("oidc_client_id"):
        sec["oidc_client_id"] = generate_client_id()
        changed = True

    if changed:
        save_config(cfg)
        print("  [secrets] Generated missing secrets and saved to config")
    else:
        print("  [secrets] All secrets present")


def generate_certs(cfg):
    """Generate self-signed TLS certificates if they don't exist."""
    domain = cfg["network"]["domain"]
    auth_domain = cfg["network"]["auth_domain"]
    cert_dir = os.path.join(PROJECT_DIR, "services", "nginx", "certs")
    os.makedirs(cert_dir, exist_ok=True)

    cert_file = os.path.join(cert_dir, f"{domain}.crt")
    key_file = os.path.join(cert_dir, f"{domain}.key")

    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("  [tls] Certificates already exist, skipping")
        return

    fluffychat_domain = cfg["network"].get("fluffychat_domain")
    san = f"DNS:{domain},DNS:{auth_domain}"
    if fluffychat_domain:
        san += f",DNS:{fluffychat_domain}"
    print(f"  [tls] Generating self-signed certificate for {san}")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_file, "-out", cert_file,
            "-days", "365", "-nodes",
            "-subj", f"/CN={domain}",
            "-addext", f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )


def generate_synapse_signing_key(cfg):
    """Generate Synapse signing key if it doesn't exist."""
    key_file = os.path.join(PROJECT_DIR, "services", "synapse", f"{cfg['network']['domain']}.signing.key")
    if os.path.exists(key_file):
        print("  [synapse] Signing key already exists, skipping")
        return

    print("  [synapse] Generating signing key")
    # Generate an ed25519 signing key in Synapse's expected format
    import base64
    raw = secrets.token_bytes(32)
    key_b64 = base64.b64encode(raw).decode("ascii").rstrip("=")
    key_id = secrets.token_hex(2)
    with open(key_file, "w") as f:
        f.write(f"ed25519 a_{key_id} {key_b64}\n")


def render_templates(cfg):
    """Render all Jinja2 templates with config values."""
    sec = cfg["secrets"]
    net = cfg["network"]

    auto_join_rooms = []
    for room in cfg.get("rooms", []):
        if room.get("auto_join", False):
            auto_join_rooms.append(f"#{room['id']}:{net['domain']}")

    admin_username = cfg["admins"][0]["username"] if cfg.get("admins") else "admin"

    context = {
        # Network
        "domain": net["domain"],
        "auth_domain": net["auth_domain"],
        "host_ip": net["host_ip"],
        # Event
        "event_name": cfg["event"]["name"],
        "event_tagline": cfg["event"]["tagline"],
        # Secrets
        "registration_shared_secret": sec["synapse_registration_shared_secret"],
        "macaroon_secret": sec["synapse_macaroon_secret"],
        "oidc_client_id": sec["oidc_client_id"],
        "oidc_client_secret": sec["oidc_client_secret"],
        "postgres_synapse_password": sec["postgres_synapse_password"],
        # Synapse
        "max_upload_size_mb": cfg.get("synapse", {}).get("max_upload_size_mb", 50),
        "signing_key_path": f"/data/{net['domain']}.signing.key",
        # Rooms
        "auto_join_rooms": auto_join_rooms,
        "admin_username": admin_username,
        "rooms": cfg.get("rooms", []),
        # Landing
        "primary_color": cfg.get("landing", {}).get("primary_color", "#4A90D9"),
        # Optional clients
        "fluffychat_domain": net.get("fluffychat_domain", ""),
    }

    templates = [
        ("services/nginx/templates/chat.conf.j2", "services/nginx/conf.d/chat.conf"),
        ("services/nginx/templates/auth.conf.j2", "services/nginx/conf.d/auth.conf"),
        ("landing/templates/index.html.j2", "landing/dist/index.html"),
    ]

    # Only render templates that exist
    synapse_templates = [
        ("services/synapse/templates/homeserver.yaml.j2", "services/synapse/homeserver.yaml"),
        ("services/synapse/templates/log.config.j2", "services/synapse/log.config"),
    ]
    element_templates = [
        ("services/element/templates/config.json.j2", "services/element/config.json"),
    ]
    authentik_templates = [
        ("services/authentik/templates/00-brand.yaml.j2", "services/authentik/blueprints/00-brand.yaml"),
        ("services/authentik/templates/01-flow-auth.yaml.j2", "services/authentik/blueprints/01-flow-auth.yaml"),
        ("services/authentik/templates/02-flow-enrollment.yaml.j2", "services/authentik/blueprints/02-flow-enrollment.yaml"),
        ("services/authentik/templates/03-provider.yaml.j2", "services/authentik/blueprints/03-provider.yaml"),
        ("services/authentik/templates/04-link-flows.yaml.j2", "services/authentik/blueprints/04-link-flows.yaml"),
    ]

    fluffychat_templates = [
        ("services/nginx/templates/fluffychat.conf.j2", "services/nginx/conf.d/fluffychat.conf"),
        ("services/fluffychat/templates/config.json.j2", "services/fluffychat/config.json"),
    ]

    all_templates = templates + synapse_templates + element_templates + fluffychat_templates + authentik_templates

    for src_rel, dst_rel in all_templates:
        src = os.path.join(PROJECT_DIR, src_rel)
        dst = os.path.join(PROJECT_DIR, dst_rel)
        if not os.path.exists(src):
            continue

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        env = Environment(
            loader=FileSystemLoader(os.path.dirname(src)),
            keep_trailing_newline=True,
        )
        template = env.get_template(os.path.basename(src))
        rendered = template.render(**context)
        with open(dst, "w") as f:
            f.write(rendered)
        print(f"  [render] {src_rel} -> {dst_rel}")


def generate_well_known(cfg):
    """Generate Matrix .well-known discovery files."""
    import json

    domain = cfg["network"]["domain"]
    wk_dir = os.path.join(PROJECT_DIR, "services", "nginx", "well-known", "matrix")
    os.makedirs(wk_dir, exist_ok=True)

    client = {"m.homeserver": {"base_url": f"https://{domain}"}}
    with open(os.path.join(wk_dir, "client"), "w") as f:
        json.dump(client, f, indent=2)

    server = {"m.server": f"{domain}:443"}
    with open(os.path.join(wk_dir, "server"), "w") as f:
        json.dump(server, f, indent=2)

    print("  [well-known] Generated Matrix discovery files")


def generate_dotenv(cfg):
    """Generate .env file for docker-compose."""
    sec = cfg["secrets"]
    net = cfg["network"]
    lines = [
        f"DOMAIN={net['domain']}",
        f"AUTH_DOMAIN={net['auth_domain']}",
        f"POSTGRES_SYNAPSE_PASSWORD={sec['postgres_synapse_password']}",
        f"POSTGRES_AUTHENTIK_PASSWORD={sec['postgres_authentik_password']}",
        f"AUTHENTIK_SECRET_KEY={sec['authentik_secret_key']}",
        f"AUTHENTIK_BOOTSTRAP_PASSWORD={sec['authentik_bootstrap_password']}",
        f"AUTHENTIK_BOOTSTRAP_TOKEN={sec['authentik_bootstrap_token']}",
    ]
    env_path = os.path.join(PROJECT_DIR, ".env")
    with open(env_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  [dotenv] Generated .env")


def create_data_dirs():
    """Create persistent data directories."""
    dirs = [
        "data/synapse-db",
        "data/synapse-media",
        "data/authentik-db",
        "data/authentik-data",
    ]
    for d in dirs:
        path = os.path.join(PROJECT_DIR, d)
        os.makedirs(path, exist_ok=True)
    print("  [data] Created data directories")


def main():
    print("Passing Circle Setup")
    print("=" * 40)

    cfg = load_config()

    print("\n1. Secrets")
    ensure_secrets(cfg)

    print("\n2. TLS Certificates")
    generate_certs(cfg)

    print("\n3. Synapse Signing Key")
    generate_synapse_signing_key(cfg)

    print("\n4. Render Templates")
    render_templates(cfg)

    print("\n5. Well-Known Discovery")
    generate_well_known(cfg)

    print("\n6. Docker Environment")
    generate_dotenv(cfg)

    print("\n7. Data Directories")
    create_data_dirs()

    print("\n" + "=" * 40)
    print("Setup complete!")


if __name__ == "__main__":
    main()
