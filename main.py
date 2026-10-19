from __future__ import annotations

import atexit
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from flaskwebgui import FlaskUI

from mellow import applog, session, ytdlp_update
from mellow.constants import LAUNCH_TOKEN_TTL_NO_WINDOW_SECS

log = logging.getLogger(__name__)

WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 780
INSTANCE_PROBE_TIMEOUT_SECS = 2
BROWSER_OPEN_DELAY_SECS = 1      # let the server start listening first
PAGE_WATCH_INTERVAL_SECS = 2
PAGE_GONE_EXIT_SECS = 30        # a reload or a short network hiccup reconnects well before
FIRST_PAGE_TIMEOUT_SECS = 120

# Where versions before sign-in wrote their port; removed at start
LEGACY_PORT_FILE = Path.home() / ".mellow_dlp.port"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


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
    existing = _running_instance()
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
    port = _find_free_port()
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
