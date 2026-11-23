"""Vault auto-sync scheduler.

A single daemon thread wakes every SCHEDULER_TICK_SECS and, when auto-sync
is enabled, enqueues a sync for every linked vault folder whose last sync is
older than its configured interval. Folders pick an interval key (or inherit
the global default) via `vault_sync_schedule` in the config:

    auto_sync_enabled: bool            — master switch (default off)
    auto_sync_default_interval: str    — "6h" | "daily" | "weekly"
    vault_sync_schedule: {path: key}   — per-folder override; "off" opts out
    auto_sync_time: "HH:MM"            — when "daily" folders sync (local time)

"daily" is a time of day, not 24 hours after the last sync: a folder is due
once that day's auto_sync_time has passed and it hasn't synced since (or
synced only SYNC_DAILY_MIN_GAP_SECS before it, by hand). A computer that was
off or asleep at that time catches up as soon as MellowDLP runs. MellowDLP
never wakes or keeps awake a computer for it (power.py holds sleep off only
while a job is queued); "6h" and "weekly" stay intervals.

Actual enqueueing is injected (`sync_fn`) so this module stays free of any
Flask/server dependency.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from . import analytics
from .config import load_config
from .constants import (
    DEFAULT_AUTO_SYNC_TIME,
    SCHEDULER_TICK_SECS,
    SYNC_DAILY_MIN_GAP_SECS,
    SYNC_INTERVALS,
    SYNC_RETRY_BACKOFF_MAX_SECS,
    SYNC_RETRY_BACKOFF_SECS,
)

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_KEY = "daily"
SCHEDULE_OFF = "off"
SCHEDULE_INHERIT = "default"
DAILY_SECS = SYNC_INTERVALS["daily"]

_thread: threading.Thread | None = None
_last_attempt: dict[str, float] = {}  # folder → when auto-sync last queued it


def _parse_sync_time(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None


def _hhmm(text: str) -> tuple[int, int] | None:
    try:
        hour, minute = (int(x) for x in str(text).split(":"))
    except ValueError:
        return None
    return (hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None


def daily_time(cfg: dict) -> str:
    """Config's daily sync time as HH:MM (an unreadable one: the default)."""
    hm = _hhmm(cfg.get("auto_sync_time") or "") or _hhmm(DEFAULT_AUTO_SYNC_TIME)
    return f"{hm[0]:02d}:{hm[1]:02d}"


def daily_mark(hhmm: str, now: float) -> float:
    """The latest local HH:MM at or before `now`: today's once it has passed,
    else yesterday's (wall-clock arithmetic, so DST days are right too)."""
    hour, minute = _hhmm(hhmm) or _hhmm(DEFAULT_AUTO_SYNC_TIME)
    now_dt = datetime.fromtimestamp(now)
    mark = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if mark > now_dt:
        mark -= timedelta(days=1)
    return mark.timestamp()


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


def is_due(cfg: dict, interval: int, last: float | None, now: float) -> bool:
    """Whether a folder with this interval, last synced at `last`, syncs now."""
    if last is None:
        return True
    if interval == DAILY_SECS:
        mark = daily_mark(daily_time(cfg), now)
        return last < mark and (mark - last) >= SYNC_DAILY_MIN_GAP_SECS
    return (now - last) >= interval


def due_folders(cfg: dict, now: float | None = None) -> list[str]:
    """Folders with linked playlists whose turn has come (is_due)."""
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
        if is_due(cfg, interval, _parse_sync_time(sync_times.get(path)), now):
            due.append(path)
    return due


def next_wait(cfg: dict, now: float | None = None) -> float:
    """How long the loop sleeps: SCHEDULER_TICK_SECS, or less when the daily
    time comes sooner, so a daily sync starts on the minute."""
    if not cfg.get("auto_sync_enabled", False):
        return SCHEDULER_TICK_SECS
    now = now if now is not None else time.time()
    next_mark = daily_mark(daily_time(cfg), now) + DAILY_SECS
    if next_mark - now > DAILY_SECS:     # a DST day: the mark computed for "tomorrow" is today's
        next_mark -= DAILY_SECS
    return max(1.0, min(SCHEDULER_TICK_SECS, next_mark - now + 1))


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
        wait = SCHEDULER_TICK_SECS
        while True:
            time.sleep(wait)
            try:
                tick(sync_fn, is_syncing_fn)
                wait = next_wait(load_config())
            except Exception as exc:
                log.warning(f"tick failed: {exc}")
                wait = SCHEDULER_TICK_SECS

    _thread = threading.Thread(target=_loop, name="auto-sync", daemon=True)
    _thread.start()
