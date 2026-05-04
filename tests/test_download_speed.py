"""
Download speed comparison: MellowDLP vs raw yt-dlp.

All tests in this module are @pytest.mark.slow — they require real network and yt-dlp.
Run with:  pytest tests/test_download_speed.py -m slow -v -s
"""
import time
import subprocess
import sys
import shutil
import pytest

# Short public-domain video (~2 MB) — fast to download, good for timing
TEST_URL = "https://www.youtube.com/watch?v=BaW_jenozKc"


def _mellow_download(tmp_path, mode="audio"):
    """Time a download through MellowDLP's downloader module."""
    import downloader
    events = []
    opts = {
        "mode": mode,
        "quality": "best",
        "audio_format": "mp3",
        "embed_thumbnail": False,
        "embed_chapters": False,
        "embed_metadata": False,
        "embed_subs": False,
        "sponsorblock": False,
        "sleep_interval": 0,
    }
    t0 = time.monotonic()
    downloader.download_video(TEST_URL, str(tmp_path), opts, progress_cb=events.append)
    elapsed = time.monotonic() - t0
    complete = [e for e in events if e.get("status") == "complete"]
    return elapsed, bool(complete), events


def _ytdlp_download(tmp_path, mode="audio"):
    """Time a download using the raw yt-dlp CLI."""
    ytdlp = shutil.which("yt-dlp") or sys.executable + " -m yt_dlp"
    if mode == "audio":
        fmt_args = ["-x", "--audio-format", "mp3"]
    else:
        fmt_args = ["-f", "bestvideo+bestaudio/best"]

    cmd = (
        ytdlp.split() if " " in ytdlp else [ytdlp]
    ) + fmt_args + [
        "--no-playlist",
        "--no-write-thumbnail",
        "--no-embed-metadata",
        "-o", str(tmp_path / "%(title)s.%(ext)s"),
        TEST_URL,
    ]
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    elapsed = time.monotonic() - t0
    return elapsed, result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.slow
def test_mellow_completes(tmp_path):
    """MellowDLP download must complete without error."""
    elapsed, ok, events = _mellow_download(tmp_path)
    statuses = [e.get("status") for e in events]
    assert ok, f"No complete event. Statuses: {statuses}"
    print(f"\n  MellowDLP finished in {elapsed:.1f}s")


@pytest.mark.slow
def test_ytdlp_completes(tmp_path):
    """Raw yt-dlp download must complete without error."""
    elapsed, ok, stderr = _ytdlp_download(tmp_path)
    assert ok, f"yt-dlp exited non-zero. stderr: {stderr[-300:]}"
    print(f"\n  yt-dlp finished in {elapsed:.1f}s")


@pytest.mark.slow
def test_speed_comparison(tmp_path):
    """
    MellowDLP should not be more than 3× slower than raw yt-dlp.
    Prints a timing report regardless of outcome.
    """
    mellow_dir = tmp_path / "mellow"
    ytdlp_dir = tmp_path / "ytdlp"
    mellow_dir.mkdir()
    ytdlp_dir.mkdir()

    mellow_t, mellow_ok, mellow_events = _mellow_download(mellow_dir)
    ytdlp_t, ytdlp_ok, _ = _ytdlp_download(ytdlp_dir)

    ratio = mellow_t / ytdlp_t if ytdlp_t > 0 else float("inf")

    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  Download speed comparison          │")
    print(f"  │  MellowDLP : {mellow_t:6.1f}s  ok={mellow_ok}         │")
    print(f"  │  yt-dlp    : {ytdlp_t:6.1f}s  ok={ytdlp_ok}         │")
    print(f"  │  ratio     : {ratio:6.2f}×                  │")
    print(f"  └─────────────────────────────────────┘")

    assert mellow_ok, "MellowDLP download failed"
    assert ytdlp_ok, "yt-dlp download failed"
    assert ratio < 3.0, (
        f"MellowDLP is {ratio:.2f}× slower than raw yt-dlp "
        f"({mellow_t:.1f}s vs {ytdlp_t:.1f}s). "
        "Check sleep_interval default and concurrent_fragments config."
    )


@pytest.mark.slow
def test_sleep_interval_zero_is_faster(tmp_path):
    """
    Downloading with sleep_interval=0 must be faster than sleep_interval=2
    for a 3-item playlist (saves at least 2×2=4 seconds).
    """
    import downloader

    PLAYLIST_3 = "https://youtube.com/playlist?list=PL29g0AFkwZD9LG2WOIiPqzXNmXbcQdAoC"
    base_opts = {
        "mode": "audio", "quality": "best", "audio_format": "mp3",
        "embed_thumbnail": False, "embed_chapters": False,
        "embed_metadata": False, "embed_subs": False, "sponsorblock": False,
    }

    fast_dir = tmp_path / "fast"
    slow_dir = tmp_path / "slow"
    fast_dir.mkdir()
    slow_dir.mkdir()

    t0 = time.monotonic()
    downloader.download_video(PLAYLIST_3, str(fast_dir), {**base_opts, "sleep_interval": 0},
                               progress_cb=lambda e: None)
    fast_t = time.monotonic() - t0

    t0 = time.monotonic()
    downloader.download_video(PLAYLIST_3, str(slow_dir), {**base_opts, "sleep_interval": 2},
                               progress_cb=lambda e: None)
    slow_t = time.monotonic() - t0

    print(f"\n  sleep=0: {fast_t:.1f}s   sleep=2: {slow_t:.1f}s   saved: {slow_t - fast_t:.1f}s")
    assert fast_t < slow_t, (
        f"sleep_interval=0 ({fast_t:.1f}s) should be faster than sleep_interval=2 ({slow_t:.1f}s)"
    )
    assert slow_t - fast_t >= 3.0, (
        f"Expected at least 3s difference for a 3-item playlist with 2s sleep, "
        f"but only saved {slow_t - fast_t:.1f}s"
    )
