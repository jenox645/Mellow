"""Fixtures for the browser smoke tests: the app, a media site, a browser.

The app (mellow.server) and a small media site run in this process on free
ports; the media site serves clips ffmpeg makes once per session, so no test
touches the network. Every test gets the root conftest's temp config/DB and
downloads into its own folder. Needs a built frontend (static/), ffmpeg and
Playwright's Chromium:

    python build_setup.py --frontend-only
    pip install playwright && python -m playwright install chromium
    python -m pytest tests/browser -m browser
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from flask import Flask, Response, abort, send_from_directory
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[2]
# The sandbox image ships a Chromium Playwright can drive; elsewhere the
# browser comes from `python -m playwright install chromium`
LOCAL_CHROMIUM = Path("/opt/pw-browsers/chromium")
SLOW_CHUNK = 64 * 1024
SLOW_CHUNK_DELAY_SECS = 0.25

CLIPS = {            # name: (seconds, test pattern)
    "clip": (2, "testsrc"),
    "second": (3, "smptebars"),
    "third": (2, "rgbtestsrc"),
    "long": (40, "testsrc2"),     # served slowly, for cancel
}


def _serve(app: Flask) -> tuple[str, callable]:
    server = make_server("127.0.0.1", 0, app, threaded=True)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server.shutdown


def _make_clips(folder: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.fail("the browser tests need ffmpeg on PATH to make their media")
    for name, (secs, pattern) in CLIPS.items():
        subprocess.run([
            ffmpeg, "-v", "error", "-y",
            "-f", "lavfi", "-i", f"{pattern}=size=160x120:rate=15:duration={secs}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart",
            str(folder / f"{name}.mp4"),
        ], check=True)


# DASH videos: video and audio as separate streams, like YouTube, so a
# download merges two parts. Audio requests for the names in here fail (403).
DASH_CLIPS = ("dash-one", "dash-two")
DASH_AUDIO_REFUSED: set[str] = set()


def _make_dash(folder: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    for i, name in enumerate(DASH_CLIPS):
        out = folder / name
        out.mkdir()
        subprocess.run([
            ffmpeg, "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=2",
            "-f", "lavfi", "-i", f"sine=frequency={440 + 220 * i}:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-shortest", "-map", "0:v", "-map", "1:a",
            "-f", "dash", "-seg_duration", "1", "-use_template", "1", "-use_timeline", "0",
            "-adaptation_sets", "id=0,streams=v id=1,streams=a", str(out / "manifest.mpd"),
        ], check=True)


@pytest.fixture(scope="session")
def media_site(tmp_path_factory):
    """A tiny video site: /<name>.mp4, /slow/<name>.mp4, /playlist (three clips) and
    /playlist-dash (two videos with separate audio, see DASH_AUDIO_REFUSED)."""
    folder = tmp_path_factory.mktemp("media")
    _make_clips(folder)
    _make_dash(folder)
    site = Flask("media_site")

    @site.route("/<name>.mp4")
    def media(name):
        return send_from_directory(folder, f"{name}.mp4", conditional=True)

    @site.route("/slow/<name>.mp4")
    def slow(name):
        path = folder / f"{name}.mp4"
        if not path.exists():
            abort(404)

        def chunks():
            with open(path, "rb") as f:
                while chunk := f.read(SLOW_CHUNK):
                    yield chunk
                    time.sleep(SLOW_CHUNK_DELAY_SECS)
        return Response(chunks(), mimetype="video/mp4",
                        headers={"Content-Length": str(path.stat().st_size)})

    @site.route("/playlist")
    def playlist():
        return ("<html><head><title>Test Mix</title></head><body>"
                '<video src="/clip.mp4"></video><video src="/second.mp4"></video>'
                '<video src="/third.mp4"></video></body></html>')

    @site.route("/dash/<name>/<path:file>")
    def dash(name, file):
        if name not in DASH_CLIPS:
            abort(404)
        if name in DASH_AUDIO_REFUSED and "stream1" in file:
            abort(403)
        return send_from_directory(folder / name, file, conditional=True)

    @site.route("/playlist-dash")
    def playlist_dash():
        return ("<html><head><title>Dash Mix</title></head><body>"
                + "".join(f'<video src="/dash/{n}/manifest.mpd"></video>' for n in DASH_CLIPS)
                + "</body></html>")

    url, stop = _serve(site)
    yield url
    stop()


@pytest.fixture(scope="session")
def app_url():
    if not (ROOT / "static" / "app.bundle.js").exists():
        pytest.fail("static/ isn't built: run `python build_setup.py --frontend-only` first")
    from mellow import server
    url, stop = _serve(server.init_app())
    yield url
    stop()


@pytest.fixture(scope="session")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        exe = os.environ.get("MELLOW_CHROMIUM") or (str(LOCAL_CHROMIUM) if LOCAL_CHROMIUM.exists() else None)
        b = pw.chromium.launch(executable_path=exe)
        yield b
        b.close()


@pytest.fixture
def downloads(isolated_user_files):
    """This test's download folder, set as the app's output_dir."""
    from mellow import config
    folder = isolated_user_files / "Downloads"
    folder.mkdir()
    # A settled install: What's new was already seen (its own test says otherwise)
    from mellow.version import APP_VERSION
    config.update_config(lambda c: c.update(output_dir=str(folder), last_seen_version=APP_VERSION))
    return folder


@pytest.fixture
def page(browser, app_url, downloads):
    """The app in a fresh browser context. Fails the test on any page error
    or a request that leaves this machine."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    problems: list[str] = []
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("request", lambda r: r.url.startswith(("http://127.0.0.1", "data:", "blob:"))
            or problems.append(f"external request: {r.url}"))
    page.goto(app_url)
    page.locator(".nav-item").first.wait_for()
    yield page
    context.close()
    assert not problems, "\n".join(problems)
