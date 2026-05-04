import pytest
import downloader

PLAYLIST_3 = 'https://youtube.com/playlist?list=PL29g0AFkwZD9LG2WOIiPqzXNmXbcQdAoC'
PLAYLIST_4 = 'https://youtube.com/playlist?list=PL29g0AFkwZD_MCTLrDMXu0NslJcCHgtNY'
PLAYLIST_100 = 'https://youtube.com/playlist?list=LRYRTC351kXIa7B3wi7tF4ZQ_n0PIWofLJtY1'


@pytest.mark.e2e
def test_get_playlist_items_3(tmp_path):
    items = downloader.get_playlist_items(PLAYLIST_3)
    assert len(items) == 3
    for item in items:
        assert 'title' in item


@pytest.mark.e2e
def test_get_playlist_items_4(tmp_path):
    items = downloader.get_playlist_items(PLAYLIST_4)
    assert len(items) == 4


@pytest.mark.e2e
def test_download_playlist_3_fires_item_done(tmp_path):
    """3-item playlist must fire 3 item_done events and 1 complete."""
    events = []
    opts = {
        'mode': 'audio', 'quality': 'best', 'audio_format': 'mp3',
        'embed_thumbnail': False, 'embed_chapters': False,
        'embed_metadata': False, 'embed_subs': False,
        'sponsorblock': False, 'sleep_interval': 0,
    }
    downloader.download_video(PLAYLIST_3, str(tmp_path), opts, progress_cb=events.append)
    item_done = [e for e in events if e.get('status') == 'item_done']
    complete = [e for e in events if e.get('status') == 'complete']
    assert len(item_done) == 3, f"Expected 3 item_done, got {len(item_done)}"
    assert len(complete) == 1


@pytest.mark.e2e
def test_download_playlist_4_fires_item_done(tmp_path):
    events = []
    opts = {
        'mode': 'audio', 'quality': 'best', 'audio_format': 'mp3',
        'embed_thumbnail': False, 'embed_chapters': False,
        'embed_metadata': False, 'embed_subs': False,
        'sponsorblock': False, 'sleep_interval': 0,
    }
    downloader.download_video(PLAYLIST_4, str(tmp_path), opts, progress_cb=events.append)
    item_done = [e for e in events if e.get('status') == 'item_done']
    assert len(item_done) == 4


@pytest.mark.slow
def test_download_playlist_100_count(tmp_path):
    items = downloader.get_playlist_items(PLAYLIST_100)
    assert len(items) == 100


@pytest.mark.e2e
def test_multi_url_single_complete(tmp_path):
    """Regression for flaw #2: multi-URL job via server fires complete once."""
    import server
    from unittest.mock import patch

    complete_count = [0]
    real_push = server._push_progress

    def counting_push(event):
        if event.get('status') == 'complete':
            complete_count[0] += 1
        real_push(event)

    opts = {
        'mode': 'audio', 'quality': 'best', 'audio_format': 'mp3',
        'embed_thumbnail': False, 'embed_chapters': False,
        'embed_metadata': False, 'embed_subs': False, 'sleep_interval': 0,
    }
    job = {
        'id': 'e2e-test', 'type': 'sync', 'url': PLAYLIST_3,
        'multi_urls': [PLAYLIST_3, PLAYLIST_4],
        'output_dir': str(tmp_path), 'opts': opts,
        'library_id': 'test-lib', 'status': 'active',
    }
    with patch('server._push_progress', side_effect=counting_push):
        server._run_job(job)

    assert complete_count[0] == 1, f"Expected 1 complete for 2-URL job, got {complete_count[0]}"
