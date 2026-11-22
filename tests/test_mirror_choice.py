"""A playlist saved as MIRROR (ADD PLAYLIST's SYNC MODE).

No job ever deletes: a mirror runs from the folder's sync dialog (preview, then
confirm). The saved choice makes that dialog open on MIRROR, and a sync of the
folder that skipped the preview says at its end that it only added.
"""
from unittest.mock import patch

from mellow import analytics, jobs, library
from mellow.config import load_config, update_config


def _entry(folder, sync_mode):
    analytics.upsert_library_entry({'id': 'm1', 'name': 'Mix', 'url': 'https://x/pl',
                                    'folder': str(folder), 'folder_name': 'Mix',
                                    'use_subfolder': True, 'sync_mode': sync_mode})
    path = str(folder / 'Mix')
    update_config(lambda c: c.setdefault('vault_playlists', {}).__setitem__(path, ['https://x/pl']))
    return path


def _queued_opts(client, route, body):
    """The opts of the job a sync route enqueued (the downloader never runs)."""
    seen = []

    def fake_dl(url, out, opts, cb, *a, **k):
        seen.append(opts)
        cb({'status': 'complete', 'title': url})
        return 'success'
    with patch('mellow.downloader.download_video', side_effect=fake_dl):
        r = client.post(route, json=body)
        assert r.status_code == 200, r.get_json()
        jobs.manager.wait_idle(timeout=10)
    assert len(seen) == 1
    return seen[0]


def test_library_sync_opts_carry_no_sync_mode(tmp_path):
    for mode in ('add', 'mirror'):
        opts, _ = library.build_sync_opts({'url': 'u', 'folder': str(tmp_path), 'sync_mode': mode},
                                          load_config())
        assert 'sync_mode' not in opts
        assert opts.get('mirror_not_applied', False) is (mode == 'mirror')


def test_library_sync_with_mode_mirror_is_an_ordinary_sync(client, tmp_path):
    """The folder view's fallback sends the entry's sync_mode: still add-only."""
    _entry(tmp_path, 'mirror')
    with patch('mellow.vault.confirm_mirror_delete') as deleted:
        opts = _queued_opts(client, '/api/library/m1/sync', {'mode': 'mirror'})
    deleted.assert_not_called()
    assert 'sync_mode' not in opts
    assert opts['mode'] == 'library' and opts['mirror_not_applied'] is True


def test_add_only_entry_syncs_without_the_note(client, tmp_path):
    _entry(tmp_path, 'add')
    assert 'mirror_not_applied' not in _queued_opts(client, '/api/library/m1/sync', {'mode': 'add'})
    assert 'mirror_not_applied' not in _queued_opts(client, '/api/vault/sync', {'path': str(tmp_path / 'Mix')})


def test_folder_sync_of_a_mirror_entry_says_it_only_added(client, tmp_path):
    """The folder's SYNC NOW, SYNC ALL and auto-sync send no mode: the note.
    The sync dialog sends one (ADD ONLY, or the add half of an applied mirror)."""
    path = _entry(tmp_path, 'mirror')
    assert _queued_opts(client, '/api/vault/sync', {'path': path})['mirror_not_applied'] is True
    assert 'mirror_not_applied' not in _queued_opts(client, '/api/vault/sync', {'path': path, 'mode': 'add'})


def test_auto_sync_of_a_mirror_entry_only_adds(client, tmp_path):
    from mellow import server
    path = _entry(tmp_path, 'mirror')
    seen = []

    def fake_dl(url, out, opts, cb, *a, **k):
        seen.append(opts)
        cb({'status': 'complete', 'title': url})
        return 'success'
    with patch('mellow.downloader.download_video', side_effect=fake_dl), \
            patch('mellow.vault.confirm_mirror_delete') as deleted:
        assert server._enqueue_vault_sync(path) is not None     # what the scheduler calls
        jobs.manager.wait_idle(timeout=10)
    deleted.assert_not_called()
    assert seen[0]['mirror_not_applied'] is True


def test_the_sync_dialog_learns_the_saved_mode(client, tmp_path):
    path = _entry(tmp_path, 'mirror')
    assert client.get('/api/vault/playlists?path=' + path).get_json()['sync_mode'] == 'mirror'
    analytics.upsert_library_entry({**analytics.get_library_entry('m1'), 'sync_mode': 'add'})
    assert client.get('/api/vault/playlists?path=' + path).get_json()['sync_mode'] == 'add'
    # A linked folder without a library entry is add-only
    other = str(tmp_path / 'Other')
    update_config(lambda c: c['vault_playlists'].__setitem__(other, ['https://x/o']))
    assert client.get('/api/vault/playlists?path=' + other).get_json()['sync_mode'] == 'add'


def test_the_sync_summary_carries_the_note():
    events = []
    m = jobs.JobManager()
    m._push = events.append

    def fake_dl(url, out, opts, cb, *a, **k):
        cb({'status': 'item_done', 'title': 'Song'})
        cb({'status': 'complete', 'title': url})
        return 'success'
    job = {'id': 's1', 'type': 'sync', 'label': 'Sync — Mix (1 playlist(s))', 'url': 'https://x/pl',
           'multi_urls': ['https://x/pl'], 'output_dir': '', 'library_id': None, 'status': 'active',
           'opts': {'mirror_not_applied': True}}
    with patch('mellow.downloader.download_video', side_effect=fake_dl):
        assert m.run_job(job) == 'complete'
    complete = [e for e in events if e['status'] == 'complete'][0]
    assert complete['sync_summary'] == {'new': 1, 'already': 0, 'failed': 0, 'mirror_not_applied': True}
