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
