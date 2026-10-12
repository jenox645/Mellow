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
from mellow import scheduler  # noqa: E402

scheduler.start = lambda *args, **kwargs: None


class RecordingKeeper:
    """Stands in for power.keeper: a test run must never block the computer's sleep."""

    def __init__(self):
        self.calls = []

    def set(self, want):
        self.calls.append(bool(want))

    @property
    def want(self):
        return bool(self.calls and self.calls[-1])


def _no_sync_plan(request):
    """A sync job reads its playlists before it starts (jobs._sync_plan). Unit
    tests mock the downloader with made-up playlist URLs, so that read is off
    there; browser tests drive the real app against locally served playlists."""
    from mellow import jobs
    if request.node.get_closest_marker('browser'):
        return jobs._sync_plan
    return lambda job: None


@pytest.fixture(autouse=True)
def isolated_user_files(tmp_path, request):
    """Point every per-user file at a temp dir for every test.

    Without this a test run reads and writes the developer's real
    ~/.mellow_dlp.json, ~/.mellow_dlp.duckdb and ~/.mellow_dlp_queue.json.
    """
    from mellow import analytics, downloader, ffmpeg_locate, jobs

    cfg_path = tmp_path / 'config.json'
    # find_ffmpeg() caches its answer and extends PATH; neither may leak from
    # a test that fakes an ffmpeg into the tests that follow.
    with patch('mellow.config.CONFIG_PATH', cfg_path), \
            patch('mellow.backup.CONFIG_PATH', cfg_path), \
            patch('mellow.analytics.DB_PATH', tmp_path / 'analytics.duckdb'), \
            patch('mellow.jobs.QUEUE_STATE_PATH', tmp_path / 'queue.json'), \
            patch('mellow.ytdlp_update.OVERLAY_PATH', tmp_path / 'ytdlp.zip'), \
            patch('mellow.ffmpeg_locate.MANAGED_DIR', tmp_path / 'ffmpeg'), \
            patch('mellow.power.keeper', RecordingKeeper()), \
            patch('mellow.jobs._sync_plan', _no_sync_plan(request)), \
            patch.dict('os.environ', {}), \
            patch.multiple(ffmpeg_locate, _cached=ffmpeg_locate._cached,
                           _last_miss=ffmpeg_locate._last_miss):
        analytics.init_db()
        downloader.resume()
        scheduler._last_attempt.clear()
        yield tmp_path
        # Let the shared worker pool finish before the paths are restored, so
        # no job outlives its test and lands in the real files.
        jobs.manager.cancel_active()
        jobs.manager.wait_idle(timeout=10)
        downloader.resume()
        analytics.reset_connections()


@pytest.fixture
def app(isolated_user_files):
    from mellow import server
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
