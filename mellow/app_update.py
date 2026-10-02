"""Is there a newer MellowDLP? Checked against the GitHub releases.

The app can't update itself (it is a PyInstaller build or a source
checkout); this only says so and opens the release page.
"""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .constants import APP_RELEASES_API, UPDATE_CHECK_TIMEOUT_SECS
from .version import APP_VERSION
from .ytdlp_update import parse_version

log = logging.getLogger(__name__)


def check() -> dict:
    """{"current", "latest", "update_available", "url", "notes"}, or an "error"."""
    base = {"current": APP_VERSION, "latest": None, "update_available": False}
    req = Request(APP_RELEASES_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"MellowDLP/{APP_VERSION}"})
    try:
        with urlopen(req, timeout=UPDATE_CHECK_TIMEOUT_SECS) as resp:
            release = json.loads(resp.read().decode())
    except HTTPError as exc:
        if exc.code == 404:  # nothing published yet
            return {**base, "message": "No releases published yet."}
        return {**base, "error": f"GitHub answered HTTP {exc.code}"}
    except Exception as exc:
        return {**base, "error": str(exc)}
    latest = str(release.get("tag_name") or "").lstrip("vV")
    newer = bool(latest) and parse_version(latest) > parse_version(APP_VERSION)
    log.info(f"app update check: current={APP_VERSION} latest={latest} update={newer}")
    return {
        **base,
        "latest": latest or None,
        "update_available": newer,
        "url": release.get("html_url"),
        "notes": (release.get("body") or "")[:2000],
    }
