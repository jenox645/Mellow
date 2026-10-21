"""API keys: how programs other than MellowDLP's own windows use it (/api/v1).

A key is made in Config → API access, shown once, and stored only as a
SHA-256 hash in the owner-only data folder (`datadir`). Each key carries the
scopes it was given; the /api/v1 endpoints check them (server.py). Keys never
reach the rest of the API: SQL, backups, settings, file paths and deleting are
for signed-in windows only. Revoking a key removes it.

Key text: "mlw_<id>_<secret>", the id (8 hex) to find it, the secret (32
random bytes) to prove it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time

from . import datadir
from .constants import API_KEY_LAST_USED_EVERY_SECS, API_KEYS_MAX

KEYS_FILE_NAME = "api_keys.json"
PREFIX = "mlw_"
# What a key may be allowed to do, and how Config describes it
SCOPES: dict[str, str] = {
    "downloads:create": "Add downloads",
    "queue:read": "See the queue",
    "events:read": "Follow download progress",
}

_lock = threading.Lock()


class ApiKeyError(ValueError):
    """A key that can't be made, in words for the user."""


def _path():
    return datadir.data_dir() / KEYS_FILE_NAME


def _load() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [k for k in data if isinstance(k, dict) and k.get("id") and k.get("hash")] if isinstance(data, list) else []


def _save(keys: list[dict]) -> None:
    folder = datadir.ensure_private()
    datadir.write_private(folder / KEYS_FILE_NAME, json.dumps(keys, indent=2))


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _public(key: dict) -> dict:
    return {k: key.get(k) for k in ("id", "name", "scopes", "created", "last_used")}


def list_keys() -> list[dict]:
    """Every key, without what would let anyone use it."""
    with _lock:
        return [_public(k) for k in _load()]


def create(name: str, scopes: list[str]) -> tuple[str, dict]:
    """(the key text, shown once; its public record)."""
    name = " ".join(str(name or "").split())[:60]
    if not name:
        raise ApiKeyError("Give the key a name (what will use it).")
    scopes = sorted(set(scopes or []))
    if not scopes or any(s not in SCOPES for s in scopes):
        raise ApiKeyError(f"Choose what the key may do: {', '.join(SCOPES)}.")
    with _lock:
        keys = _load()
        if len(keys) >= API_KEYS_MAX:
            raise ApiKeyError(f"At most {API_KEYS_MAX} keys: revoke one you no longer use.")
        key_id, secret = secrets.token_hex(4), secrets.token_urlsafe(32)
        record = {"id": key_id, "name": name, "scopes": scopes, "hash": _hash(secret),
                  "created": int(time.time()), "last_used": None}
        keys.append(record)
        _save(keys)
    return f"{PREFIX}{key_id}_{secret}", _public(record)


def revoke(key_id: str) -> bool:
    with _lock:
        keys = _load()
        kept = [k for k in keys if k["id"] != key_id]
        if len(kept) == len(keys):
            return False
        _save(kept)
        return True


def check(text: str | None) -> dict | None:
    """The public record of the key `text` is, or None (unknown, revoked, malformed)."""
    if not text or not text.startswith(PREFIX):
        return None
    key_id, _, secret = text[len(PREFIX):].partition("_")
    if not key_id or not secret:
        return None
    with _lock:
        keys = _load()
        key = next((k for k in keys if k["id"] == key_id), None)
        try:
            given = _hash(secret)
        except UnicodeEncodeError:
            return None
        if key is None or not hmac.compare_digest(key["hash"].encode(), given.encode()):
            return None
        now = int(time.time())
        # Written now and then, not on every request
        if not key.get("last_used") or now - key["last_used"] >= API_KEY_LAST_USED_EVERY_SECS:
            key["last_used"] = now
            try:
                _save(keys)
            except OSError:
                pass
        return _public(key)
