import tempfile
import threading
from unittest.mock import patch

import jobs


def _make_manager(events):
    m = jobs.JobManager()
    m._push = events.append
    return m


def test_single_complete_for_multi_url_job():
    """Multi-URL job should only fire complete once (on the final URL)."""
    events = []

    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        cb({'status': 'downloading', 'pct': 50})
        cb({'status': 'complete', 'title': url})
        return 'success'

    with tempfile.TemporaryDirectory() as tmp:
        job = {
            'id': 'test',
            'type': 'feed',
            'label': 'test',
            'url': 'https://youtu.be/a',
            'multi_urls': ['https://youtu.be/a', 'https://youtu.be/b', 'https://youtu.be/c'],
            'output_dir': tmp,
            'opts': {},
            'library_id': None,
            'status': 'active',
        }
        with patch('downloader.download_video', side_effect=fake_dl):
            assert _make_manager(events).run_job(job) == 'complete'

    complete_events = [e for e in events if e.get('status') == 'complete']
    assert len(complete_events) == 1, f"Expected 1 complete, got {len(complete_events)}"
    # Events must be attributable when multiple downloads run concurrently
    assert complete_events[0].get('job_id') == 'test'


def test_sleep_interval_default_is_zero():
    from config import load_config
    cfg = load_config()
    assert cfg.get('sleep_interval', 0) == 0, "sleep_interval default must be 0 for speed"


def test_run_job_cancelled_mid_loop():
    """If cancelled after first URL, remaining URLs are skipped."""
    called = []
    events = []

    def fake_dl_cancel(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        called.append(url)
        # Cancel arrives mid-download: the per-job event gets set
        if cancel_event is not None:
            cancel_event.set()
        cb({'status': 'cancelled'})
        return 'cancelled'

    with tempfile.TemporaryDirectory() as tmp:
        job = {
            'id': 'test2',
            'type': 'feed',
            'label': 'test2',
            'url': 'https://youtu.be/a',
            'multi_urls': ['https://youtu.be/a', 'https://youtu.be/b'],
            'output_dir': tmp,
            'opts': {},
            'library_id': None,
            'status': 'active',
        }
        with patch('downloader.download_video', side_effect=fake_dl_cancel):
            assert _make_manager(events).run_job(job) == 'cancelled'

    assert len(called) == 1, f"Should stop after cancel, but called: {called}"


def test_reorder_moves_queued_job():
    m = jobs.JobManager()
    m._push = lambda e: None
    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(jobs, 'QUEUE_STATE_PATH', jobs.Path(tmp) / 'queue.json'):
        a = m.enqueue('https://youtu.be/a', tmp, {})
        b = m.enqueue('https://youtu.be/b', tmp, {})
        c = m.enqueue('https://youtu.be/c', tmp, {})
        assert [j['id'] for j in m._pending] == [a['id'], b['id'], c['id']]
        assert m.reorder(c['id'], 0)
        assert [j['id'] for j in m._pending] == [c['id'], a['id'], b['id']]
        # Cancelling a queued job removes it from the pending order
        m.cancel(b['id'])
        assert [j['id'] for j in m._pending] == [c['id'], a['id']]


def test_cancelled_before_start_never_runs():
    m = jobs.JobManager()
    m._push = lambda e: None
    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(jobs, 'QUEUE_STATE_PATH', jobs.Path(tmp) / 'queue.json'):
        job = m.enqueue('https://youtu.be/a', tmp, {})
        m.cancel(job['id'])
        assert job['status'] == 'cancelled'
        assert job not in m._pending


def test_configured_workers_clamped():
    with patch('jobs.load_config', return_value={'download_workers': 99}):
        assert jobs.configured_workers() == jobs.MAX_DOWNLOAD_WORKERS
    with patch('jobs.load_config', return_value={'download_workers': 0}):
        assert jobs.configured_workers() == 1
    with patch('jobs.load_config', return_value={'download_workers': 'garbage'}):
        assert jobs.configured_workers() == 1


def test_worker_pool_respects_limit():
    """With download_workers=2, two jobs run concurrently, the third waits."""
    started = threading.Semaphore(0)
    release = threading.Event()
    peak = {'n': 0, 'cur': 0}
    lock = threading.Lock()

    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        with lock:
            peak['cur'] += 1
            peak['n'] = max(peak['n'], peak['cur'])
        started.release()
        release.wait(timeout=10)
        with lock:
            peak['cur'] -= 1
        return 'success'

    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(jobs, 'QUEUE_STATE_PATH', jobs.Path(tmp) / 'queue.json'), \
            patch('jobs.load_config', return_value={'download_workers': 2}), \
            patch('downloader.download_video', side_effect=fake_dl):
        m = jobs.JobManager()
        m.start(lambda e: None)
        for i in range(3):
            m.enqueue(f'https://youtu.be/{i}', tmp, {})
        # Wait for exactly two to start; the third must be gated
        assert started.acquire(timeout=10) and started.acquire(timeout=10)
        assert not started.acquire(timeout=0.5), "third job started despite limit=2"
        release.set()
        assert started.acquire(timeout=10), "third job never started after slots freed"
        assert peak['n'] == 2
