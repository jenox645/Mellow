"""Start a built MellowDLP and check that it serves the app.

    python scripts/smoke_binary.py dist/MellowDLP     (or dist/MellowDLP/MellowDLP.exe)

Runs it with --no-window and a throwaway home folder, waits for the port
file, then checks /api/system (version, yt-dlp importable inside the
bundle), the page, the bundled fonts and React. Exits non-zero on the first
failure. Used by CI after every build and by the release workflow before it
publishes anything.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mellow.version import APP_VERSION  # noqa: E402

# The app log holds non-ASCII; a Windows console would choke on it (cp1252)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

START_TIMEOUT_SECS = 90     # a one-file build unpacks itself first
REQUEST_TIMEOUT_SECS = 15


def _get(url: str) -> bytes:
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECS) as resp:
        if resp.status != 200:
            raise AssertionError(f"{url} → HTTP {resp.status}")
        return resp.read()


def _check(base: str) -> None:
    system = json.loads(_get(base + "/api/system"))
    print(f"  /api/system: app {system.get('app_version')}, yt-dlp {system.get('ytdlp_version')}")
    assert system.get("app_version") == APP_VERSION, f"app_version {system.get('app_version')} != {APP_VERSION}"
    assert system.get("ytdlp_version") not in (None, "", "unknown"), "yt-dlp isn't importable in the build"

    page = _get(base + "/").decode("utf-8", "replace")
    for ref in ("fonts/fonts.css", "react.min.js", "app.bundle.js"):
        assert ref in page, f"index.html doesn't load {ref}"
    for path in ("/fonts/fonts.css", "/react.min.js", "/react-dom.min.js", "/app.bundle.js", "/mascots.js"):
        size = len(_get(base + path))
        assert size > 0, f"{path} is empty"
        print(f"  {path}: {size:,} bytes")


_NEW_GROUP = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
              else {"start_new_session": True})


def _stop(proc: subprocess.Popen) -> None:
    """Stop the app and every process it started."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait()


def main(binary: str) -> int:
    exe = Path(binary).resolve()
    if not exe.exists():
        print(f"no such file: {exe}")
        return 1
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home:
        env = {**os.environ, "HOME": home, "USERPROFILE": home}
        port_file = Path(home) / ".mellow_dlp.port"
        # Its own process group: a one-file build (and an AppImage) runs the
        # app as a child that outlives the launcher's terminate()
        proc = subprocess.Popen([str(exe), "--no-window"], env=env, **_NEW_GROUP)
        try:
            deadline = time.monotonic() + START_TIMEOUT_SECS
            while not port_file.exists():
                if proc.poll() is not None:
                    print(f"exited with code {proc.returncode} before it served anything")
                    return 1
                if time.monotonic() > deadline:
                    print(f"no port file after {START_TIMEOUT_SECS}s")
                    return 1
                time.sleep(0.5)
            base = f"http://127.0.0.1:{port_file.read_text().strip()}"
            print(f"  serving at {base}")
            # The port file is written just before the server binds
            for attempt in range(20):
                try:
                    _check(base)
                    break
                except (ConnectionError, OSError) as exc:
                    if attempt == 19:
                        raise
                    print(f"  not up yet ({exc})")
                    time.sleep(0.5)
        except AssertionError as exc:
            print(f"FAILED: {exc}")
            return 1
        finally:
            _stop(proc)
            log = Path(home) / ".mellow_dlp.log"
            if log.exists():
                print("-- app log --")
                print(log.read_text(encoding="utf-8", errors="replace")[-4000:])
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
