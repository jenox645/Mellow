import tempfile
import pytest
from unittest.mock import patch
import server
import downloader


def test_single_complete_for_multi_url_job():
    """Fix #2: multi-URL job should only fire complete once."""
    events = []

    def fake_dl(url, out, opts, cb, lib_id=None):
        cb({'status': 'downloading', 'pct': 50})
        cb({'status': 'complete', 'title': url})

    with tempfile.TemporaryDirectory() as tmp:
        job = {
            'id': 'test',
            'type': 'feed',
            'url': 'https://youtu.be/a',
            'multi_urls': ['https://youtu.be/a', 'https://youtu.be/b', 'https://youtu.be/c'],
            'output_dir': tmp,
            'opts': {},
            'library_id': None,
            'status': 'active',
        }
        with patch('downloader.download_video', side_effect=fake_dl):
            with patch('server._push_progress', side_effect=events.append):
                server._run_job(job)

    complete_events = [e for e in events if e.get('status') == 'complete']
    assert len(complete_events) == 1, f"Expected 1 complete, got {len(complete_events)}"


def test_sleep_interval_default_is_zero():
    cfg = server._load_config()
    assert cfg.get('sleep_interval', 0) == 0, "sleep_interval default must be 0 for speed"


def test_run_job_cancelled_mid_loop():
    """If cancelled after first URL, remaining URLs are skipped."""
    called = []

    def fake_dl(url, out, opts, cb, lib_id=None):
        called.append(url)
        cb({'status': 'complete', 'title': url})

    with tempfile.TemporaryDirectory() as tmp:
        job = {
            'id': 'test2',
            'type': 'feed',
            'url': 'https://youtu.be/a',
            'multi_urls': ['https://youtu.be/a', 'https://youtu.be/b'],
            'output_dir': tmp,
            'opts': {},
            'library_id': None,
            'status': 'active',
        }
        cancel_after = [0]

        def is_cancelled():
            cancel_after[0] += 1
            return cancel_after[0] > 1

        with patch('downloader.download_video', side_effect=fake_dl):
            with patch('server._push_progress'):
                with patch.object(downloader, '_is_cancelled', side_effect=is_cancelled):
                    server._run_job(job)

    assert len(called) == 1, f"Should stop after cancel, but called: {called}"
