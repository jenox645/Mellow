import pytest

from mellow import downloader


def test_detect_platform_youtube():
    assert downloader._detect_platform('https://youtube.com/watch?v=abc') == 'YouTube'


def test_detect_platform_twitter():
    result = downloader._detect_platform('https://twitter.com/user/status/123')
    assert 'Twitter' in result or result == 'X'


@pytest.mark.parametrize("url,expected", [
    ('https://www.tiktok.com/@user/video/123', 'TikTok'),
    ('https://vimeo.com/123456', 'Vimeo'),
    ('https://www.twitch.tv/videos/123', 'Twitch'),
    ('https://www.reddit.com/r/sub/comments/abc', 'Reddit'),
    ('https://soundcloud.com/user/track', 'SoundCloud'),
    ('https://instagram.com/p/abc', 'Instagram'),
    ('https://example.com/video', 'Other'),
])
def test_detect_platform_all(url, expected):
    assert downloader._detect_platform(url) == expected


def test_parse_time_seconds():
    assert downloader._parse_time('90') == 90.0


def test_parse_time_mm_ss():
    assert downloader._parse_time('1:30') == 90.0


def test_parse_time_hh_mm_ss():
    assert downloader._parse_time('1:01:30') == 3690.0


def test_parse_time_none():
    assert downloader._parse_time('') is None


def test_quality_map_has_all_tiers():
    for q in ['best', '4k', '1080p', '720p', '480p', '360p']:
        assert q in downloader.QUALITY_MAP


def test_parse_url_file_plain():
    from mellow.downloader import parse_url_file
    content = "https://youtube.com/watch?v=a\nhttps://youtube.com/watch?v=b\n"
    urls, fmt = parse_url_file(content)
    assert fmt == 'url_list'
    assert len(urls) == 2


def test_parse_url_file_archive():
    from mellow.downloader import parse_url_file
    content = "youtube dQw4w9WgXcQ\nyoutube xxxxxxxxxxx\n"
    urls, fmt = parse_url_file(content)
    assert fmt == 'archive'
    assert all('youtube.com' in u for u in urls)


def test_parse_url_file_ignores_comments():
    from mellow.downloader import parse_url_file
    content = "# comment\nhttps://youtube.com/watch?v=a\n"
    urls, _ = parse_url_file(content)
    assert len(urls) == 1


def test_unreadable_clip_time_is_an_error_not_the_whole_video():
    """"1:3x" used to read as "from the start", downloading the whole video
    for a clip request."""
    import pytest
    with pytest.raises(ValueError, match="1:3x"):
        downloader._clip_range('1:3x', '')
    with pytest.raises(ValueError, match='before it starts'):
        downloader._clip_range('2:00', '1:00')
    assert downloader._clip_range('', '1:30') == (0.0, 90.0)
    assert downloader._clip_range('10', '') == (10.0, float('inf'))


def test_bad_clip_time_fails_the_download_with_a_terminal_error(tmp_path):
    from unittest.mock import patch
    events = []
    with patch('mellow.downloader.find_ffmpeg', return_value='/usr/bin/ffmpeg'), \
            patch('mellow.downloader.yt_dlp.YoutubeDL') as ydl:
        status = downloader.download_video(
            'https://youtu.be/abc', str(tmp_path), {'start_time': 'abc'}, events.append)
    assert status == 'error'
    assert not ydl.called
    assert events[-1]['status'] == 'error' and 'abc' in events[-1]['message']


def _yt_like_formats():
    """Separate video/audio streams, worst to best (the order yt-dlp sorts them in)."""
    formats = [
        {'format_id': '140', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a', 'filesize': 3_000_000},
        {'format_id': '251', 'ext': 'webm', 'vcodec': 'none', 'acodec': 'opus', 'filesize': 3_500_000},
        {'format_id': '134', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none', 'height': 360, 'filesize': 10_000_000},
        {'format_id': '136', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none', 'height': 720, 'filesize': 30_000_000},
        {'format_id': '137', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none', 'height': 1080,
         'filesize_approx': 60_000_000},
    ]
    return [{**f, 'url': f"https://media.example/{f['format_id']}"} for f in formats]


def test_size_estimates_follow_the_download_format_selection():
    """The Feed shows what a download will fetch: best video under the height
    plus the m4a audio the format strings prefer."""
    from unittest.mock import patch
    with downloader.yt_dlp.YoutubeDL({'quiet': True}) as ydl, \
            patch('mellow.downloader.find_ffmpeg', return_value='/usr/bin/ffmpeg'):
        est = downloader._size_estimates(ydl, {'formats': _yt_like_formats(), 'duration': 300})
    assert est['video']['1080p'] == 63_000_000
    assert est['video']['720p'] == 33_000_000
    assert est['video']['360p'] == 13_000_000
    assert est['video']['best'] == 63_000_000
    assert est['audio'] == 3_500_000  # bestaudio: the opus stream


def test_size_estimates_without_ffmpeg_use_single_file_formats():
    from unittest.mock import patch
    formats = [*_yt_like_formats(),
               {'format_id': '18', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'mp4a', 'height': 360,
                'filesize': 12_000_000, 'url': 'https://media.example/18'}]
    with downloader.yt_dlp.YoutubeDL({'quiet': True}) as ydl, \
            patch('mellow.downloader.find_ffmpeg', return_value=None):
        est = downloader._size_estimates(ydl, {'formats': formats})
    assert est['video']['1080p'] == 12_000_000  # only the combined 360p file can be saved
    assert est['audio'] == 3_000_000  # bestaudio[ext=m4a]


def test_failed_playlist_items_name_their_url():
    """So the Queue can retry just that item."""
    assert downloader.item_url_from_error('ERROR: [youtube] dQw4w9WgXcQ: Video unavailable') \
        == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    assert downloader.item_url_from_error('ERROR: [generic] missing: HTTP Error 404') is None
    assert downloader.item_url_from_error('ERROR: [youtube:tab] PLx: does not exist') is None
    events = []
    logger = downloader._GeoBlockLogger(events.append, None)
    logger.error('ERROR: [youtube] dQw4w9WgXcQ: Private video')
    assert events[0]['url'] == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


def test_logger_reports_archive_and_filter_skips():
    events = []
    logger = downloader._GeoBlockLogger(events.append, None)
    logger.debug('[download] \x1b[0;33mdQw4w9WgXcQ\x1b[0m: Some Title has already been recorded in the archive')
    logger.debug('[download] A Short does not pass filter (media_type!=?short), skipping ..')
    logger.debug('[youtube] Extracting URL: https://youtu.be/x')
    assert [(e['status'], e['reason'], e.get('title')) for e in events] == [
        ('item_skipped', 'archive', None), ('item_skipped', 'filtered', 'A Short')]


def test_analyzing_a_playlist_returns_its_items_in_one_extraction():
    from unittest.mock import patch

    from mellow import downloader
    flat = {'_type': 'playlist', 'title': 'Mix', 'entries': [
        {'id': 'a', 'title': 'One', 'url': 'https://x/a', 'duration': 60},
        None,  # unavailable: keeps its slot, so the next item is position 3
        {'id': 'c', 'title': 'Three', 'url': 'https://x/c', 'thumbnails': [{'url': 't.jpg'}]},
    ]}
    with patch('yt_dlp.YoutubeDL.YoutubeDL.extract_info', return_value=flat) as extract:
        info = downloader.get_video_info('https://x/list')
    assert extract.call_count == 1
    assert info['is_playlist'] and info['playlist_count'] == 3
    assert [(i['idx'], i['title']) for i in info['items']] == [(1, 'One'), (3, 'Three')]
    assert info['items'][1]['thumbnail'] == 't.jpg'
    with patch('yt_dlp.YoutubeDL.YoutubeDL.extract_info', return_value=flat):
        assert downloader.get_playlist_items('https://x/list') == info['items']


def test_a_single_video_has_no_items():
    from unittest.mock import patch

    from mellow import downloader
    with patch('yt_dlp.YoutubeDL.YoutubeDL.extract_info', return_value={'id': 'v', 'title': 'V', 'formats': []}):
        assert downloader.get_video_info('https://x/v')['items'] is None


def test_search_lists_youtube_results_as_items():
    from unittest.mock import patch

    from mellow import downloader
    found = {'_type': 'playlist', 'entries': [
        {'id': 'aaaaaaaaaaa', 'title': 'Lofi One', 'url': 'https://www.youtube.com/watch?v=aaaaaaaaaaa',
         'channel': 'Chill', 'duration': 3600, 'view_count': 1200000},
        {'id': 'bbbbbbbbbbb', 'title': 'Lofi Two', 'url': 'bbbbbbbbbbb'},   # id only
    ]}
    with patch('yt_dlp.YoutubeDL.YoutubeDL.extract_info', return_value=found) as extract:
        items = downloader.search('  lofi \n  beats ')
    assert extract.call_args[0][0] == f'ytsearch{downloader.SEARCH_RESULTS}:lofi beats'
    assert [(i['title'], i['url'], i['uploader'], i['view_count']) for i in items] == [
        ('Lofi One', 'https://www.youtube.com/watch?v=aaaaaaaaaaa', 'Chill', 1200000),
        ('Lofi Two', 'https://www.youtube.com/watch?v=bbbbbbbbbbb', '', None)]
    assert downloader.search('   ') == []


def test_saved_hook_reports_the_final_file(tmp_path):
    from mellow import downloader
    events = []
    hook = downloader._make_saved_hook(events.append, 'lib1')
    f = tmp_path / 'Song.mp3'
    f.write_bytes(b'x' * 1234)
    hook(str(f))
    hook(str(tmp_path / 'gone.mp3'))   # nothing kept: no event
    assert events == [{'status': 'item_saved', 'file_path': str(f), 'file_size': 1234, 'library_id': 'lib1'}]


# ── File names that fit ───────────────────────────────────────────────────

_LONG_INFO = {
    "id": "dQw4w9WgXcQ", "ext": "webm", "upload_date": "20240131",
    "title": "とても長い：タイトル/テスト " * 30,           # 450 characters, ~1.3 KB in UTF-8
    "playlist_title": "My very long playlist name " * 10, "playlist_index": 7,
    "section_title": "A chapter whose name goes on and on " * 8, "section_number": 3,
}


def _expand(template, out_dir, windows):
    import yt_dlp
    fitted = downloader._fit_template(template, out_dir, windows=windows)
    with yt_dlp.YoutubeDL({"windows_filenames": True, "quiet": True}) as ydl:
        return str(out_dir / ydl.evaluate_outtmpl(fitted, dict(_LONG_INFO), True))


@pytest.mark.parametrize("template", [
    "%(title)s.%(ext)s",
    "%(title)s [%(id)s].%(ext)s",
    "%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s",
    "%(upload_date>%Y/%m)s/%(title)s.%(ext)s",
    "%(title)s - %(section_number)02d %(section_title)s.%(ext)s",     # chosen chapters
])
@pytest.mark.parametrize("windows", [False, True])
def test_a_long_title_still_fits_a_file_name(template, windows):
    from pathlib import PurePosixPath, PureWindowsPath
    out_dir = PureWindowsPath(r"C:\Users\someone\Downloads\MellowDLP") if windows \
        else PurePosixPath("/home/someone/Downloads/MellowDLP")
    path = _expand(template, out_dir, windows)
    # Room for what yt-dlp adds while it works (".f251.webm.part")
    working = path + ".f251-drc.webm.part"
    for name in working.replace("\\", "/").split("/"):
        assert (len(name) if windows else len(name.encode())) <= 255, name
    if windows:
        assert len(working) <= 259, working
    assert "とても長い" in path                       # cut, not dropped
    if "[%(id)s]" in template:
        assert "[dQw4w9WgXcQ]" in path                 # the id after the title survives


def test_a_short_title_is_left_whole():
    from pathlib import PureWindowsPath
    title = "x" * 100                          # YouTube's longest title
    fitted = downloader._fit_template("%(title)s [%(id)s].%(ext)s",
                                      PureWindowsPath(r"C:\Users\someone\Downloads\MellowDLP"), windows=True)
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        assert ydl.evaluate_outtmpl(fitted, {"title": title, "id": "a", "ext": "mp4"}, True) == title + " [a].mp4"


@pytest.mark.parametrize("template", ["%(title).50s.%(ext)s", "%(id)s.%(ext)s", "%(title,id)s.%(ext)s"])
def test_a_template_without_plain_free_text_is_kept(template):
    from pathlib import Path
    assert downloader._fit_template(template, Path("/x"), windows=False) == template


def test_a_deep_folder_still_leaves_a_readable_title():
    from pathlib import PureWindowsPath
    deep = PureWindowsPath("C:\\" + "\\".join(["a folder with a long name"] * 9))
    assert "%(title).32s" in downloader._fit_template("%(title)s.%(ext)s", deep, windows=True)


def test_items_removed_from_the_queue_are_skipped_while_the_playlist_runs():
    """✕ on a pending item adds it to the job's skip_items: the match filter
    reads that list at every entry, so it works on a running download."""
    ydl_opts = {}
    opts = {'skip_items': [], 'skip_shorts': True}
    downloader._apply_playlist_opts(ydl_opts, opts, 'https://www.youtube.com/playlist?list=PLx')
    match = ydl_opts['match_filter']
    assert match({'id': 'a', 'title': 'One'}) is None
    opts['skip_items'].append('a')                       # ✕ while it runs
    assert match({'id': 'a', 'title': 'One'}) == f'One {downloader.REMOVED_REASON}'
    assert match({'id': 'b', 'url': 'https://x/b'}, incomplete=True) is None
    opts['skip_items'].append('https://x/b')             # a link works as well as an id
    assert downloader.REMOVED_REASON in match({'id': 'b', 'url': 'https://x/b'})
    # The skip filters still apply to the rest
    assert 'does not pass filter' in match({'id': 'c', 'title': 'Short', 'media_type': 'short'})
    events = []
    downloader._GeoBlockLogger(events.append, None).debug(f'[download] One {downloader.REMOVED_REASON}')
    assert [(e['reason'], e['title']) for e in events] == [('removed', 'One')]


def test_a_single_link_gets_no_queue_filter():
    ydl_opts = {}
    downloader._apply_playlist_opts(ydl_opts, {'skip_items': []}, 'https://youtu.be/x')
    assert 'match_filter' not in ydl_opts
