"""Vault auto-sync scheduler.

A single daemon thread wakes every SCHEDULER_TICK_SECS and, when auto-sync
is enabled, enqueues a sync for every linked vault folder whose last sync is
older than its configured interval. Folders pick an interval key (or inherit
the global default) via `vault_sync_schedule` in the config:

    auto_sync_enabled: bool            — master switch (default off)
    auto_sync_default_interval: str    — "6h" | "daily" | "weekly"
    vault_sync_schedule: {path: key}   — per-folder override; "off" opts out

Actual enqueueing is injected (`sync_fn`) so this module stays free of any
Flask/server dependency.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable

from . import analytics
from .config import load_config
from .constants import (
    SCHEDULER_TICK_SECS,
    SYNC_INTERVALS,
    SYNC_RETRY_BACKOFF_MAX_SECS,
    SYNC_RETRY_BACKOFF_SECS,
)

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_KEY = "daily"
SCHEDULE_OFF = "off"
SCHEDULE_INHERIT = "default"

_thread: threading.Thread | None = None
_last_attempt: dict[str, float] = {}  # folder → when auto-sync last queued it


def _parse_sync_time(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None


def interval_for(cfg: dict, path: str) -> int | None:
    """The folder's auto-sync interval in seconds, or None when it doesn't auto-sync."""
    key = cfg.get("vault_sync_schedule", {}).get(path, SCHEDULE_INHERIT)
    if key == SCHEDULE_INHERIT:
        key = cfg.get("auto_sync_default_interval", DEFAULT_INTERVAL_KEY)
    if key == SCHEDULE_OFF:
        return None
    return SYNC_INTERVALS.get(key)


def hold_off(folder: str, interval: int) -> tuple[float, int]:
    """(seconds this folder's auto-sync still waits, consecutive failures), from
    its last sync reports, which survive restarts and follow folder moves.

    Cancelled by the user: not before its next turn. Failed N times in a row:
    SYNC_RETRY_BACKOFF_SECS doubled each time, up to SYNC_RETRY_BACKOFF_MAX_SECS
    (a folder whose playlist is gone used to be retried every hour, forever).
    """
    outcomes = analytics.recent_sync_outcomes(folder)
    if not outcomes:
        return 0.0, 0
    status, age = outcomes[0]
    if status == "cancelled":
        return max(0.0, interval - age), 0
    failures = 0
    for outcome, _age in outcomes:
        if outcome != "failed":
            break
        failures += 1
    if not failures:
        return 0.0, 0
    wait = min(SYNC_RETRY_BACKOFF_SECS * 2 ** (failures - 1), SYNC_RETRY_BACKOFF_MAX_SECS)
    return max(0.0, wait - age), failures


def due_folders(cfg: dict, now: float | None = None) -> list[str]:
    """Folders with linked playlists whose last sync is older than their interval."""
    if not cfg.get("auto_sync_enabled", False):
        return []
    now = now if now is not None else time.time()
    sync_times: dict = cfg.get("vault_sync_times", {})
    due: list[str] = []
    for path, urls in cfg.get("vault_playlists", {}).items():
        if not urls:
            continue
        interval = interval_for(cfg, path)
        if not interval:
            continue
        last = _parse_sync_time(sync_times.get(path))
        if last is None or (now - last) >= interval:
            due.append(path)
    return due


def tick(sync_fn: Callable[[str], bool],
         is_syncing_fn: Callable[[str], bool],
         now: float | None = None) -> list[str]:
    """Queue a sync for every due folder; returns the folders queued.

    A folder only stops being due once a sync completes, so one that fails or
    is cancelled (offline, locked cookie DB, user hit cancel) would otherwise
    be re-queued on every tick. SYNC_RETRY_BACKOFF_SECS spaces those retries.
    """
    now = now if now is not None else time.time()
    queued: list[str] = []
    cfg = load_config()
    for path in due_folders(cfg, now):
        if is_syncing_fn(path):
            continue
        if now - _last_attempt.get(path, float("-inf")) < SYNC_RETRY_BACKOFF_SECS:
            continue
        if hold_off(path, interval_for(cfg, path) or 0)[0] > 0:
            continue
        if sync_fn(path):
            _last_attempt[path] = now
            queued.append(path)
            log.info(f"auto-sync queued: {path}")
    return queued


def start(sync_fn: Callable[[str], bool],
          is_syncing_fn: Callable[[str], bool]) -> None:
    """Spawn the scheduler loop (idempotent).

    sync_fn(path) enqueues a sync job; is_syncing_fn(path) reports whether a
    sync for that folder is already queued or running (avoids pile-ups).
    """
    global _thread
    if _thread is not None and _thread.is_alive():
        return

    def _loop() -> None:
        while True:
            time.sleep(SCHEDULER_TICK_SECS)
            try:
                tick(sync_fn, is_syncing_fn)
            except Exception as exc:
                log.warning(f"tick failed: {exc}")

    _thread = threading.Thread(target=_loop, name="auto-sync", daemon=True)
    _thread.start()
