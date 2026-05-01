def test_server_imports():
    import server
    assert hasattr(server, 'app')

def test_downloader_imports():
    import downloader
    assert callable(getattr(downloader, 'download_video', None))

def test_analytics_imports():
    import analytics
    assert callable(getattr(analytics, 'record_download', None))

def test_downloader_quality_map():
    from downloader import QUALITY_MAP
    assert '1080p' in QUALITY_MAP

def test_downloader_detect_platform():
    from downloader import _detect_platform
    assert _detect_platform('https://youtube.com/watch?v=abc') == 'YouTube'
