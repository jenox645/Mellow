from __future__ import annotations

import atexit
import json
import logging
import socket
import sys
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from flaskwebgui import FlaskUI

from mellow import applog
from mellow.server import init_app

log = logging.getLogger(__name__)

WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 780
INSTANCE_PROBE_TIMEOUT_SECS = 2

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

    flask_app = init_app()
    port = _find_free_port()
    _write_port_file(port)

    ui = FlaskUI(
        app=flask_app,
        server="flask",
        port=port,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
    )
    ui.run()


if __name__ == "__main__":
    main()
