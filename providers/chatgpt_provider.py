"""ChatGPT (Codex CLI) usage — reads ~/.codex/auth.json (created by
`codex login`) and calls chatgpt.com's private usage endpoint, the
same one the Codex CLI itself uses to enforce your plan's rate limit.

Read-only: never modifies the auth file.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import certifi

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

AUTH_FILE = Path.home() / ".codex" / "auth.json"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


@dataclass
class Window:
    percent: Optional[float] = None
    resets_at: Optional[datetime] = None
    label: str = ""


@dataclass
class ChatGPTUsage:
    windows: list
    plan_type: Optional[str] = None
    fetched_at: Optional[datetime] = None
    available: bool = False
    error: Optional[str] = None

    def __init__(self, windows=None, plan_type=None, fetched_at=None, available=False, error=None):
        self.windows = windows or []
        self.plan_type = plan_type
        self.fetched_at = fetched_at
        self.available = available
        self.error = error


def _load_auth():
    if not AUTH_FILE.exists():
        return None
    try:
        return json.loads(AUTH_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _refresh_access_token(refresh_token: str) -> Optional[dict]:
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }).encode("ascii")
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _save_auth(data: dict, tokens: dict):
    data = dict(data)
    data["tokens"] = tokens
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2))


def _try_fetch(token: str, account_id: Optional[str]):
    """Returns (json_data, None) on success, or (None, error_string).
    error_string is the literal "expired" for a 401 so callers can
    distinguish "needs token refresh" from any other failure."""
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "codex_cli/0",
        "Accept": "application/json",
        "Originator": "codex_cli",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id

    req = urllib.request.Request(USAGE_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, "expired"
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)[:120]


def fetch_usage() -> ChatGPTUsage:
    data = _load_auth()
    if not data:
        return ChatGPTUsage(error="Not signed in — click 'Sign in with ChatGPT' below")

    tokens = data.get("tokens") or {}
    token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    refresh_token = tokens.get("refresh_token")
    if not token:
        return ChatGPTUsage(error="Not signed in — click 'Sign in with ChatGPT' below")

    usage_data, err = _try_fetch(token, account_id)

    # A 401 from a browser-OAuth session (has a refresh_token) means the
    # short-lived access token expired — refresh once and retry, exactly
    # like a normal "stay signed in" browser session, no re-login needed.
    if err == "expired" and refresh_token:
        refreshed = _refresh_access_token(refresh_token)
        if refreshed and refreshed.get("access_token"):
            tokens["access_token"] = refreshed["access_token"]
            tokens["refresh_token"] = refreshed.get("refresh_token", refresh_token)
            if refreshed.get("id_token"):
                tokens["id_token"] = refreshed["id_token"]
            _save_auth(data, tokens)
            usage_data, err = _try_fetch(tokens["access_token"], account_id)

    if err == "expired":
        return ChatGPTUsage(error="Session expired — click 'Sign in with ChatGPT' again")
    if err:
        return ChatGPTUsage(error=err)

    rl = usage_data.get("rate_limit") or {}
    pw = rl.get("primary_window") or {}
    sw = rl.get("secondary_window") or {}

    windows = []
    if pw.get("used_percent") is not None:
        window_seconds = pw.get("limit_window_seconds") or 0
        label = "5-hour" if window_seconds <= 6 * 3600 else "Weekly"
        resets_at = (
            datetime.fromtimestamp(pw["reset_at"], tz=timezone.utc)
            if pw.get("reset_at") else None
        )
        windows.append(Window(percent=pw["used_percent"], resets_at=resets_at, label=label))
    if sw and sw.get("used_percent") is not None:
        window_seconds = sw.get("limit_window_seconds") or 0
        label = "5-hour" if window_seconds <= 6 * 3600 else "Weekly"
        resets_at = (
            datetime.fromtimestamp(sw["reset_at"], tz=timezone.utc)
            if sw.get("reset_at") else None
        )
        windows.append(Window(percent=sw["used_percent"], resets_at=resets_at, label=label))

    return ChatGPTUsage(
        windows=windows,
        plan_type=data.get("plan_type"),
        fetched_at=datetime.now(timezone.utc),
        available=True,
    )
