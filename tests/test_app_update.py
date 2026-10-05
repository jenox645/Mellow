"""Checking GitHub for a newer MellowDLP, and installing it."""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from mellow import app_update
from mellow.constants import APP_ASSET_NAMES, APP_ASSET_SUMS, APP_DOWNLOADS_PREFIX
from mellow.version import APP_VERSION

ROOT = Path(__file__).resolve().parent.parent
NEW = '99.0.0'
PAYLOAD = b'new MellowDLP build ' * 50_000   # ~1 MB: several chunks


def _release(tag, url='https://github.com/jenox645/Mellow/releases/tag/x', assets=()):
    return io.BytesIO(json.dumps({'tag_name': tag, 'html_url': url, 'body': 'notes',
                                  'assets': list(assets)}).encode())


def _asset_entry(name, size, prefix=APP_DOWNLOADS_PREFIX):
    return {'name': name, 'size': size, 'browser_download_url': f'{prefix}v{NEW}/{name}'}


class _Resp(io.BytesIO):
    def __init__(self, data, url=''):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}
        self.url = url

    def geturl(self):
        return self.url


def _github(kind, payload=PAYLOAD, sums_hash=None, prefix=APP_DOWNLOADS_PREFIX, api_limited=False):
    """A fake GitHub serving release NEW with the asset for `kind` (its API
    answering 403 when `api_limited`, like an anonymous caller over its quota)."""
    name = APP_ASSET_NAMES[kind].format(version=NEW)
    sums = f'{sums_hash or hashlib.sha256(payload).hexdigest()}  {name}\nabc  other-file\n'
    assets = [_asset_entry(name, len(payload), prefix), _asset_entry(APP_ASSET_SUMS, len(sums), prefix)]

    def urlopen(req, timeout=None):
        url = req.full_url
        if 'api.github.com' in url:
            if api_limited:
                raise HTTPError(url, 403, 'rate limit exceeded', {}, None)
            return _Resp(_release('v' + NEW, assets=assets).getvalue())
        if url.endswith('/releases/latest'):
            return _Resp(b'<html>', url=f'https://github.com/jenox645/Mellow/releases/tag/v{NEW}')
        if url.endswith(APP_ASSET_SUMS):
            return _Resp(sums.encode())
        if url.endswith(name):
            return _Resp(payload)
        raise AssertionError(f'unexpected request {url}')
    return urlopen


# ── Check ─────────────────────────────────────────────────────────────────────

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
        for _ in range(50):
            if open_url.called:
                break
            time.sleep(0.02)
    open_url.assert_called_once_with('https://github.com/jenox645/Mellow/releases/latest')


@pytest.mark.parametrize('kind', list(APP_ASSET_NAMES))
def test_check_offers_the_install_when_the_release_has_this_systems_file(kind):
    with patch('mellow.app_update.install_kind', return_value=(kind, None)), \
            patch('mellow.app_update.urlopen', side_effect=_github(kind)):
        data = app_update.check()
    assert data['can_install'] is True and data['install_kind'] == kind
    assert data['download_size'] == len(PAYLOAD)


def test_a_rate_limited_api_falls_back_to_the_release_page(tmp_path, monkeypatch):
    fake = _github('linux-binary', api_limited=True)
    with patch('mellow.app_update.install_kind', return_value=('linux-binary', None)), \
            patch('mellow.app_update.urlopen', side_effect=fake):
        data = app_update.check()
    assert data['latest'] == NEW and data['can_install'] is True
    assert data['download_size'] is None        # the page doesn't say; the download does
    target = tmp_path / 'app' / 'MellowDLP'
    target.parent.mkdir()
    target.write_bytes(b'old build')
    monkeypatch.delenv('APPIMAGE', raising=False)
    events, handed = _install('linux-binary', target, fake, monkeypatch)
    assert target.read_bytes() == PAYLOAD and handed
    pcts = [e['pct'] for e in events if e['stage'] == 'downloading']
    assert pcts[-1] == 100


def test_check_ignores_files_hosted_anywhere_else():
    fake = _github('appimage', prefix='https://evil.example/releases/download/')
    with patch('mellow.app_update.install_kind', return_value=('appimage', None)), \
            patch('mellow.app_update.urlopen', side_effect=fake):
        data = app_update.check()
    assert data['update_available'] is True and data['can_install'] is False
    assert 'no download' in data['install_note']


def test_from_source_the_release_page_is_the_way():
    with patch('mellow.app_update.urlopen', side_effect=_github('linux-binary')):
        data = app_update.check()
    assert data['update_available'] is True and data['can_install'] is False
    assert 'source' in data['install_note']


def test_release_workflow_publishes_the_names_the_app_looks_for():
    workflow = (ROOT / '.github' / 'workflows' / 'release.yml').read_text(encoding='utf-8')
    published = set(re.findall(r'"release/(MellowDLP-\$VERSION-[^"]+)"', workflow))
    assert published == {name.format(version='$VERSION') for name in APP_ASSET_NAMES.values()}
    assert APP_ASSET_SUMS in workflow


# ── What this copy is ─────────────────────────────────────────────────────────

def _frozen(monkeypatch, exe, platform):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(exe))
    monkeypatch.setattr(sys, 'platform', platform)


def test_install_kind(tmp_path, monkeypatch):
    assert app_update.install_kind()[0] is None   # pytest runs from source
    exe = tmp_path / 'MellowDLP.exe'
    exe.write_bytes(b'x')
    _frozen(monkeypatch, exe, 'win32')
    assert app_update.install_kind() == (None, app_update.install_kind()[1])
    (tmp_path / 'unins000.exe').write_bytes(b'x')
    assert app_update.install_kind() == ('windows-installer', None)

    binary = tmp_path / 'MellowDLP'
    binary.write_bytes(b'x')
    _frozen(monkeypatch, binary, 'linux')
    monkeypatch.delenv('APPIMAGE', raising=False)
    assert app_update.install_kind() == ('linux-binary', None)
    monkeypatch.setenv('APPIMAGE', str(tmp_path / 'MellowDLP.AppImage'))
    (tmp_path / 'MellowDLP.AppImage').write_bytes(b'x')
    assert app_update.install_kind() == ('appimage', None)
    with patch('mellow.app_update.os.access', return_value=False):
        kind, note = app_update.install_kind()
    assert kind is None and "can't be replaced" in note

    _frozen(monkeypatch, binary, 'darwin')
    assert app_update.install_kind()[0] is None


# ── Install ───────────────────────────────────────────────────────────────────

def _install(kind, target, fake, monkeypatch):
    events, handed = [], []
    monkeypatch.setattr(sys, 'executable', str(target))
    with patch('mellow.app_update.install_kind', return_value=(kind, None)), \
            patch('mellow.app_update.urlopen', side_effect=fake), \
            patch('mellow.fetch.urlopen', side_effect=fake), \
            patch('mellow.app_update._hand_over', side_effect=lambda cmd, env: handed.append((cmd, env))):
        app_update.install(events.append)
    return events, handed


def test_install_replaces_the_binary_and_restarts_it(tmp_path, monkeypatch):
    tmp_path = tmp_path / 'app'     # the test's own folder also holds its database
    tmp_path.mkdir()
    target = tmp_path / 'MellowDLP'
    target.write_bytes(b'old build')
    monkeypatch.delenv('APPIMAGE', raising=False)
    monkeypatch.setattr(sys, 'argv', ['MellowDLP', '--no-window'])
    events, handed = _install('linux-binary', target, _github('linux-binary'), monkeypatch)

    assert target.read_bytes() == PAYLOAD and os.access(target, os.X_OK)
    assert [p.name for p in tmp_path.iterdir()] == ['MellowDLP']    # nothing left behind
    stages = [e['stage'] for e in events]
    assert stages[0] == 'downloading' and stages[-2:] == ['installing', 'restarting']
    pcts = [e['pct'] for e in events if e['stage'] == 'downloading']
    assert pcts[0] == 0 and pcts[-1] == 100 and pcts == sorted(set(pcts))
    assert all(e['version'] == NEW for e in events)
    [(cmd, env)] = handed
    assert cmd[:2] == ['/bin/sh', '-c'] and cmd[-2:] == [str(target), '--no-window']
    assert env['PYINSTALLER_RESET_ENVIRONMENT'] == '1' and env['MELLOW_PID'] == str(os.getpid())


def test_install_replaces_the_appimage_not_the_binary_inside_it(tmp_path, monkeypatch):
    appimage = tmp_path / 'MellowDLP-2.0.0-x86_64.AppImage'
    appimage.write_bytes(b'old appimage')
    monkeypatch.setenv('APPIMAGE', str(appimage))
    inner = tmp_path / 'mount' / 'MellowDLP'
    inner.parent.mkdir()
    inner.write_bytes(b'inner')
    _, handed = _install('appimage', inner, _github('appimage'), monkeypatch)
    assert appimage.read_bytes() == PAYLOAD and inner.read_bytes() == b'inner'
    assert str(appimage) in handed[0][0]


def test_a_download_that_fails_its_checksum_changes_nothing(tmp_path, monkeypatch):
    tmp_path = tmp_path / 'app'
    tmp_path.mkdir()
    target = tmp_path / 'MellowDLP'
    target.write_bytes(b'old build')
    monkeypatch.delenv('APPIMAGE', raising=False)
    events, handed = _install('linux-binary', target, _github('linux-binary', sums_hash='0' * 64), monkeypatch)
    assert target.read_bytes() == b'old build' and not handed
    assert [p.name for p in tmp_path.iterdir()] == ['MellowDLP']
    assert events[-1]['stage'] == 'error' and 'checksum' in events[-1]['message']


def test_windows_runs_the_installer_after_exiting(tmp_path, monkeypatch):
    exe = tmp_path / 'MellowDLP.exe'
    exe.write_bytes(b'old')
    monkeypatch.setattr(sys, 'argv', ['MellowDLP.exe'])
    monkeypatch.setattr(app_update.tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))
    (tmp_path / 'temp').mkdir()
    _, handed = _install('windows-installer', exe, _github('windows-installer'), monkeypatch)
    [(cmd, env)] = handed
    setup = Path(env['MELLOW_SETUP'])
    assert setup.read_bytes() == PAYLOAD and setup.name == f'MellowDLP-{NEW}-windows-setup.exe'
    assert exe.read_bytes() == b'old'       # the installer replaces it, once this process is gone
    assert cmd[0] == 'powershell' and '$env:MELLOW_SETUP' in cmd[-1]
    assert '/VERYSILENT' in env['MELLOW_SETUP_ARGS'] and env['MELLOW_EXE'] == str(exe)
    assert env['MELLOW_ARGS'] == ''


def test_nothing_to_install_when_already_latest(monkeypatch):
    events = []
    with patch('mellow.app_update.install_kind', return_value=('linux-binary', None)), \
            patch('mellow.app_update.urlopen', return_value=_release('v' + APP_VERSION)):
        app_update.install(events.append)
    assert events == [{'status': 'app_update', 'stage': 'error',
                       'message': f'MellowDLP {APP_VERSION} is already the latest version.'}]


def test_from_source_install_explains_why_not():
    events = []
    app_update.install(events.append)
    assert events[-1]['stage'] == 'error' and 'source' in events[-1]['message']


@pytest.mark.skipif(sys.platform == 'win32', reason='the POSIX helper')
def test_posix_helper_waits_for_the_app_to_exit_then_starts_it(tmp_path):
    app = subprocess.Popen(['sleep', '1'])
    started = tmp_path / 'started'
    helper = subprocess.Popen(['/bin/sh', '-c', app_update._POSIX_HELPER, 'mellow-relaunch',
                               'touch', str(started)], env={**os.environ, 'MELLOW_PID': str(app.pid)})
    time.sleep(0.5)
    assert not started.exists()             # still waiting for the app
    app.wait()
    helper.wait(timeout=5)
    assert started.exists()


# ── API ───────────────────────────────────────────────────────────────────────

def test_install_endpoint_asks_first_when_downloads_are_running(client):
    with patch('mellow.app_update.install') as install, \
            patch('mellow.jobs.manager.status', return_value={'active': 2}):
        busy = client.post('/api/app-update/install', json={})
        assert busy.status_code == 409 and busy.get_json()['running'] == 2
        assert client.post('/api/app-update/install', json={'force': True}).status_code == 200
        for _ in range(50):
            if install.called:
                break
            time.sleep(0.02)
    install.assert_called_once()
