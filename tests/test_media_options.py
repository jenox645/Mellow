"""The yt-dlp options built for cover art, trimming, the webm container and
SponsorBlock.

Each of these was silently broken at some point: cover art was never embedded
(yt-dlp only embeds a thumbnail it wrote itself), trims crashed on the range
format, webm asked for an m4a audio stream it cannot hold, and SponsorBlock
looked the segments up without ever cutting them out.
"""
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from mellow import downloader, ffmpeg_locate, vault
from mellow.constants import SPONSORBLOCK_REMOVE_CATEGORIES

FFMPEG = '/usr/bin/ffmpeg'


def _opts_for(tmp_dir, opts, ffmpeg=FFMPEG, info=None):
    """Run download_video against a fake YoutubeDL; return (ydl_opts, ydl, events)."""
    ydl = MagicMock()
    ydl.extract_info.return_value = info or {'title': 'T', 'id': 'abc'}
    ydl._download_retcode = 0
    cls = MagicMock()
    cls.return_value.__enter__.return_value = ydl
    events = []
    with patch('mellow.downloader.yt_dlp.YoutubeDL', cls), \
            patch('mellow.downloader.find_ffmpeg', return_value=ffmpeg):
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


# ── SponsorBlock ───────────────────────────────────────────────────────────────

CATEGORIES = list(SPONSORBLOCK_REMOVE_CATEGORIES)


def _keys(ydl_opts):
    return [pp['key'] for pp in ydl_opts['postprocessors']]


def test_sponsorblock_cuts_the_segments_out(tmp_dir):
    ydl_opts, _, events = _opts_for(tmp_dir, {
        'sponsorblock': True, 'embed_chapters': True, 'embed_metadata': True})
    pps = ydl_opts['postprocessors']
    # The lookup has to happen before the download, like the CLI does it
    assert {'key': 'SponsorBlock', 'categories': CATEGORIES, 'when': 'after_filter'} in pps
    # ...and something has to act on what it found
    assert {'key': 'ModifyChapters', 'remove_sponsor_segments': CATEGORIES} in pps
    keys = _keys(ydl_opts)
    assert keys.index('ModifyChapters') < keys.index('FFmpegMetadata'), \
        "chapters are written after the cut, or they point at the uncut video"
    assert 'warning' not in [e['status'] for e in events]


def test_sponsorblock_is_off_unless_asked_for(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'embed_chapters': True, 'embed_metadata': True})
    assert _keys(ydl_opts) == ['FFmpegMetadata']


def test_sponsorblock_cuts_the_converted_audio_file(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'mode': 'audio', 'audio_format': 'mp3',
                                         'sponsorblock': True, 'embed_metadata': True})
    post_process = [pp['key'] for pp in ydl_opts['postprocessors'] if 'when' not in pp]
    assert post_process == ['FFmpegExtractAudio', 'ModifyChapters', 'FFmpegMetadata']


def test_subtitles_are_embedded_before_the_cut(tmp_dir):
    """Embedded afterwards they would keep the uncut video's timing."""
    ydl_opts, _, _ = _opts_for(tmp_dir, {'sponsorblock': True, 'embed_subs': True})
    keys = _keys(ydl_opts)
    assert keys.index('FFmpegEmbedSubtitle') < keys.index('ModifyChapters')
    assert ydl_opts['writesubtitles'] is True


def test_subtitles_are_still_embedded_without_sponsorblock(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'embed_subs': True})
    assert {'key': 'FFmpegEmbedSubtitle', 'already_have_subtitle': False} \
        in ydl_opts['postprocessors']
    ydl_opts, _, _ = _opts_for(tmp_dir, {'mode': 'audio', 'embed_subs': True})
    assert 'FFmpegEmbedSubtitle' not in _keys(ydl_opts)


def test_sponsorblock_needs_ffmpeg(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'sponsorblock': True}, ffmpeg=None)
    assert ydl_opts['postprocessors'] == []


def test_sponsorblock_is_skipped_for_a_trimmed_download(tmp_dir):
    """Segment times refer to the whole video, not to the trimmed file."""
    ydl_opts, _, events = _opts_for(tmp_dir, {'sponsorblock': True, 'start_time': '0:10',
                                              'end_time': '0:40', 'embed_metadata': True})
    assert _keys(ydl_opts) == ['FFmpegMetadata']
    warnings = [e for e in events if e['status'] == 'warning']
    assert [w['code'] for w in warnings] == ['sponsorblock_skipped']
    complete = next(e for e in events if e['status'] == 'complete')
    assert complete['warning'] == warnings[0]['message']


def test_library_sync_passes_the_entry_flag_through(tmp_dir):
    lib = {'quality': '720p', 'mode': 'VIDEO', 'embed_thumbnail': False,
           'embed_chapters': True, 'embed_metadata': True, 'sponsorblock': True}
    ydl_opts, _, _ = _opts_for(tmp_dir, vault.build_sync_opts({}, lib, {}))
    assert _keys(ydl_opts) == ['SponsorBlock', 'ModifyChapters', 'FFmpegMetadata']
    ydl_opts, _, _ = _opts_for(
        tmp_dir, vault.build_sync_opts({}, dict(lib, sponsorblock=False), {}))
    assert _keys(ydl_opts) == ['FFmpegMetadata']


def test_ytdlp_accepts_the_sponsorblock_postprocessors():
    """The real YoutubeDL must take these dicts and queue them in CLI order."""
    pps = downloader._build_postprocessors(
        {'embed_chapters': True, 'embed_metadata': True}, embed_subs=True, cut_sponsors=True)
    with downloader.yt_dlp.YoutubeDL({'postprocessors': pps, 'quiet': True}) as ydl:
        assert [pp.PP_NAME for pp in ydl._pps['after_filter']] == ['SponsorBlock']
        queued = ydl._pps['post_process']
        assert [pp.PP_NAME for pp in queued] == ['EmbedSubtitle', 'ModifyChapters', 'Metadata']
        assert queued[1]._remove_sponsor_segments == set(CATEGORIES)


def test_history_records_the_length_of_the_cut_file(tmp_dir):
    from mellow import analytics
    saved = Path(tmp_dir) / 'T.mp4'
    saved.write_bytes(b'x')
    # ModifyChapters shortens the download's duration, not the video's
    info = {'title': 'T', 'id': 'abc', 'duration': 236,
            'requested_downloads': [{'filepath': str(saved), 'duration': 220.9}]}
    _opts_for(tmp_dir, {'sponsorblock': True}, info=info)
    assert analytics.get_history()[0]['duration_seconds'] == 221


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
    with patch('mellow.downloader._save_thumbnail_sidecar') as save:
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
    with patch('mellow.ffmpeg_locate._search', return_value=str(fake)):
        assert ffmpeg_locate.find_ffmpeg(refresh=True) == str(fake)
    parts = os.environ['PATH'].split(os.pathsep)
    assert parts[0] == str(tmp_path)
    with patch('mellow.ffmpeg_locate._search', return_value=str(fake)):
        ffmpeg_locate.find_ffmpeg(refresh=True)
    assert os.environ['PATH'].split(os.pathsep).count(str(tmp_path)) == 1


def test_playlists_skip_shorts_and_live_streams_as_configured(tmp_dir):
    ydl_opts, _, _ = _opts_for(tmp_dir, {'mode': 'library', 'skip_shorts': True, 'skip_live': True})
    skip = ydl_opts['match_filter']
    assert skip({'id': 's', 'media_type': 'short'}, incomplete=False)
    assert skip({'id': 'l', 'live_status': 'is_live'}, incomplete=False)
    assert skip({'id': 'u', 'live_status': 'is_upcoming'}, incomplete=False)
    assert skip({'id': 'v', 'media_type': 'video', 'live_status': 'not_live'}, incomplete=False) is None
    assert skip({'id': 'r', 'media_type': 'livestream', 'live_status': 'was_live'}, incomplete=False) is None
    # a flat playlist entry carries neither field yet
    assert skip({'id': 'f'}, incomplete=True) is None


def test_a_single_link_is_never_filtered(tmp_dir):
    """What the user pasted is what they asked for, Short or not."""
    ydl_opts, _, _ = _opts_for(tmp_dir, {'mode': 'video', 'skip_shorts': True, 'skip_live': True})
    assert 'match_filter' not in ydl_opts


def test_skip_settings_reach_every_download(client, tmp_dir):
    from unittest.mock import patch

    from mellow import jobs
    from mellow.config import download_settings, load_config
    assert download_settings(load_config())['skip_live'] is True
    assert download_settings(load_config())['skip_shorts'] is False
    client.post('/api/config', json={'skip_shorts': True})
    with patch('mellow.downloader.download_video') as dl:
        client.post('/api/download', json={'url': 'https://youtube.com/playlist?list=X', 'output_dir': tmp_dir})
        assert jobs.manager.wait_idle(10)
    assert dl.call_args[0][2]['skip_shorts'] is True
