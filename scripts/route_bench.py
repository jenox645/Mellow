"""Server-side time of the routes a big library makes slow (#127).

    python scripts/make_big_library.py <home>
    python scripts/route_bench.py <home> [--runs 5]

Runs the app's routes in this process (Flask's test client, a signed-in
window) against the library in <home>, the way the pages ask for them, and
prints the first call and the median of the next `--runs` for each. The stats
cache is emptied before every /api/stats call, so each one is computed (the
page's first visit after a download). "startup" starts the real app
(`main.py --no-window`) on <home> and times its first /api/stats answer.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bench(home: Path, runs: int) -> list[tuple[str, float, float, str]]:
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
    sys.path.insert(0, str(ROOT))
    from mellow import analytics, config, server, session
    from mellow.config import load_config
    analytics.DB_PATH = home / ".mellow_dlp.duckdb"
    config.CONFIG_PATH = home / ".mellow_dlp.json"
    app = server.init_app()
    sid, token = session.new_session()
    client = app.test_client()
    client.set_cookie(session.COOKIE, sid, domain="localhost")
    headers = {session.HEADER: token}

    cfg = load_config()
    root = Path(cfg["output_dir"])
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    big = max(folders, key=lambda p: sum(1 for _ in p.iterdir()))
    linked = next(iter(cfg.get("vault_playlists") or {str(big): []}))
    big_files = [str(p) for p in big.iterdir() if p.suffix != ".jpg"]
    year = time.localtime().tm_year

    def get(url: str):
        return lambda: client.get(url, headers=headers)

    def post(url: str, body: dict):
        return lambda: client.post(url, json=body, headers=headers)

    def stats(range_: str):
        def ask():
            with analytics._stats_lock:
                analytics._stats_cache.clear()
            return client.get(f"/api/stats?range={range_}", headers=headers)
        return ask

    cases = [
        ("Vault root  /api/vault", get("/api/vault")),
        ("open folder (2,000 files)  /api/vault/folder", get(f"/api/vault/folder?path={big}")),
        ("its pictures  /api/vault/file-thumbs", post("/api/vault/file-thumbs", {"paths": big_files})),
        ("one card's mosaic  /api/vault/folder-previews", get(f"/api/vault/folder-previews?path={big}")),
        ("STATS & BUDGET  /api/vault/folder-stats", get(f"/api/vault/folder-stats?path={big}")),
        ("sync report  /api/vault/sync-report", get(f"/api/vault/sync-report?path={linked}")),
        ("DUPES (300 folders)  /api/vault/duplicates", get("/api/vault/duplicates")),
        # Every sync of a folder starts with this backfill (vault.sync_plan)
        ("archive backfill (2,000 files)  archive-generate",
         post("/api/vault/archive-generate", {"path": str(big)})),
        ("library  /api/library", get("/api/library")),
        ("Analytics 7d  /api/stats", stats("7d")),
        ("Analytics 30d  /api/stats", stats("30d")),
        ("Analytics all  /api/stats", stats("all")),
        ("history page 1  /api/history", get("/api/history?limit=50&offset=0")),
        ("history page 100  /api/history", get("/api/history?limit=50&offset=4950")),
        ("history search  /api/history", get("/api/history?limit=50&offset=0&search=night")),
        ("WRAPPED  /api/analytics/wrapped", get(f"/api/analytics/wrapped?year={year}")),
        ("Queue  /api/queue/status", get("/api/queue/status")),
    ]
    results = []
    for name, call in cases:
        times = []
        for _ in range(runs + 1):
            t0 = time.perf_counter()
            resp = call()
            times.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200, (name, resp.status_code, resp.get_data(as_text=True)[:300])
        size = len(resp.get_data())
        results.append((name, times[0], statistics.median(times[1:]), f"{size / 1024:.0f} KB"))
    return results


def _startup(home: Path) -> float:
    """Launch → the real app's first /api/stats answer (ms)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from urllib.request import ProxyHandler, Request, build_opener

    from smoke_binary import app_env, running_apps, sign_in
    env = {**app_env(str(home)), "XDG_DATA_HOME": tempfile.mkdtemp(), "LOCALAPPDATA": tempfile.mkdtemp()}
    opener = build_opener(ProxyHandler({}))
    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "--no-window"], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while not running_apps(env):
            if time.perf_counter() - t0 > 60 or proc.poll() is not None:
                raise RuntimeError("the app didn't start")
            time.sleep(0.01)
        (base, info), = running_apps(env)
        headers = sign_in(base, info)
        while True:
            try:
                with opener.open(Request(base + "/api/stats", headers=headers), timeout=30) as resp:
                    resp.read()
                return (time.perf_counter() - t0) * 1000
            except OSError:
                time.sleep(0.01)
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("home", help="a home made by scripts/make_big_library.py")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    home = Path(args.home).resolve()
    if not (home / ".mellow_dlp.duckdb").exists():
        print(f"no library in {home}: run scripts/make_big_library.py first")
        return 1
    startups = [_startup(home) for _ in range(3)]
    results = _bench(home, args.runs)
    if args.json:
        print(json.dumps({"startup": startups, "routes": results}))
        return 0
    print(f"{'route':<50} {'first':>8} {'median':>8}  answer")
    print(f"{'startup (launch → first /api/stats)':<50} {startups[0]:>6.0f}ms "
          f"{statistics.median(startups):>6.0f}ms  ({' / '.join(f'{s:.0f}' for s in startups)})")
    for name, first, median, size in results:
        print(f"{name:<50} {first:>6.0f}ms {median:>6.0f}ms  {size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
