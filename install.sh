#!/usr/bin/env bash
# claude-usage-statusline installer for macOS and Linux.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
TARGET_SCRIPT="$SCRIPTS_DIR/claude_usage.py"
OS_NAME="$(uname -s)"

echo "==> Claude Usage Status Line — Installer"
echo ""

case "$OS_NAME" in
  Darwin)
    PLATFORM="macOS"
    COOKIES_DB="$HOME/Library/Application Support/Claude/Cookies"
    ;;
  Linux)
    PLATFORM="Linux"
    COOKIES_DB="${XDG_CONFIG_HOME:-$HOME/.config}/Claude/Cookies"
    ;;
  *)
    echo "ERROR: install.sh supports macOS and Linux."
    echo "       On Windows, run install.ps1 from PowerShell."
    exit 1
    ;;
esac

echo "==> Platform: $PLATFORM"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  if [[ "$OS_NAME" == "Darwin" ]]; then
    echo "       Install it with Homebrew: brew install python"
  else
    echo "       Install it with your package manager, for example: sudo apt install python3 python3-pip"
  fi
  exit 1
fi

if ! python3 -c "from cryptography.hazmat.primitives.ciphers import Cipher" 2>/dev/null; then
  echo "==> Installing 'cryptography' Python package..."
  python3 -m pip install --user --quiet cryptography
fi

if [[ "$OS_NAME" == "Linux" ]] && ! command -v secret-tool >/dev/null 2>&1; then
  echo "WARNING: secret-tool not found."
  echo "         If Claude Desktop uses GNOME Keyring/libsecret, install libsecret-tools."
  echo "         Debian/Ubuntu: sudo apt install libsecret-tools"
  echo "         The script will still try Chromium's legacy fallback key."
fi

if [[ ! -f "$COOKIES_DB" ]]; then
  echo "ERROR: Claude Desktop cookies database not found:"
  echo "       $COOKIES_DB"
  echo "       Install Claude Desktop and log in first."
  echo "       If your path is different, set CLAUDE_COOKIES_DB before running the status line."
  exit 1
fi

echo "✓ Prerequisites OK"

mkdir -p "$SCRIPTS_DIR"
cp "$SCRIPT_DIR/claude_usage.py" "$TARGET_SCRIPT"
chmod +x "$TARGET_SCRIPT"
echo "✓ Script installed at $TARGET_SCRIPT"

echo "==> Testing script..."
if [[ "$OS_NAME" == "Darwin" ]]; then
  echo "    You may see a Keychain prompt. Click 'Always Allow'."
fi

OUTPUT=$(python3 "$TARGET_SCRIPT" 2>&1 || true)

if [[ -z "$OUTPUT" ]]; then
  echo ""
  echo "WARNING: Script ran but returned no output."
  echo "         Make sure you are logged in to Claude Desktop."
  echo "         Debug manually: CLAUDE_USAGE_DEBUG=1 python3 $TARGET_SCRIPT"
else
  echo "✓ Script output: $OUTPUT"
fi

echo "==> Updating $SETTINGS_FILE ..."
mkdir -p "$CLAUDE_DIR"

python3 - <<PYEOF
import json
import os

settings_file = os.path.expanduser("$SETTINGS_FILE")
target_script = "$TARGET_SCRIPT"

if os.path.exists(settings_file):
    with open(settings_file, encoding="utf-8") as f:
        settings = json.load(f)
else:
    settings = {}

settings["statusLine"] = {
    "type": "command",
    "command": f"python3 {target_script}",
    "refreshInterval": 60
}

with open(settings_file, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\\n")

print("✓ settings.json updated")
PYEOF

echo ""
echo "✅ Installation complete!"
echo ""
echo "   Restart Claude Code to see the status line:"
echo "   Session: 32% ███░░░░░ resets in 4h 8m  Weekly: 12% █░░░░░░░ resets in 5d 17h"
echo ""
echo "   The status line refreshes every 60 seconds."
