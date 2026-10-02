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
