from __future__ import annotations

import atexit
import json
import logging
import os
import secrets
import signal
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from flaskwebgui import FlaskUI

from mellow import applog, session, shell, ytdlp_update
from mellow.config import load_config
from mellow.constants import API_PORT_MIN, LAUNCH_TOKEN_TTL_NO_WINDOW_SECS

log = logging.getLogger(__name__)

WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 780
INSTANCE_PROBE_TIMEOUT_SECS = 2
BROWSER_OPEN_DELAY_SECS = 1      # let the server start listening first
PAGE_WATCH_INTERVAL_SECS = 2
PAGE_GONE_EXIT_SECS = 30        # a reload or a short network hiccup reconnects well before
FIRST_PAGE_TIMEOUT_SECS = 120
# --shell: a desktop shell (src-tauri/) owns the window and reads READY_PREFIX + launch URL
SHELL_FLAG = "--shell"
READY_PREFIX = "MELLOW_READY "
# With --shell: the shell started at login, with no window (its tray only)
BACKGROUND_FLAG = "--background"
STD_INPUT_HANDLE = -10          # Windows GetStdHandle/SetStdHandle
STD_OUTPUT_HANDLE = -11

# Where versions before sign-in wrote their port; removed at start
LEGACY_PORT_FILE = Path.home() / ".mellow_dlp.port"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _choose_port() -> int:
    """Config's fixed port (api_port, for programs using the API) when it is
    free, else any free one."""
    try:
        wanted = int(load_config().get("api_port") or 0)
    except (TypeError, ValueError):
        wanted = 0
    if API_PORT_MIN <= wanted <= 65535:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", wanted))
            return wanted
        except OSError as exc:
            log.warning(f"fixed port {wanted} is taken ({exc}): using a free one this time")
    return _find_free_port()


def _running_instance() -> dict | None:
    """The copy this account already runs ({port, secret, url}), or None.

    The instance file may be stale (crash, reboot), and after a crash another
    program may have taken its port: only a server that proves it knows the
    secret (session.instance_proof) is ours. Asked directly, never through a
    proxy.
    """
    info = session.read_instance()
    if info is None:
        return None
    url = f"http://127.0.0.1:{info['port']}"
    nonce = secrets.token_urlsafe(24)
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(f"{url}/api/instance/hello?nonce={nonce}",
                         timeout=INSTANCE_PROBE_TIMEOUT_SECS) as resp:
            proof = str(json.loads(resp.read().decode()).get("proof", ""))
    except Exception:
        return None
    if not session.same(proof, session.instance_proof(nonce, info["secret"], info["port"])):
        log.warning(f"port {info['port']} answers but isn't this MellowDLP: starting a new one")
        return None
    return {**info, "url": url}


def _launch_page_uri(url: str, secret: bytes | None = None, port: int | None = None) -> str:
    """file:// URI of an owner-only page that signs a window in to `url` (session.py)."""
    return session.launch_page(url, session.launch_token(secret, port)).as_uri()


def _stop_instance() -> None:
    session.stop_instance()


def main() -> None:
    applog.setup()
    # Anything that escapes (like a database that won't open) lands in the
    # log file too, not only in the crash dialog
    previous_hook = sys.excepthook

    def _log_crash(*exc) -> None:
        log.critical("unhandled exception", exc_info=exc)
        previous_hook(*exc)
    sys.excepthook = _log_crash
    # Single-instance guard: a second launch opens the existing UI instead of
    # spawning a duplicate server + window.
    shell = SHELL_FLAG in sys.argv
    existing = _running_instance()
    if existing and shell:
        # The shell's window signs in to the running copy instead
        log.info(f"already running at {existing['url']}: the shell attaches to it")
        _print_ready(existing["url"], session.launch_token(existing["secret"], existing["port"]),
                     attached=True)
        sys.exit(0)
    if existing:
        log.info(f"already running at {existing['url']}, opening a window on it")
        _open_in_browser(_launch_page_uri(existing["url"], existing["secret"], existing["port"]))
        sys.exit(0)

    static_dir = Path(__file__).parent / "static"
    if not static_dir.exists():
        # Logged, not printed: the packaged app has no console
        log.critical(f"static/ directory not found at {static_dir}; "
                     "run build_setup.py first to generate static assets")
        sys.exit(1)

    # Before anything imports yt_dlp: a newer downloaded one replaces the bundled one
    ytdlp_update.activate_overlay()
    from mellow.server import init_app
    flask_app = init_app()
    from mellow import js_runtime
    threading.Thread(target=js_runtime.log_found, daemon=True).start()
    port = _choose_port()
    LEGACY_PORT_FILE.unlink(missing_ok=True)
    session.start_instance(port)
    atexit.register(_stop_instance)

    if "--no-window" in sys.argv:
        # Just the server, for your own browser (and the build's smoke test).
        # The sign-in link goes to this terminal only, never to the log file
        log.info(f"serving without a window at http://127.0.0.1:{port}")
        token = session.launch_token(ttl=LAUNCH_TOKEN_TTL_NO_WINDOW_SECS)
        print(f"MellowDLP: http://127.0.0.1:{port}\n"
              f"Open this link to sign in (once, within {LAUNCH_TOKEN_TTL_NO_WINDOW_SECS // 60} min): "
              f"http://127.0.0.1:{port}/launch?t={token}", flush=True)
        flask_app.run(host="127.0.0.1", port=port, threaded=True)
        return
    if shell:
        _run_shell(flask_app, port, background=BACKGROUND_FLAG in sys.argv)
        return
    _run_window(flask_app, port)


def _print_ready(url: str, token: str, attached: bool = False, out=None) -> None:
    """The one stdout line a desktop shell waits for (SHELL_FLAG): where its
    window signs in. The token is single-use and short-lived
    (LAUNCH_TOKEN_TTL_SECS), and goes through the shell's pipe, never a
    command line."""
    print(f"{READY_PREFIX}{url}/launch?t={token}{' attached' if attached else ''}",
          file=out or sys.stdout, flush=True)


def _run_shell(flask_app, port: int, stdin=None, background: bool = False) -> None:
    """--shell: serve for a desktop shell that started this process (src-tauri/)
    and owns the window. Prints the ready line once the server listens, then
    talks to the shell over the same pipes (mellow/shell.py); exits when the
    shell closes stdin (it quit or died).

    background (BACKGROUND_FLAG): the shell started at login with no window,
    so nobody sees the "resume pending downloads?" prompt: what was
    unfinished (a download for the night, a sync the shutdown cut short) is
    queued again at once."""
    from werkzeug.serving import make_server

    from mellow import jobs
    from mellow import server as app_server
    server = make_server("127.0.0.1", port, flask_app, threaded=True)
    channel = _detach_stdout() or sys.stdout
    watched = stdin if stdin is not None else _detach_stdin()
    base = f"http://127.0.0.1:{port}"
    # A new window (from the tray, long after the first link expired) signs in with a fresh link
    shell.register("launch", lambda _message: shell.send("launch", url=f"{base}/launch?t={session.launch_token()}"))
    threading.Thread(target=_exit_with_parent, args=(watched,), daemon=True).start()
    log.info(f"serving for a desktop shell at {base}" + (" (started in the background)" if background else ""))
    _print_ready(base, session.launch_token(), out=channel)
    shell.attach(channel, open_pages=app_server.open_pages)
    if background and jobs.manager.restorable:
        resumed = jobs.manager.restore_pending()
        log.info(f"started in the background: {len(resumed)} unfinished download(s) queued again")
        shell.notify("Downloads resumed", f"{len(resumed)} unfinished download(s) queued again.")
    server.serve_forever()


def _detach_stdout():
    """The shell's pipe as the channel's own file, with stdout itself pointed elsewhere.

    The shell reads its messages (the ready line, then shell.py's) from this
    pipe: a print or a library writing to stdout must not land in the middle
    of one. stdout goes to stderr when there is one, else nowhere. None when
    stdout isn't a real file (pythonw, tests)."""
    try:
        fd = os.dup(sys.stdout.fileno())
    except (AttributeError, OSError, ValueError):
        return None
    try:
        target = os.dup(2)
    except OSError:                 # no stderr: the windowed build under the shell
        target = os.open(os.devnull, os.O_WRONLY)
    os.dup2(target, 1)
    os.close(target)
    if os.name == "nt":
        import ctypes
        import msvcrt
        ctypes.windll.kernel32.SetStdHandle(STD_OUTPUT_HANDLE, msvcrt.get_osfhandle(1))
    sys.stdout = sys.stderr if sys.stderr is not None else open(os.devnull, "w")
    return os.fdopen(fd, "w", encoding="utf-8", errors="replace")


def _detach_stdin():
    """The shell's pipe as a file of its own, with stdin itself pointed at the null device.

    The watcher blocks reading that pipe. On Windows a child process that
    inherits it as stdin (ffmpeg, deno… every Popen without stdin=) hangs at
    start until that pending read ends: analyzing a link would wait until
    the window closed. Children get the null device instead."""
    try:
        fd = os.dup(sys.stdin.fileno())
    except (AttributeError, OSError, ValueError):     # no stdin (pythonw), or not a real one
        return None
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    if os.name == "nt":
        import ctypes
        import msvcrt
        ctypes.windll.kernel32.SetStdHandle(STD_INPUT_HANDLE, msvcrt.get_osfhandle(0))
    return os.fdopen(fd, "r", encoding="ascii", errors="replace")


def _exit_with_parent(stdin) -> None:
    """Act on the shell's commands (shell.dispatch) until it closes our stdin
    (EOF), then quit like the window does."""
    if stdin is None:   # no stdin at all (pythonw): nothing to watch
        return
    try:
        while line := stdin.readline():
            shell.dispatch(line)
    except (OSError, ValueError):
        pass
    log.info("the desktop shell closed: quitting")
    _stop_instance()
    _end_own_group()
    os._exit(0)


def _end_own_group() -> None:
    """Unix: what this backend started (ffmpeg, deno…) ends with it.

    The desktop shell starts the backend as the leader of its own process
    group and kills that group when its window closes. A shell that died
    (SIGKILL, a crash) can't, and the children would outlive the backend, so
    the backend ends its group itself as its last act (Windows: the shell's
    job object does it). Never when it shares its parent's group (started from
    a terminal or a test): that would end the parent too."""
    if not hasattr(os, "killpg") or os.getpgrp() != os.getpid():
        return
    logging.shutdown()
    os.killpg(os.getpid(), signal.SIGKILL)


def _run_window(flask_app, port: int) -> None:
    """Serve the app in a Chrome/Edge/Brave/Chromium app window until it closes."""
    ui = FlaskUI(
        app=flask_app,
        server="flask",
        port=port,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
    )
    url = f"http://127.0.0.1:{port}"
    # The window opens the launch page, not the URL: the sign-in token must
    # not be on the browser's command line, which other accounts can read
    page = _launch_page_uri(url)
    if not ui.browser_path:
        # Without one (a Firefox-only Linux) flaskwebgui would leave a server
        # with no window: open the default browser instead
        log.warning(f"no Chromium-based browser found: opening {url} in the default browser")
        threading.Timer(BROWSER_OPEN_DELAY_SECS, _open_in_browser, (page,)).start()
        threading.Thread(target=_watch_pages, daemon=True).start()
        flask_app.run(host="127.0.0.1", port=port, threaded=True)
        return
    ui.browser_command = [f"--app={page}" if arg.startswith("--app=") else arg
                          for arg in ui.browser_command]
    ui.run()


def _open_in_browser(url: str) -> None:
    if not webbrowser.open(url):
        log.error(f"couldn't open a browser: open {url} yourself")
        print(f"MellowDLP: open {url} in your browser", flush=True)


def _watch_pages(sleep=time.sleep, clock=time.monotonic) -> None:
    """In a browser tab there is no window whose closing ends the app: quit
    once no page has been open for PAGE_GONE_EXIT_SECS and nothing downloads,
    or when no page ever connected within FIRST_PAGE_TIMEOUT_SECS."""
    from mellow import jobs, server
    started = clock()
    seen = False
    gone_since = None
    while True:
        sleep(PAGE_WATCH_INTERVAL_SECS)
        now = clock()
        if server.open_pages():
            seen, gone_since = True, None
            continue
        if jobs.manager.has_active():
            continue
        if not seen:
            if now - started < FIRST_PAGE_TIMEOUT_SECS:
                continue
            log.info("no page ever connected: quitting")
            break
        gone_since = gone_since or now
        if now - gone_since >= PAGE_GONE_EXIT_SECS:
            log.info("the MellowDLP tab was closed: quitting")
            break
    _stop_instance()
    os._exit(0)


if __name__ == "__main__":
    main()
