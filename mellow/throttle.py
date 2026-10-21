"""The download speed limit, shared by every download in the app.

yt-dlp's own ``ratelimit`` holds each connection to the limit, but a
fragmented stream (HLS/DASH) downloads ``concurrent_fragments`` pieces at
once and each job runs its own yt-dlp: four threads and two jobs used eight
times what Config's Rate Limit says. The progress hooks of all running
downloads feed one limiter here instead, and the thread that reported the
bytes sleeps until the app as a whole is back under the limit.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from .constants import PAUSE_POLL_SECS, RATE_LIMIT_BURST_SECS


class SharedRateLimit:
    """A byte budget at ``rate`` bytes/second for all callers together
    (GCRA: each call moves a shared "next free" time forward by
    nbytes / rate; a caller ahead of it by more than the burst waits)."""

    def __init__(self, burst_secs: float = RATE_LIMIT_BURST_SECS,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._burst = burst_secs
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._free_at = 0.0

    def take(self, nbytes: float, rate: float | None,
             cancelled: Callable[[], bool] = lambda: False) -> None:
        """Count ``nbytes`` just received; sleep while the app is over ``rate``.

        Returns early once ``cancelled()`` is true, so a cancel never waits
        out a long sleep.
        """
        if nbytes <= 0 or not rate or rate <= 0:
            return
        with self._lock:
            now = self._clock()
            self._free_at = max(self._free_at, now) + nbytes / rate
            until = self._free_at - self._burst
        while not cancelled():
            left = until - self._clock()
            if left <= 0:
                return
            self._sleep(min(left, PAUSE_POLL_SECS))


limiter = SharedRateLimit()


class ByteCounter:
    """New bytes since the last progress report, per file of one download.

    yt-dlp reports a running total per file (fragment threads add into one
    total). The first report of a file only sets the starting point: a
    resumed .part starts at what is already on disk, which isn't new traffic.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: dict[str, int] = {}

    def new_bytes(self, key: str, total: int | None) -> int:
        if total is None:
            return 0
        with self._lock:
            last = self._seen.get(key)
            if last is None or total > last:
                self._seen[key] = total
            return total - last if last is not None and total > last else 0
