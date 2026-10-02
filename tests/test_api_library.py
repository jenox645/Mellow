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


def test_library_sync_does_not_stamp_last_synced_before_it_runs(client, tmp_dir):
    """Stamped when the sync completes; stamping on enqueue called a failed or
    still-queued sync "synced"."""
    from unittest.mock import patch

    from mellow import jobs
    r = client.post('/api/library', json={
        'name': 'Pl', 'url': 'https://youtube.com/playlist?list=X', 'folder': tmp_dir})
    entry_id = r.get_json()['id']
    with patch('mellow.downloader.download_video', return_value='error'):
        assert client.post(f'/api/library/{entry_id}/sync', json={}).status_code == 200
        jobs.manager.wait_idle(timeout=10)
    entry = next(e for e in client.get('/api/library').get_json() if e['id'] == entry_id)
    assert entry['last_synced'] is None


def test_audio_entry_without_audio_format_is_mp3_not_mp4():
    """The legacy "audio format in container" fallback turned the default
    container into audio_format "mp4"."""
    from mellow import library
    entry = library.build_entry({'name': 'A', 'url': 'u', 'mode': 'AUDIO'}, 'id', 'now')
    assert (entry['audio_format'], entry['container']) == ('mp3', 'mp4')
    legacy = library.build_entry({'name': 'A', 'url': 'u', 'mode': 'AUDIO', 'container': 'FLAC'},
                                 'id', 'now')
    assert (legacy['audio_format'], legacy['container']) == ('flac', 'mp4')
    video = library.build_entry({'name': 'V', 'url': 'u', 'mode': 'VIDEO', 'container': 'mkv'},
                                'id', 'now')
    assert (video['audio_format'], video['container']) == ('mp3', 'mkv')


def test_entry_without_folder_syncs_where_the_vault_shows_it(client, tmp_path):
    """An entry with no folder of its own lives in the download folder; the
    vault never listed it."""
    from mellow import analytics, library
    from mellow.config import load_config, update_config
    root = tmp_path / 'root'
    update_config(lambda c: c.__setitem__('output_dir', str(root)))
    analytics.upsert_library_entry({'id': 'e1', 'name': 'Lofi', 'url': 'https://x/pl',
                                    'folder': '', 'folder_name': 'Lofi', 'use_subfolder': True})
    entry = analytics.get_library_entry('e1')
    _, output_dir = library.build_sync_opts(entry, load_config(), 'add')
    assert output_dir == str(root / 'Lofi')
    folders = client.get('/api/vault').get_json()['folders']
    assert [(f['path'], f.get('library_id')) for f in folders] == [(str(root / 'Lofi'), 'e1')]


def test_library_entry_is_not_matched_to_its_parent_folder(client, tmp_path):
    """Syncing the download folder itself must not pick up the settings of a
    library entry that merely lives inside it."""
    from mellow import analytics, server
    from mellow.config import load_config
    analytics.upsert_library_entry({'id': 'e2', 'name': 'Sub', 'url': 'https://x/pl',
                                    'folder': str(tmp_path), 'folder_name': 'Sub'})
    cfg = load_config()
    assert server._library_entry_for(str(tmp_path / 'Sub'), cfg)['id'] == 'e2'
    assert server._library_entry_for(str(tmp_path), cfg) is None
