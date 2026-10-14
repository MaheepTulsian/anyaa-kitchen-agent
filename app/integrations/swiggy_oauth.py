"""OAuth 2.1 + PKCE for the Swiggy MCP servers.

Flow: /api/instamart/login sends the browser to Swiggy (phone + OTP), Swiggy redirects back to
/api/instamart/callback, we swap the code for a token and keep it in data/swiggy_token.json.
"""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx

from app import config
from app.models import Model

TOKEN_PATH = config.DATA_DIR / "swiggy_token.json"
SCOPE = "mcp:tools"

# state -> (code_verifier, redirect_uri, client_id), held only until the callback arrives
_pending: dict[str, tuple[str, str, str]] = {}


class SwiggyToken(Model):
    access_token: str
    refresh_token: str | None = None
    expires_at: float  # unix seconds
    client_id: str


class OAuthError(RuntimeError):
    pass


def _register_client(redirect_uri: str) -> str:
    """Dynamic client registration; Swiggy returns a public client id."""
    response = httpx.post(
        f"{config.SWIGGY_AUTH_URL}/register",
        json={
            "client_name": "Anyaa Kitchen Agent",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
        timeout=15,
    )
    if response.status_code not in (200, 201):
        raise OAuthError(f"client registration failed: {response.status_code} {response.text[:200]}")
    return response.json()["client_id"]


def login_url(redirect_uri: str) -> str:
    client_id = _register_client(redirect_uri)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    state = secrets.token_urlsafe(16)
    _pending[state] = (verifier, redirect_uri, client_id)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
            "resource": "https://mcp.swiggy.com",
        }
    )
    return f"{config.SWIGGY_AUTH_URL}/authorize?{query}"


def _save(body: dict, client_id: str, old_refresh: str | None = None) -> SwiggyToken:
    token = SwiggyToken(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token") or old_refresh,
        expires_at=time.time() + int(body.get("expires_in", 3600)),
        client_id=client_id,
    )
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token.model_dump_json())
    return token


def exchange_code(code: str, state: str) -> SwiggyToken:
    if state not in _pending:
        raise OAuthError("unknown or expired login attempt; start again from /api/instamart/login")
    verifier, redirect_uri, client_id = _pending.pop(state)
    response = httpx.post(
        f"{config.SWIGGY_AUTH_URL}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise OAuthError(f"token exchange failed: {response.status_code} {response.text[:200]}")
    return _save(response.json(), client_id)


def load_token() -> SwiggyToken | None:
    if not TOKEN_PATH.exists():
        return None
    return SwiggyToken.model_validate_json(TOKEN_PATH.read_text())


def access_token() -> str:
    """A valid access token, refreshing it if it is about to expire."""
    token = load_token()
    if token is None:
        raise OAuthError("not logged in to Swiggy; open /api/instamart/login")
    if time.time() < token.expires_at - 60:
        return token.access_token
    if not token.refresh_token:
        raise OAuthError("Swiggy session expired; log in again at /api/instamart/login")

    response = httpx.post(
        f"{config.SWIGGY_AUTH_URL}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": token.client_id,
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise OAuthError(f"token refresh failed: {response.status_code}; log in again")
    return _save(response.json(), token.client_id, token.refresh_token).access_token


def logout() -> None:
    TOKEN_PATH.unlink(missing_ok=True)
