import os
from unittest.mock import patch


def test_vault_list_empty(client):
    r = client.get('/api/vault')
    assert r.status_code == 200
    assert 'folders' in r.get_json()


def test_vault_watch_add_remove(client, tmp_dir):
    r = client.post('/api/vault/watch', json={'path': tmp_dir})
    assert r.status_code == 200
    r2 = client.get('/api/vault/watch')
    data2 = r2.get_json()
    folders2 = data2.get('folders', data2.get('watched_folders', []))
    assert tmp_dir in folders2
    client.delete('/api/vault/watch', json={'path': tmp_dir})
    r3 = client.get('/api/vault/watch')
    data3 = r3.get_json()
    folders3 = data3.get('folders', data3.get('watched_folders', []))
    assert tmp_dir not in folders3


def test_vault_folder_list_files(client, tmp_dir):
    fpath = os.path.join(tmp_dir, 'test.mp4')
    open(fpath, 'w').close()
    r = client.get('/api/vault/folder?path=' + tmp_dir)
    assert r.status_code == 200
    files = r.get_json().get('files', [])
    assert any(f['name'] == 'test.mp4' for f in files)


def test_vault_playlists_crud(client, tmp_dir):
    url = 'https://youtube.com/playlist?list=TEST'
    r = client.post('/api/vault/playlists', json={'path': tmp_dir, 'url': url})
    assert r.status_code == 200
    r2 = client.get('/api/vault/playlists?path=' + tmp_dir)
    assert url in r2.get_json().get('playlists', [])
    client.delete('/api/vault/playlists', json={'path': tmp_dir, 'url': url})
    r3 = client.get('/api/vault/playlists?path=' + tmp_dir)
    assert url not in r3.get_json().get('playlists', [])


def test_vault_play_files_opens(client, tmp_dir):
    fpath = os.path.join(tmp_dir, 'test.mp4')
    open(fpath, 'w').close()
    with patch('server._open_file') as mock_open:
        with patch('subprocess.Popen') as mock_popen:
            r = client.post('/api/vault/play-files', json={'paths': [fpath]})
            assert r.status_code == 200
            data = r.get_json()
            assert data.get('status') == 'ok'
            # Either VLC was launched directly or _open_file was used for m3u fallback
            launched = mock_open.called or mock_popen.called
            assert launched, "Expected either _open_file or subprocess.Popen to be called"


def test_vault_thumb_unicode_filename(client, tmp_dir):
    """Thumb endpoint must handle filenames with ⧸, ：, quotes, and Japanese characters."""
    # Create a fake video file and sidecar jpg with special Unicode name
    tricky = '「天使のテーゼ」⧸Zankoku na Tenshi no Te-ze "Thesis".mp4'
    vpath = os.path.join(tmp_dir, tricky)
    jpath = os.path.join(tmp_dir, tricky.replace('.mp4', '.jpg'))
    open(vpath, 'w').close()
    # Create a minimal valid JPEG (smallest valid JPEG bytes)
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9,
    ])
    open(jpath, 'wb').write(jpeg_bytes)
    from urllib.parse import quote
    r = client.get('/api/vault/thumb?path=' + quote(vpath))
    assert r.status_code == 200
    assert r.content_type.startswith('image/')


def test_vault_play_files_empty(client):
    r = client.post('/api/vault/play-files', json={'paths': []})
    assert r.status_code == 400


def test_vault_sync_requires_playlist(client, tmp_dir):
    r = client.post('/api/vault/sync', json={'path': tmp_dir, 'mode': 'add'})
    assert r.status_code in (400, 404)
