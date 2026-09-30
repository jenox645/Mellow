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


def _multi_job(tmp, urls, job_id='multi', job_type='sync', library_id=None):
    return {
        'id': job_id, 'type': job_type, 'label': 'Sync — Music (2 playlist(s))',
        'url': urls[0], 'multi_urls': urls, 'output_dir': tmp, 'opts': {},
        'library_id': library_id, 'status': 'active',
        'cancel_event': threading.Event(),
    }


def _fake_dl_failing(failing):
    """Downloader stand-in: URLs in `failing` end in error, the rest complete."""
    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        cb({'status': 'starting', 'url': url})
        if url in failing:
            cb({'status': 'error', 'message': f'ERROR: {url} is private', 'url': url})
            return 'error'
        cb({'status': 'item_done', 'title': url, 'video_id': url[-1]})
        cb({'status': 'complete', 'title': url})
        return 'success'
    return fake_dl


def _terminal(events):
    return [e for e in events if e.get('status') in ('complete', 'error', 'cancelled')]


def test_multi_url_job_first_playlist_failing_ends_in_one_complete():
    """A failed first playlist used to push `error` mid-job (UI showed the
    sync as failed, then as running again)."""
    events = []
    urls = ['https://youtube.com/playlist?list=A', 'https://youtube.com/playlist?list=B']
    with tempfile.TemporaryDirectory() as tmp, \
            patch('downloader.download_video', side_effect=_fake_dl_failing({urls[0]})):
        assert _make_manager(events).run_job(_multi_job(tmp, urls)) == 'complete'
    terminal = _terminal(events)
    assert [e['status'] for e in terminal] == ['complete']
    assert '1 of 2' in terminal[0]['warning']
    assert events[-1] is terminal[0], 'the terminal event must be the last one'
    failed = [e for e in events if e.get('status') == 'item_failed']
    assert [e['url'] for e in failed] == [urls[0]]
    assert 'private' in failed[0]['message']


def test_multi_url_job_last_playlist_failing_is_not_reported_as_error():
    """The job counts as complete, so the UI must not be told it failed."""
    events = []
    urls = ['https://youtube.com/playlist?list=A', 'https://youtube.com/playlist?list=B']
    with tempfile.TemporaryDirectory() as tmp, \
            patch('downloader.download_video', side_effect=_fake_dl_failing({urls[1]})):
        assert _make_manager(events).run_job(_multi_job(tmp, urls)) == 'complete'
    assert [e['status'] for e in _terminal(events)] == ['complete']


def test_multi_url_job_all_failing_ends_in_one_error():
    events = []
    urls = ['https://youtube.com/playlist?list=A', 'https://youtube.com/playlist?list=B']
    with tempfile.TemporaryDirectory() as tmp, \
            patch('downloader.download_video', side_effect=_fake_dl_failing(set(urls))):
        assert _make_manager(events).run_job(_multi_job(tmp, urls)) == 'failed'
    terminal = _terminal(events)
    assert [e['status'] for e in terminal] == ['error']
    assert terminal[0]['url'] == urls[1]  # retry target
    assert terminal[0]['job_id'] == 'multi'


def test_job_whose_downloader_sent_no_terminal_event_still_gets_one():
    """The UI has no timeout: a job must always end in a terminal event."""
    events = []
    with tempfile.TemporaryDirectory() as tmp, \
            patch('downloader.download_video', return_value='success'):
        m = _make_manager(events)
        assert m.run_job(_multi_job(tmp, ['https://youtu.be/a'], job_type='feed')) == 'complete'
    assert [e['status'] for e in _terminal(events)] == ['complete']


def test_library_last_synced_is_stamped_on_completion_only():
    import analytics
    analytics.upsert_library_entry({'id': 'lib1', 'name': 'L', 'url': 'https://x/pl'})
    m = _make_manager([])

    def last_synced():
        return next(e for e in analytics.get_library_entries() if e['id'] == 'lib1')['last_synced']

    job = {'type': 'sync', 'library_id': 'lib1', 'counts': {}}
    m._on_finished(job, 'failed')
    assert last_synced() is None
    m._on_finished(job, 'complete')
    assert last_synced() is not None


def test_failed_link_that_reported_its_own_items_is_not_counted_twice():
    """Library runs log each failure as item_failed already; the job summary
    must not add a second one for the same link."""
    events = []
    urls = ['https://youtube.com/playlist?list=A', 'https://youtube.com/playlist?list=B']

    def fake_dl(url, out, opts, cb, lib_id=None, cancel_event=None, pause_event=None):
        if url == urls[0]:
            cb({'status': 'item_failed', 'reason': 'error', 'message': 'HTTP Error 404'})
            cb({'status': 'error', 'message': 'HTTP Error 404', 'url': url})
            return 'error'
        cb({'status': 'complete', 'title': url})
        return 'success'

    with tempfile.TemporaryDirectory() as tmp, patch('downloader.download_video', side_effect=fake_dl):
        assert _make_manager(events).run_job(_multi_job(tmp, urls)) == 'complete'
    assert len([e for e in events if e['status'] == 'item_failed']) == 1
    assert '1 of 2' in _terminal(events)[0]['warning']
