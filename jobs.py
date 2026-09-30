"""Download job queue — worker pool, per-job cancel, reordering, persistence.

The manager owns a small pool of worker threads (MAX_DOWNLOAD_WORKERS); how
many may run downloads at once is the `download_workers` config value, read
live so changing it applies to already-queued work. Every SSE event emitted
through a job is tagged with `job_id`/`job_type`/`job_label` so the frontend
can attribute progress when more than one download is active.

Queued jobs are persisted to QUEUE_STATE_PATH so a restart can offer to
resume them.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

import analytics
import downloader
import errors
from config import download_root, load_config, update_config
from constants import (
    DEFAULT_DOWNLOAD_WORKERS,
    JOB_HISTORY_KEEP,
    MAX_DOWNLOAD_WORKERS,
)

log = logging.getLogger(__name__)

QUEUE_STATE_PATH = Path.home() / ".mellow_dlp_queue.json"

_PERSIST_KEYS = ("id", "type", "label", "url", "multi_urls",
                 "output_dir", "opts", "library_id", "sync_path")
# Internal fields stripped from /api/queue/status responses
PUBLIC_SKIP_KEYS = ("opts", "multi_urls", "cancel_event", "_t0")

TERMINAL_STATUSES = ("complete", "failed", "cancelled")
# SSE events that end a job; the UI expects exactly one per job
TERMINAL_EVENTS = ("complete", "error", "cancelled")


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
        self._started = False
        self.restorable: list[dict] = []
        self._load_restorable()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, push_fn: Callable[[dict], None]) -> None:
        """Attach the SSE broadcast function and spawn the worker pool."""
        self._push = push_fn
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
                sync_path: str | None = None) -> dict:
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
        try:
            with self._cv:
                pending = [{k: j.get(k) for k in _PERSIST_KEYS} for j in self._pending]
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
        """Re-enqueue jobs that were still queued when the app last exited."""
        restored = []
        for j in self.restorable:
            job = self.enqueue(
                j["url"], j.get("output_dir") or download_root(load_config()),
                j.get("opts") or {}, j.get("library_id"),
                job_type=j.get("type", "feed"), label=j.get("label", ""),
                multi_urls=j.get("multi_urls"), sync_path=j.get("sync_path"))
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
                while not (self._pending and self._active_count < configured_workers()):
                    self._cv.wait(timeout=5)
                    if not self._pending:
                        continue
                job = self._pending.pop(0)
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
                self._on_finished(job, status)
            except Exception as exc:
                log.warning(f"post-job bookkeeping failed: {exc}")
            finally:
                with self._cv:
                    self._active_count -= 1
                    if self._active_count == 0:
                        downloader.resume()
                    self._trim_finished()
                    self._cv.notify_all()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until nothing is queued or running. False on timeout."""
        with self._cv:
            return self._cv.wait_for(
                lambda: not self._pending and self._active_count == 0, timeout)

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
            push(terminal or {"status": "error", "message": "Download failed", "url": url})
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
        def _cb(event: dict) -> None:
            status = event.get("status")
            if status == "item_done":
                job["counts"]["new"] += 1
            elif status == "item_failed":
                job["counts"]["errors"] += 1
            # Tag so the frontend can attribute events with concurrent workers
            event.setdefault("job_id", job["id"])
            event.setdefault("job_type", job["type"])
            event.setdefault("job_label", job["label"])
            # Plain-language title/hint/action next to yt-dlp's raw message
            errors.annotate(event)
            self._push(event)
        return _cb

    def _on_finished(self, job: dict, status: str) -> None:
        """Post-job bookkeeping: sync timestamps and the sync_log fact table."""
        if job.get("type") != "sync" or status != "complete":
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
        duration = int(time.monotonic() - job.get("_t0", time.monotonic()))
        analytics.record_sync_log(
            job.get("library_id") or "", counts.get("new", 0), 0,
            counts.get("errors", 0), duration)


manager = JobManager()
