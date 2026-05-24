#!/usr/bin/env python3
"""
Claude Code status line — session & weekly usage from claude.ai
Reads Claude Desktop cookies (macOS) and calls the usage API.
Cache: 60s TTL in /tmp/claude_usage_cache.json
"""

import hashlib, json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

CACHE_FILE       = "/tmp/claude_usage_cache.json"
CACHE_TTL        = 60  # seconds
COOKIES_DB       = os.path.expanduser("~/Library/Application Support/Claude/Cookies")
KEYCHAIN_SERVICE = "Claude Safe Storage"
KEYCHAIN_ACCOUNT = "Claude"

# ── helpers ──────────────────────────────────────────────────────────────────

def get_aes_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
        capture_output=True, text=True
    )
    password = result.stdout.strip()
    if not password:
        raise RuntimeError("Could not read Claude Safe Storage key from Keychain")
    return hashlib.pbkdf2_hmac("sha1", password.encode(), b"saltysalt", iterations=1003, dklen=16)

def decrypt_cookie(enc_val, aes_key):
    iv = b" " * 16
    ciphertext = enc_val[3:]  # strip v10 prefix
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    decrypted = dec.update(ciphertext) + dec.finalize()
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]
    # Chrome/OSCrypt prepends 32 bytes of binary prefix before the actual value
    return decrypted[32:].decode("ascii", errors="replace").rstrip("\x00")

def get_cookies():
    aes_key = get_aes_key()
    conn = sqlite3.connect(COOKIES_DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, encrypted_value FROM cookies "
        "WHERE host_key LIKE '%claude%' "
        "AND name IN ('sessionKey', 'cf_clearance', 'anthropic-device-id')"
    )
    cookies = {}
    for name, enc_val in cur.fetchall():
        if enc_val and enc_val[:3] == b"v10":
            cookies[name] = decrypt_cookie(enc_val, aes_key)
    conn.close()
    if not cookies:
        raise RuntimeError("No Claude session cookies found — make sure Claude Desktop is installed and you are logged in")
    return cookies

def make_headers(cookies):
    return {
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://claude.ai/",
    }

def get_org_id(cookies):
    """Auto-discover the primary org ID from the API."""
    req = urllib.request.Request("https://claude.ai/api/organizations", headers=make_headers(cookies))
    with urllib.request.urlopen(req, timeout=8) as resp:
        orgs = json.loads(resp.read())
    # Prefer a non-personal org (has members), otherwise fall back to first
    for org in orgs:
        if org.get("capabilities") and "claude_pro" in org.get("capabilities", []):
            return org["uuid"]
    return orgs[0]["uuid"]

def fetch_usage(cookies, org_id):
    url = f"https://claude.ai/api/organizations/{org_id}/usage"
    req = urllib.request.Request(url, headers=make_headers(cookies))
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())

# ── formatting ────────────────────────────────────────────────────────────────

def fmt_countdown(resets_at_iso):
    if not resets_at_iso:
        return "?"
    try:
        dt = datetime.fromisoformat(resets_at_iso)
        remaining = dt - datetime.now(timezone.utc)
        total_secs = int(remaining.total_seconds())
        if total_secs <= 0:
            return "soon"
        days  = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins  = (total_secs % 3600)  // 60
        if days > 0:
            return f"{days}d {hours}h"
        return f"{hours}h {mins}m"
    except Exception:
        return "?"

def bar(pct, width=8):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def render(data):
    s5 = data.get("five_hour", {}) or {}
    s7 = data.get("seven_day", {}) or {}
    p5 = s5.get("utilization", 0)
    p7 = s7.get("utilization", 0)
    r5 = fmt_countdown(s5.get("resets_at"))
    r7 = fmt_countdown(s7.get("resets_at"))
    return f"Session: {p5:.0f}% {bar(p5)} resets in {r5}  Weekly: {p7:.0f}% {bar(p7)} resets in {r7}"

# ── cache ─────────────────────────────────────────────────────────────────────

def load_cache():
    try:
        with open(CACHE_FILE) as f:
            c = json.load(f)
        if time.time() - c.get("ts", 0) < CACHE_TTL:
            return c.get("output"), c.get("org_id")
    except Exception:
        pass
    return None, None

def save_cache(output, org_id):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"ts": time.time(), "output": output, "org_id": org_id}, f)
    except Exception:
        pass

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    cached_output, cached_org = load_cache()
    if cached_output:
        print(cached_output)
        return

    try:
        cookies = get_cookies()
        org_id  = cached_org or get_org_id(cookies)
        data    = fetch_usage(cookies, org_id)
        output  = render(data)
    except Exception as e:
        output  = ""
        org_id  = None

    if output:
        save_cache(output, org_id)
    print(output)

if __name__ == "__main__":
    main()
