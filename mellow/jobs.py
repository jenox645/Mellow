"""Download job queue — worker pool, per-job cancel, reordering, persistence.

The manager owns a small pool of worker threads (MAX_DOWNLOAD_WORKERS); how
many may run downloads at once is the `download_workers` config value, read
live so changing it applies to already-queued work. Every SSE event emitted
through a job is tagged with `job_id`/`job_type`/`job_label` so the frontend
can attribute progress when more than one download is active.

Unfinished jobs (running or queued) are persisted to QUEUE_STATE_PATH so a
restart can offer to resume them.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import analytics, downloader, errors
from .config import download_root, load_config, update_config
from .constants import (
    DEFAULT_DOWNLOAD_WORKERS,
    DEFAULT_SCHEDULE_START,
    JOB_HISTORY_KEEP,
    MAX_DOWNLOAD_WORKERS,
    SYNC_REPORT_ITEMS_KEEP,
    WORKER_POLL_SECS,
)

log = logging.getLogger(__name__)

QUEUE_STATE_PATH = Path.home() / ".mellow_dlp_queue.json"

_PERSIST_KEYS = ("id", "type", "label", "url", "multi_urls",
                 "output_dir", "opts", "library_id", "sync_path", "not_before")
# Internal fields stripped from /api/queue/status responses
PUBLIC_SKIP_KEYS = ("opts", "multi_urls", "cancel_event", "_t0")

TERMINAL_STATUSES = ("complete", "failed", "cancelled")
# SSE events that end a job; the UI expects exactly one per job
TERMINAL_EVENTS = ("complete", "error", "cancelled")


def next_time_of_day(hhmm: str, now: float | None = None) -> float:
    """Epoch seconds of the next local HH:MM (later today, else tomorrow).

    An unreadable value falls back to the default start time.
    """
    try:
        hour, minute = (int(x) for x in str(hhmm).split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError(hhmm)
    except ValueError:
        hour, minute = (int(x) for x in DEFAULT_SCHEDULE_START.split(":"))
    now_dt = datetime.fromtimestamp(now if now is not None else time.time())
    target = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_dt:
        target += timedelta(days=1)
    return target.timestamp()


def configured_workers() -> int:
    """Live-read the concurrency limit from config, clamped to the pool size."""
    try:
        n = int(load_config().get("download_workers", DEFAULT_DOWNLOAD_WORKERS))
    except (TypeError, ValueError):
        n = DEFAULT_DOWNLOAD_WORKERS
    return max(1, min(MAX_DOWNLOAD_WORKERS, n))


class JobManager:
    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._pending: list[dict] = []   # waiting, in run order (reorderable)
        self._jobs: list[dict] = []      # everything: pending + active + finished
        self._active_count = 0
        self._push: Callable[[dict], None] = lambda event: None
        self._on_idle: Callable[[list[dict]], None] = lambda done: None
        # Jobs that saved something since the queue was last idle
        self._done_since_idle: list[dict] = []
        self._started = False
        self.restorable: list[dict] = []
        self._load_restorable()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, push_fn: Callable[[dict], None],
              on_idle: Callable[[list[dict]], None] | None = None) -> None:
        """Attach the SSE broadcast function and spawn the worker pool.

        on_idle(done) runs (on its own thread) each time the queue runs dry,
        with the jobs that downloaded something since it last did.
        """
        self._push = push_fn
        if on_idle is not None:
            self._on_idle = on_idle
        if self._started:
            return
        self._started = True
        for i in range(MAX_DOWNLOAD_WORKERS):
            threading.Thread(target=self._worker, name=f"dl-worker-{i}", daemon=True).start()

    # ── Enqueue / cancel / reorder ─────────────────────────────────────────────

    def enqueue(self, url: str, output_dir: str, opts: dict,
                library_id: str | None = None,
                job_type: str = "feed",
                label: str = "",
                multi_urls: list | None = None,
                sync_path: str | None = None,
                not_before: float | None = None) -> dict:
        """Queue a job. not_before (epoch seconds) holds it until that time."""
        job: dict = {
            "id": str(uuid.uuid4()),
            "type": job_type,
            "label": label or url,
            "url": url,
            "multi_urls": multi_urls,
            "output_dir": output_dir,
            "opts": opts,
            "library_id": library_id,
            "sync_path": sync_path,
            "not_before": not_before,
            "status": "queued",
            "cancel_event": threading.Event(),
            "counts": {"new": 0, "errors": 0},
        }
        with self._cv:
            self._jobs.append(job)
            self._pending.append(job)
            self._cv.notify_all()
        self._persist()
        return job

    def cancel(self, job_id: str) -> dict | None:
        """Cancel a queued or active job. Returns the job, or None if unknown."""
        with self._cv:
            job = next((j for j in self._jobs if j["id"] == job_id), None)
            if job is None:
                return None
            job["cancel_event"].set()
            if job["status"] == "queued":
                job["status"] = "cancelled"
                if job in self._pending:
                    self._pending.remove(job)
        self._persist()
        return job

    def retry(self, job_id: str, url: str | None = None) -> dict | None:
        """Run job `job_id` again, or just `url` from it, with its options and folder.

        A plain re-download used the Feed defaults, so an item of an MP3
        playlist came back as video. One item is a plain download (no sync
        time or sync log); the whole job is re-run as what it was, a sync
        included. None when the job is no longer known.
        """
        with self._cv:
            job = next((j for j in self._jobs if j["id"] == job_id), None)
        if job is None:
            return None
        if url:
            return self.enqueue(url, job["output_dir"], dict(job["opts"]), job.get("library_id"),
                                job_type="feed", label=f"Retry — {url}")
        return self.enqueue(job["url"], job["output_dir"], dict(job["opts"]), job.get("library_id"),
                            job_type=job["type"], label=job["label"],
                            multi_urls=job.get("multi_urls"), sync_path=job.get("sync_path"))

    def start_now(self, job_id: str) -> bool:
        """Drop a queued job's scheduled start time. False if it isn't queued."""
        with self._cv:
            job = next((j for j in self._pending if j["id"] == job_id), None)
            if job is None:
                return False
            job["not_before"] = None
            self._cv.notify_all()
        self._persist()
        return True

    def _next_runnable(self) -> int | None:
        """Index in the pending order of the first job due to run (lock held)."""
        now = time.time()
        return next((i for i, j in enumerate(self._pending)
                     if not j.get("not_before") or j["not_before"] <= now), None)

    def _seconds_to_next_due(self) -> float:
        """How long a worker may sleep (lock held): until the earliest scheduled
        job is due, at most WORKER_POLL_SECS (config changes, missed wakeups)."""
        now = time.time()
        due = [j["not_before"] - now for j in self._pending if j.get("not_before")]
        return max(0.05, min([WORKER_POLL_SECS, *due]))

    def has_sync_for(self, sync_path: str) -> bool:
        """True when a sync for this folder is already queued or running."""
        with self._cv:
            return any(
                j.get("sync_path") == sync_path and j["status"] in ("queued", "active")
                for j in self._jobs
            )

    def has_active(self) -> bool:
        with self._cv:
            return self._active_count > 0

    def cancel_active(self) -> list[str]:
        """Cancel every running job (legacy /api/cancel semantics)."""
        with self._cv:
            active = [j for j in self._jobs if j["status"] == "active"]
            for j in active:
                j["cancel_event"].set()
        return [j["id"] for j in active]

    def reorder(self, job_id: str, new_index: int) -> bool:
        """Move a queued job to a new position in the pending order."""
        with self._cv:
            job = next((j for j in self._pending if j["id"] == job_id), None)
            if job is None:
                return False
            self._pending.remove(job)
            self._pending.insert(max(0, min(new_index, len(self._pending))), job)
        self._persist()
        return True

    # ── Status ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._cv:
            pending_order = {j["id"]: i for i, j in enumerate(self._pending)}
            jobs = []
            for j in self._jobs:
                pub = {k: v for k, v in j.items() if k not in PUBLIC_SKIP_KEYS}
                if j["id"] in pending_order:
                    pub["queue_position"] = pending_order[j["id"]]
                jobs.append(pub)
        return {
            "jobs": jobs,
            "queued": sum(1 for j in jobs if j["status"] == "queued"),
            "active": sum(1 for j in jobs if j["status"] == "active"),
            "workers": configured_workers(),
        }

    # ── Restart persistence ────────────────────────────────────────────────────

    def _persist(self) -> None:
        """Save every unfinished job: running ones first, then the queue.

        A download still running when the app closes is the one most worth
        offering again (yt-dlp resumes its .part file); saving only the
        queued jobs lost it.
        """
        try:
            with self._cv:
                unfinished = [j for j in self._jobs if j["status"] == "active"] + self._pending
                pending = [{k: j.get(k) for k in _PERSIST_KEYS} for j in unfinished]
            if pending:
                QUEUE_STATE_PATH.write_text(json.dumps(pending), encoding="utf-8")
            elif QUEUE_STATE_PATH.exists():
                QUEUE_STATE_PATH.unlink()
        except OSError as exc:
            log.warning(f"queue persist failed: {exc}")

    def _load_restorable(self) -> None:
        try:
            if QUEUE_STATE_PATH.exists():
                data = json.loads(QUEUE_STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.restorable = [j for j in data if isinstance(j, dict) and j.get("url")]
        except Exception as exc:
            log.warning(f"could not read persisted queue: {exc}")

    def restore_pending(self) -> list[str]:
        """Re-enqueue jobs that were unfinished when the app last exited."""
        restored = []
        for j in self.restorable:
            job = self.enqueue(
                j["url"], j.get("output_dir") or download_root(load_config()),
                j.get("opts") or {}, j.get("library_id"),
                job_type=j.get("type", "feed"), label=j.get("label", ""),
                multi_urls=j.get("multi_urls"), sync_path=j.get("sync_path"),
                not_before=j.get("not_before"))  # a scheduled job keeps its time
            restored.append(job["id"])
        self.restorable = []
        return restored

    def discard_restorable(self) -> None:
        self.restorable = []
        try:
            if QUEUE_STATE_PATH.exists():
                QUEUE_STATE_PATH.unlink()
        except OSError:
            pass

    # ── Worker pool ────────────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            with self._cv:
                # Scheduled jobs wait for their time: wake when the next one is due
                while self._active_count >= configured_workers() or self._next_runnable() is None:
                    self._cv.wait(timeout=self._seconds_to_next_due())
                job = self._pending.pop(self._next_runnable())
                if job["cancel_event"].is_set() or job["status"] == "cancelled":
                    job["status"] = "cancelled"
                    self._cv.notify_all()
                    continue
                job["status"] = "active"
                job["_t0"] = time.monotonic()
                if self._active_count == 0:
                    # Pause is one flag shared by every running download; a
                    # pause left over from an idle queue must not freeze this job
                    downloader.resume()
                self._active_count += 1
            self._persist()
            try:
                try:
                    status = self.run_job(job)
                except Exception as exc:
                    status = "failed"
                    job["error"] = str(exc)
                    # The UI is waiting on a terminal event for this job
                    self._make_cb(job)(
                        {"status": "error", "message": str(exc), "url": job.get("url")})
                with self._cv:
                    job["status"] = status
                    if status == "complete" and job["counts"]["new"]:
                        self._done_since_idle.append(job)
                self._on_finished(job, status)
            except Exception as exc:
                log.warning(f"post-job bookkeeping failed: {exc}")
            finally:
                with self._cv:
                    self._active_count -= 1
                    if self._active_count == 0:
                        downloader.resume()
                    self._trim_finished()
                    # Saved before waking waiters, so an idle queue is also
                    # an up-to-date file (the lock is re-entrant)
                    self._persist()
                    done: list[dict] = []
                    if self._active_count == 0 and self._next_runnable() is None:
                        done, self._done_since_idle = self._done_since_idle, []
                    self._cv.notify_all()
                if done:
                    threading.Thread(target=self._report_idle, args=(done,), daemon=True).start()

    def _report_idle(self, done: list[dict]) -> None:
        try:
            self._on_idle(done)
        except Exception as exc:
            log.warning(f"queue-finished action failed: {exc}")

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until nothing is running or due to run (scheduled jobs don't
        count). False on timeout."""
        with self._cv:
            return self._cv.wait_for(
                lambda: self._next_runnable() is None and self._active_count == 0, timeout)

    def _trim_finished(self) -> None:
        done = [j for j in self._jobs if j["status"] in TERMINAL_STATUSES]
        if len(done) > JOB_HISTORY_KEEP:
            for old in done[:-JOB_HISTORY_KEEP]:
                if old in self._jobs:
                    self._jobs.remove(old)

    # ── Job execution ──────────────────────────────────────────────────────────

    def run_job(self, job: dict) -> str:
        """Run all URLs of a job and emit its one terminal event.

        Returns the aggregate status. Every downloader run ends in its own
        terminal event; with several URLs (a folder linked to more than one
        playlist) passing those through told the UI "failed" mid-job, or
        showed an error for a job that then counted as complete. They are held
        back here and summed up into exactly one.
        """
        urls = job.get("multi_urls") or [job["url"]]
        cancel_event = job.setdefault("cancel_event", threading.Event())
        job.setdefault("counts", {"new": 0, "errors": 0})
        # The metadata toggle is read at run time so config changes apply to
        # already-queued jobs too.
        job["opts"]["write_metadata"] = load_config().get("write_metadata", True)
        push = self._make_cb(job)
        # (url, result, terminal event, whether the run already reported item_failed)
        outcomes: list[tuple[str, str, dict, bool]] = []
        for url in urls:
            if cancel_event.is_set():
                break
            terminal: dict = {}
            reported: list[bool] = []

            def _cb(event: dict, terminal: dict = terminal, reported: list = reported) -> None:
                if event.get("status") in TERMINAL_EVENTS:
                    terminal.update(event)
                    return
                if event.get("status") == "item_failed":
                    reported.append(True)
                push(event)

            result = downloader.download_video(
                url, job["output_dir"], job["opts"], _cb,
                job.get("library_id"), cancel_event=cancel_event,
                pause_event=downloader._pause_event)
            outcomes.append((url, result, terminal, bool(reported)))
        return self._emit_terminal(job, outcomes, push)

    def _emit_terminal(self, job: dict, outcomes: list[tuple[str, str, dict, bool]],
                       push: Callable[[dict], None]) -> str:
        if job["cancel_event"].is_set() or any(r == "cancelled" for _, r, _, _ in outcomes):
            push({"status": "cancelled"})
            return "cancelled"
        failed = [(url, t, reported) for url, r, t, reported in outcomes if r == "error"]
        if outcomes and len(failed) == len(outcomes):
            url, terminal, _ = failed[-1]
            job["error"] = terminal.get("message") or "Download failed"
            push(terminal or {"status": "error", "message": job["error"], "url": url})
            return "failed"
        done = next((t for _, r, t, _ in reversed(outcomes) if r != "error" and t), None)
        complete = dict(done) if done else {"status": "complete", "title": job.get("label") or job["url"]}
        if failed:
            for url, terminal, reported in failed:
                if reported:
                    continue  # its items were already listed as failed
                push({"status": "item_failed", "reason": "error", "url": url,
                      "code": terminal.get("code"),
                      "message": terminal.get("message") or f"Could not download {url}"})
            note = f"{len(failed)} of {len(outcomes)} links could not be downloaded."
            complete["warning"] = " ".join(w for w in (complete.get("warning"), note) if w)
        push(complete)
        return "complete"

    def _make_cb(self, job: dict) -> Callable[[dict], None]:
        report = job.setdefault("report", _empty_report())

        def _cb(event: dict) -> None:
            status = event.get("status")
            if status == "item_skipped":
                # For the sync report only; one per archived item is no UI news
                if event.get("reason") == "filtered":
                    _keep(report["filtered"], event.get("title") or "?")
                else:
                    report["archived"] += 1
                return
            if status == "item_done":
                job["counts"]["new"] += 1
                _keep(report["added"], event.get("title") or "?")
            elif status == "item_failed":
                job["counts"]["errors"] += 1
            # Tag so the frontend can attribute events with concurrent workers
            event.setdefault("job_id", job["id"])
            event.setdefault("job_type", job["type"])
            event.setdefault("job_label", job["label"])
            # Plain-language title/hint/action next to yt-dlp's raw message
            errors.annotate(event)
            if status == "item_failed":
                _keep(report["failed"], {"message": event.get("message"), "url": event.get("url"),
                                         "title": event.get("title"), "hint": event.get("hint")})
            self._push(event)
        return _cb

    def _on_finished(self, job: dict, status: str) -> None:
        """Post-job bookkeeping for syncs: the folder's sync report (whatever
        the outcome), and on success the sync timestamps and sync_log row."""
        if job.get("type") != "sync":
            return
        duration = int(time.monotonic() - job.get("_t0", time.monotonic()))
        report = job.get("report") or _empty_report()
        folder = job.get("sync_path") or job.get("output_dir")
        if folder:
            try:
                analytics.record_sync_report(folder, status, report, duration,
                                             error=job.get("error"))
            except Exception as exc:
                log.warning(f"sync report not saved: {exc}")
        if status != "complete":
            return
        # Stamped on completion, not enqueue, so a failed sync isn't "synced"
        t_done = time.strftime("%Y-%m-%dT%H:%M:%S")
        sync_path = job.get("sync_path")
        if sync_path:
            def _stamp(cfg: dict) -> None:
                cfg.setdefault("vault_sync_times", {})[sync_path] = t_done
            update_config(_stamp)
        if job.get("library_id"):
            analytics.update_library_last_synced(job["library_id"])
        counts = job.get("counts", {})
        analytics.record_sync_log(
            job.get("library_id") or "", counts.get("new", 0),
            report["archived"] + len(report["filtered"]), counts.get("errors", 0), duration)


def _empty_report() -> dict:
    """What a sync did, item by item (see analytics.record_sync_report)."""
    return {"added": [], "failed": [], "filtered": [], "archived": 0}


def _keep(items: list, item) -> None:
    """Append to a report list, up to SYNC_REPORT_ITEMS_KEEP entries."""
    if len(items) < SYNC_REPORT_ITEMS_KEEP:
        items.append(item)


manager = JobManager()
