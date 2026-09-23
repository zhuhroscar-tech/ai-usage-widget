"""Claude.ai usage — reads Claude.app's own decrypted session cookie
(via its Keychain-protected Safe Storage key) and calls the same
private endpoint Claude.app itself uses to show your usage bar.

Nothing is uploaded anywhere except the one HTTPS request to
claude.ai, using credentials already present on this Mac. Read-only:
never writes to the cookie file or Keychain.
"""
import json
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import certifi
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

COOKIES_DB = Path.home() / "Library/Application Support/Claude/Cookies"
ORG_CACHE = Path.home() / ".ai-usage-widget" / "claude_org_id.cache"


_cached_key: Optional[bytes] = None


def _get_keychain_password() -> bytes:
    out = subprocess.run(
        ["security", "find-generic-password", "-s", "Claude Safe Storage", "-a", "Claude Key", "-w"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip().encode()


def _get_derived_key() -> bytes:
    # Cached for the lifetime of the process so we only ever hit the
    # Keychain once per app launch, not on every 90s refresh — avoids
    # macOS re-prompting for access repeatedly.
    global _cached_key
    if _cached_key is None:
        _cached_key = _derive_key(_get_keychain_password())
    return _cached_key


def _derive_key(password: bytes) -> bytes:
    return PBKDF2(password, b"saltysalt", dkLen=16, count=1003)


def _decrypt_v10(enc: bytes, key: bytes) -> str:
    if enc[:3] != b"v10":
        raise ValueError(f"unsupported cookie prefix {enc[:3]!r}")
    cipher = AES.new(key, AES.MODE_CBC, iv=b" " * 16)
    pt = cipher.decrypt(enc[3:])
    pad = pt[-1]
    if pad and pad <= 16:
        pt = pt[:-pad]
    if len(pt) > 32:
        try:
            return pt[32:].decode("utf-8")
        except UnicodeDecodeError:
            pass
    return pt.decode("utf-8")


def _load_cookies() -> dict:
    if not COOKIES_DB.exists():
        raise FileNotFoundError("Claude.app cookie store not found — is Claude.app installed and signed in?")
    key = _get_derived_key()
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy(COOKIES_DB, tmp)
    try:
        con = sqlite3.connect(tmp)
        rows = con.execute(
            "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%claude.ai%'"
        ).fetchall()
    finally:
        con.close()
        Path(tmp).unlink(missing_ok=True)
    cookies = {}
    for name, enc in rows:
        try:
            cookies[name] = _decrypt_v10(enc, key)
        except Exception:
            pass
    return cookies


def _http_get(url: str, cookies: dict) -> dict:
    headers = {
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Anthropic-Client-Platform": "web_claude_ai",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_org_id(cookies: dict) -> str:
    last = cookies.get("lastActiveOrg")
    if last:
        return last
    if ORG_CACHE.exists():
        try:
            return ORG_CACHE.read_text().strip()
        except OSError:
            pass
    data = _http_get("https://claude.ai/api/organizations", cookies)
    if isinstance(data, list) and data:
        org_id = data[0].get("uuid")
        if org_id:
            ORG_CACHE.parent.mkdir(parents=True, exist_ok=True)
            ORG_CACHE.write_text(org_id)
            return org_id
    raise RuntimeError("could not discover Claude organization id")


@dataclass
class Window:
    percent: Optional[float] = None
    resets_at: Optional[datetime] = None
    label: str = ""


@dataclass
class ClaudeUsage:
    windows: list = field(default_factory=list)  # list[Window]
    fetched_at: Optional[datetime] = None
    available: bool = False
    error: Optional[str] = None


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def fetch_usage() -> ClaudeUsage:
    try:
        cookies = _load_cookies()
        if "sessionKey" not in cookies:
            return ClaudeUsage(error="Not signed in to Claude.app")
        org_id = _get_org_id(cookies)
        data = _http_get(f"https://claude.ai/api/organizations/{org_id}/usage", cookies)
    except urllib.error.HTTPError as e:
        return ClaudeUsage(error=f"HTTP {e.code}")
    except FileNotFoundError as e:
        return ClaudeUsage(error=str(e))
    except Exception as e:
        return ClaudeUsage(error=str(e)[:120])

    windows = []
    fh = data.get("five_hour")
    if fh and fh.get("utilization") is not None:
        windows.append(Window(percent=fh["utilization"], resets_at=_parse_iso(fh.get("resets_at")), label="5-hour session"))
    sd = data.get("seven_day")
    if sd and sd.get("utilization") is not None:
        windows.append(Window(percent=sd["utilization"], resets_at=_parse_iso(sd.get("resets_at")), label="7-day"))

    # Fall back to the generic `limits` array for accounts where the
    # top-level five_hour/seven_day keys are null but `limits` is populated.
    if not windows:
        for lim in data.get("limits") or []:
            if lim.get("kind") == "session" and lim.get("percent") is not None:
                windows.append(Window(percent=lim["percent"], resets_at=_parse_iso(lim.get("resets_at")), label="5-hour session"))
            elif lim.get("group") == "weekly" and lim.get("is_active") and lim.get("percent") is not None:
                windows.append(Window(percent=lim["percent"], resets_at=_parse_iso(lim.get("resets_at")), label="Weekly"))

    return ClaudeUsage(windows=windows, fetched_at=datetime.now(timezone.utc), available=True)
