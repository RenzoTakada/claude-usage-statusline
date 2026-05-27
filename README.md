# claude-usage-statusline

Monitor your Claude Pro session and weekly usage directly inside Claude Code's terminal status line — no browser extension needed.

![macOS](https://img.shields.io/badge/macOS-supported-brightgreen?logo=apple&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-experimental-yellow?logo=linux&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-experimental-yellow?logo=windows&logoColor=white)

![Preview](preview.png)

The status line shows:
- **Session** usage (5-hour window) with a progress bar and reset countdown
- **Weekly** usage (7-day window) with a progress bar and reset countdown

```
Session: 32% ███░░░░░ resets in 4h 8m  Weekly: 12% █░░░░░░░ resets in 5d 17h
```

---

## Platform support

| Platform | Status | Notes |
|---|---|---|
| macOS | ✅ Supported | Full support via Keychain + Claude Desktop |
| Linux | 🧪 Experimental | Supports Claude Desktop cookie DB with `libsecret`/GNOME Keyring or Chromium fallback |
| Windows | 🧪 Experimental | Supports Claude Desktop cookie DB with Chromium `Local State` + Windows DPAPI |

---

## Requirements

- macOS 12+, Linux, or Windows 10/11
- [Claude Desktop](https://claude.ai/download) installed and logged in
- [Claude Code CLI](https://claude.ai/code) installed
- Python 3 (`python3 --version`)
- Python package: `cryptography` (installed by the installer when missing)

Linux note: if Claude Desktop uses GNOME Keyring/libsecret, install `secret-tool`:

```bash
# Debian/Ubuntu
sudo apt install libsecret-tools
```

---

## Install (one command)

```bash
git clone https://github.com/RenzoTakada/claude-usage-statusline.git
cd claude-usage-statusline
bash install.sh
```

Windows PowerShell:

```powershell
git clone https://github.com/RenzoTakada/claude-usage-statusline.git
cd claude-usage-statusline
.\install.ps1
```

The installer will:
1. Check prerequisites (OS, Python 3, Claude Desktop)
2. Install the `cryptography` Python package if missing
3. Copy the script to `~/.claude/scripts/claude_usage.py`
4. Run a smoke test
5. Update `~/.claude/settings.json` with the status line configuration

Then **restart Claude Code** — the usage counter will appear in the status line.

> **Keychain prompt:** The first time the script runs, macOS will ask for permission to read Claude Desktop's stored key. Click **"Always Allow"** so it never asks again.

---

## How it works

Claude Desktop stores your session cookies in a local SQLite database. The default paths are:

| Platform | Cookie database |
|---|---|
| macOS | `~/Library/Application Support/Claude/Cookies` |
| Linux | `~/.config/Claude/Cookies` or `$XDG_CONFIG_HOME/Claude/Cookies` |
| Windows | `%APPDATA%\Claude\Cookies` |

The script supports Chromium/Electron cookie encryption per platform:

| Platform | Key source |
|---|---|
| macOS | Keychain entry `Claude Safe Storage` |
| Linux | `secret-tool`/libsecret when available, otherwise Chromium's legacy fallback key |
| Windows | `Local State` encrypted key unwrapped with Windows DPAPI |

The script:
1. Reads the local Claude Desktop cookie key for the current platform
2. Decrypts the session cookies
3. Calls `https://claude.ai/api/organizations/{org}/usage` using those cookies
4. Formats the response and prints it to stdout for Claude Code's status line

Results are cached for 60 seconds in the system temp directory so the API is called at most once per minute, regardless of how often the status line refreshes.

The org ID is **auto-discovered** on the first run (no hardcoded IDs).

### Overrides

Use these environment variables when Claude Desktop stores data in a non-standard location:

| Variable | Purpose |
|---|---|
| `CLAUDE_COOKIES_DB` | Path to the Claude Desktop `Cookies` SQLite DB |
| `CLAUDE_LOCAL_STATE` | Path to Chromium/Electron `Local State` |
| `CLAUDE_SAFE_STORAGE_PASSWORD` | Explicit safe storage password/key fallback |
| `CLAUDE_USAGE_ORG_ID` | Force a specific Claude organization UUID |
| `CLAUDE_USAGE_CACHE_FILE` | Override cache file location |
| `CLAUDE_USAGE_DEBUG=1` | Print errors to stderr |

---

## Manual install (without the installer)

```bash
# 1. Copy the script
mkdir -p ~/.claude/scripts
cp claude_usage.py ~/.claude/scripts/

# 2. Install dependency
pip3 install cryptography

# 3. Add to ~/.claude/settings.json
```

In `~/.claude/settings.json`, add the `statusLine` field:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /home/YOUR_USERNAME/.claude/scripts/claude_usage.py",
    "refreshInterval": 60
  }
}
```

---

## Uninstall

```bash
rm ~/.claude/scripts/claude_usage.py
rm /tmp/claude_usage_cache.json
```

Then remove the `"statusLine"` key from `~/.claude/settings.json`.

---

## Troubleshooting

**Status line shows nothing**
- Make sure Claude Desktop is installed and you are logged in at claude.ai
- Run `python3 ~/.claude/scripts/claude_usage.py` manually to see any errors

**Keychain prompt keeps appearing**
- Click **"Always Allow"** (not just "Allow") when prompted

**`ModuleNotFoundError: cryptography`**
- Run `pip3 install cryptography`

**Linux returns no output**
- Install `secret-tool` (`libsecret-tools`) and make sure your desktop keyring is unlocked
- Run `CLAUDE_USAGE_DEBUG=1 python3 ~/.claude/scripts/claude_usage.py`
- If Claude Desktop uses a custom data path, set `CLAUDE_COOKIES_DB`

**Windows returns no output**
- Run PowerShell as the same user that is logged in to Claude Desktop
- Run `$env:CLAUDE_USAGE_DEBUG=1; python $HOME\.claude\scripts\claude_usage.py`
- If Claude Desktop uses a custom data path, set `CLAUDE_COOKIES_DB` and `CLAUDE_LOCAL_STATE`

---

## Inspiration

Inspired by [claude-counter](https://github.com/she-llac/claude-counter), a browser extension that shows the same metrics as an overlay on claude.ai. This project brings the same information to the Claude Code terminal without requiring a browser extension.

---

## License

MIT
