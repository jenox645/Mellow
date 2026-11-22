"""The desktop shell's channel: what the tray, the taskbar button and the
window's close button need, notifications, and the tray's commands.

The Tauri shell (src-tauri/) starts the backend with `main.py --shell` and
talks to it over the backend's own stdin and stdout, so the page never needs
Tauri IPC:

- backend → shell: after the ready line, one line per message on stdout,
  `MELLOW_EVENT <json object>` with a "type":
    state   what the shell shows and does: progress for the taskbar button
            and the tray's tooltip, pause, and whether closing the window
            keeps MellowDLP in the tray (state())
    notify  a system notification ("title", "body"), sent when no window
            shows the app (a page shows its own)
    launch  a fresh one-time sign-in link ("url"), for a new window
- shell → backend: one JSON object per line on stdin, {"cmd": ...}. The
  module that owns an action registers its handler (server.py); each runs on
  its own thread, so a slow one never stalls the channel. EOF means the shell
  closed or died, and the backend quits (main.py).

Nothing is sent before attach(): without a shell (FlaskWebGUI's window,
--no-window, the tests) every function here is a no-op.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, TextIO

from . import scheduler
from .config import load_config
from .constants import SHELL_STATE_MIN_INTERVAL_SECS, SHELL_STATE_REFRESH_SECS

log = logging.getLogger(__name__)

EVENT_PREFIX = "MELLOW_EVENT "
# Window titles and file names can be long; the tray's tooltip can't
TITLE_MAX_CHARS = 80

_out: TextIO | None = None
_out_lock = threading.Lock()
_handlers: dict[str, Callable[[dict], None]] = {}


# ── The channel ─────────────────────────────────────────────────────────────

def attach(out: TextIO, open_pages: Callable[[], int] = lambda: 0) -> None:
    """Send the shell's messages to `out` (the pipe it reads) from now on."""
    global _out
    with _out_lock:
        _out = out
    _pump.start(open_pages)


def detach() -> None:
    global _out
    with _out_lock:
        _out = None
    _pump.stop()


def active() -> bool:
    """Whether a desktop shell is listening."""
    return _out is not None


def send(kind: str, **data) -> bool:
    """One message to the shell; False when there is none (or its pipe broke)."""
    global _out
    line = EVENT_PREFIX + json.dumps({"type": kind, **data}, ensure_ascii=True, separators=(",", ":"))
    with _out_lock:
        if _out is None:
            return False
        try:
            # One write: the shell reads whole lines
            _out.write(line + "\n")
            _out.flush()
        except (OSError, ValueError) as exc:
            log.warning(f"the desktop shell's pipe broke: {exc}")
            _out = None
            return False
    return True


def register(cmd: str, handler: Callable[[dict], None]) -> None:
    """Run handler(message) for each {"cmd": cmd, ...} the shell sends."""
    _handlers[cmd] = handler


def dispatch(line: str) -> bool:
    """Act on one line from the shell; False when it isn't a known command."""
    line = line.strip()
    if not line:
        return False
    try:
        message = json.loads(line)
    except ValueError:
        log.warning(f"the desktop shell sent something that isn't JSON: {line[:80]!r}")
        return False
    handler = _handlers.get(message.get("cmd")) if isinstance(message, dict) else None
    if handler is None:
        log.warning(f"the desktop shell sent an unknown command: {line[:80]!r}")
        return False

    def _run() -> None:
        try:
            handler(message)
        except Exception as exc:
            log.warning(f"shell command {message.get('cmd')!r} failed: {exc}")
        finally:
            changed()   # whatever it did probably shows in the tray
    threading.Thread(target=_run, name=f"shell-{message.get('cmd')}", daemon=True).start()
    return True


# ── What the shell shows ────────────────────────────────────────────────────

class _Progress:
    """Each running job's latest progress, from the progress events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def observe(self, event: dict) -> None:
        status, job_id = event.get("status"), event.get("job_id")
        if not job_id:
            return
        with self._lock:
            if status in ("complete", "error", "cancelled"):
                self._jobs.pop(job_id, None)
                return
            job = self._jobs.setdefault(job_id, {"pct": None, "phase": "starting", "title": None})
            if status == "downloading":
                job["phase"] = "downloading"
                if isinstance(event.get("pct"), (int, float)):
                    job["pct"] = float(event["pct"])
                job["title"] = event.get("current_item_title") or event.get("title") or job["title"]
            elif status == "processing":
                job["phase"] = "processing"
            elif status in ("starting", "sync_plan"):
                job["phase"] = "starting"

    def of(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def forget_others(self, keep: set[str]) -> None:
        """Drop jobs that ended without a terminal event reaching us."""
        with self._lock:
            for job_id in list(self._jobs):
                if job_id not in keep:
                    del self._jobs[job_id]


_progress = _Progress()


def _short(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= TITLE_MAX_CHARS else text[:TITLE_MAX_CHARS - 1] + "…"


def daily_sync(cfg: dict) -> dict | None:
    """The daily sync as the tray tells it: {"time", "folders"}, or None when
    auto-sync is off or no linked folder syncs daily."""
    if not cfg.get("auto_sync_enabled"):
        return None
    daily = [path for path, urls in (cfg.get("vault_playlists") or {}).items()
             if urls and scheduler.interval_for(cfg, path) == scheduler.DAILY_SECS]
    others = [path for path, urls in (cfg.get("vault_playlists") or {}).items()
              if urls and scheduler.interval_for(cfg, path) not in (None, scheduler.DAILY_SECS)]
    if not daily and not others:
        return None
    return {"time": scheduler.daily_time(cfg), "folders": len(daily), "other_folders": len(others)}


def state(queue: dict, paused: bool, cfg: dict | None = None) -> dict:
    """What the shell shows, from the queue (jobs.manager.status()), the pause
    flag and the config.

    phase: idle | starting | downloading | processing | paused (of the first
    running job). keep_running: closing the window keeps MellowDLP in the
    tray, because Config's "Run in the background" is on and there is
    something to do: a download running or waiting (for its time too), or a
    sync that runs by itself.
    """
    cfg = cfg if cfg is not None else load_config()
    jobs = queue.get("jobs") or []
    now = time.time()
    running = [j for j in jobs if j.get("status") == "active"]
    waiting = [j for j in jobs if j.get("status") == "queued"]
    scheduled = sorted(j["not_before"] for j in waiting if (j.get("not_before") or 0) > now)
    _progress.forget_others({j["id"] for j in running})
    first = _progress.of(running[0]["id"]) if running else None
    if not running:
        phase = "idle"
    elif paused:
        phase = "paused"
    else:
        phase = (first or {}).get("phase") or "starting"
    sync = daily_sync(cfg)
    has_work = bool(running or waiting or sync)
    return {
        "phase": phase,
        "pct": round(first["pct"], 1) if first and first.get("pct") is not None else None,
        "title": _short((first or {}).get("title") or (running[0].get("label") if running else None)),
        "active": len(running),
        "queued": len(waiting) - len(scheduled),
        "scheduled": len(scheduled),
        "next_start": time.strftime("%H:%M", time.localtime(scheduled[0])) if scheduled else None,
        "daily_sync": sync,
        "linked_folders": sum(1 for urls in (cfg.get("vault_playlists") or {}).values() if urls),
        "run_in_background": bool(cfg.get("run_in_background", True)),
        "start_with_system": bool(cfg.get("start_with_system", False)),
        "tray_notice_seen": bool(cfg.get("tray_notice_seen", False)),
        "keep_running": bool(cfg.get("run_in_background", True)) and has_work,
    }


class _Pump:
    """Sends state() whenever something changed, at most every
    SHELL_STATE_MIN_INTERVAL_SECS, and every SHELL_STATE_REFRESH_SECS anyway
    (a scheduled download's time comes, config edited elsewhere)."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._dirty = False
        self._thread: threading.Thread | None = None
        self._running = False
        self._last: dict | None = None
        self.open_pages: Callable[[], int] = lambda: 0

    def start(self, open_pages: Callable[[], int]) -> None:
        self.open_pages = open_pages
        with self._cv:
            self._dirty, self._last = True, None
            if self._thread is None or not self._thread.is_alive():
                self._running = True
                self._thread = threading.Thread(target=self._run, name="shell-state", daemon=True)
                self._thread.start()
            self._cv.notify()

    def stop(self) -> None:
        with self._cv:
            self._running = False
            self._cv.notify()

    def changed(self) -> None:
        with self._cv:
            self._dirty = True
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._dirty or not self._running, SHELL_STATE_REFRESH_SECS)
                if not self._running:
                    return
                self._dirty = False
            try:
                self.publish()
            except Exception as exc:
                log.warning(f"tray state not sent: {exc}")
            time.sleep(SHELL_STATE_MIN_INTERVAL_SECS)

    def publish(self, force: bool = False) -> None:
        from . import downloader, jobs
        current = state(jobs.manager.status(), downloader.is_paused())
        if force or current != self._last:
            if send("state", **current):
                self._last = current


_pump = _Pump()


def changed() -> None:
    """Something the shell shows may have changed: it gets a new state() soon."""
    if active():
        _pump.changed()


def observe(event: dict) -> None:
    """Every progress event the app pushes (server._push_progress)."""
    if not active():
        return
    _progress.observe(event)
    _pump.changed()
    if _pump.open_pages() == 0:
        _notify_for(event)


# ── Notifications ───────────────────────────────────────────────────────────

def notify(title: str, body: str = "") -> bool:
    """A system notification through the shell (no-op without one)."""
    return send("notify", title=_short(title) or "MellowDLP", body=str(body or "")[:300])


def background_notifications(cfg: dict | None = None) -> bool:
    cfg = cfg if cfg is not None else load_config()
    return bool(cfg.get("background_notifications", True))


def sync_folder_name(label: str | None) -> str:
    """The folder a sync job's label names ("Sync — Lo-fi (2 playlist(s))" → "Lo-fi")."""
    name = str(label or "")
    if name.startswith("Sync — "):
        name = name[len("Sync — "):]
    if name.endswith(")") and " (" in name:
        name = name[:name.rindex(" (")]
    return name or "a vault folder"


def _notify_for(event: dict) -> None:
    """What deserves a notification while no window shows the app. A page,
    when there is one, shows its own toasts and notifications."""
    status = event.get("status")
    if status not in ("complete", "error") or not background_notifications():
        return
    if status == "complete" and event.get("job_type") == "sync":
        new = (event.get("sync_summary") or {}).get("new") or 0
        if new:
            what = "1 new item" if new == 1 else f"{new} new items"
            notify(f"{what} in {sync_folder_name(event.get('job_label'))}",
                   "Synced in the background." if event.get("auto") else "Sync finished.")
    elif status == "error":
        notify("Download failed", event.get("title") if event.get("hint") is None
               else f"{event.get('title') or ''} — {event.get('hint')}".strip(" —"))


def queue_finished(done: list[dict], open_pages: int) -> None:
    """The queue ran dry (server._queue_finished): with no window, say what the
    downloads saved. A sync already said what it found."""
    if not active() or open_pages or not background_notifications():
        return
    saved = [j for j in done if j.get("type") != "sync"]
    if saved:
        notify("Downloads finished", "1 download saved." if len(saved) == 1 else f"{len(saved)} downloads saved.")
