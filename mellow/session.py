"""Who may use the app's API: the windows MellowDLP itself opened.

Every running copy makes a random secret and writes it, with its port, to an
instance file only this account can read (`INSTANCE_FILE`, in `datadir`).
Whoever can read that file is this user: main.py (and a second launch) use it
to make a one-time launch token, put it in a launch page that is also
owner-only, and open that page. The page passes the token to `/launch`, which
answers with

- a session cookie (HttpOnly, SameSite=Strict): what the browser sends by
  itself, for the requests a page can't add a header to (the progress stream,
  video and thumbnails), and
- a per-session token the page keeps in sessionStorage and sends as the
  `X-Mellow-Token` header with every API call. Cookies are shared by every
  port of 127.0.0.1, sessionStorage is not: a page another program serves on
  this machine never has the token.

The token never appears on a command line (other accounts can read those on
Linux and macOS). Launch tokens are an HMAC of the secret with a nonce and an
expiry, so the process that opens the window doesn't need to share memory
with the server (on macOS flaskwebgui runs the server in a child process).

A second launch proves the running copy is ours before opening it
(`instance_proof`): a program that took the port after a crash doesn't know
the secret.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path

from . import datadir
from .constants import (
    LAUNCH_PAGE_KEEP_SECS,
    LAUNCH_TOKEN_TTL_NO_WINDOW_SECS,
    LAUNCH_TOKEN_TTL_SECS,
    SESSIONS_KEEP,
)

log = logging.getLogger(__name__)

COOKIE = "mellow_session"
HEADER = "X-Mellow-Token"
INSTANCE_FILE_NAME = "instance.json"
# sessionStorage key the launch page stores the header token under (gui/lib/api.js)
STORAGE_KEY = "mellow-token"

_lock = threading.Lock()
_secret: bytes | None = None
_port: int | None = None
_used_nonces: dict[str, float] = {}       # launch nonce -> expiry (single use)
_sessions: dict[str, str] = {}            # session id -> header token, oldest first


def instance_file() -> Path:
    return datadir.data_dir() / INSTANCE_FILE_NAME


# ── This copy's secret ─────────────────────────────────────────────────────────

def start_instance(port: int, publish: bool = True) -> None:
    """Make this copy's secret and publish it, with the port, to the owner only
    (publish=False: an in-process server, e.g. the browser tests)."""
    global _secret, _port
    with _lock:
        _secret, _port = secrets.token_bytes(32), port
    if not publish:
        return
    folder = datadir.ensure_private()
    datadir.write_private(folder / INSTANCE_FILE_NAME, json.dumps({"port": port, "secret": _secret.hex(),
                                                          "pid": os.getpid()}))


def stop_instance() -> None:
    """Remove the instance file if it is still ours (a newer copy may have replaced it)."""
    try:
        data = read_instance()
        if data and data["port"] == _port:
            instance_file().unlink(missing_ok=True)
    except OSError:
        pass
    _remove_launch_pages(0)


def read_instance(path: Path | None = None) -> dict | None:
    """{port, secret} of the copy that last started (this account's, or the one at `path`), or None."""
    try:
        data = json.loads((path or instance_file()).read_text(encoding="utf-8"))
        return {"port": int(data["port"]), "secret": bytes.fromhex(data["secret"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _mac(secret: bytes, *parts: object) -> str:
    return hmac.new(secret, "|".join(str(p) for p in parts).encode(), hashlib.sha256).hexdigest()


def same(sent: str, expected: str) -> bool:
    """Constant-time equality for text from a request (compare_digest refuses non-ASCII str)."""
    return hmac.compare_digest(sent.encode("utf-8", "surrogateescape"), expected.encode())


def instance_proof(nonce: str, secret: bytes | None = None, port: int | None = None) -> str:
    """What only a copy that knows the secret can answer to `nonce` (this copy by default)."""
    secret, port = secret or _secret, port or _port
    if secret is None:
        raise RuntimeError("no instance secret: start_instance() first")
    return _mac(secret, "instance", port, nonce)


# ── Launch tokens ─────────────────────────────────────────────────────────────

def launch_token(secret: bytes | None = None, port: int | None = None,
                 ttl: float = LAUNCH_TOKEN_TTL_SECS) -> str:
    """A one-time token that signs a window in (this copy's secret by default)."""
    secret, port = secret or _secret, port or _port
    if secret is None:
        raise RuntimeError("no instance secret: start_instance() first")
    nonce, expires = secrets.token_urlsafe(16), int(time.time() + ttl)
    return f"{nonce}.{expires}.{_mac(secret, 'launch', port, nonce, expires)}"


def redeem(token: str) -> tuple[str, str] | None:
    """(session id, header token) for a valid, unused, unexpired launch token."""
    try:
        nonce, expires_text, mac = token.split(".")
        expires = int(expires_text)
    except (AttributeError, ValueError):
        return None
    now = time.time()
    if _secret is None or expires < now or expires > now + LAUNCH_TOKEN_TTL_NO_WINDOW_SECS:
        return None
    if not same(mac, _mac(_secret, "launch", _port, nonce, expires)):
        return None
    with _lock:
        for old in [n for n, e in _used_nonces.items() if e < now]:
            del _used_nonces[old]
        if nonce in _used_nonces:
            return None
        _used_nonces[nonce] = expires
    return new_session()


def new_session() -> tuple[str, str]:
    """A signed-in session: (id for the cookie, token for the header)."""
    sid, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with _lock:
        _sessions[sid] = token
        while len(_sessions) > SESSIONS_KEEP:
            del _sessions[next(iter(_sessions))]
    return sid, token


def header_token(sid: str | None) -> str | None:
    """The header token of a signed-in session, or None."""
    if not sid:
        return None
    with _lock:
        return _sessions.get(sid)


def end_sessions() -> None:
    with _lock:
        _sessions.clear()


# ── Launch pages ──────────────────────────────────────────────────────────────

def launch_page(base_url: str, token: str) -> Path:
    """An owner-only page that opens `base_url` signed in with `token`.

    Opened instead of the URL itself, so the token is never on a command line.
    """
    folder = datadir.ensure_private()
    _remove_launch_pages(LAUNCH_PAGE_KEEP_SECS)
    target = f"{base_url.rstrip('/')}/launch?t={token}"
    page = folder / f"launch-{secrets.token_hex(8)}.html"
    # replace(): the link with the token doesn't stay in the window's history
    datadir.write_private(page, (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>MellowDLP</title>'
        f'<noscript><meta http-equiv="refresh" content="0;url={html.escape(target, quote=True)}"></noscript>'
        '</head><body style="background:#07090F">'
        f'<script>location.replace({json.dumps(target)});</script></body></html>'))
    return page


def _remove_launch_pages(older_than: float) -> None:
    cutoff = time.time() - older_than
    try:
        for page in datadir.data_dir().glob("launch-*.html"):
            try:
                if page.stat().st_mtime <= cutoff:
                    page.unlink()
            except OSError:
                continue
    except OSError:
        pass


def sign_in(base_url: str, secret: bytes, port: int, timeout: float = 15) -> dict:
    """Sign a program in as the owner (it read the instance file): the headers
    the app's own page sends. For scripts that drive a running copy."""
    from urllib.request import ProxyHandler, build_opener
    opener = build_opener(ProxyHandler({}))
    url = f"{base_url.rstrip('/')}/launch?t={launch_token(secret, port)}"
    with opener.open(url, timeout=timeout) as resp:
        cookie = resp.headers.get("Set-Cookie", "").split(";", 1)[0]
        body = resp.read().decode("utf-8", "replace")
    token = json.loads(body.split(f"sessionStorage.setItem({json.dumps(STORAGE_KEY)}, ", 1)[1].split(")", 1)[0])
    return {"Cookie": cookie, HEADER: token}


def signed_in_page(token: str) -> str:
    """What /launch answers: keep the header token for this tab, then open the app."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>MellowDLP</title></head><body>'
        f'<script>sessionStorage.setItem({json.dumps(STORAGE_KEY)}, {json.dumps(token)});'
        'location.replace("/");</script></body></html>')
