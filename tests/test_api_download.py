from unittest.mock import patch


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


def test_cancel_download(client):
    r = client.post('/api/cancel', json={})
    assert r.status_code == 200


def test_pause_resume(client):
    assert client.post('/api/download/pause', json={}).status_code == 200
    assert client.post('/api/download/resume', json={}).status_code == 200


def test_queue_status(client):
    r = client.get('/api/queue/status')
    assert r.status_code == 200
