"""The yt-dlp options built for cover art, trimming and the webm container.

Each of these was silently broken at some point: cover art was never embedded
(yt-dlp only embeds a thumbnail it wrote itself), trims crashed on the range
format, and webm asked for an m4a audio stream it cannot hold.
"""
import os
import threading
import time
from unittest.mock import MagicMock, patch

import downloader
import ffmpeg_locate

FFMPEG = '/usr/bin/ffmpeg'


def _opts_for(tmp_dir, opts, ffmpeg=FFMPEG):
    """Run download_video against a fake YoutubeDL; return (ydl_opts, ydl, events)."""
    ydl = MagicMock()
    ydl.extract_info.return_value = {'title': 'T', 'id': 'abc'}
    ydl._download_retcode = 0
    cls = MagicMock()
    cls.return_value.__enter__.return_value = ydl
    events = []
    with patch('downloader.yt_dlp.YoutubeDL', cls), \
            patch('downloader.find_ffmpeg', return_value=ffmpeg):
        assert downloader.download_video('https://youtu.be/abc', tmp_dir, opts, events.append) \
            == 'success', events
    return cls.call_args[0][0], ydl, events


# ── cover art ──────────────────────────────────────────────────────────────────

def test_embed_thumbnail_makes_ytdlp_write_and_keep_the_thumbnail(tmp_dir):
    ydl_opts, ydl, _ = _opts_for(tmp_dir, {'mode': 'audio', 'embed_thumbnail': True})
    assert ydl_opts['writethumbnail'] is True
    # No stray "<playlist name>.jpg" next to the items
    assert ydl_opts['outtmpl']['pl_thumbnail'] == ''
    assert ydl_opts['outtmpl']['default'].endswith('%(title)s.%(ext)s')
    assert {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg', 'when': 'before_dl'} \
        in ydl_opts['postprocessors']
    (pp,), kwargs = ydl.add_post_processor.call_args
    assert isinstance(pp, downloader._EmbedThumbnailBestEffort)
    assert pp._already_have_thumbnail is True, "the .jpg doubles as the vault sidecar"
    assert kwargs == {'when': 'post_process'}


def test_no_thumbnail_work_when_embedding_is_off_or_ffmpeg_is_missing(tmp_dir):
    for opts, ffmpeg in (({'embed_thumbnail': False}, FFMPEG), ({'embed_thumbnail': True}, None)):
        ydl_opts, ydl, _ = _opts_for(tmp_dir, opts, ffmpeg=ffmpeg)
        assert 'writethumbnail' not in ydl_opts
        assert isinstance(ydl_opts['outtmpl'], str)
        ydl.add_post_processor.assert_not_called()


def test_failed_embed_does_not_fail_the_download(tmp_path):
    media = tmp_path / 'Song.wav'
    media.write_bytes(b'x')
    leftover = tmp_path / 'Song.temp.wav'
    leftover.write_bytes(b'')
    pp = downloader._EmbedThumbnailBestEffort(None, already_have_thumbnail=True)
    info = {'filepath': str(media)}
    error = downloader.yt_dlp.utils.PostProcessingError('Supported filetypes ...')
    with patch.object(downloader.yt_dlp.postprocessor.EmbedThumbnailPP, 'run', side_effect=error), \
            patch.object(pp, 'report_warning') as warn:
        assert pp.run(info) == ([], info)
    warn.assert_called_once()
    assert media.exists() and not leftover.exists()


# ── trimming ───────────────────────────────────────────────────────────────────

def _ranges(ydl_opts, duration=100):
    return list(ydl_opts['download_ranges']({'duration': duration}, None))


def test_trim_range_is_usable_by_ytdlp(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'start_time': '0:05', 'end_time': '1:10'})
    assert _ranges(ydl_opts) == [{'start_time': 5.0, 'end_time': 70.0}]
    assert ydl_opts['force_keyframes_at_cuts'] is True


def test_trim_with_only_one_end_given(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'start_time': '12'})
    assert _ranges(ydl_opts) == [{'start_time': 12.0, 'end_time': float('inf')}]
    ydl_opts, _, _ = _opts_for(tmp_dir, {'end_time': '30'})
    assert _ranges(ydl_opts) == [{'start_time': 0, 'end_time': 30.0}]


# ── containers ─────────────────────────────────────────────────────────────────

def test_webm_asks_for_streams_webm_can_hold(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'quality': '720p', 'container': 'webm'})
    first_choice = ydl_opts['format'].split('/')[0]
    assert first_choice == 'bestvideo[height<=720][ext=webm]+bestaudio[ext=webm]'
    assert 'm4a' not in ydl_opts['format']
    # An impossible merge must land in mkv instead of failing in ffmpeg
    assert ydl_opts['merge_output_format'] == 'webm/mkv'


def test_other_containers_keep_the_quality_map(tmp_dir):
    for container in ('mp4', 'mkv'):
        ydl_opts, _, _ = _opts_for(tmp_dir, {'quality': '4k', 'container': container})
        assert ydl_opts['format'] == downloader.QUALITY_MAP['4k']
        assert ydl_opts['merge_output_format'] == container


def test_custom_format_wins_over_container_defaults(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'container': 'webm', 'custom_format': 'bv*+ba'})
    assert ydl_opts['format'] == 'bv*+ba'


# ── progress hook ──────────────────────────────────────────────────────────────

def test_merged_download_reports_item_done_once():
    """yt-dlp fires 'finished' per stream (video, then audio) of one item."""
    events = []
    now = time.monotonic()
    tracker = {'samples': [], 't0': now, 'item_t0': now, 'item_sample_start': 0, 'items': {}}
    hook = downloader._make_progress_hook(
        events.append, None, tracker, threading.Event(), threading.Event(), save_sidecar=False)
    for name in ('T.f137.mp4', 'T.f140.m4a'):
        hook({'status': 'finished', 'filename': name, 'info_dict': {'id': 'abc', 'title': 'T'}})
    hook({'status': 'finished', 'filename': 'U.f137.mp4', 'info_dict': {'id': 'xyz', 'title': 'U'}})
    assert [e['video_id'] for e in events if e['status'] == 'item_done'] == ['abc', 'xyz']
    assert [e['status'] for e in events].count('processing') == 3


def test_hook_leaves_the_thumbnail_to_ytdlp_when_embedding():
    now = time.monotonic()
    tracker = {'samples': [], 't0': now, 'item_t0': now, 'item_sample_start': 0, 'items': {}}
    finished = {'status': 'finished', 'filename': 'T.mp4',
                'info_dict': {'id': 'abc', 'thumbnail': 'http://x/t.jpg'}}
    with patch('downloader._save_thumbnail_sidecar') as save:
        downloader._make_progress_hook(lambda e: None, None, dict(tracker, items={}),
                                       threading.Event(), threading.Event(),
                                       save_sidecar=False)(finished)
        save.assert_not_called()
        downloader._make_progress_hook(lambda e: None, None, dict(tracker, items={}),
                                       threading.Event(), threading.Event())(finished)
        save.assert_called_once_with('T.mp4', 'http://x/t.jpg')


# ── ffmpeg found outside PATH ──────────────────────────────────────────────────

def test_ffmpeg_found_off_path_is_added_to_path(tmp_path):
    """yt-dlp's ffmpeg downloader (trims) only looks on PATH."""
    fake = tmp_path / ffmpeg_locate._EXE
    fake.write_bytes(b'')
    with patch('ffmpeg_locate._search', return_value=str(fake)):
        assert ffmpeg_locate.find_ffmpeg(refresh=True) == str(fake)
    parts = os.environ['PATH'].split(os.pathsep)
    assert parts[0] == str(tmp_path)
    with patch('ffmpeg_locate._search', return_value=str(fake)):
        ffmpeg_locate.find_ffmpeg(refresh=True)
    assert os.environ['PATH'].split(os.pathsep).count(str(tmp_path)) == 1
