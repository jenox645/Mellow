"""Quality-of-life backend: explained errors, "already downloaded", low disk."""
from pathlib import Path
from unittest.mock import patch

import pytest

from mellow import errors, jobs


@pytest.mark.parametrize('raw,code,action', [
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser",
     'bot_check', errors.OPEN_CONFIG),
    ('ERROR: unable to download video data: HTTP Error 403: Forbidden', 'forbidden', errors.UPDATE_YTDLP),
    ('ERROR: [youtube] abc: Private video. Sign in if you have access', 'private', None),
    ('ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader',
     'unavailable', None),
    ('ERROR: [youtube] abc: The uploader has not made this video available in your country',
     'geo_blocked', errors.OPEN_CONFIG),
    ('ERROR: Sign in to confirm your age. This video may be inappropriate for some users.',
     'bot_check', errors.OPEN_CONFIG),  # yt-dlp words both the same way; either fix is cookies
    ('ERROR: [youtube:tab] PLx: YouTube said: The playlist does not exist.', 'unavailable', None),
    ('ERROR: [youtube] aaaaaaaaaaa: This video is unavailable', 'unavailable', None),
    ('ERROR: Unsupported URL: https://example.com/page', 'unsupported', errors.UPDATE_YTDLP),
    ('ERROR: [youtube] abc: Requested format is not available', 'format', None),
    ('<urlopen error [Errno 11001] getaddrinfo failed>', 'network', errors.OPEN_CONFIG),
    ('[Errno 28] No space left on device', 'disk_full', errors.OPEN_CONFIG),
    ('HTTP Error 429: Too Many Requests', 'rate_limited', errors.OPEN_CONFIG),
    ('ERROR: [generic] late: Unable to download webpage: HTTP Error 404: NOT FOUND', 'not_found', None),
    ("ERROR: [generic] x: Unable to download webpage: <urlopen error Tunnel connection failed: "
     "403 Forbidden> (caused by ProxyError('<urlopen error Tunnel connection failed: 403 Forbidden>'))",
     'proxy', errors.OPEN_CONFIG),
])
def test_known_errors_are_explained(raw, code, action):
    found = errors.explain(raw)
    assert found and found['code'] == code and found['action'] == action
    assert found['title'] and found['hint']


def test_unknown_error_is_left_alone():
    assert errors.explain('ERROR: something nobody has seen before') is None
    assert errors.explain('') is None


def test_queue_events_carry_the_explanation():
    events = []
    m = jobs.JobManager()
    m._push = events.append
    job = {'id': 'j', 'type': 'feed', 'label': 'x', 'counts': {'new': 0, 'errors': 0}}
    cb = m._make_cb(job)
    cb({'status': 'error', 'message': 'HTTP Error 403: Forbidden'})
    cb({'status': 'error', 'message': 'merge failed', 'code': 'ffmpeg_missing'})
    cb({'status': 'item_failed', 'message': 'ERROR: [youtube] a: Private video'})
    assert events[0]['code'] == 'forbidden' and events[0]['action'] == errors.UPDATE_YTDLP
    assert events[1]['code'] == 'ffmpeg_missing' and 'title' not in events[1]
    assert events[2]['code'] == 'private'


def test_analyze_error_is_explained(client):
    with patch('mellow.downloader.get_video_info', side_effect=RuntimeError('HTTP Error 403: Forbidden')):
        data = client.post('/api/info', json={'url': 'https://youtu.be/x'}).get_json()
    assert data['error'] and data['code'] == 'forbidden' and data['hint']


def test_analyze_says_when_a_video_was_already_downloaded(client, tmp_dir):
    from mellow import analytics
    f = Path(tmp_dir) / 'Song.mp3'
    f.write_bytes(b'x')
    analytics.record_download({'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'title': 'Song',
                               'status': 'success', 'file_path': str(f)})
    info = {'title': 'Song', 'is_playlist': False, 'id': 'dQw4w9WgXcQ',
            'webpage_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
    with patch('mellow.downloader.get_video_info', return_value=dict(info)):
        # Same video through a different kind of link
        data = client.post('/api/info', json={'url': 'https://youtu.be/dQw4w9WgXcQ'}).get_json()
    prev = data['previous_download']
    assert prev['file_path'] == str(f) and prev['exists'] is True
    f.unlink()
    with patch('mellow.downloader.get_video_info', return_value=dict(info)):
        data = client.post('/api/info', json={'url': 'https://youtu.be/dQw4w9WgXcQ'}).get_json()
    assert data['previous_download']['exists'] is False


def test_analyze_new_video_has_no_previous_download(client):
    with patch('mellow.downloader.get_video_info', return_value={'title': 'T', 'is_playlist': False, 'id': 'zzzzzzzzzzz'}):
        assert client.post('/api/info', json={'url': 'https://youtu.be/zzzzzzzzzzz'}).get_json()['previous_download'] is None


def test_failed_downloads_do_not_count_as_already_downloaded():
    from mellow import analytics
    analytics.record_download({'url': 'https://youtu.be/aaaaaaaaaaa', 'status': 'error'})
    assert analytics.find_previous_download(['https://youtu.be/aaaaaaaaaaa'], 'aaaaaaaaaaa') is None


def test_download_warns_when_disk_is_low(client, tmp_dir):
    with patch('mellow.downloader.download_video'), patch('mellow.server._free_bytes_near', return_value=500 * 1024 ** 2):
        data = client.post('/api/download', json={'url': 'https://youtu.be/x', 'output_dir': tmp_dir}).get_json()
        assert jobs.manager.wait_idle(10)
    assert data['status'] == 'started' and '0.5 GB' in data['disk_warning']
    with patch('mellow.downloader.download_video'), patch('mellow.server._free_bytes_near', return_value=50 * 1024 ** 3):
        data = client.post('/api/download', json={'url': 'https://youtu.be/x', 'output_dir': tmp_dir}).get_json()
        assert jobs.manager.wait_idle(10)
    assert 'disk_warning' not in data


def test_nothing_saved_writes_no_history_row(tmp_dir):
    """An up-to-date sync (the archive already has the video) saves nothing.
    It recorded a "success" row without a file, which inflated the stats and
    made "already downloaded" say the file was moved."""
    from unittest.mock import MagicMock

    from mellow import analytics, downloader
    ydl = MagicMock()
    ydl.extract_info.return_value = {'title': 'T', 'id': 'abc'}  # no requested_downloads
    ydl._download_retcode = 0
    cls = MagicMock()
    cls.return_value.__enter__.return_value = ydl
    events = []
    with patch('mellow.downloader.yt_dlp.YoutubeDL', cls), patch('mellow.downloader.find_ffmpeg', return_value=None):
        assert downloader.download_video('https://youtu.be/abc', tmp_dir, {'mode': 'library'},
                                         events.append) == 'success'
    assert events[-1]['status'] == 'complete'
    assert analytics.get_history(10) == []


def test_fileless_success_rows_do_not_count_as_already_downloaded(tmp_dir):
    from mellow import analytics
    f = Path(tmp_dir) / 'Song.mp3'
    f.write_bytes(b'x')
    url = 'https://youtu.be/bbbbbbbbbbb'
    analytics.record_download({'url': url, 'status': 'success', 'file_path': str(f)})
    analytics.record_download({'url': url, 'status': 'success', 'file_path': None})  # older builds
    prev = analytics.find_previous_download([url], 'bbbbbbbbbbb')
    assert prev['file_path'] == str(f) and prev['exists'] is True


def _cookie_file(tmp_dir, lines):
    p = Path(tmp_dir) / 'cookies.txt'
    p.write_text('# Netscape HTTP Cookie File\n' + ''.join(
        f'{domain}\tTRUE\t/\tTRUE\t2147483647\t{name}\tv\n' for domain, name in lines))
    return str(p)


def test_cookie_test_reads_a_cookies_txt(client, tmp_dir):
    path = _cookie_file(tmp_dir, [('.youtube.com', 'SID'), ('.youtube.com', 'PREF'), ('.example.com', 'a')])
    r = client.post('/api/cookies/test', json={'cookies_browser': 'none', 'cookies_file': path})
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'count': 3, 'youtube': 2, 'youtube_signed_in': True,
                            'undecryptable': 0}


def test_cookie_test_explains_a_missing_browser(client, tmp_dir):
    # A machine without Firefox: its profile folder search finds nothing
    with patch('yt_dlp.cookies._firefox_browser_dirs', return_value=[tmp_dir]):
        r = client.post('/api/cookies/test', json={'cookies_browser': 'firefox'})
    data = r.get_json()
    assert r.status_code == 400
    assert 'could not find firefox cookies database' in data['error']
    assert data['code'] == 'cookies_not_found' and data['hint']


def test_cookie_test_without_a_source_or_with_a_missing_file(client, tmp_dir):
    r = client.post('/api/cookies/test', json={'cookies_browser': 'none', 'cookies_file': ''})
    assert r.status_code == 400 and 'No cookie source' in r.get_json()['error']
    r = client.post('/api/cookies/test', json={'cookies_file': str(Path(tmp_dir) / 'nope.txt')})
    assert r.status_code == 400 and 'not found' in r.get_json()['error']


@pytest.mark.parametrize('raw,code', [
    ('ERROR: Could not copy Chrome cookie database. See  https://github.com/yt-dlp/yt-dlp/issues/7271', 'cookies_locked'),
    ('failed to load cookies — could not find chrome cookies database in "/x"', 'cookies_not_found'),
    ('Extracted 12 cookies from edge (40 could not be decrypted)', 'cookies_encrypted'),
    ('ERROR: failed to load cookies', 'cookies'),
])
def test_cookie_errors_are_explained(raw, code):
    assert errors.explain(raw)['code'] == code


@pytest.mark.parametrize('template,ok,shown', [
    ('', True, 'Never Gonna Give You Up (Official Video).mp4'),
    ('%(uploader)s/%(playlist_index)03d - %(title)s.%(ext)s', True, '003 - Never Gonna'),
    ('%(title)s', False, 'must end with .%(ext)s'),
    ('/music/%(title)s.%(ext)s', False, 'relative to the download folder'),
    ('%(title.%(ext)s', False, 'Invalid template'),
])
def test_filename_template_preview(client, template, ok, shown):
    r = client.post('/api/filename-preview', json={'template': template})
    data = r.get_json()
    assert data['ok'] is ok and r.status_code == (200 if ok else 400)
    assert shown in (data.get('example') or data.get('error'))


def test_layout_defaults_to_classic_and_a_switch_is_saved(client):
    assert client.get('/api/config').get_json()['ui_layout'] == 'classic'
    assert client.post('/api/config', json={'ui_layout': 'studio'}).status_code == 200
    from mellow import config
    assert config.load_config()['ui_layout'] == 'studio'
    # RESET DEFAULTS puts the layout back too
    assert client.post('/api/config/reset', json={}).get_json()['ui_layout'] == 'classic'


def test_studio_stylesheet_is_scoped_to_the_studio_layout():
    # Every Studio rule must leave Classic alone
    import re
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / 'gui' / 'studio.css').read_text(encoding='utf-8')
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'@import url\([^)]*\);', '', css)
    css = re.sub(r'@keyframes[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}', '', css)
    css = re.sub(r'@media[^{]*\{', '', css)
    selectors = [s.strip() for block in re.findall(r'([^{}]+)\{[^}]*\}', css) for s in block.split(',')]
    selectors = [s for s in selectors if s]
    assert selectors
    unscoped = [s for s in selectors if not s.startswith(':root[data-layout="studio"]')]
    assert unscoped == []
