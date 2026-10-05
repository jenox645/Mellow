"""GET FFMPEG: pick, download, verify and install a static ffmpeg build."""
import hashlib
import io
import sys
import tarfile
import time
import zipfile
from unittest.mock import patch

import pytest

from mellow import ffmpeg_install, ffmpeg_locate
from mellow.constants import FFMPEG_BUILDS_URL

LINUX = 'ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz'
WIN = 'ffmpeg-n9.0-latest-win64-gpl-9.0.zip'
SCRIPT = b'#!/bin/sh\necho "ffmpeg version 9.0-test Copyright (c) the FFmpeg developers"\n'


def _sums(**files):
    """A checksums.sha256 like BtbN's: older branches, master, shared builds."""
    lines = [f'{"a" * 64}  ffmpeg-master-latest-linux64-gpl.tar.xz',
             f'{"b" * 64}  ffmpeg-n8.1-latest-linux64-gpl-8.1.tar.xz',
             f'{"c" * 64}  ffmpeg-n9.0-latest-linux64-gpl-shared-9.0.tar.xz',
             f'{"d" * 64}  ffmpeg-n8.1-latest-win64-gpl-8.1.zip',
             f'{"e" * 64}  ffmpeg-n9.0-latest-win64-lgpl-9.0.zip']
    lines += [f'{hashlib.sha256(data).hexdigest()}  {name}' for name, data in files.items()]
    return '\n'.join(lines) + '\n'


def _tar_xz(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:xz') as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _linux_build(**extra):
    root = 'ffmpeg-n9.0-latest-linux64-gpl-9.0/'
    return _tar_xz({root + 'bin/ffmpeg': SCRIPT, root + 'bin/ffprobe': SCRIPT,
                    root + 'bin/ffplay': b'not wanted', root + 'doc/ffmpeg.html': b'<html>',
                    root + 'LICENSE.txt': b'GPL', **extra})


class _Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}


def _site(files, sums=None):
    sums = sums if sums is not None else _sums(**files)

    def urlopen(req, timeout=None):
        name = req.full_url.removeprefix(FFMPEG_BUILDS_URL)
        if name == ffmpeg_install.SUMS_NAME:
            return _Resp(sums.encode())
        return _Resp(files[name])
    return urlopen


def _install(urlopen, plat='linux64'):
    events = []
    with patch('mellow.ffmpeg_install.build_platform', return_value=plat), \
            patch('mellow.fetch.urlopen', side_effect=urlopen), \
            patch('mellow.ffmpeg_locate.shutil.which', return_value=None):
        ffmpeg_install.install(events.append)
        found = ffmpeg_locate.find_ffmpeg(refresh=True)
    return events, found


def _leftovers(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir() if p.name.startswith('ffmpeg.'))


def test_picks_the_newest_release_branch_not_master_or_shared():
    sums = _sums() + f'{"f" * 64}  {LINUX}\n{"9" * 64}  {WIN}\n'
    assert ffmpeg_install.pick_build(sums, 'linux64') == (LINUX, '9.0', 'f' * 64)
    assert ffmpeg_install.pick_build(sums, 'win64') == (WIN, '9.0', '9' * 64)
    assert ffmpeg_install.pick_build(sums, 'linuxarm64') is None


def test_daily_build_names_work_too():
    # The files of BtbN's dated daily releases carry the full version
    sums = '\n'.join([
        f'{"a" * 64}  ffmpeg-N-127203-ga35c879992-linux64-gpl.tar.xz',
        f'{"b" * 64}  ffmpeg-n8.1.3-14-g330caae0c1-linux64-gpl-8.1.tar.xz',
        f'{"c" * 64}  ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz',
        f'{"d" * 64}  ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-shared-9.0.tar.xz',
        f'{"e" * 64}  ffmpeg-n9.0.2-22-g46d8f462ee-win64-gpl-9.0.zip',
    ])
    assert ffmpeg_install.pick_build(sums, 'linux64') == (
        'ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz', '9.0.2', 'c' * 64)
    assert ffmpeg_install.pick_build(sums, 'win64')[1] == '9.0.2'


@pytest.mark.parametrize('platform_name, machine, expected', [
    ('win32', 'AMD64', 'win64'), ('linux', 'x86_64', 'linux64'), ('linux', 'aarch64', 'linuxarm64'),
    ('darwin', 'arm64', None), ('win32', 'ARM64', None),
])
def test_build_platform(monkeypatch, platform_name, machine, expected):
    monkeypatch.setattr(sys, 'platform', platform_name)
    monkeypatch.setattr(ffmpeg_install.platform, 'machine', lambda: machine)
    assert ffmpeg_install.build_platform() == expected
    assert (ffmpeg_install.unavailable_reason() is None) == (expected is not None)


@pytest.mark.skipif(sys.platform == 'win32', reason='runs the installed (shell script) ffmpeg')
def test_installs_ffmpeg_and_ffprobe_and_the_lookup_finds_them(tmp_path):
    events, found = _install(_site({LINUX: _linux_build()}))
    managed = ffmpeg_locate.MANAGED_DIR
    assert sorted(p.name for p in managed.iterdir()) == ['ffmpeg', 'ffprobe']   # no ffplay, no docs
    assert found == str(managed / 'ffmpeg')
    assert ffmpeg_install.installed_here(found)
    stages = [e['stage'] for e in events]
    assert stages[0] == 'downloading' and stages[-2:] == ['installing', 'done']
    assert events[-1]['detail'].startswith('ffmpeg version 9.0-test')
    assert events[-1]['version'] == '9.0'
    assert [e['pct'] for e in events if e['stage'] == 'downloading'][-1] == 100
    assert _leftovers(tmp_path) == []


def test_windows_zip_keeps_only_the_two_exes(tmp_path):
    root = 'ffmpeg-n9.0-latest-win64-gpl-9.0/'
    build = _zip({root + 'bin/ffmpeg.exe': b'MZ ffmpeg', root + 'bin/ffprobe.exe': b'MZ ffprobe',
                  root + 'bin/ffplay.exe': b'MZ ffplay', root + 'doc/x.html': b'<html>'})
    with patch('mellow.ffmpeg_install._EXE', '.exe'), \
            patch('mellow.ffmpeg_install._probe', return_value='ffmpeg version 9.0'):
        events, _ = _install(_site({WIN: build}), plat='win64')
    assert events[-1]['stage'] == 'done', events[-1]
    managed = ffmpeg_locate.MANAGED_DIR
    assert sorted(p.name for p in managed.iterdir()) == ['ffmpeg.exe', 'ffprobe.exe']
    assert (managed / 'ffmpeg.exe').read_bytes() == b'MZ ffmpeg'


def test_a_checksum_mismatch_installs_nothing(tmp_path):
    build = _linux_build()
    sums = _sums() + f'{"0" * 64}  {LINUX}\n'
    events, found = _install(_site({LINUX: build}, sums=sums))
    assert events[-1] == {'status': 'ffmpeg_install', 'stage': 'error',
                          'message': "The ffmpeg download doesn't match its published checksum."}
    assert not ffmpeg_locate.MANAGED_DIR.exists()
    assert _leftovers(tmp_path) == []


def test_a_broken_build_keeps_the_ffmpeg_already_installed(tmp_path):
    managed = ffmpeg_locate.MANAGED_DIR
    managed.mkdir()
    (managed / 'ffmpeg').write_bytes(SCRIPT)
    no_ffprobe = _tar_xz({'ffmpeg-n9.0-latest-linux64-gpl-9.0/bin/ffmpeg': SCRIPT})
    events, _ = _install(_site({LINUX: no_ffprobe}))
    assert events[-1]['stage'] == 'error' and 'ffprobe' in events[-1]['message']
    assert (managed / 'ffmpeg').read_bytes() == SCRIPT
    assert _leftovers(tmp_path) == []


def test_a_build_that_wont_run_is_not_installed(tmp_path):
    with patch('mellow.ffmpeg_install._probe', side_effect=ffmpeg_install.InstallError('won\'t run')):
        events, _ = _install(_site({LINUX: _linux_build()}))
    assert events[-1]['stage'] == 'error'
    assert not ffmpeg_locate.MANAGED_DIR.exists()


def test_unsupported_system_says_how_to_get_it():
    events = []
    with patch('mellow.ffmpeg_install.build_platform', return_value=None), \
            patch.object(sys, 'platform', 'darwin'):
        ffmpeg_install.install(events.append)
    assert events == [{'status': 'ffmpeg_install', 'stage': 'error',
                       'message': 'Install it with Homebrew: brew install ffmpeg'}]


def test_api(client):
    system = client.get('/api/system').get_json()
    assert 'ffmpeg_installable' in system and system['ffmpeg_installed_by_app'] is False
    with patch('mellow.ffmpeg_install.unavailable_reason', return_value='brew install ffmpeg'):
        refused = client.post('/api/ffmpeg/install', json={})
    assert refused.status_code == 400 and refused.get_json()['error'] == 'brew install ffmpeg'
    with patch('mellow.ffmpeg_install.unavailable_reason', return_value=None), \
            patch('mellow.ffmpeg_install.install') as install:
        assert client.post('/api/ffmpeg/install', json={}).status_code == 200
        for _ in range(50):
            if install.called:
                break
            time.sleep(0.02)
    install.assert_called_once()
