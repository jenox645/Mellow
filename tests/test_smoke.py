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


def test_download_options_keys():
    import downloader
    assert downloader is not None


def test_stats_endpoint_no_cache():
    import server
    routes = [str(r) for r in server.app.url_map.iter_rules()]
    assert any('stats' in r for r in routes), f"No stats route found. Routes: {routes}"


def test_thumbnail_sidecar_function():
    import downloader
    assert hasattr(downloader, '_save_thumbnail_sidecar'), \
        "_save_thumbnail_sidecar function missing from downloader.py"


def test_item_done_in_progress_hook():
    """item_done event must be emitted by the progress hook on 'finished' status."""
    from downloader import _make_progress_hook
    events = []
    hook = _make_progress_hook(events.append, None, {"samples": []})
    hook({"status": "finished", "info_dict": {"title": "Test Video", "thumbnail": "http://x.jpg", "playlist_index": 1}, "filename": "test.mp4"})
    statuses = [e.get("status") for e in events]
    assert "item_done" in statuses, f"Expected item_done event, got: {statuses}"
    item = next(e for e in events if e.get("status") == "item_done")
    assert item["title"] == "Test Video"
    assert item["playlist_index"] == 1


def test_vault_folder_stats_route():
    import server
    routes = [str(r) for r in server.app.url_map.iter_rules()]
    assert any('folder-stats' in r for r in routes), f"No folder-stats route. Routes: {routes}"
