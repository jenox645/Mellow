from __future__ import annotations

import atexit
import json
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from flaskwebgui import FlaskUI

from mellow import applog, ytdlp_update

log = logging.getLogger(__name__)

WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 780
INSTANCE_PROBE_TIMEOUT_SECS = 2
BROWSER_OPEN_DELAY_SECS = 1      # let the server start listening first
PAGE_WATCH_INTERVAL_SECS = 2
PAGE_GONE_EXIT_SECS = 30        # a reload or a short network hiccup reconnects well before
FIRST_PAGE_TIMEOUT_SECS = 120

# Written on startup with the live port; lets a second launch find us
PORT_FILE = Path.home() / ".mellow_dlp.port"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _running_instance_url() -> str | None:
    """URL of an already-running MellowDLP, or None.

    The port file may be stale (crash, reboot) — only trust it if the
    server there answers /api/system with our app_version marker.
    """
    try:
        port = int(PORT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    url = f"http://127.0.0.1:{port}"
    try:
        with urlopen(f"{url}/api/system", timeout=INSTANCE_PROBE_TIMEOUT_SECS) as resp:
            payload = json.loads(resp.read().decode())
        if "app_version" in payload:
            return url
    except Exception:
        pass
    return None


def _write_port_file(port: int) -> None:
    try:
        PORT_FILE.write_text(str(port), encoding="utf-8")
        atexit.register(_remove_port_file)
    except OSError:
        pass


def _remove_port_file() -> None:
    try:
        PORT_FILE.unlink(missing_ok=True)
    except OSError:
        pass


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
    existing = _running_instance_url()
    if existing:
        log.info(f"already running at {existing}, opening it")
        webbrowser.open(existing)
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
    port = _find_free_port()
    _write_port_file(port)

    if "--no-window" in sys.argv:
        # Just the server, for your own browser (and the build's smoke test)
        log.info(f"serving without a window at http://127.0.0.1:{port}")
        print(f"MellowDLP: http://127.0.0.1:{port}", flush=True)
        flask_app.run(host="127.0.0.1", port=port, threaded=True)
        return
    _run_window(flask_app, port)


def _run_window(flask_app, port: int) -> None:
    """Serve the app in a Chrome/Edge/Brave/Chromium app window until it closes."""
    ui = FlaskUI(
        app=flask_app,
        server="flask",
        port=port,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
    )
    if not ui.browser_path:
        # Without one (a Firefox-only Linux) flaskwebgui would leave a server
        # with no window: open the default browser instead
        url = f"http://127.0.0.1:{port}"
        log.warning(f"no Chromium-based browser found: opening {url} in the default browser")
        threading.Timer(BROWSER_OPEN_DELAY_SECS, _open_in_browser, (url,)).start()
        threading.Thread(target=_watch_pages, daemon=True).start()
        flask_app.run(host="127.0.0.1", port=port, threaded=True)
        return
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
    _remove_port_file()
    os._exit(0)


if __name__ == "__main__":
    main()
