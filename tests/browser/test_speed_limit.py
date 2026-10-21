"""Rate Limit holds for everything downloading at once: a fragmented (HLS)
stream fetched by several threads, two jobs side by side.

Each yt-dlp connection used to get the whole limit, so 4 fragment threads
and 2 jobs ran at about 5x what Config said.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time

import pytest
from conftest import _serve
from flask import Flask, send_from_directory

from mellow import downloader

pytestmark = pytest.mark.browser

RATE = "1M"                    # yt-dlp's units: 1 MiB/s
RATE_BYTES = 1024 * 1024


@pytest.fixture(scope="module")
def hls_stream(tmp_path_factory):
    """An 8-second HLS stream in 16 segments (~1.8 MB: noise doesn't compress)."""
    folder = tmp_path_factory.mktemp("hls")
    subprocess.run([
        shutil.which("ffmpeg") or pytest.fail("needs ffmpeg"), "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=8,noise=alls=60:allf=t",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", "-an",
        "-g", "12", "-f", "hls", "-hls_time", "0.5", "-hls_list_size", "0",
        str(folder / "stream.m3u8"),
    ], check=True)
    site = Flask("hls_site")
    site.add_url_rule("/<path:name>", view_func=lambda name: send_from_directory(folder, name))
    url, stop = _serve(site)
    yield f"{url}/stream.m3u8", sum(p.stat().st_size for p in folder.glob("*.ts"))
    stop()


def test_two_jobs_of_four_fragment_threads_share_one_limit(hls_stream, tmp_path):
    url, size = hls_stream
    opts = {"format": "video", "quality": "best", "container": "mp4",
            "rate_limit": RATE, "concurrent_fragments": 4}
    results = []

    def job(n):
        out = tmp_path / f"job{n}"
        out.mkdir()
        results.append(downloader.download_video(url, str(out), opts, lambda e: None))

    t0 = time.monotonic()
    threads = [threading.Thread(target=job, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    elapsed = time.monotonic() - t0

    assert results == ["success", "success"]
    # Both streams through one 1 MiB/s limit, less the burst it lets through
    least = 2 * size / RATE_BYTES - downloader.throttle.limiter._burst
    assert elapsed >= 0.9 * least, f"{2 * size} bytes in {elapsed:.2f}s: over the limit"
