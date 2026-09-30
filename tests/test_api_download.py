from unittest.mock import patch

import jobs


def test_download_requires_url(client):
    r = client.post('/api/download', json={})
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_download_enqueues_job(client, tmp_dir):
    with patch('downloader.download_video') as mock_dl:
        mock_dl.return_value = None
        r = client.post('/api/download', json={
            'url': 'https://youtube.com/watch?v=dQw4w9WgXcQ',
            'output_dir': tmp_dir,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('status') == 'started'
        assert 'job_id' in data
        # Drain the queue while the downloader is still mocked, so the worker
        # can't pick the job up afterwards and start a real download.
        assert jobs.manager.wait_idle(10)
        assert mock_dl.call_args[0][0] == 'https://youtube.com/watch?v=dQw4w9WgXcQ'


def test_download_multi_urls(client, tmp_dir):
    with patch('downloader.download_video') as mock_dl:
        mock_dl.return_value = None
        urls = ['https://youtu.be/a', 'https://youtu.be/b']
        r = client.post('/api/download', json={
            'url': urls[0],
            'multi_urls': urls,
            'output_dir': tmp_dir,
        })
        assert r.status_code == 200
        assert jobs.manager.wait_idle(10)
        assert [c[0][0] for c in mock_dl.call_args_list] == urls


def test_cancel_download(client):
    r = client.post('/api/cancel', json={})
    assert r.status_code == 200


def test_pause_resume(client):
    import downloader
    with patch.object(jobs.manager, 'has_active', return_value=True):
        assert client.post('/api/download/pause', json={}).get_json()['status'] == 'paused'
    assert downloader._pause_event.is_set()
    assert client.post('/api/download/resume', json={}).get_json()['status'] == 'resumed'
    assert not downloader._pause_event.is_set()


def test_queue_status(client):
    r = client.get('/api/queue/status')
    assert r.status_code == 200
