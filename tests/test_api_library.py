def test_library_crud(client, tmp_dir):
    entry = {
        'name': 'Test',
        'url': 'https://youtube.com/playlist?list=X',
        'folder': tmp_dir,
        'folder_name': 'Test',
        'quality': '1080p',
        'mode': 'VIDEO',
        'sync_mode': 'add',
    }
    r = client.post('/api/library', json=entry)
    assert r.status_code in (200, 201)

    r2 = client.get('/api/library')
    entries = r2.get_json()
    assert any(e['name'] == 'Test' for e in entries)
    entry_id = next(e['id'] for e in entries if e['name'] == 'Test')

    r3 = client.delete('/api/library/' + entry_id)
    assert r3.status_code == 200

    r4 = client.get('/api/library')
    assert not any(e['name'] == 'Test' for e in r4.get_json())


def test_library_sync_requires_library(client):
    r = client.post('/api/library/nonexistent-id/sync', json={})
    assert r.status_code in (400, 404)


def test_library_list_empty(client):
    r = client.get('/api/library')
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
