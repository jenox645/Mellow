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
