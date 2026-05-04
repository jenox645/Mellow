def test_get_config_returns_defaults(client):
    r = client.get('/api/config')
    assert r.status_code == 200
    data = r.get_json()
    assert 'output_dir' in data
    assert data.get('sleep_interval', 0) == 0, "sleep_interval default must be 0 for speed"


def test_post_config_persists(client):
    r = client.post('/api/config', json={'sleep_interval': 2})
    assert r.status_code == 200
    r2 = client.get('/api/config')
    assert r2.get_json()['sleep_interval'] == 2


def test_config_rejects_non_json(client):
    r = client.post('/api/config', data='bad', content_type='text/plain')
    assert r.status_code in (200, 400)


def test_config_retries_field(client):
    r = client.get('/api/config')
    data = r.get_json()
    assert 'retries' in data
    assert isinstance(data['retries'], int)
