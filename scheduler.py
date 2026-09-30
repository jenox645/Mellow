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

import threading
import time
from datetime import datetime
from typing import Callable

from config import load_config
from constants import SCHEDULER_TICK_SECS, SYNC_INTERVALS

DEFAULT_INTERVAL_KEY = "daily"
SCHEDULE_OFF = "off"
SCHEDULE_INHERIT = "default"

_thread: threading.Thread | None = None


def _parse_sync_time(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None


def due_folders(cfg: dict, now: float | None = None) -> list[str]:
    """Folders with linked playlists whose last sync is older than their interval."""
    if not cfg.get("auto_sync_enabled", False):
        return []
    now = now if now is not None else time.time()
    default_key = cfg.get("auto_sync_default_interval", DEFAULT_INTERVAL_KEY)
    schedule: dict = cfg.get("vault_sync_schedule", {})
    sync_times: dict = cfg.get("vault_sync_times", {})
    due: list[str] = []
    for path, urls in cfg.get("vault_playlists", {}).items():
        if not urls:
            continue
        key = schedule.get(path, SCHEDULE_INHERIT)
        if key == SCHEDULE_INHERIT:
            key = default_key
        if key == SCHEDULE_OFF:
            continue
        interval = SYNC_INTERVALS.get(key)
        if not interval:
            continue
        last = _parse_sync_time(sync_times.get(path))
        if last is None or (now - last) >= interval:
            due.append(path)
    return due


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
                cfg = load_config()
                for path in due_folders(cfg):
                    if is_syncing_fn(path):
                        continue
                    if sync_fn(path):
                        print(f"[SCHEDULER] auto-sync queued: {path}", flush=True)
            except Exception as exc:
                print(f"[SCHEDULER] tick failed: {exc}", flush=True)

    _thread = threading.Thread(target=_loop, name="auto-sync", daemon=True)
    _thread.start()
