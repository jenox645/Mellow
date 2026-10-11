"""Keeps the computer from going to sleep while downloads run or wait.

A laptop that sleeps after a few idle minutes stops a long playlist halfway,
and a download queued for the night never starts. While the queue holds a
job, MellowDLP asks the system not to sleep when idle. The screen can still
turn off, and closing the lid or choosing Sleep still sleeps. No extra tool:
Windows' SetThreadExecutionState, macOS' caffeinate, Linux's systemd-inhibit.
Config `keep_awake` turns it off.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .constants import HELPER_START_CHECK_SECS

log = logging.getLogger(__name__)

# SetThreadExecutionState flags
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class KeepAwake:
    """Holds or releases the system's idle-sleep block on its own thread.

    Windows ties the request to the thread that made it, so one long-lived
    thread makes them all; elsewhere it runs a helper process for as long as
    the block is held (one that also ends if MellowDLP is killed).
    """

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._want = False
        self._held = False
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None

    def set(self, want: bool) -> None:
        with self._cv:
            self._want = want
            if self._thread is None:
                if not want:
                    return
                self._thread = threading.Thread(target=self._run, name="keep-awake", daemon=True)
                self._thread.start()
            self._cv.notify()

    @property
    def held(self) -> bool:
        return self._held

    def _run(self) -> None:
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._want != self._held)
                want = self._want
            try:
                self._hold() if want else self._release()
                log.info("keep awake: " + ("on (downloads queued)" if want else "off"))
            except Exception as exc:
                log.warning(f"keep awake: could not turn it {'on' if want else 'off'}: {exc}")
            with self._cv:
                self._held = want   # also after a failure: no retry loop
                self._cv.notify_all()

    def _hold(self) -> None:
        if sys.platform == "win32":
            import ctypes
            # Returns the previous state, which may be 0: nothing to check
            ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
            return
        cmd = _helper_command()
        if cmd is None:
            raise OSError("no caffeinate or systemd-inhibit on this system")
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            # One that quits at once had nothing to talk to (no session bus)
            code = proc.wait(timeout=HELPER_START_CHECK_SECS)
        except subprocess.TimeoutExpired:
            self._proc = proc
            return
        raise OSError(f"{Path(cmd[0]).name} exited with code {code}")

    def _release(self) -> None:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            return
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def wait_settled(self, timeout: float = 5) -> bool:
        """Block until the requested state is in effect (tests)."""
        with self._cv:
            return self._cv.wait_for(lambda: self._want == self._held, timeout)


def _helper_command() -> list[str] | None:
    """A process that blocks idle sleep while it runs, and exits with this one."""
    pid = str(os.getpid())
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        return ["caffeinate", "-i", "-w", pid]
    inhibit, tail = shutil.which("systemd-inhibit"), shutil.which("tail")
    if inhibit and tail:
        # The block lasts while `tail` runs: until it's terminated, or this
        # process exits (a crash must not keep the computer awake for good)
        return [inhibit, "--what=idle", "--who=MellowDLP", "--why=Downloading",
                "--mode=block", tail, f"--pid={pid}", "-f", "/dev/null"]
    return None


keeper = KeepAwake()
