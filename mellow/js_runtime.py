"""The JavaScript engine yt-dlp solves YouTube's player challenges with.

YouTube hides its stream links behind a puzzle written in JavaScript (the
"n" and signature challenges). yt-dlp solves it by running yt-dlp-ejs'
solver scripts in a JavaScript engine it finds on the computer. Left alone,
yt-dlp only looks for Deno, so a computer with Node (or Bun, or QuickJS) got
no solving at all: fewer formats, or none. Every yt-dlp call MellowDLP makes
enables all four (``ytdlp_opts``, through ``downloader._apply_network_opts``)
and yt-dlp takes the one it finds, in its own order. ``found()`` names that
one for Config and the log.
"""
from __future__ import annotations

import logging
import threading
import time

from .constants import JS_RUNTIME_RECHECK_SECS

log = logging.getLogger(__name__)

# yt-dlp's names, in the order yt-dlp prefers them when several are installed
ENGINES: tuple[str, ...] = ("deno", "node", "quickjs", "bun")

_lock = threading.Lock()
_cache: tuple[float, dict | None] | None = None


def ytdlp_opts() -> dict:
    """yt-dlp's ``js_runtimes`` option: every engine, each looked up on PATH.
    A new dict each time (yt-dlp edits the one it's given)."""
    return {name: {} for name in ENGINES}


def found(refresh: bool = False) -> dict | None:
    """The engine yt-dlp will use: ``{name, version, path, supported}``.

    ``supported`` is False when the only engine found is older than yt-dlp
    accepts (Node before 22, Deno before 2.3…): yt-dlp then has none. None
    when nothing is installed. Looked up again after JS_RUNTIME_RECHECK_SECS
    (each lookup runs the engines' ``--version``; /api/system asks often).
    """
    global _cache
    with _lock:
        if not refresh and _cache and time.monotonic() - _cache[0] < JS_RUNTIME_RECHECK_SECS:
            return _cache[1]
    result = _look()
    with _lock:
        _cache = (time.monotonic(), result)
    return result


def _look() -> dict | None:
    try:
        from yt_dlp.globals import supported_js_runtimes
        classes = supported_js_runtimes.value
    except Exception as exc:          # an older yt-dlp: no engines at all
        log.debug(f"yt-dlp has no JavaScript runtimes ({exc})")
        return None
    too_old = None
    for name in ENGINES:
        cls = classes.get(name)
        try:
            info = cls().info if cls else None
        except Exception as exc:
            log.debug(f"looking for {name} failed: {exc}")
            info = None
        if not info:
            continue
        engine = {"name": info.name, "version": info.version, "path": info.path,
                  "supported": bool(info.supported)}
        if engine["supported"]:
            return engine
        too_old = too_old or engine
    return too_old


def log_found() -> None:
    """Names the engine in the log (main.py, in the background: it runs them)."""
    engine = found()
    (log.info if engine and engine["supported"] else log.warning)(describe(engine))


def describe(engine: dict | None) -> str:
    """One line for the log."""
    if not engine:
        return "no JavaScript runtime found (Deno, Node, QuickJS or Bun): YouTube may offer fewer formats"
    if not engine["supported"]:
        return f"{engine['name']} {engine['version']} is too old for yt-dlp: YouTube may offer fewer formats"
    return f"JavaScript runtime: {engine['name']} {engine['version']} ({engine['path']})"
