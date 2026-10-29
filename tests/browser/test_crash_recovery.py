"""A sync stopped halfway, and the app started again.

The real app runs as its own process (main.py --no-window, with a throwaway
home folder) and is killed (SIGKILL: no shutdown code runs, as when the
computer loses power) while the fourth item of a four-item playlist sync is
downloading. Started again, it offers the unfinished sync; resumed, the sync
must finish the missing item and nothing else: no file twice, no history row
twice, an archive that lists each item once and a report that says what
happened.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from mellow import session
from mellow.datadir import data_dir as real_data_dir  # conftest swaps the module's for each test
from mellow.version import APP_VERSION

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(sys.platform == "win32", reason="kills the app's process group (POSIX)"),
]

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_binary import app_env, sign_in  # noqa: E402

START_TIMEOUT_SECS = 60
SYNC_TIMEOUT_SECS = 120
MEDIA = (".mp4", ".mkv", ".webm")


def _start(env: dict, stale_port: int | None = None) -> tuple[subprocess.Popen, str, dict]:
    """The app from source, headless; its address and a signed-in window's headers."""
    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "--no-window"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + START_TIMEOUT_SECS
    while time.monotonic() < deadline:
        assert proc.poll() is None, f"the app exited ({proc.returncode})"
        # The app the test started: the one its instance file names
        info = session.read_instance(real_data_dir(env) / session.INSTANCE_FILE_NAME)
        if info and info["port"] != stale_port:
            base = f"http://127.0.0.1:{info['port']}"
            try:
                headers = sign_in(base, info)
                _call(base, headers, "/api/system")
                return proc, base, headers
            except OSError:
                pass
        time.sleep(0.2)
    _kill(proc)
    pytest.fail("the app didn't start")


def _kill(proc: subprocess.Popen) -> None:
    """As a power cut would: no chance to save anything."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)


def _call(base: str, headers: dict, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = Request(base + path, data=data, method="GET" if body is None else "POST",
                  headers={**headers, "Content-Type": "application/json"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"null")


def _media(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.suffix in MEDIA)


def _wait(what: str, check, timeout: float = SYNC_TIMEOUT_SECS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result := check():
            return result
        time.sleep(0.2)
    pytest.fail(f"timed out waiting for {what}")


def test_a_sync_stopped_halfway_finishes_after_a_restart_without_doing_anything_twice(media_site, tmp_path):
    home = tmp_path / "home"
    folder = home / "Downloads" / "Crash Mix"
    folder.mkdir(parents=True)
    url = f"{media_site}/playlist-crash"
    (home / ".mellow_dlp.json").write_text(json.dumps({
        "output_dir": str(home / "Downloads"),
        "vault_playlists": {str(folder): [url]},
        "last_seen_version": APP_VERSION,
        "update_check_on_launch": False,
        "auto_sync_enabled": False,
        "keep_awake": False,
    }), encoding="utf-8")
    env = app_env(str(home))

    # First run: the three quick clips land, the fourth is crawling in
    proc, base, headers = _start(env)
    try:
        _call(base, headers, "/api/vault/sync", {"path": str(folder)})
        _wait("three finished files and the fourth under way",
              lambda: len(_media(folder)) == 3 and any(p.suffix == ".part" for p in folder.iterdir()))
    finally:
        _kill(proc)
    first_port = int(base.rsplit(":", 1)[1])
    before = _media(folder)
    assert len(before) == 3

    # Second run: the sync is offered again and resumed
    proc, base, headers = _start(env, stale_port=first_port)
    try:
        offered = _call(base, headers, "/api/queue/restorable")["jobs"]
        assert [j["type"] for j in offered] == ["sync"], offered
        assert _call(base, headers, "/api/queue/restore", {})["restored"] == 1
        _wait("the sync to finish", lambda: (s := _call(base, headers, "/api/queue/status"))["jobs"]
              and not s["queued"] and not s["active"])
        status = _call(base, headers, "/api/queue/status")
        history = _call(base, headers, "/api/history?limit=100")
        report = _call(base, headers, "/api/vault/sync-report?path=" + quote(str(folder)))["report"]
    finally:
        _kill(proc)

    assert [j["status"] for j in status["jobs"]] == ["complete"], status["jobs"]
    # Every item once, the three from before untouched
    after = _media(folder)
    assert len(after) == 4 and set(before) <= set(after), after
    assert not [p.name for p in folder.iterdir() if p.suffix in (".part", ".ytdl")]
    # The archive lists each item once: the next sync downloads nothing
    archive = [line for line in (folder / "mellow_archive.txt").read_text().splitlines() if line.strip()]
    assert len(archive) == len(set(archive)) == 4, archive
    # One history row per file
    done = [h for h in history if h["status"] == "success"]
    assert sorted(Path(h["file_path"]).name for h in done) == after, history
    # The report of the resumed sync: one added, three already there
    assert report["status"] == "complete" and len(report["added"]) == 1, report
    assert report["archived"] == 3, report


def test_cancelling_a_sync_keeps_the_history_of_the_files_it_finished(app_url, media_site, downloads):
    """CANCEL halfway through a playlist: the files already saved stay, and so
    must their history rows (RE-TAG, same-title names and the stats use them).
    They were written only when the whole run ended, so a cancel lost them."""
    from conftest import signed_in

    from mellow import analytics, config, jobs
    folder = downloads / "Crash Mix"
    folder.mkdir()
    config.update_config(lambda c: c.update(vault_playlists={str(folder): [f"{media_site}/playlist-crash"]}))
    headers = signed_in()
    job_id = _call(app_url, headers, "/api/vault/sync", {"path": str(folder)})["job_id"]
    _wait("three finished files and the fourth under way",
          lambda: len(_media(folder)) == 3 and any(p.suffix == ".part" for p in folder.iterdir()))
    _call(app_url, headers, f"/api/queue/{job_id}/cancel", {})
    assert jobs.manager.wait_idle(SYNC_TIMEOUT_SECS)
    saved = [h for h in analytics.get_history() if h["status"] == "success"]
    assert sorted(Path(h["file_path"]).name for h in saved) == _media(folder) and len(saved) == 3
