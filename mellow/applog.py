"""Logging setup: the console plus a rotating log file in the home folder.

The packaged app has no console, so without the file there is nothing to
look at when a download misbehaves. Modules log through
logging.getLogger(__name__); only main.py calls setup().
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .constants import LOG_BACKUPS, LOG_MAX_BYTES

LOG_PATH = Path.home() / ".mellow_dlp.log"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup(level: int = logging.INFO) -> Path:
    """Send app logs to LOG_PATH (rotated) and, when there is one, the console."""
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        print(f"MellowDLP: cannot write {LOG_PATH}: {exc}", file=sys.stderr)
    if sys.stderr is not None:  # None in the windowed (no console) build
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)
    # One line per HTTP request (the UI polls every few seconds) drowns the rest
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return LOG_PATH
