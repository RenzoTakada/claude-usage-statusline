#!/usr/bin/env bash
# claude-usage-statusline installer
# Installs the usage monitor into Claude Code's status line (macOS only)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
TARGET_SCRIPT="$SCRIPTS_DIR/claude_usage.py"

echo "==> Claude Usage Status Line — Installer"
echo ""

# ── 1. Prerequisites ──────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This tool requires macOS (uses Claude Desktop cookies + Keychain)."
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install it via 'brew install python'."
    exit 1
fi

if ! python3 -c "from cryptography.hazmat.primitives.ciphers import Cipher" 2>/dev/null; then
    echo "==> Installing 'cryptography' Python package..."
    pip3 install --quiet cryptography
fi

COOKIES_DB="$HOME/Library/Application Support/Claude/Cookies"
if [[ ! -f "$COOKIES_DB" ]]; then
    echo "ERROR: Claude Desktop not found at expected path."
    echo "       Install Claude Desktop from https://claude.ai/download and log in first."
    exit 1
fi

echo "✓ Prerequisites OK"

# ── 2. Copy script ────────────────────────────────────────────────────────────

mkdir -p "$SCRIPTS_DIR"
cp "$SCRIPT_DIR/claude_usage.py" "$TARGET_SCRIPT"
chmod +x "$TARGET_SCRIPT"
echo "✓ Script installed at $TARGET_SCRIPT"

# ── 3. Quick smoke test ───────────────────────────────────────────────────────

echo "==> Testing script (you may see a Keychain prompt — click 'Always Allow')..."
OUTPUT=$(python3 "$TARGET_SCRIPT" 2>&1)

if [[ -z "$OUTPUT" ]]; then
    echo ""
    echo "WARNING: Script ran but returned no output."
    echo "         Make sure you are logged in to Claude Desktop."
    echo "         You can test manually: python3 $TARGET_SCRIPT"
else
    echo "✓ Script output: $OUTPUT"
fi

# ── 4. Update ~/.claude/settings.json ────────────────────────────────────────

echo "==> Updating $SETTINGS_FILE ..."

python3 - <<PYEOF
import json, os, sys

settings_file = os.path.expanduser("$SETTINGS_FILE")
target_script = "$TARGET_SCRIPT"

# Load existing settings or start fresh
if os.path.exists(settings_file):
    with open(settings_file) as f:
        settings = json.load(f)
else:
    settings = {}

# Inject statusLine (preserve everything else)
settings["statusLine"] = {
    "type": "command",
    "command": f"python3 {target_script}",
    "refreshInterval": 60
}

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print(f"✓ settings.json updated")
PYEOF

# ── 5. Done ───────────────────────────────────────────────────────────────────

echo ""
echo "✅ Installation complete!"
echo ""
echo "   Restart Claude Code (or open a new session) to see the status line:"
echo "   Session: 32% ███░░░░░ resets in 4h 8m  Weekly: 12% █░░░░░░░ resets in 5d 17h"
echo ""
echo "   The status line refreshes every 60 seconds."
echo "   If prompted by Keychain again, click 'Always Allow' to allow permanently."
