"""Let a built MellowDLP update itself from the real GitHub release.

    python scripts/update_e2e.py <app> <expected install kind>

<app> must be a build whose APP_VERSION is older than the latest release
(CI builds one as 0.0.1): an installed MellowDLP.exe (windows-installer),
an AppImage (appimage) or a Linux binary (linux-binary). The script starts
it headless with a throwaway home folder, checks that it offers the update,
starts the install through the API, and waits for the app to come back as
the released version. Needs psutil (a flaskwebgui dependency) to stop the
new copy, which the update helper starts, not this script.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_binary import _NEW_GROUP, _stop  # noqa: E402

START_TIMEOUT_SECS = 90
UPDATE_TIMEOUT_SECS = 600      # download (~40 MB) + install + first start


def _api(base: str, path: str, body: dict | None = None) -> dict:
    req = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _wait_for_server(port_file: Path, not_port: str | None, deadline: float) -> str:
    """The base URL of the copy that wrote the port file (another than `not_port`)."""
    while time.monotonic() < deadline:
        try:
            port = port_file.read_text().strip()
            if port and port != not_port:
                base = f"http://127.0.0.1:{port}"
                _api(base, "/api/system")
                return base
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise SystemExit("FAILED: no MellowDLP answered in time")


def _stop_port_owner(port: int) -> None:
    for proc in psutil.process_iter():
        try:
            if any(c.laddr and c.laddr.port == port for c in proc.net_connections(kind="inet")):
                for p in [*proc.children(recursive=True), proc]:
                    p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def main(app: str, expected_kind: str) -> int:
    exe = Path(app).resolve()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home:
        env = {**os.environ, "HOME": home, "USERPROFILE": home}
        port_file = Path(home) / ".mellow_dlp.port"
        proc = subprocess.Popen([str(exe), "--no-window"], env=env, **_NEW_GROUP)
        try:
            base = _wait_for_server(port_file, None, time.monotonic() + START_TIMEOUT_SECS)
            before = _api(base, "/api/system")["app_version"]
            offer = _api(base, "/api/check-app-update")
            print(f"  running {before}; offered: {json.dumps(offer)[:400]}")
            if not (offer.get("update_available") and offer.get("can_install")
                    and offer.get("install_kind") == expected_kind):
                print(f"FAILED: expected an installable {expected_kind} update")
                return 1
            print("  install:", _api(base, "/api/app-update/install", {}))
            old_port = base.rsplit(":", 1)[1]
            try:
                proc.wait(timeout=UPDATE_TIMEOUT_SECS)
            except subprocess.TimeoutExpired:
                print("FAILED: the old copy never exited")
                return 1
            print(f"  old copy exited ({proc.returncode})")
            base = _wait_for_server(port_file, old_port, time.monotonic() + START_TIMEOUT_SECS)
            after = _api(base, "/api/system")["app_version"]
            print(f"  now running {after}")
            _stop_port_owner(int(base.rsplit(":", 1)[1]))
            if after != offer["latest"]:
                print(f"FAILED: expected {offer['latest']}")
                return 1
        finally:
            if proc.poll() is None:
                _stop(proc)
            for log in (".mellow_dlp.log", ".mellow_dlp_update.log"):
                path = Path(home) / log
                if path.exists():
                    print(f"-- {log} --")
                    print(path.read_text(encoding="utf-8", errors="replace")[-3000:])
    print(f"update test passed: {before} -> {after}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
