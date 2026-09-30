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
    # text/plain is what a cross-origin "simple" POST sends — must be rejected
    r = client.post('/api/config', data='bad', content_type='text/plain')
    assert r.status_code == 415


def test_config_retries_field(client):
    r = client.get('/api/config')
    data = r.get_json()
    assert 'retries' in data
    assert isinstance(data['retries'], int)


def test_reset_defaults_resets_every_setting_but_keeps_user_data(client):
    from config import _DEFAULTS, update_config

    def _customise(cfg):
        cfg.update(force_ipv4=True, default_quality='720p', proxy='http://p:1', download_workers=3,
                   ui_victory_animation=False,
                   vault_playlists={'/m': ['https://x/pl']}, vault_budgets={'/m': 5},
                   download_presets=[{'name': 'p'}], webhooks={'complete': ['https://h']})
    update_config(_customise)
    cfg = client.post('/api/config/reset', json={}).get_json()
    for key in ('force_ipv4', 'default_quality', 'proxy', 'download_workers', 'ui_victory_animation'):
        assert cfg[key] == _DEFAULTS[key], key
    assert cfg['vault_playlists'] == {'/m': ['https://x/pl']}
    assert cfg['vault_budgets'] == {'/m': 5}
    assert cfg['download_presets'] == [{'name': 'p'}]
    assert cfg['webhooks'] == {'complete': ['https://h']}
