from __future__ import annotations

import socket
import sys
from pathlib import Path

from flaskwebgui import FlaskUI

from server import init_app


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def main() -> None:
    flask_app = init_app()
    port = _find_free_port()

    static_dir = Path(__file__).parent / "static"
    if not static_dir.exists():
        print(f"ERROR: static/ directory not found at {static_dir}", file=sys.stderr)
        print("Run build_setup.py first to generate static assets.", file=sys.stderr)
        sys.exit(1)

    ui = FlaskUI(
        app=flask_app,
        server="flask",
        port=port,
        width=1100,
        height=780,
    )
    ui.run()


if __name__ == "__main__":
    main()
