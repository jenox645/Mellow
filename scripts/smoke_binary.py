"""Start a built MellowDLP and check that it serves the app.

    python scripts/smoke_binary.py dist/MellowDLP     (or dist/MellowDLP/MellowDLP.exe)
    python scripts/smoke_binary.py --shell dist/MellowDLP-backend/mellowdlp-backend[.exe]

Runs it with --no-window and a throwaway home folder, waits for its
instance file, signs in with it (as the app signs its own window in), then
checks /api/system (version, yt-dlp importable inside the bundle), the page,
the bundled fonts and React. Exits non-zero on the first
failure. Used by CI after every build and by the release workflow before it
publishes anything.

--shell: the backend the Tauri app carries (build_setup.py --tauri), started
the way its shell starts it (src-tauri/src/backend.rs: `--shell`, pipes,
MELLOW_SHELL=tauri): the ready line, its one-time launch link, the same
checks, then stdin closed as when the window closes: it must exit 0 and
remove its instance file.
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mellow import datadir, session  # noqa: E402
from mellow.version import APP_VERSION  # noqa: E402

# The app log holds non-ASCII; a Windows console would choke on it (cp1252)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

START_TIMEOUT_SECS = 90     # a one-file build unpacks itself first
REQUEST_TIMEOUT_SECS = 15
SHELL_EXIT_TIMEOUT_SECS = 10   # stdin closed → the backend is gone
READY_PREFIX = "MELLOW_READY "   # main.py READY_PREFIX


def app_env(home: str) -> dict:
    """The environment to start the app with: every per-user folder in `home`."""
    return {**os.environ, "HOME": home, "USERPROFILE": home,
            "LOCALAPPDATA": str(Path(home) / "AppData" / "Local"),
            "XDG_DATA_HOME": str(Path(home) / ".local" / "share")}


def running_apps(env: dict) -> list[tuple[str, dict | None]]:
    """(base URL, instance info) of each copy started with `env` that left its address.

    A version from before sign-in wrote only ~/.mellow_dlp.port (info None):
    the update check starts from, or ends on, such a release.
    """
    found = []
    info = session.read_instance(datadir.data_dir(env) / session.INSTANCE_FILE_NAME)
    if info:
        found.append((f"http://127.0.0.1:{info['port']}", info))
    try:
        port = int((Path(env["HOME"]) / ".mellow_dlp.port").read_text().strip())
        found.append((f"http://127.0.0.1:{port}", None))
    except (OSError, ValueError):
        pass
    return found


def sign_in(base: str, info: dict | None) -> dict:
    """The headers a signed-in window sends (none for a version without sign-in)."""
    return session.sign_in(base, info["secret"], info["port"]) if info else {}


def _get(url: str, headers: dict | None = None) -> bytes:
    with urlopen(Request(url, headers=headers or {}), timeout=REQUEST_TIMEOUT_SECS) as resp:
        if resp.status != 200:
            raise AssertionError(f"{url} → HTTP {resp.status}")
        return resp.read()


def _check(base: str, headers: dict) -> None:
    system = json.loads(_get(base + "/api/system", headers))
    print(f"  /api/system: app {system.get('app_version')}, yt-dlp {system.get('ytdlp_version')}")
    assert system.get("app_version") == APP_VERSION, f"app_version {system.get('app_version')} != {APP_VERSION}"
    assert system.get("ytdlp_version") not in (None, "", "unknown"), "yt-dlp isn't importable in the build"
    notes = json.loads(_get(base + "/api/whats-new?all=1", headers)).get("entries") or []
    assert notes and notes[0]["version"] == APP_VERSION, "CHANGELOG.md isn't in the build (What's new)"
    print(f"  What's new: {len(notes)} releases, newest {notes[0]['version']}")

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


def _serve_and_check(proc: subprocess.Popen, env: dict) -> None:
    """Wait for the instance file, sign in with it and check what it serves."""
    deadline = time.monotonic() + START_TIMEOUT_SECS
    while not (found := running_apps(env)):
        if proc.poll() is not None:
            raise AssertionError(f"exited with code {proc.returncode} before it served anything")
        if time.monotonic() > deadline:
            raise AssertionError(f"no instance file after {START_TIMEOUT_SECS}s")
        time.sleep(0.5)
    base, info = found[0]
    print(f"  serving at {base}")
    # The instance file is written just before the server binds
    for attempt in range(20):
        try:
            _check(base, sign_in(base, info))
            break
        except (ConnectionError, OSError) as exc:
            if attempt == 19:
                raise
            print(f"  not up yet ({exc})")
            time.sleep(0.5)


def _ready_line(proc: subprocess.Popen) -> str:
    """The backend's first stdout line, as the shell reads it (main.py _print_ready)."""
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True).start()
    try:
        line = lines.get(timeout=START_TIMEOUT_SECS).decode("utf-8", "replace").strip()
    except queue.Empty:
        raise AssertionError(f"no ready line after {START_TIMEOUT_SECS}s") from None
    if not line.startswith(READY_PREFIX):
        raise AssertionError(f"the first line isn't the ready line: {line!r}")
    return line[len(READY_PREFIX):]


def _check_shell(proc: subprocess.Popen, env: dict) -> None:
    """--shell: the ready line, a launch link that works once, the app, then
    stdin closed (the window closed) ends it."""
    url = _ready_line(proc)
    assert url.startswith("http://127.0.0.1:") and "/launch?t=" in url and " " not in url, url
    print(f"  ready line: {url.split('?')[0]}?t=…")
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECS) as resp:
        assert resp.status == 200 and "Set-Cookie" in resp.headers, "/launch didn't sign the window in"
    try:
        urlopen(url, timeout=REQUEST_TIMEOUT_SECS)
        raise AssertionError("the launch link worked twice")
    except HTTPError as exc:
        assert exc.code == 403, f"a used launch link answered {exc.code}"
    print("  launch link: signs in once, then 403")
    _serve_and_check(proc, env)
    proc.stdin.close()
    try:
        code = proc.wait(timeout=SHELL_EXIT_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        raise AssertionError(f"still running {SHELL_EXIT_TIMEOUT_SECS}s after its stdin closed") from None
    # Unix: started as its own process group's leader (as the shell starts it), the
    # backend ends that group, itself included, with SIGKILL as its last act
    # (main._end_own_group), after removing its instance file
    clean = (0,) if sys.platform == "win32" else (0, -signal.SIGKILL)
    assert code in clean, f"exited with code {code} after its stdin closed"
    assert not running_apps(env), "its instance file is still there"
    print(f"  stdin closed: exited ({code}), instance file removed")


def main(binary: str, shell: bool = False) -> int:
    exe = Path(binary).resolve()
    if not exe.exists():
        print(f"no such file: {exe}")
        return 1
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home:
        env = app_env(home)
        try:
            if shell:
                # As the Tauri shell starts it: pipes, no console, its own process group
                env["MELLOW_SHELL"] = "tauri"
                flags = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                         if sys.platform == "win32" else {"start_new_session": True})
                proc = subprocess.Popen([str(exe), "--shell"], env=env, cwd=str(exe.parent),
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, **flags)
            else:
                # Its own process group: a one-file build (and an AppImage) runs the
                # app as a child that outlives the launcher's terminate()
                proc = subprocess.Popen([str(exe), "--no-window"], env=env, **_NEW_GROUP)
        except OSError as exc:
            print(f"FAILED: couldn't start {exe}: {exc}")
            return 1
        try:
            if shell:
                _check_shell(proc, env)
            else:
                _serve_and_check(proc, env)
        except AssertionError as exc:
            print(f"FAILED: {exc}")
            return 1
        finally:
            if proc.poll() is None:
                _stop(proc)
            log = Path(home) / ".mellow_dlp.log"
            if log.exists():
                print("-- app log --")
                print(log.read_text(encoding="utf-8", errors="replace")[-4000:])
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    shell_mode = "--shell" in args
    args = [a for a in args if a != "--shell"]
    if len(args) != 1:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(args[0], shell=shell_mode))
