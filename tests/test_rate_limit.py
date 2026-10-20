"""Rate Limit is one limit for the whole app (mellow/throttle.py)."""
from __future__ import annotations

import threading

import pytest
import yt_dlp

from mellow import downloader, throttle


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, secs: float) -> None:
        self.slept.append(secs)
        self.now += secs


def _limit(burst: float = 0.5) -> tuple[throttle.SharedRateLimit, FakeTime]:
    t = FakeTime()
    return throttle.SharedRateLimit(burst_secs=burst, clock=t.clock, sleep=t.sleep), t


def test_bytes_within_the_burst_pass_without_waiting():
    lim, t = _limit()
    lim.take(500, 1000)
    assert t.now == 0


def test_callers_together_wait_until_they_are_back_under_the_limit():
    lim, t = _limit()
    for _ in range(4):              # four fragment threads, 1000 bytes each
        lim.take(1000, 1000)
    # 4000 bytes at 1000 B/s is 4 s of traffic; the burst lets them be 0.5 s ahead
    assert t.now == pytest.approx(3.5)


def test_a_quiet_spell_is_not_saved_up_for_a_burst_later():
    lim, t = _limit()
    lim.take(1000, 1000)
    t.now = 60.0                     # paused, or nothing downloading
    lim.take(3000, 1000)
    assert t.now == pytest.approx(62.5)


def test_no_limit_never_waits():
    lim, t = _limit()
    for rate in (None, 0, -5):
        lim.take(10 ** 9, rate)
    lim.take(0, 1000)
    assert t.now == 0 and t.slept == []


def test_a_cancel_stops_the_wait():
    lim, t = _limit()
    calls = []

    def cancelled():
        calls.append(t.now)
        return len(calls) > 2

    lim.take(10 ** 6, 1000, cancelled)       # would be ~1000 s
    assert t.now < 1


def test_waits_are_short_steps():
    lim, t = _limit()
    lim.take(5000, 1000)
    assert t.slept and max(t.slept) <= downloader.PAUSE_POLL_SECS + 1e-9


def test_the_byte_counter_counts_what_is_new_per_file():
    c = throttle.ByteCounter()
    assert c.new_bytes("a.mp4", 4000) == 0          # resumed .part: already there
    assert c.new_bytes("a.mp4", 5000) == 1000
    assert c.new_bytes("a.mp4", 4500) == 0          # a thread reporting late
    assert c.new_bytes("a.mp4", 5600) == 600
    assert c.new_bytes("a.m4a", 100) == 0           # the audio stream of a merge
    assert c.new_bytes("a.m4a", 300) == 200
    assert c.new_bytes("a.mp4", None) == 0


def _hook(rate, cancel=None):
    return downloader._make_progress_hook(
        lambda e: None, None, {"samples": [], "t0": 0}, cancel or threading.Event(), threading.Event(),
        save_sidecar=False, rate_limit=rate)


def test_the_progress_hook_counts_downloaded_bytes_against_the_limit(monkeypatch):
    taken = []
    monkeypatch.setattr(throttle.limiter, "take", lambda n, rate, cancelled: taken.append((n, rate)))
    hook = _hook(1000)
    for done in (100, 700, 1500):
        hook({"status": "downloading", "filename": "/x/a.f137.mp4", "downloaded_bytes": done})
    for done in (100, 400):          # then the audio stream, counted from its own start
        hook({"status": "downloading", "filename": "/x/a.f140.m4a", "downloaded_bytes": done})
    assert taken == [(0, 1000), (600, 1000), (800, 1000), (0, 1000), (300, 1000)]


def test_without_a_limit_the_hook_never_waits(monkeypatch):
    monkeypatch.setattr(throttle.limiter, "take", lambda *a: pytest.fail("no limit set"))
    _hook(None)({"status": "downloading", "filename": "/x/a.mp4", "downloaded_bytes": 10})


def test_a_cancel_while_waiting_ends_the_download(monkeypatch):
    cancel = threading.Event()
    monkeypatch.setattr(throttle.limiter, "take", lambda n, rate, cancelled: cancel.set())
    with pytest.raises(yt_dlp.utils.DownloadCancelled):
        _hook(1000, cancel)({"status": "downloading", "filename": "/x/a.mp4", "downloaded_bytes": 10})


def test_downloads_pass_the_parsed_limit_to_the_hook(tmp_path, monkeypatch):
    seen = {}
    real = downloader._make_progress_hook

    def spy(*a, **kw):
        seen["rate"] = kw.get("rate_limit")
        return real(*a, **kw)

    monkeypatch.setattr(downloader, "_make_progress_hook", spy)

    class FakeYDL:
        def __init__(self, params):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            return 0

        def add_post_processor(self, *a, **kw):
            pass

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    downloader.download_video("https://example.com/v", str(tmp_path),
                              {"format": "video", "quality": "best", "rate_limit": "2M"}, lambda e: None)
    assert seen["rate"] == 2 * 1024 * 1024
