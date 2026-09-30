"""The log file the packaged app writes (it has no console)."""
import logging
from unittest.mock import patch

import pytest

import applog


@pytest.fixture
def isolated_root_logger():
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    yield
    for h in root.handlers:
        if h not in saved[0]:
            h.close()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])


def test_setup_writes_app_logs_to_the_file(tmp_path, isolated_root_logger):
    log_file = tmp_path / 'mellow.log'
    with patch('applog.LOG_PATH', log_file):
        applog.setup()
        logging.getLogger('downloader').warning('something went sideways')
        logging.getLogger('werkzeug').info('GET /api/system 200')  # request noise
        for h in logging.getLogger().handlers:
            h.flush()
    text = log_file.read_text(encoding='utf-8')
    assert 'WARNING downloader: something went sideways' in text
    assert '/api/system' not in text


def test_open_log_without_a_file(client, tmp_path):
    with patch('applog.LOG_PATH', tmp_path / 'missing.log'):
        r = client.post('/api/open-log', json={})
    assert r.status_code == 404


def test_system_reports_the_log_path(client):
    assert client.get('/api/system').get_json()['log_path'].endswith('.mellow_dlp.log')
