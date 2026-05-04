import pytest
import downloader


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
    from server import _parse_url_file
    content = "https://youtube.com/watch?v=a\nhttps://youtube.com/watch?v=b\n"
    urls, fmt = _parse_url_file(content)
    assert fmt == 'url_list'
    assert len(urls) == 2


def test_parse_url_file_archive():
    from server import _parse_url_file
    content = "youtube dQw4w9WgXcQ\nyoutube xxxxxxxxxxx\n"
    urls, fmt = _parse_url_file(content)
    assert fmt == 'archive'
    assert all('youtube.com' in u for u in urls)


def test_parse_url_file_ignores_comments():
    from server import _parse_url_file
    content = "# comment\nhttps://youtube.com/watch?v=a\n"
    urls, _ = _parse_url_file(content)
    assert len(urls) == 1
