#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

# ── 1. Create venv if it doesn't exist ────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating Python virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

PIP="$VENV_DIR/bin/pip"
PLAYWRIGHT="$VENV_DIR/bin/playwright"
PYTEST="$VENV_DIR/bin/pytest"

# ── 2. Install / upgrade Python dependencies ──────────────────────────────
echo "==> Installing Python dependencies ..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$REQUIREMENTS"

# ── 3. Ensure Chromium browser is installed ───────────────────────────────
# playwright install is idempotent — fast no-op when already up to date.
if ! "$PLAYWRIGHT" install --dry-run chromium 2>&1 | grep -q "is already installed"; then
    echo "==> Installing Playwright Chromium browser ..."
    "$PLAYWRIGHT" install chromium

    echo "==> Installing system dependencies for Chromium ..."
    if ! "$PLAYWRIGHT" install-deps chromium 2>/dev/null; then
        echo "    WARNING: Could not install system deps (may need sudo)."
        echo "    If the browser fails to launch, run:"
        echo "      sudo $PLAYWRIGHT install-deps chromium"
    fi
else
    echo "==> Chromium already installed."
fi

# ── 4. Run pytest ─────────────────────────────────────────────────────────
echo "==> Running e2e tests ..."
"$PYTEST" "$SCRIPT_DIR" "$@"
