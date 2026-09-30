"""Regression tests for failure handling: every download must end in a
terminal event, a missing ffmpeg must degrade instead of failing, and one
job's cancel/pause must not leak into another."""
import io
import json
import threading
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mellow import downloader, ffmpeg_locate, jobs, scheduler, ytdlp_update

TERMINAL = ('complete', 'error', 'cancelled')
DEFAULT_INFO = {'title': 'T', 'id': 'abc'}


def _fake_ydl(info, retcode=0):
    """Patch target standing in for yt_dlp.YoutubeDL; records the opts it got."""
    ydl = MagicMock()
    ydl.extract_info.return_value = info
    ydl._download_retcode = retcode
    cls = MagicMock()
    cls.return_value.__enter__.return_value = ydl
    return cls


def _run(tmp_dir, opts, info=DEFAULT_INFO, retcode=0, ffmpeg='/usr/bin/ffmpeg',
         url='https://youtu.be/abc'):
    events = []
    ydl_cls = _fake_ydl(info, retcode)
    with patch('mellow.downloader.yt_dlp.YoutubeDL', ydl_cls), \
            patch('mellow.downloader.find_ffmpeg', return_value=ffmpeg):
        result = downloader.download_video(url, tmp_dir, opts, events.append)
    ydl_opts = ydl_cls.call_args[0][0] if ydl_cls.call_args else None
    return result, events, ydl_opts


def _statuses(events):
    return [e['status'] for e in events]


# ── ffmpeg present / missing ───────────────────────────────────────────────────

def test_video_with_ffmpeg_merges_best_streams(tmp_dir):
    result, events, ydl_opts = _run(tmp_dir, {'mode': 'video', 'quality': '1080p'})
    assert result == 'success'
    assert ydl_opts['format'] == downloader.QUALITY_MAP['1080p']
    assert ydl_opts['merge_output_format'] == 'mp4'
    assert ydl_opts['ffmpeg_location'] == '/usr/bin/ffmpeg'
    assert 'warning' not in _statuses(events)


def test_video_without_ffmpeg_falls_back_to_single_file(tmp_dir):
    result, events, ydl_opts = _run(
        tmp_dir, {'mode': 'video', 'quality': '1080p', 'embed_thumbnail': True,
                  'embed_metadata': True, 'embed_subs': True}, ffmpeg=None)
    assert result == 'success'
    # Nothing that needs merging or an ffmpeg postprocessor may be requested
    assert ydl_opts['format'] == 'best[height<=1080]/best'
    assert '+' not in ydl_opts['format']
    assert ydl_opts['postprocessors'] == []
    assert 'merge_output_format' not in ydl_opts
    warnings = [e for e in events if e['status'] == 'warning']
    assert len(warnings) == 1 and warnings[0]['code'] == 'ffmpeg_missing'
    complete = next(e for e in events if e['status'] == 'complete')
    assert complete['warning'] == warnings[0]['message']


def test_audio_without_ffmpeg_keeps_native_format(tmp_dir):
    result, events, ydl_opts = _run(
        tmp_dir, {'mode': 'audio', 'audio_format': 'mp3', 'embed_thumbnail': True}, ffmpeg=None)
    assert result == 'success'
    assert ydl_opts['format'] == downloader.NO_FFMPEG_AUDIO_FORMAT
    assert ydl_opts['postprocessors'] == []
    assert 'MP3' in next(e for e in events if e['status'] == 'warning')['message']


def test_audio_with_ffmpeg_converts(tmp_dir):
    _, _, ydl_opts = _run(tmp_dir, {'mode': 'audio', 'audio_format': 'flac'})
    assert ydl_opts['postprocessors'][0] == {
        'key': 'FFmpegExtractAudio', 'preferredcodec': 'flac', 'preferredquality': '0'}


def test_video_failure_without_ffmpeg_points_at_ffmpeg(tmp_dir):
    events = []
    ydl_cls = _fake_ydl(None)
    ydl_cls.return_value.__enter__.return_value.extract_info.side_effect =         downloader.yt_dlp.utils.DownloadError('Requested format is not available')
    with patch('mellow.downloader.yt_dlp.YoutubeDL', ydl_cls),             patch('mellow.downloader.find_ffmpeg', return_value=None):
        result = downloader.download_video('https://youtu.be/abc', tmp_dir, {}, events.append)
    assert result == 'error'
    assert events[-1]['code'] == 'ffmpeg_missing'
    assert 'winget install Gyan.FFmpeg' in events[-1]['message']


def test_history_records_the_file_that_was_actually_saved(tmp_dir):
    """Asked for MP3 but, without ffmpeg, an .m4a landed on disk."""
    from mellow import analytics
    saved = Path(tmp_dir) / 'Song.m4a'
    saved.write_bytes(b'x' * 10)
    info = {'title': 'Song', 'id': 'abc', 'requested_downloads': [{'filepath': str(saved)}]}
    _run(tmp_dir, {'mode': 'audio', 'audio_format': 'mp3'}, info=info, ffmpeg=None)
    row = analytics.get_history()[0]
    assert (row['format'], row['container'], row['file_size_bytes']) == ('audio', 'm4a', 10)


def test_audio_library_sync_is_recorded_as_audio(tmp_dir):
    from mellow import analytics
    saved = Path(tmp_dir) / 'T.opus'
    saved.write_bytes(b'x')
    _run(tmp_dir, {'mode': 'library', 'sync_audio': True, 'audio_format': 'opus'},
         info={**DEFAULT_INFO, 'requested_downloads': [{'filepath': str(saved)}]})
    row = analytics.get_history()[0]
    assert (row['format'], row['container']) == ('audio', 'opus')


def test_trim_without_ffmpeg_is_a_clear_error(tmp_dir):
    result, events, _ = _run(tmp_dir, {'start_time': '0:10', 'end_time': '0:20'}, ffmpeg=None)
    assert result == 'error'
    assert 'ffmpeg' in events[-1]['message']


def test_single_file_format_tiers():
    assert downloader._single_file_format('720p') == 'best[height<=720]/best'
    assert downloader._single_file_format('best') == 'best'
    assert downloader._single_file_format('nonsense') == 'best'


def test_find_ffmpeg_honours_config_override(tmp_path):
    fake = tmp_path / ffmpeg_locate._EXE
    fake.write_bytes(b'')
    with patch('mellow.ffmpeg_locate.load_config', return_value={'ffmpeg_location': str(tmp_path)}):
        assert ffmpeg_locate.find_ffmpeg(refresh=True) == str(fake)


def test_find_ffmpeg_miss_is_cached_then_rechecked(tmp_path):
    with patch('mellow.ffmpeg_locate._search', return_value=None) as search:
        assert ffmpeg_locate.find_ffmpeg(refresh=True) is None
        assert ffmpeg_locate.find_ffmpeg() is None
        assert search.call_count == 1, "a miss must not hit the disk on every call"
        with patch('mellow.ffmpeg_locate.FFMPEG_RECHECK_SECS', 0):
            ffmpeg_locate.find_ffmpeg()
        assert search.call_count == 2, "a miss must be re-probed after the recheck interval"


def test_system_endpoint_reports_ffmpeg(client):
    with patch('mellow.server.find_ffmpeg', return_value=None):
        assert client.get('/api/system').get_json()['ffmpeg'] is False
    with patch('mellow.server.find_ffmpeg', return_value='/x/ffmpeg'):
        data = client.get('/api/system').get_json()
        assert data['ffmpeg'] is True and data['ffmpeg_path'] == '/x/ffmpeg'


# ── every download ends in a terminal event ────────────────────────────────────

def test_null_options_from_client_do_not_crash(tmp_dir):
    opts = {k: None for k in (
        'mode', 'quality', 'container', 'audio_format', 'custom_format', 'start_time',
        'end_time', 'cookies_browser', 'cookies_file', 'cookies_browser_profile', 'proxy',
        'sub_langs', 'playlist_start', 'playlist_end', 'playlist_items', 'date_before',
        'date_after', 'filename_template', 'rate_limit', 'concurrent_fragments', 'retries')}
    result, events, ydl_opts = _run(tmp_dir, opts)
    assert result == 'success'
    assert ydl_opts['format'] == downloader.QUALITY_MAP['best']
    assert _statuses(events)[-1] == 'complete'


def test_unwritable_output_folder_reports_error(tmp_path):
    blocker = tmp_path / 'not_a_folder'
    blocker.write_text('x')
    events = []
    result = downloader.download_video(
        'https://youtu.be/abc', str(blocker / 'sub'), {}, events.append)
    assert result == 'error'
    assert events[-1]['status'] == 'error' and events[-1]['url'] == 'https://youtu.be/abc'


def test_dead_playlist_is_an_error_not_a_success(tmp_dir):
    """ignoreerrors makes yt-dlp return None for a dead playlist; that used to
    be reported as 'complete' and recorded as a successful download."""
    from mellow import analytics
    url = 'https://www.youtube.com/playlist?list=PLdead'
    events = []
    ydl_cls = _fake_ydl(None, retcode=1)

    def _extract(*args, **kwargs):
        ydl_cls.call_args[0][0]['logger'].error('ERROR: The playlist does not exist.')
        return None
    ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = _extract

    with patch('mellow.downloader.yt_dlp.YoutubeDL', ydl_cls), \
            patch('mellow.downloader.find_ffmpeg', return_value='/usr/bin/ffmpeg'):
        result = downloader.download_video(url, tmp_dir, {'mode': 'library'}, events.append)

    assert result == 'error'
    assert 'complete' not in _statuses(events)
    assert 'does not exist' in events[-1]['message']
    assert [h['status'] for h in analytics.get_history()] == ['error']


def test_archive_skip_is_still_a_success(tmp_dir):
    """A single video already in the archive also returns None, without error."""
    result, events, _ = _run(tmp_dir, {'mode': 'library'}, info=None, retcode=0)
    assert result == 'success'
    assert _statuses(events)[-1] == 'complete'


def _run_playlist(tmp_dir, entries, finished_ids, errors=()):
    """Fake a playlist run: `finished_ids` reach the progress hook as finished
    files, `errors` are logged the way yt-dlp does under ignoreerrors."""
    url = 'https://www.youtube.com/playlist?list=PLx'
    info = {'_type': 'playlist', 'title': 'PL', 'entries': entries}
    ydl_cls = _fake_ydl(info, retcode=1 if errors else 0)

    def _extract(*args, **kwargs):
        ydl_opts = ydl_cls.call_args[0][0]
        for vid in finished_ids:
            ydl_opts['progress_hooks'][0]({
                'status': 'finished', 'filename': f'{vid}.mp3', 'info_dict': {'id': vid}})
        for msg in errors:
            ydl_opts['logger'].error(msg)
        return info
    ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = _extract

    events = []
    with patch('mellow.downloader.yt_dlp.YoutubeDL', ydl_cls), \
            patch('mellow.downloader.find_ffmpeg', return_value='/usr/bin/ffmpeg'):
        result = downloader.download_video(url, tmp_dir, {'mode': 'audio'}, events.append)
    return result, events


def test_playlist_where_every_item_fails_is_an_error(tmp_dir):
    """e.g. an outdated yt-dlp: every item extracts, every download gets a 403."""
    from mellow import analytics
    entries = [{'id': i, 'title': i, 'requested_downloads': [{'filepath': f'{tmp_dir}/{i}.mp3'}]}
               for i in ('a', 'b')]
    result, events = _run_playlist(
        tmp_dir, entries, finished_ids=[],
        errors=['ERROR: unable to download video data: HTTP Error 403: Forbidden'])
    assert result == 'error'
    assert 'complete' not in _statuses(events)
    assert 'HTTP Error 403' in events[-1]['message']
    assert [h['status'] for h in analytics.get_history()] == ['error']


def test_partly_failed_playlist_completes_and_records_only_real_files(tmp_dir):
    from mellow import analytics
    ok = Path(tmp_dir) / 'a.mp3'
    ok.write_bytes(b'x' * 7)
    entries = [
        {'id': 'a', 'title': 'A', 'requested_downloads': [{'filepath': str(ok)}]},
        # extracted, but its download failed: planned path, no file on disk
        {'id': 'b', 'title': 'B', 'thumbnail': 'http://x/b.jpg',
         'requested_downloads': [{'filepath': str(Path(tmp_dir) / 'b.mp3')}]},
        None,  # skipped by the archive
    ]
    with patch('mellow.downloader._save_thumbnail_sidecar') as sidecar:
        result, events = _run_playlist(tmp_dir, entries, finished_ids=['a'],
                                       errors=['ERROR: [youtube] b: Video unavailable'])
    assert result == 'success'
    assert _statuses(events)[-1] == 'complete'
    assert [(h['title'], h['status'], h['file_size_bytes']) for h in analytics.get_history()] \
        == [('A', 'success', 7)]
    # No orphan .jpg for the item that never arrived
    assert not any('b.mp3' in str(call) for call in sidecar.call_args_list)


# ── yt-dlp self-update reports what actually happened ──────────────────────────

def _run_update(client, *, frozen, version_after):
    import yt_dlp
    events = []
    done = threading.Event()

    def push(event):
        events.append(event)
        done.set()

    def fake_reload(module):
        if module is yt_dlp.version:
            module.__version__ = version_after
        return module

    with patch.object(yt_dlp.version, '__version__', '2026.06.09'), \
            patch('mellow.server._push_progress', side_effect=push), \
            patch('mellow.ytdlp_update.subprocess.run'), \
            patch('importlib.reload', side_effect=fake_reload), \
            patch.object(ytdlp_update.sys, 'frozen', frozen, create=True), \
            patch('shutil.which', return_value='/usr/bin/yt-dlp'):
        assert client.post('/api/update-ytdlp', json={}).status_code == 200
        assert done.wait(10)
    return events[-1]


def test_update_asks_for_restart_when_a_newer_ytdlp_was_installed(client):
    event = _run_update(client, frozen=False, version_after='2026.09.27')
    assert event['ok'] is True and event['restart_required'] is True
    assert '2026.09.27' in event['message'] and 'Restart' in event['message']


def test_update_in_packaged_app_does_not_claim_success(client):
    """The frozen app imports the yt-dlp inside the .exe; nothing replaces it."""
    event = _run_update(client, frozen=True, version_after='2026.06.09')
    assert event['ok'] is False
    assert 'bundles yt-dlp 2026.06.09' in event['error']


def test_update_when_already_current(client):
    event = _run_update(client, frozen=False, version_after='2026.06.09')
    assert event['ok'] is True and 'restart_required' not in event
    assert 'up to date' in event['message']


def test_worker_pushes_error_when_job_crashes(tmp_dir):
    events = []
    done = threading.Event()

    def push(event):
        events.append(event)
        if event.get('status') in TERMINAL:
            done.set()

    with patch('mellow.downloader.download_video', side_effect=RuntimeError('boom')):
        m = jobs.JobManager()
        m.start(push)
        job = m.enqueue('https://youtu.be/a', tmp_dir, {})
        assert done.wait(10), "UI never received a terminal event for the crashed job"
        assert m.wait_idle(10)
    assert events[-1]['status'] == 'error'
    assert events[-1]['message'] == 'boom'
    assert events[-1]['job_id'] == job['id']
    assert job['status'] == 'failed'


# ── cancel / pause isolation between jobs ──────────────────────────────────────

def test_cancelling_one_active_job_leaves_the_other_running(client, tmp_dir):
    release = threading.Event()
    started = threading.Semaphore(0)

    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        started.release()
        release.wait(10)
        return 'cancelled' if cancel_event.is_set() else 'success'

    with patch('mellow.downloader.download_video', side_effect=fake_dl), \
            patch('mellow.jobs.load_config', return_value={'download_workers': 2}):
        first = jobs.manager.enqueue('https://youtu.be/first', tmp_dir, {})
        assert started.acquire(timeout=10)
        second = jobs.manager.enqueue('https://youtu.be/second', tmp_dir, {})
        assert started.acquire(timeout=10)

        r = client.post(f"/api/queue/{first['id']}/cancel", json={})
        assert r.get_json()['status'] == 'cancelling'
        assert first['cancel_event'].is_set()
        assert not second['cancel_event'].is_set(), "cancelling one job cancelled another"

        release.set()
        assert jobs.manager.wait_idle(10)
    assert first['status'] == 'cancelled'
    assert second['status'] == 'complete'


def test_pause_survives_another_job_finishing_but_not_an_idle_queue(tmp_dir):
    gates = {'a': threading.Event(), 'b': threading.Event()}
    started = threading.Semaphore(0)

    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        assert pause_event is downloader._pause_event
        started.release()
        gates[url[-1]].wait(10)
        return 'success'

    with patch('mellow.downloader.download_video', side_effect=fake_dl), \
            patch('mellow.jobs.load_config', return_value={'download_workers': 2}):
        m = jobs.JobManager()
        m.start(lambda e: None)
        m.enqueue('https://youtu.be/a', tmp_dir, {})
        m.enqueue('https://youtu.be/b', tmp_dir, {})
        assert started.acquire(timeout=10) and started.acquire(timeout=10)

        downloader.pause()
        gates['a'].set()
        # Wait for job a to be fully finished (active count back to 1)
        for _ in range(100):
            if m.status()['active'] == 1:
                break
            threading.Event().wait(0.05)
        assert downloader._pause_event.is_set(), "a finishing job un-paused the other download"

        gates['b'].set()
        assert m.wait_idle(10)
        assert not downloader._pause_event.is_set(), "pause leaked past the end of the queue"

        # A pause set while idle must not freeze the next job either
        downloader.pause()
        gates['a'].clear()
        m.enqueue('https://youtu.be/a', tmp_dir, {})
        assert started.acquire(timeout=10)
        assert not downloader._pause_event.is_set()
        gates['a'].set()
        assert m.wait_idle(10)


def test_pause_is_a_noop_when_nothing_is_downloading(client):
    r = client.post('/api/download/pause', json={})
    assert r.get_json()['status'] == 'idle'
    assert not downloader._pause_event.is_set()


# ── scheduler ──────────────────────────────────────────────────────────────────

def test_failed_auto_sync_is_not_requeued_every_tick():
    cfg = {
        'auto_sync_enabled': True,
        'vault_playlists': {'/folder/a': ['https://pl']},
        'vault_sync_times': {},  # never completes, so the folder stays due
    }
    queued = []

    def sync(path):
        queued.append(path)
        return True

    with patch('mellow.scheduler.load_config', return_value=cfg):
        assert scheduler.tick(sync, lambda p: False, now=1000.0) == ['/folder/a']
        assert scheduler.tick(sync, lambda p: False, now=1300.0) == []
        later = 1000.0 + scheduler.SYNC_RETRY_BACKOFF_SECS
        assert scheduler.tick(sync, lambda p: False, now=later) == ['/folder/a']
    assert queued == ['/folder/a', '/folder/a']


def test_tick_skips_folder_already_syncing():
    cfg = {'auto_sync_enabled': True, 'vault_playlists': {'/folder/a': ['https://pl']}}
    with patch('mellow.scheduler.load_config', return_value=cfg):
        assert scheduler.tick(lambda p: pytest.fail('queued twice'), lambda p: True, now=1.0) == []


# ── config ─────────────────────────────────────────────────────────────────────

def test_old_config_file_gains_new_default_keys(isolated_user_files):
    from mellow import config
    config.CONFIG_PATH.write_text(json.dumps({'output_dir': 'X', 'sleep_interval': 1}),
                                  encoding='utf-8')
    cfg = config.load_config()
    assert cfg['output_dir'] == 'X' and cfg['sleep_interval'] == 1
    assert cfg['download_workers'] == 1
    assert cfg['default_quality'] == '1080p'


def test_config_defaults_are_not_shared_between_loads():
    from mellow import config
    config.load_config()['vault_budgets']['/x'] = 5
    assert config.load_config()['vault_budgets'] == {}


def test_config_with_non_object_root_falls_back_to_defaults(isolated_user_files):
    from mellow import config
    config.CONFIG_PATH.write_text('[1, 2, 3]', encoding='utf-8')
    assert config.load_config()['retries'] == 3
    assert config.CONFIG_PATH.with_suffix('.json.corrupt').exists()


# ── backup with the database open (the normal state of a running app) ──────────

def test_backup_and_restore_while_db_is_open(client):
    from mellow import analytics
    analytics.record_download({'url': 'u1', 'title': 'kept', 'status': 'success'})

    r = client.get('/api/backup')
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert 'mellow_dlp.duckdb' in names

    analytics.record_download({'url': 'u2', 'title': 'added after backup', 'status': 'success'})
    assert len(analytics.get_history()) == 2

    r2 = client.post('/api/backup/restore', data={'file': (io.BytesIO(r.data), 'b.zip')},
                     content_type='multipart/form-data')
    assert r2.status_code == 200, r2.get_json()
    assert [h['title'] for h in analytics.get_history()] == ['kept']


def test_sync_with_one_failed_item_and_the_rest_archived_is_not_a_failure(tmp_dir):
    """A playlist where one video went private: every later sync saw errors
    and no new file, and was reported (and retried) as a dead playlist."""
    def fake_extract(url, download=True):
        logger = ydl_cls.call_args[0][0]['logger']
        logger.debug('[download] aaaaaaaaaaa: Song A has already been recorded in the archive')
        logger.error('ERROR: [youtube] bbbbbbbbbbb: Private video')
        return {'_type': 'playlist', 'title': 'Mix', 'entries': []}

    ydl_cls = _fake_ydl({}, retcode=1)
    ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = fake_extract
    events = []
    with patch('mellow.downloader.yt_dlp.YoutubeDL', ydl_cls), \
            patch('mellow.downloader.find_ffmpeg', return_value='/usr/bin/ffmpeg'):
        result = downloader.download_video('https://youtube.com/playlist?list=P', tmp_dir,
                                           {'mode': 'library'}, events.append)
    assert result == 'success'
    assert [e['status'] for e in events if e['status'] in TERMINAL] == ['complete']
    assert [e['status'] for e in events].count('item_failed') == 1


def test_playlist_where_everything_failed_is_still_a_failure(tmp_dir):
    result, events, _ = _run(tmp_dir, {'mode': 'library'}, retcode=1)
    assert result == 'error'
