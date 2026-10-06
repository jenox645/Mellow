"""main.py: the window, or the default browser when there's no Chromium-based one."""
from unittest.mock import MagicMock, patch

import main


def _run(browser_path):
    flask_app = MagicMock()
    ui = MagicMock(browser_path=browser_path)
    with patch('main.FlaskUI', return_value=ui), \
            patch('main.threading.Timer') as timer, \
            patch('main.webbrowser.open') as browser_open:
        main._run_window(flask_app, 5123)
        if timer.called:
            delay, fn, args = timer.call_args.args
            fn(*args)
    return flask_app, ui, browser_open


def test_opens_an_app_window_with_a_chromium_based_browser():
    flask_app, ui, browser_open = _run('/usr/bin/chromium')
    ui.run.assert_called_once()
    flask_app.run.assert_not_called()
    browser_open.assert_not_called()


def test_without_one_it_serves_and_opens_the_default_browser():
    flask_app, ui, browser_open = _run(None)
    ui.run.assert_not_called()
    flask_app.run.assert_called_once_with(host='127.0.0.1', port=5123, threaded=True)
    browser_open.assert_called_once_with('http://127.0.0.1:5123')


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
            patch('main._remove_port_file'), \
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
