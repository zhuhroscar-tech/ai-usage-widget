"""'Sign in with ChatGPT' — a real, no-terminal browser OAuth flow.

Uses the same public OAuth client Codex CLI and the open-source
openai-oauth project use (loopback PKCE flow against auth.openai.com).
This is the OpenAI-side equivalent of "Sign in with Google" for apps —
no API key, no terminal command, just a normal browser login.

On success, tokens are written to ~/.codex/auth.json in the exact
format Codex CLI itself uses, so chatgpt_provider.py (and the real
Codex CLI, if the user has it) both work off the same file.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

import certifi

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/oauth/authorize"
TOKEN_URL = f"{ISSUER}/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email offline_access"
CALLBACK_PORT = 1455
CALLBACK_PATH = "/auth/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"
AUTH_FILE = Path.home() / ".codex" / "auth.json"

SUCCESS_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Signed in</title>
<style>body{font-family:-apple-system,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#0d0d0d;color:#eee}
.card{text-align:center}</style></head>
<body><div class="card"><h2>You're signed in to ChatGPT.</h2>
<p>You can close this window and return to the menu bar widget.</p></div></body></html>"""

FAILURE_HTML_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>Sign-in failed</title>
<style>body{{font-family:-apple-system,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#0d0d0d;color:#eee}}
.card{{text-align:center;max-width:480px}}</style></head>
<body><div class="card"><h2>Sign-in failed</h2><p>{message}</p></div></body></html>"""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _random_url_safe(n_bytes: int) -> str:
    return _b64url(secrets.token_bytes(n_bytes))


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def _decode_jwt_claims(jwt: str) -> dict:
    try:
        payload = jwt.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


def _derive_account_id(id_token: Optional[str]) -> Optional[str]:
    if not id_token:
        return None
    claims = _decode_jwt_claims(id_token)
    auth_claim = claims.get("https://api.openai.com/auth", {})
    return auth_claim.get("chatgpt_account_id")


class _CallbackResult:
    def __init__(self):
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.event = threading.Event()


def _make_handler(expected_state: str, result: _CallbackResult):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # silence default request logging

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return

            params = dict(urllib.parse.parse_qsl(parsed.query))
            error = params.get("error")
            state = params.get("state")
            code = params.get("code")

            if error:
                result.error = params.get("error_description", error)
                self._respond(400, FAILURE_HTML_TEMPLATE.format(message=result.error))
            elif not code or state != expected_state:
                result.error = "Invalid callback (missing code or mismatched state)."
                self._respond(400, FAILURE_HTML_TEMPLATE.format(message=result.error))
            else:
                result.code = code
                self._respond(200, SUCCESS_HTML)

            result.event.set()

        def _respond(self, status: int, body: str):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

    return Handler


def _exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }).encode("ascii")

    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def start_sign_in(timeout_seconds: float = 300.0, on_message=None) -> dict:
    """Opens the user's real browser to OpenAI's own login page and
    blocks until they finish signing in (or the timeout expires).

    Returns {"ok": True} on success, or {"ok": False, "error": "..."}.
    No password, code, or token ever touches this process's stdin/UI —
    it all happens on OpenAI's own hosted login page in the browser.
    """
    msg = on_message or (lambda s: None)

    state = _random_url_safe(24)
    code_verifier = _random_url_safe(48)
    code_challenge = _code_challenge(code_verifier)

    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    })
    auth_url = f"{AUTHORIZE_URL}?{auth_params}"

    result = _CallbackResult()
    handler_cls = _make_handler(state, result)

    try:
        server = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), handler_cls)
    except OSError as e:
        return {"ok": False, "error": f"Could not start local sign-in listener on port {CALLBACK_PORT}: {e}"}

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    msg("Opening browser to sign in to ChatGPT…")
    webbrowser.open(auth_url)

    got_response = result.event.wait(timeout=timeout_seconds)
    server.shutdown()
    server.server_close()

    if not got_response:
        return {"ok": False, "error": "Sign-in timed out — no response from browser."}
    if result.error:
        return {"ok": False, "error": result.error}
    if not result.code:
        return {"ok": False, "error": "No authorization code received."}

    msg("Exchanging code for tokens…")
    try:
        token_data = _exchange_code_for_tokens(result.code, code_verifier)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "error": f"Token exchange failed (HTTP {e.code}): {body}"}
    except Exception as e:
        return {"ok": False, "error": f"Token exchange failed: {e}"}

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    id_token = token_data.get("id_token")
    account_id = _derive_account_id(id_token) or _derive_account_id(access_token)

    if not access_token or not account_id:
        return {"ok": False, "error": "Sign-in succeeded but no usable account was returned."}

    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if AUTH_FILE.exists():
        try:
            existing = json.loads(AUTH_FILE.read_text())
        except Exception:
            existing = {}

    existing.update({
        "auth_mode": "chatgpt",
        "tokens": {
            "id_token": id_token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "account_id": account_id,
        },
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    AUTH_FILE.write_text(json.dumps(existing, indent=2))
    os.chmod(AUTH_FILE, 0o600)

    return {"ok": True}


def is_signed_in() -> bool:
    if not AUTH_FILE.exists():
        return False
    try:
        data = json.loads(AUTH_FILE.read_text())
        return bool((data.get("tokens") or {}).get("access_token"))
    except Exception:
        return False


def sign_out() -> None:
    if AUTH_FILE.exists():
        try:
            data = json.loads(AUTH_FILE.read_text())
            data.pop("tokens", None)
            AUTH_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            AUTH_FILE.unlink(missing_ok=True)
