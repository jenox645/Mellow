"""main.py --shell as a desktop shell (the Tauri trial, src-tauri/) runs it.

The real backend runs as its own process with a throwaway home folder: it
prints one ready line whose launch URL signs a window in once, a second
--shell launch attaches to it, and closing its stdin (what the shell does when
its window closes, or what the OS does when the shell dies) ends it.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

import main
from mellow import session
from mellow.datadir import data_dir as real_data_dir  # conftest swaps the module's for each test

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_binary import app_env  # noqa: E402

START_TIMEOUT_SECS = 60
EXIT_TIMEOUT_SECS = 15
ANALYZE_TIMEOUT_SECS = 30


def _shell(env: dict) -> tuple[subprocess.Popen, str]:
    """`python main.py --shell` and its ready line (without the prefix)."""
    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py"), main.SHELL_FLAG], cwd=ROOT, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True)
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.append(proc.stdout.readline()), daemon=True)
    reader.start()
    reader.join(START_TIMEOUT_SECS)
    if not lines or not lines[0].startswith(main.READY_PREFIX):
        proc.kill()
        pytest.fail(f"no ready line: {lines}")
    return proc, lines[0][len(main.READY_PREFIX):].strip()


def test_the_shell_backend_signs_its_window_in_once_and_ends_with_its_shell(tmp_path, media_site):
    home = tmp_path / "home"
    home.mkdir()
    env = app_env(str(home))
    proc, ready = _shell(env)
    try:
        url = ready.split()[0]
        info = session.read_instance(real_data_dir(env) / session.INSTANCE_FILE_NAME)
        assert url.startswith(f"http://127.0.0.1:{info['port']}/launch?t=")
        opener = build_opener(ProxyHandler({}))
        with opener.open(url, timeout=15) as resp:
            assert resp.status == 200
            assert resp.headers.get("Set-Cookie", "").startswith(f"{session.COOKIE}=")
        with pytest.raises(HTTPError) as refused:      # the token works once
            opener.open(url, timeout=15)
        assert refused.value.code == 403

        # Analyzing starts child processes (ffmpeg…): they must not inherit the
        # shell's pipe, which hangs them on Windows while the watcher reads it
        headers = {**session.sign_in(f"http://127.0.0.1:{info['port']}", info["secret"], info["port"]),
                   "Content-Type": "application/json"}
        req = Request(f"http://127.0.0.1:{info['port']}/api/info", method="POST", headers=headers,
                      data=json.dumps({"url": f"{media_site}/clip.mp4"}).encode())
        with opener.open(req, timeout=ANALYZE_TIMEOUT_SECS) as resp:
            assert json.loads(resp.read())["title"]

        # A second launch signs its window in to the running copy and exits
        second, again = _shell(env)
        assert second.wait(timeout=EXIT_TIMEOUT_SECS) == 0
        assert again.endswith(" attached")
        assert again.startswith(f"http://127.0.0.1:{info['port']}/launch?t=")

        # The shell closes stdin: the backend quits and removes its instance file
        proc.stdin.close()
        assert proc.wait(timeout=EXIT_TIMEOUT_SECS) == 0
        assert session.read_instance(real_data_dir(env) / session.INSTANCE_FILE_NAME) is None
    finally:
        if proc.poll() is None:
            proc.kill()
