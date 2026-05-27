#!/usr/bin/env python3
"""
Claude Code status line — session & weekly usage from claude.ai.

Reads Claude Desktop cookies on macOS, Linux, or Windows and calls the Claude
usage API. Cookie locations and encryption keys can be overridden with:

  CLAUDE_COOKIES_DB
  CLAUDE_LOCAL_STATE
  CLAUDE_SAFE_STORAGE_PASSWORD
  CLAUDE_USAGE_ORG_ID
  CLAUDE_USAGE_CACHE_FILE
"""

import base64
import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CACHE_TTL = 60
KEYCHAIN_SERVICE = "Claude Safe Storage"
KEYCHAIN_ACCOUNT = "Claude"
COOKIE_NAMES = ("sessionKey", "cf_clearance", "anthropic-device-id")


def user_agent():
    system = platform.system()
    if system == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    if system == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )


def app_data_dir():
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Claude"
    if system == "Windows":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Claude"
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "Claude"


def cookies_db_path():
    override = os.environ.get("CLAUDE_COOKIES_DB")
    return Path(override).expanduser() if override else app_data_dir() / "Cookies"


def local_state_path():
    override = os.environ.get("CLAUDE_LOCAL_STATE")
    return Path(override).expanduser() if override else app_data_dir() / "Local State"


def cache_file_path():
    override = os.environ.get("CLAUDE_USAGE_CACHE_FILE")
    if override:
        return Path(override).expanduser()
    return Path(tempfile.gettempdir()) / "claude_usage_cache.json"


def derive_chromium_key(password, iterations):
    return hashlib.pbkdf2_hmac("sha1", password.encode(), b"saltysalt", iterations=iterations, dklen=16)


def get_macos_password():
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    password = result.stdout.strip()
    if not password:
        raise RuntimeError("Could not read Claude Safe Storage key from macOS Keychain")
    return password


def secret_tool_lookup(*args):
    if not shutil.which("secret-tool"):
        return None
    result = subprocess.run(["secret-tool", "lookup", *args], capture_output=True, text=True, check=False)
    value = result.stdout.strip()
    return value or None


def get_linux_password():
    override = os.environ.get("CLAUDE_SAFE_STORAGE_PASSWORD")
    if override:
        return override

    lookups = [
        ("application", "Claude"),
        ("application", "claude"),
        ("application", "chrome"),
        ("application", "chromium"),
    ]
    for attrs in lookups:
        value = secret_tool_lookup(*attrs)
        if value:
            return value

    # Chromium's historical Linux fallback when no keyring is available.
    return "peanuts"


def dpapi_unprotect(data):
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise RuntimeError("Windows DPAPI could not decrypt Claude cookie key")

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def get_windows_aes_key():
    path = local_state_path()
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as f:
        local_state = json.load(f)

    encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
    if not encrypted_key_b64:
        return None

    encrypted_key = base64.b64decode(encrypted_key_b64)
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    return dpapi_unprotect(encrypted_key)


def candidate_keys():
    system = platform.system()
    keys = []

    override = os.environ.get("CLAUDE_SAFE_STORAGE_PASSWORD")
    if override:
        keys.append(derive_chromium_key(override, 1003))

    if system == "Darwin":
        keys.append(derive_chromium_key(get_macos_password(), 1003))
    elif system == "Linux":
        password = get_linux_password()
        iterations = 1 if password == "peanuts" else 1
        keys.append(derive_chromium_key(password, iterations))
    elif system == "Windows":
        key = get_windows_aes_key()
        if key:
            keys.append(key)

    return keys


def decrypt_cbc(encrypted_value, key):
    iv = b" " * 16
    ciphertext = encrypted_value[3:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    candidates = []
    if len(decrypted) > 32:
        candidates.append(decrypted[32:])
    candidates.append(decrypted)

    for candidate in candidates:
        try:
            text = candidate.decode("utf-8").rstrip("\x00")
            if text:
                return text
        except UnicodeDecodeError:
            pass

    return decrypted.decode("utf-8", errors="replace").rstrip("\x00")


def decrypt_gcm(encrypted_value, key):
    nonce = encrypted_value[3:15]
    ciphertext_and_tag = encrypted_value[15:]
    return AESGCM(key).decrypt(nonce, ciphertext_and_tag, None).decode("utf-8")


def decrypt_cookie(encrypted_value, keys):
    if not encrypted_value:
        return ""

    if isinstance(encrypted_value, memoryview):
        encrypted_value = encrypted_value.tobytes()

    if not encrypted_value.startswith((b"v10", b"v11")):
        if platform.system() == "Windows":
            return dpapi_unprotect(encrypted_value).decode("utf-8")
        return encrypted_value.decode("utf-8", errors="replace")

    errors = []
    for key in keys:
        if len(key) in (16, 24, 32):
            try:
                return decrypt_gcm(encrypted_value, key)
            except Exception as exc:
                errors.append(exc)

            try:
                return decrypt_cbc(encrypted_value, key)
            except Exception as exc:
                errors.append(exc)

    raise RuntimeError(f"Could not decrypt Claude cookie ({len(errors)} attempts failed)")


def get_cookies():
    db_path = cookies_db_path()
    if not db_path.exists():
        raise RuntimeError(f"Claude cookies database not found: {db_path}")

    keys = candidate_keys()
    if not keys:
        raise RuntimeError("No cookie decryption key available for this platform")

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in COOKIE_NAMES)
        cur.execute(
            "SELECT name, value, encrypted_value FROM cookies "
            "WHERE host_key LIKE '%claude%' "
            f"AND name IN ({placeholders})",
            COOKIE_NAMES,
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    cookies = {}
    for name, value, encrypted_value in rows:
        if value:
            cookies[name] = value
        elif encrypted_value:
            cookies[name] = decrypt_cookie(encrypted_value, keys)

    if not cookies:
        raise RuntimeError("No Claude session cookies found — make sure Claude Desktop is installed and logged in")

    return cookies


def make_headers(cookies):
    return {
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "User-Agent": user_agent(),
        "Accept": "application/json",
        "Referer": "https://claude.ai/",
    }


def get_org_id(cookies):
    override = os.environ.get("CLAUDE_USAGE_ORG_ID")
    if override:
        return override

    req = urllib.request.Request("https://claude.ai/api/organizations", headers=make_headers(cookies))
    with urllib.request.urlopen(req, timeout=8) as resp:
        orgs = json.loads(resp.read())

    for org in orgs:
        if org.get("capabilities") and "claude_pro" in org.get("capabilities", []):
            return org["uuid"]
    return orgs[0]["uuid"]


def fetch_usage(cookies, org_id):
    url = f"https://claude.ai/api/organizations/{org_id}/usage"
    req = urllib.request.Request(url, headers=make_headers(cookies))
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


def fmt_countdown(resets_at_iso):
    if not resets_at_iso:
        return "?"
    try:
        dt = datetime.fromisoformat(resets_at_iso)
        remaining = dt - datetime.now(timezone.utc)
        total_secs = int(remaining.total_seconds())
        if total_secs <= 0:
            return "soon"
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60
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


def load_cache():
    try:
        with cache_file_path().open() as f:
            cache = json.load(f)
        if time.time() - cache.get("ts", 0) < CACHE_TTL:
            return cache.get("output"), cache.get("org_id")
    except Exception:
        pass
    return None, None


def save_cache(output, org_id):
    try:
        with cache_file_path().open("w") as f:
            json.dump({"ts": time.time(), "output": output, "org_id": org_id}, f)
    except Exception:
        pass


def main():
    cached_output, cached_org = load_cache()
    if cached_output:
        print(cached_output)
        return

    try:
        cookies = get_cookies()
        org_id = cached_org or get_org_id(cookies)
        data = fetch_usage(cookies, org_id)
        output = render(data)
    except Exception as exc:
        if os.environ.get("CLAUDE_USAGE_DEBUG"):
            print(f"claude-usage-statusline error: {exc}", file=sys.stderr)
        output = ""
        org_id = None

    if output:
        save_cache(output, org_id)
    print(output)


if __name__ == "__main__":
    main()
