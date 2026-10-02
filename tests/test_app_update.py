"""Checking GitHub for a newer MellowDLP."""
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from mellow import app_update
from mellow.version import APP_VERSION


def _release(tag, url='https://github.com/jenox645/Mellow/releases/tag/x'):
    return io.BytesIO(json.dumps({'tag_name': tag, 'html_url': url, 'body': 'notes'}).encode())


def test_newer_release_is_reported(client):
    with patch('mellow.app_update.urlopen', return_value=_release('v99.0.0')):
        data = client.get('/api/check-app-update').get_json()
    assert data['update_available'] is True and data['latest'] == '99.0.0'
    assert data['current'] == APP_VERSION and data['url'].startswith('https://github.com/')


def test_same_version_is_up_to_date():
    with patch('mellow.app_update.urlopen', return_value=_release('v' + APP_VERSION)):
        assert app_update.check()['update_available'] is False


def test_no_release_published_yet_is_not_an_error():
    err = HTTPError(app_update.APP_RELEASES_API, 404, 'Not Found', {}, None)
    with patch('mellow.app_update.urlopen', side_effect=err):
        data = app_update.check()
    assert 'error' not in data and data['update_available'] is False and data['message']


def test_offline_is_reported_as_an_error():
    with patch('mellow.app_update.urlopen', side_effect=OSError('network down')):
        data = app_update.check()
    assert data['error'] == 'network down' and data['update_available'] is False


def test_open_release_opens_only_the_release_page(client):
    with patch('mellow.desktop.open_url') as open_url:
        assert client.post('/api/open-release', json={'url': 'https://evil.example'}).status_code == 200
        import time
        for _ in range(50):
            if open_url.called:
                break
            time.sleep(0.02)
    open_url.assert_called_once_with('https://github.com/jenox645/Mellow/releases/latest')
