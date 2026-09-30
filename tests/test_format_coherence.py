"""What the user picks must be what gets downloaded, wherever the download
starts from: the Feed, a vault link, a vault sync, auto-sync or "sync all"."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import downloader
import jobs
import server
import vault


def _post_download(client, tmp_dir, **payload):
    with patch('downloader.download_video') as dl:
        r = client.post('/api/download', json={'url': 'https://youtu.be/x', 'output_dir': tmp_dir, **payload})
        assert r.status_code == 200
        assert jobs.manager.wait_idle(10)
    return dl.call_args[0][2]


def test_feed_audio_download_into_a_vault_stays_audio(client, tmp_dir):
    """The Feed's vault link downloads in library mode; sync_audio used to be
    dropped by /api/download, so an MP3 choice arrived as video."""
    opts = _post_download(client, tmp_dir, mode='library', sync_audio=True,
                          audio_format='flac', audio_quality='192')
    assert opts['mode'] == 'library'
    assert opts['sync_audio'] is True
    assert opts['audio_format'] == 'flac'
    assert opts['audio_quality'] == '192'


def test_audio_quality_defaults_to_config(client, tmp_dir):
    config.update_config(lambda c: c.__setitem__('default_audio_quality', '128'))
    assert _post_download(client, tmp_dir, mode='audio')['audio_quality'] == '128'


def _ydl_opts(tmp_dir, opts):
    ydl = MagicMock()
    ydl.extract_info.return_value = {'title': 'T', 'id': 'abc'}
    ydl._download_retcode = 0
    cls = MagicMock()
    cls.return_value.__enter__.return_value = ydl
    with patch('downloader.yt_dlp.YoutubeDL', cls), \
            patch('downloader.find_ffmpeg', return_value='/usr/bin/ffmpeg'):
        assert downloader.download_video('https://youtu.be/abc', tmp_dir, opts, lambda e: None) == 'success'
    return cls.call_args[0][0]


def test_audio_bitrate_reaches_the_converter(tmp_dir):
    for choice, expected in (('best', '0'), ('320', '320'), ('128', '128'), ('bogus', '0')):
        pps = _ydl_opts(tmp_dir, {'mode': 'audio', 'audio_format': 'mp3', 'audio_quality': choice})['postprocessors']
        assert pps[0]['key'] == 'FFmpegExtractAudio'
        assert pps[0]['preferredquality'] == expected, choice


def test_audio_library_sync_does_not_write_subtitles(tmp_dir):
    ydl_opts = _ydl_opts(tmp_dir, {'mode': 'library', 'sync_audio': True, 'embed_subs': True})
    assert 'writesubtitles' not in ydl_opts
    assert not any(p['key'] == 'FFmpegEmbedSubtitle' for p in ydl_opts['postprocessors'])


# ── vault folders remember and infer their format ─────────────────────────────

def _touch(folder, *names):
    for n in names:
        (Path(folder) / n).write_bytes(b'x')


def test_infer_format_from_folder_contents(tmp_dir):
    assert vault.infer_folder_format(tmp_dir) == {}
    _touch(tmp_dir, 'a.flac', 'b.flac', 'c.mp3', 'd.mp4', 'cover.jpg')
    assert vault.infer_folder_format(tmp_dir) == {'sync_audio': True, 'audio_format': 'flac'}


def test_infer_video_folder(tmp_dir):
    _touch(tmp_dir, 'a.mkv', 'b.mkv', 'c.m4a')
    assert vault.infer_folder_format(tmp_dir) == {'sync_audio': False, 'container': 'mkv'}


def test_sync_without_a_dialog_follows_the_folder_not_1080p_video(tmp_dir):
    """Auto-sync and "sync all" send no options. An MP3 folder with no library
    entry used to be synced as 1080p mp4 video."""
    _touch(tmp_dir, 'a.mp3', 'b.mp3')
    opts = vault.build_sync_opts({}, None, config.load_config(), tmp_dir)
    assert opts['sync_audio'] is True and opts['audio_format'] == 'mp3'


def test_precedence_request_then_saved_then_library(tmp_dir):
    lib = {'mode': 'VIDEO', 'quality': '720p', 'container': 'mkv', 'audio_format': 'mp3'}
    cfg = {'vault_sync_formats': {tmp_dir: {'sync_audio': True, 'audio_format': 'opus'}}}
    opts = vault.build_sync_opts({}, lib, cfg, tmp_dir)
    assert (opts['sync_audio'], opts['audio_format']) == (True, 'opus')
    opts = vault.build_sync_opts({'sync_audio': False, 'quality': '4k'}, lib, cfg, tmp_dir)
    assert (opts['sync_audio'], opts['quality']) == (False, '4k')
    opts = vault.build_sync_opts({}, lib, {}, tmp_dir)
    assert (opts['sync_audio'], opts['quality'], opts['container']) == (False, '720p', 'mkv')


def test_dialog_choice_is_remembered_for_auto_sync(client, tmp_dir):
    url = 'https://youtube.com/playlist?list=PLx'
    client.post('/api/vault/playlists', json={'path': tmp_dir, 'url': url})
    with patch('downloader.download_video') as dl:
        client.post('/api/vault/sync', json={'path': tmp_dir, 'sync_audio': True, 'audio_format': 'm4a'})
        assert jobs.manager.wait_idle(10)
        # Later, auto-sync / sync-all: no options in the request
        assert server._enqueue_vault_sync(tmp_dir) is not None
        assert jobs.manager.wait_idle(10)
    last_opts = dl.call_args[0][2]
    assert (last_opts['sync_audio'], last_opts['audio_format']) == (True, 'm4a')
    fmt = client.get('/api/vault/playlists?path=' + tmp_dir).get_json()['sync_format']
    assert fmt['sync_audio'] is True and fmt['audio_format'] == 'm4a'


def test_linking_from_the_feed_saves_the_format(client, tmp_dir):
    r = client.post('/api/vault/playlists', json={
        'path': tmp_dir, 'url': 'https://youtube.com/playlist?list=PLy',
        'sync_format': {'sync_audio': True, 'audio_format': 'opus', 'not_a_format_key': 1}})
    assert r.status_code == 200
    saved = config.load_config()['vault_sync_formats'][tmp_dir]
    assert saved == {'sync_audio': True, 'audio_format': 'opus'}


def test_library_entry_without_folder_gets_its_own_subfolder(client, tmp_dir):
    """An empty folder used to hide the entry from the Vault and send its
    syncs loose into the download folder."""
    config.update_config(lambda c: c.__setitem__('output_dir', tmp_dir))
    url = 'https://youtube.com/playlist?list=PLz'
    entry = client.post('/api/library', json={'name': 'Mix', 'url': url, 'folder': '',
                                               'folder_name': 'Mix', 'use_subfolder': False}).get_json()
    assert entry['folder'] == tmp_dir and entry['use_subfolder'] is True
    assert entry['folder_path'] == str(Path(tmp_dir) / 'Mix')
    assert url in config.load_config()['vault_playlists'][entry['folder_path']]


def test_library_entry_with_a_picked_folder_uses_it_as_is(client, tmp_dir):
    entry = client.post('/api/library', json={'name': 'Mix', 'url': 'https://pl', 'folder': tmp_dir,
                                               'folder_name': 'Mix', 'use_subfolder': False}).get_json()
    assert entry['folder_path'] == tmp_dir


# ── thumbnails ─────────────────────────────────────────────────────────────────

def test_dotted_title_finds_its_own_sidecar(tmp_dir):
    """"Episode.10.mp4" pairs with "Episode.10.jpg", never with "Episode.jpg"."""
    _touch(tmp_dir, 'Episode.10.mp4')
    (Path(tmp_dir) / 'Episode.10.jpg').write_bytes(b'right')
    (Path(tmp_dir) / 'Episode.jpg').write_bytes(b'wrong')
    assert vault.get_thumb_bytes(os.path.join(tmp_dir, 'Episode.10.mp4')) == (b'right', 'image/jpeg')


def test_missing_cover_is_not_retried_on_every_request(tmp_dir):
    _touch(tmp_dir, 'song.mp3')
    song = os.path.join(tmp_dir, 'song.mp3')
    failed = MagicMock(returncode=1)
    with patch('vault.find_ffmpeg', return_value='/usr/bin/ffmpeg'), \
            patch('vault.subprocess.run', return_value=failed) as run:
        assert vault.get_thumb_bytes(song) is None
        assert vault.get_thumb_bytes(song) is None
    assert run.call_count == 1
    # The audio path asks ffmpeg for the embedded cover (first video stream)
    assert '0:v:0' in run.call_args[0][0]


# ── network settings reach every yt-dlp call ───────────────────────────────────

def test_analyze_uses_proxy_and_force_ipv4(client):
    config.update_config(lambda c: c.update(proxy='socks5://127.0.0.1:9', force_ipv4=True))
    with patch('downloader.yt_dlp.YoutubeDL') as ydl_cls:
        ydl_cls.return_value.__enter__.return_value.extract_info.return_value = {'title': 'T'}
        client.post('/api/info', json={'url': 'https://youtu.be/x'})
        client.post('/api/playlist-items', json={'url': 'https://youtube.com/playlist?list=P'})
    for call in ydl_cls.call_args_list:
        opts = call[0][0]
        assert opts['proxy'] == 'socks5://127.0.0.1:9'
        assert opts['source_address'] == '0.0.0.0'
        assert opts['socket_timeout'] > 0
    assert ydl_cls.call_count == 2


def test_download_honours_force_ipv4(tmp_dir):
    assert _ydl_opts(tmp_dir, {'force_ipv4': True})['source_address'] == '0.0.0.0'
    assert 'source_address' not in _ydl_opts(tmp_dir, {})


# ── mirror sync ────────────────────────────────────────────────────────────────

def _mirror(folder, playlists):
    """playlists: url -> list of ids, or an Exception to raise."""
    def fake_cls(opts):
        ydl = MagicMock()

        def extract(url, download=False):
            result = playlists[url]
            if isinstance(result, Exception):
                raise result
            return {'entries': [{'id': i} for i in result]}
        ydl.extract_info.side_effect = extract
        cm = MagicMock()
        cm.__enter__.return_value = ydl
        return cm
    with patch('yt_dlp.YoutubeDL', side_effect=fake_cls):
        return vault.get_mirror_preview(folder, list(playlists))


def test_mirror_deletes_nothing_when_a_playlist_failed_to_load(tmp_dir):
    _touch(tmp_dir, 'kept [aaaaaaaaaaa].mp3', 'other [bbbbbbbbbbb].mp3')
    ok = _mirror(tmp_dir, {'pl1': ['aaaaaaaaaaa']})
    assert [f['video_id'] for f in ok['to_delete']] == ['bbbbbbbbbbb']
    # pl2 held bbbbbbbbbbb but could not be read: it must not be deleted
    risky = _mirror(tmp_dir, {'pl1': ['aaaaaaaaaaa'], 'pl2': RuntimeError('HTTP 403')})
    assert risky['to_delete'] == [] and risky['fetch_errors'] == ['pl2']


def test_mirror_finds_files_named_without_an_id(tmp_dir):
    """Default names are just the title; the id comes from the history."""
    import analytics
    song = Path(tmp_dir) / 'Some Song.mp3'
    song.write_bytes(b'x')
    analytics.record_download({'url': 'https://www.youtube.com/watch?v=ccccccccccc',
                               'title': 'Some Song', 'status': 'success', 'file_path': str(song)})
    preview = _mirror(tmp_dir, {'pl1': ['aaaaaaaaaaa']})
    assert [f['name'] for f in preview['to_delete']] == ['Some Song.mp3']
    preview = _mirror(tmp_dir, {'pl1': ['ccccccccccc']})
    assert preview['to_delete'] == [] and preview['unchanged_count'] == 1
