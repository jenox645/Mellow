import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub tkinter before server.py is imported (headless test environment)
if 'tkinter' not in sys.modules:
    sys.modules['tkinter'] = MagicMock()
    sys.modules['tkinter.filedialog'] = MagicMock()

# Stub flaskwebgui if not installed
try:
    import flaskwebgui  # noqa: F401 — availability probe
except ImportError:
    sys.modules['flaskwebgui'] = MagicMock()

# The auto-sync thread would read the config and enqueue real syncs during a
# long test session; tests drive scheduler.tick() directly instead.
import scheduler  # noqa: E402

scheduler.start = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def isolated_user_files(tmp_path):
    """Point every per-user file at a temp dir for every test.

    Without this a test run reads and writes the developer's real
    ~/.mellow_dlp.json, ~/.mellow_dlp.duckdb and ~/.mellow_dlp_queue.json.
    """
    import analytics
    import downloader
    import ffmpeg_locate
    import jobs

    cfg_path = tmp_path / 'config.json'
    # find_ffmpeg() caches its answer and extends PATH; neither may leak from
    # a test that fakes an ffmpeg into the tests that follow.
    with patch('config.CONFIG_PATH', cfg_path), \
            patch('backup.CONFIG_PATH', cfg_path), \
            patch('analytics.DB_PATH', tmp_path / 'analytics.duckdb'), \
            patch('jobs.QUEUE_STATE_PATH', tmp_path / 'queue.json'), \
            patch.dict('os.environ', {}), \
            patch.multiple(ffmpeg_locate, _cached=ffmpeg_locate._cached,
                           _last_miss=ffmpeg_locate._last_miss):
        analytics.init_db()
        downloader._current_cancel_event = None
        downloader.resume()
        scheduler._last_attempt.clear()
        yield tmp_path
        # Let the shared worker pool finish before the paths are restored, so
        # no job outlives its test and lands in the real files.
        jobs.manager.cancel_active()
        jobs.manager.wait_idle(timeout=10)
        downloader._current_cancel_event = None
        downloader.resume()
        analytics.reset_connections()


@pytest.fixture
def app(isolated_user_files):
    import server
    server.app.config['TESTING'] = True
    return server.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tmp_dir(tmp_path):
    d = tmp_path / 'media'
    d.mkdir()
    return str(d)


@pytest.fixture
def mock_ytdlp():
    with patch('yt_dlp.YoutubeDL') as mock:
        yield mock


@pytest.fixture
def sample_config(tmp_dir):
    return {
        "output_dir": tmp_dir,
        "sleep_interval": 0,
        "concurrent_fragments": 4,
        "retries": 3,
        "cookies_browser": "none",
    }
