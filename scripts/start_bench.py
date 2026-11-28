"""How fast the backend starts as the desktop shell starts it, and what memory it keeps.

    python scripts/start_bench.py dist/MellowDLP-backend/mellowdlp-backend[.exe]
    python scripts/start_bench.py main.py            # from source, with this Python
    python scripts/start_bench.py <backend> --runs 5 --settle 12

Every run starts the backend with `--shell` and `MELLOW_SHELL=tauri`, as
src-tauri/src/backend.rs does (pipes, its own process group), in one throwaway
home shared by every run (the first, unrecorded run creates the config and the
database there, as an installed copy has them). A Chromium page (Playwright,
started before the backend, as the shell's webview is) then opens the ready
line's sign-in link, as the window does. Times are from just before the
process starts:

  ready       the ready line (the server listens)
  first data  the page's first /api/ answer
  stats       the page's /api/stats answer (the sidebar's numbers: the database)

USS (memory only this process uses: Task Manager's "Memory" column) is read
`--settle` seconds after the start, with nothing else asked in between. It
needs psutil (`pip install psutil`), else Linux's /proc is read; without
either it's left out. Set MELLOW_CHROMIUM to use another Chromium (as
tests/browser does).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from smoke_binary import READY_PREFIX, app_env  # noqa: E402

READY_TIMEOUT_SECS = 90


def _uss_mb(pid: int) -> float | None:
    try:
        import psutil
        return psutil.Process(pid).memory_full_info().uss / 2**20
    except ImportError:
        pass
    try:
        rollup = Path(f"/proc/{pid}/smaps_rollup").read_text()
    except OSError:
        return None
    kb = sum(int(line.split()[1]) for line in rollup.splitlines()
             if line.startswith(("Private_Clean:", "Private_Dirty:")))
    return kb / 1024


def _command(target: Path) -> list[str]:
    if target.suffix == ".py":
        return [sys.executable, str(target), "--shell"]
    return [str(target), "--shell"]


def _ready_url(proc: subprocess.Popen) -> str:
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True).start()
    line = lines.get(timeout=READY_TIMEOUT_SECS).decode("utf-8", "replace").strip()
    if not line.startswith(READY_PREFIX):
        raise RuntimeError(f"the first line isn't the ready line: {line!r}")
    return line[len(READY_PREFIX):].split(" ", 1)[0]


def one_run(target: Path, env: dict, settle: float, browser) -> dict:
    flags = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
             if sys.platform == "win32" else {"start_new_session": True})
    context = browser.new_context()
    page = context.new_page()
    answers: dict[str, float] = {}
    t0 = time.perf_counter()

    def answered(response) -> None:
        path = urlsplit(response.url).path
        if path.startswith("/api/") and path not in answers:
            answers[path] = time.perf_counter() - t0
    page.on("response", answered)
    proc = subprocess.Popen(_command(target), env=env, cwd=str(target.parent),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, **flags)
    try:
        url = _ready_url(proc)
        ready = time.perf_counter() - t0
        page.goto(url)
        deadline = time.perf_counter() + 30
        while "/api/stats" not in answers and time.perf_counter() < deadline:
            page.wait_for_timeout(5)
        if "/api/stats" not in answers:
            raise RuntimeError(f"the page never got /api/stats (answers: {sorted(answers)})")
        page.wait_for_timeout(max(0.0, settle - (time.perf_counter() - t0)) * 1000)
        uss = _uss_mb(proc.pid)
        return {"ready": ready, "first": min(answers.values()), "stats": answers["/api/stats"],
                "uss": uss}
    finally:
        context.close()
        proc.stdin.close()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backend", help="the backend exe, or main.py to run it from source")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--settle", type=float, default=12.0, help="seconds from the start to the USS reading")
    parser.add_argument("--json", action="store_true", help="print each run's numbers as JSON instead")
    args = parser.parse_args()
    target = Path(args.backend).resolve()
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home, sync_playwright() as pw:
        # Started before the backend: the shell's webview is up by the ready line too
        browser = pw.chromium.launch(executable_path=os.environ.get("MELLOW_CHROMIUM") or None)
        env = {**app_env(home), "MELLOW_SHELL": "tauri"}
        one_run(target, env, 0, browser)   # warm-up: creates the config and the database
        runs = [one_run(target, env, args.settle, browser) for _ in range(args.runs)]
        browser.close()

    if args.json:
        print(json.dumps(runs))
        return 0

    def row(key: str, unit: str, scale: float = 1.0) -> str:
        values = [r[key] for r in runs if r[key] is not None]
        if not values:
            return f"  {key:<10} (not available)"
        shown = " / ".join(f"{v * scale:.0f}" for v in values)
        return f"  {key:<10} {shown} {unit}  (median {statistics.median(values) * scale:.0f})"
    print(f"{target.name}, {args.runs} runs after a warm-up:")
    print(row("ready", "ms", 1000))
    print(row("first", "ms", 1000).replace("first     ", "first data"))
    print(row("stats", "ms", 1000))
    print(row("uss", "MB"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
