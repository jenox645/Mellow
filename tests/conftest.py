import sys
import pytest
import tempfile
import os
import json
import pathlib
from unittest.mock import patch, MagicMock

# Stub tkinter before server.py is imported (headless test environment)
if 'tkinter' not in sys.modules:
    sys.modules['tkinter'] = MagicMock()
    sys.modules['tkinter.filedialog'] = MagicMock()

# Stub flaskwebgui if not installed
try:
    import flaskwebgui
except ImportError:
    sys.modules['flaskwebgui'] = MagicMock()


@pytest.fixture
def app():
    import server
    server.app.config['TESTING'] = True
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = pathlib.Path(tmp) / 'config.json'
        db_path = pathlib.Path(tmp) / 'analytics.duckdb'
        with patch('config.CONFIG_PATH', cfg_path):
            with patch('analytics.DB_PATH', db_path):
                import analytics
                analytics.init_db()
                yield server.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_cancel_state():
    import downloader
    downloader._reset_cancel()
    yield
    downloader._reset_cancel()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


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
