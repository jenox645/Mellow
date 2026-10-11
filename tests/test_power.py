"""Keep awake: no idle sleep while the queue holds a job."""
import ctypes
import os
import sys
import threading
import time
from unittest.mock import patch

import pytest

from mellow import config, jobs, power


def _manager():
    m = jobs.JobManager()
    m.start(lambda e: None)
    return m


def test_the_queue_keeps_the_computer_awake_until_it_runs_dry(tmp_path):
    release = threading.Event()

    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        release.wait(10)
        return 'success'

    with patch('mellow.downloader.download_video', side_effect=fake_dl):
        m = _manager()
        assert not power.keeper.want
        m.enqueue('https://youtu.be/a', str(tmp_path), {})
        m.enqueue('https://youtu.be/b', str(tmp_path), {})
        time.sleep(0.3)
        assert power.keeper.want                       # running, and one waiting
        release.set()
        assert m.wait_idle(10)
    assert power.keeper.want is False


def test_a_job_scheduled_for_later_keeps_it_awake_and_cancelling_it_lets_it_sleep(tmp_path):
    m = _manager()
    job = m.enqueue('https://youtu.be/later', str(tmp_path), {}, not_before=time.time() + 3600)
    assert power.keeper.want                           # it can't start in a sleeping computer
    m.cancel(job['id'])
    assert power.keeper.want is False


def test_turned_off_in_config_it_never_holds(tmp_path):
    config.update_config(lambda c: c.update(keep_awake=False))
    m = _manager()
    job = m.enqueue('https://youtu.be/later', str(tmp_path), {}, not_before=time.time() + 3600)
    assert power.keeper.calls and not any(power.keeper.calls)
    m.cancel(job['id'])


def test_the_helper_process_runs_while_held(monkeypatch):
    keeper = power.KeepAwake()
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(power, '_helper_command', lambda: [sys.executable, '-c', 'import time; time.sleep(60)'])
    keeper.set(True)
    assert keeper.wait_settled() and keeper.held
    proc = keeper._proc
    assert proc.poll() is None
    keeper.set(False)
    assert keeper.wait_settled() and not keeper.held
    assert proc.wait(5) is not None and keeper._proc is None


def test_without_a_helper_it_logs_and_carries_on(monkeypatch, caplog):
    keeper = power.KeepAwake()
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(power, '_helper_command', lambda: None)
    keeper.set(True)
    assert keeper.wait_settled()
    keeper.set(False)
    assert keeper.wait_settled()
    assert 'could not turn it on' in caplog.text


def test_windows_asks_from_one_thread(monkeypatch):
    calls = []

    class Kernel32:
        def SetThreadExecutionState(self, flags):  # noqa: N802 — the Windows API name
            calls.append((flags, threading.get_ident()))
            return 1

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'windll', type('W', (), {'kernel32': Kernel32()})(), raising=False)
    keeper = power.KeepAwake()
    keeper.set(True)
    assert keeper.wait_settled()
    keeper.set(False)
    assert keeper.wait_settled()
    keeper.set(True)
    assert keeper.wait_settled()
    keeper.set(False)
    assert keeper.wait_settled()
    on = power._ES_CONTINUOUS | power._ES_SYSTEM_REQUIRED
    assert [f for f, _ in calls] == [on, power._ES_CONTINUOUS, on, power._ES_CONTINUOUS]
    # Windows ties the request to the calling thread: every call from the same one
    assert len({t for _, t in calls}) == 1 and calls[0][1] != threading.get_ident()


@pytest.mark.parametrize("platform,found,expected", [
    ("darwin", {"caffeinate"}, "caffeinate"),
    ("linux", {"systemd-inhibit", "tail"}, "systemd-inhibit"),
    ("linux", {"tail"}, None),
])
def test_helper_command(monkeypatch, platform, found, expected):
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.setattr(power.shutil, 'which', lambda name: f"/usr/bin/{name}" if name in found else None)
    cmd = power._helper_command()
    if expected is None:
        assert cmd is None
    else:
        assert expected in cmd[0]
        # It must end with this process, or a crash would keep the computer awake
        assert any(str(os.getpid()) in part for part in cmd)
