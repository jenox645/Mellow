"""main.py: the window, or the default browser when there's no Chromium-based one."""
import json
from unittest.mock import MagicMock, patch

import pytest

import main

PAGE = 'file:///home/u/.local/share/mellowdlp/launch-0123.html'


def _run(browser_path):
    flask_app = MagicMock()
    ui = MagicMock(browser_path=browser_path,
                   browser_command=['/usr/bin/chromium', '--new-window', '--app=http://127.0.0.1:5123'])
    with patch('main.FlaskUI', return_value=ui), \
            patch('main._launch_page_uri', return_value=PAGE) as page, \
            patch('main.threading.Timer') as timer, \
            patch('main.webbrowser.open') as browser_open:
        main._run_window(flask_app, 5123)
        if timer.called:
            delay, fn, args = timer.call_args.args
            fn(*args)
    page.assert_called_once_with('http://127.0.0.1:5123')
    return flask_app, ui, browser_open


def test_opens_an_app_window_with_a_chromium_based_browser():
    flask_app, ui, browser_open = _run('/usr/bin/chromium')
    ui.run.assert_called_once()
    flask_app.run.assert_not_called()
    browser_open.assert_not_called()
    # The window opens the owner-only launch page: no sign-in token on its command line
    assert ui.browser_command == ['/usr/bin/chromium', '--new-window', f'--app={PAGE}']


def test_without_one_it_serves_and_opens_the_default_browser():
    flask_app, ui, browser_open = _run(None)
    ui.run.assert_not_called()
    flask_app.run.assert_called_once_with(host='127.0.0.1', port=5123, threaded=True)
    browser_open.assert_called_once_with(PAGE)


def _watch(pages, active=False):
    """Run main._watch_pages against a scripted page count, one per tick; returns
    the tick at which it quit, or None if it was still watching at the end."""
    ticks = iter(pages)
    clock = {'t': 0.0}

    def sleep(secs):
        clock['t'] += secs

    class StopWatchingError(Exception):
        pass

    def open_pages():
        try:
            return next(ticks)
        except StopIteration:
            raise StopWatchingError from None   # ran out of script: still watching

    with patch('mellow.server.open_pages', side_effect=open_pages), \
            patch('mellow.jobs.manager.has_active', return_value=active), \
            patch('main._stop_instance'), \
            patch('main.os._exit', side_effect=StopWatchingError) as exit_:
        try:
            main._watch_pages(sleep=sleep, clock=lambda: clock['t'])
        except StopWatchingError:
            pass
    return clock['t'] if exit_.called else None


def test_the_tab_mode_app_quits_once_its_page_is_closed():
    gone = main.PAGE_GONE_EXIT_SECS // main.PAGE_WATCH_INTERVAL_SECS
    # Open for a while, closed: quits PAGE_GONE_EXIT_SECS later
    assert _watch([1] * 5 + [0] * (gone + 5)) == (5 + gone + 1) * main.PAGE_WATCH_INTERVAL_SECS
    # A reload drops the connection for a moment: still running
    assert _watch([1] * 5 + [0] * 2 + [1] * 50) is None
    # Never closes while something downloads
    assert _watch([1] * 5 + [0] * (gone * 3), active=True) is None


def test_the_tab_mode_app_quits_when_no_page_ever_connects():
    first = main.FIRST_PAGE_TIMEOUT_SECS // main.PAGE_WATCH_INTERVAL_SECS
    assert _watch([0] * (first + 5)) == first * main.PAGE_WATCH_INTERVAL_SECS


def test_a_browser_that_wont_open_says_where_to_go(capsys):
    with patch('main.webbrowser.open', return_value=False):
        main._open_in_browser('http://127.0.0.1:5123')
    assert 'http://127.0.0.1:5123' in capsys.readouterr().out


# ── a second launch ─────────────────────────────────────────────────────────────

class _Answer:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.body).encode()


def _probe(answer):
    """main._running_instance() against a server answering `answer(nonce)`."""
    from mellow import session
    session.start_instance(5123)
    opener = MagicMock()
    opener.open.side_effect = lambda url, timeout: _Answer(answer(url.split("nonce=")[1]))
    with patch('main.build_opener', return_value=opener) as build:
        found = main._running_instance()
    # Asked directly, never through a proxy from the environment
    assert build.call_args.args[0].proxies == {}
    return found


def test_a_second_launch_finds_the_running_copy_by_its_proof(isolated_user_files):
    from mellow import session
    found = _probe(lambda nonce: {"proof": session.instance_proof(nonce)})
    assert found["url"] == 'http://127.0.0.1:5123'


def test_a_program_squatting_the_port_is_not_mistaken_for_it(isolated_user_files):
    """After a crash another program may answer on the old port; it doesn't know the secret."""
    assert _probe(lambda nonce: {"proof": "0" * 64, "app_version": "2.12.0"}) is None
    assert _probe(lambda nonce: {"app_version": "2.12.0"}) is None


def test_nothing_running_means_a_new_copy(isolated_user_files):
    assert main._running_instance() is None                      # no instance file
    from mellow import session
    session.start_instance(5123)
    opener = MagicMock()
    opener.open.side_effect = OSError("connection refused")
    with patch('main.build_opener', return_value=opener):
        assert main._running_instance() is None


def test_a_second_launch_opens_a_signed_in_window_on_the_running_copy():
    running = {"port": 5123, "secret": b"s" * 32, "url": "http://127.0.0.1:5123"}
    with patch('main.applog.setup'), \
            patch.object(main.sys, 'excepthook', main.sys.excepthook), \
            patch('main._running_instance', return_value=running), \
            patch('main._launch_page_uri', return_value=PAGE) as page, \
            patch('main.webbrowser.open', return_value=True) as browser_open, \
            pytest.raises(SystemExit):
        main.main()
    page.assert_called_once_with("http://127.0.0.1:5123", b"s" * 32, 5123)
    browser_open.assert_called_once_with(PAGE)



# ── an instance file left behind ────────────────────────────────────────────────

def _dead_pid() -> int:
    """The id of a process that has just ended."""
    import subprocess
    import sys
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _instance_file(pid="absent", port=5123):
    from mellow import datadir, session
    data = {"port": port, "secret": "ab" * 32}
    if pid != "absent":
        data["pid"] = pid
    folder = datadir.ensure_private()
    datadir.write_private(folder / session.INSTANCE_FILE_NAME, json.dumps(data))
    return session.instance_file()


def test_the_instance_file_names_this_process(isolated_user_files):
    import os

    from mellow import session
    session.start_instance(5123)
    assert session.read_instance()["pid"] == os.getpid()
    assert session.process_alive(os.getpid())
    assert not session.process_alive(_dead_pid())
    assert not session.process_alive(0)


def test_a_copy_that_is_gone_is_not_probed(isolated_user_files):
    """Closing the window ends the process before it can remove its file: the next start
    finds the file, sees its process is gone, and starts at once (no ~2 s refused connect)."""
    import time
    path = _instance_file(pid=_dead_pid())
    with patch('main.build_opener') as build:
        started = time.monotonic()
        assert main._running_instance() is None
        assert time.monotonic() - started < 0.5
    build.assert_not_called()
    assert not path.exists()


def test_a_live_process_is_still_asked_for_its_proof(isolated_user_files):
    """A running process id may belong to another program (ids are reused after a reboot)."""
    import os
    _instance_file(pid=os.getpid())
    opener = MagicMock()
    opener.open.side_effect = lambda url, timeout: _Answer({"proof": "0" * 64})
    with patch('main.build_opener', return_value=opener):
        assert main._running_instance() is None
    opener.open.assert_called_once()


def test_an_older_file_without_a_pid_is_probed_as_before(isolated_user_files):
    path = _instance_file()
    opener = MagicMock()
    opener.open.side_effect = OSError("connection refused")
    with patch('main.build_opener', return_value=opener):
        assert main._running_instance() is None
    opener.open.assert_called_once()
    assert path.exists()   # nothing proves it stale: the next copy simply replaces it


def test_a_stale_file_replaced_meanwhile_is_left_alone(isolated_user_files):
    from mellow import session
    dead = _dead_pid()
    path = _instance_file(pid=dead + 1)
    session.drop_stale_instance(dead)
    assert path.exists()


def test_removing_a_stale_file_waits_for_a_copy_publishing_its_own(isolated_user_files):
    """Two launches find the same stale file: the one tidying up checks and removes it under the
    instance lock, so it can't remove the file the other has just written."""
    import threading

    from mellow import session
    dead = _dead_pid()
    path = _instance_file(pid=dead)
    with session._instance_file_lock() as locked:     # a copy publishing its file right now
        assert locked
        tidy = threading.Thread(target=session.drop_stale_instance, args=(dead,))
        tidy.start()
        tidy.join(0.3)
        assert tidy.is_alive()                         # waiting for the lock
        _instance_file(pid=dead + 1)                   # the new copy's file
    tidy.join(5)
    assert not tidy.is_alive()
    assert path.exists() and session.read_instance()["pid"] == dead + 1


def test_closing_the_window_forgets_the_instance():
    """FlaskWebGUI ends the server with a signal when the window closes (atexit doesn't run);
    its on_shutdown runs first."""
    flask_app, ui, _ = _run('/usr/bin/chromium')
    with patch('main.FlaskUI', return_value=ui) as flask_ui, \
            patch('main._launch_page_uri', return_value=PAGE):
        main._run_window(flask_app, 5123)
    assert flask_ui.call_args.kwargs["on_shutdown"] is main._stop_instance


# ── the port ────────────────────────────────────────────────────────────────────

def test_a_fixed_port_is_used_when_free_and_skipped_when_taken():
    import socket

    from mellow.config import update_config
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    update_config(lambda c: c.update(api_port=free))
    assert main._choose_port() == free
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", free))
        taken.listen()
        assert main._choose_port() != free
    for bad in (0, 80, 70000, "x"):
        update_config(lambda c, bad=bad: c.update(api_port=bad))
        assert main._choose_port() >= 1024
