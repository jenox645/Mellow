"""Moving a vault folder: on disk, and every reference to its path."""
import errno
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mellow import analytics, folder_move, jobs
from mellow.config import load_config, update_config


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'Downloads'
    src = root / 'Wrong Folder'
    (src / 'sub').mkdir(parents=True)
    (src / 'Song [aaaaaaaaaaa].mp3').write_bytes(b'x')
    (src / 'Song [aaaaaaaaaaa].jpg').write_bytes(b'j')
    (src / 'mellow_archive.txt').write_text('youtube aaaaaaaaaaa\n', encoding='utf-8')
    elsewhere = tmp_path / 'Music'
    elsewhere.mkdir()
    s, other = str(src), str(root / 'Other')
    update_config(lambda c: c.update(
        output_dir=str(root),
        vault_playlists={s: ['https://x/pl'], other: ['https://x/o']},
        vault_sync_formats={s: {'sync_audio': True}}, vault_sync_times={s: '2026-10-01T10:00:00'},
        vault_names={s: 'Chill'}, vault_budgets={s: 10}, vault_sync_schedule={s: 'daily'},
        vault_hidden=[str(src / 'sub')], recent_output_dirs=[s, other], watched_folders=[]))
    analytics.upsert_library_entry({'id': 'e1', 'name': 'Chill', 'url': 'https://x/pl',
                                    'folder': str(root), 'folder_name': 'Wrong Folder'})
    analytics.upsert_library_entry({'id': 'e2', 'name': 'Other', 'url': 'https://x/o',
                                    'folder': str(root), 'folder_name': 'Other'})
    song = src / 'Song [aaaaaaaaaaa].mp3'
    analytics.record_download({'url': 'https://youtu.be/aaaaaaaaaaa', 'title': 'Song', 'status': 'success',
                               'file_path': str(song)})
    analytics.record_sync_report(s, 'complete', {'added': ['Song'], 'failed': [], 'filtered': [], 'archived': 0}, 3)
    return root, src, elsewhere


def test_a_folder_moves_with_everything_that_names_it(setup):
    root, src, elsewhere = setup
    new = folder_move.move_folder(str(src), str(elsewhere))
    dest = elsewhere / 'Wrong Folder'
    assert new == str(dest)
    assert not src.exists()
    assert sorted(p.name for p in dest.iterdir()) == [
        'Song [aaaaaaaaaaa].jpg', 'Song [aaaaaaaaaaa].mp3', 'mellow_archive.txt', 'sub']
    cfg, d, other = load_config(), str(dest), str(root / 'Other')
    assert cfg['vault_playlists'] == {d: ['https://x/pl'], other: ['https://x/o']}
    for key, value in (('vault_sync_formats', {'sync_audio': True}), ('vault_sync_times', '2026-10-01T10:00:00'),
                       ('vault_names', 'Chill'), ('vault_budgets', 10), ('vault_sync_schedule', 'daily')):
        assert cfg[key] == {d: value}, key
    assert cfg['vault_hidden'] == [str(dest / 'sub')]           # folders inside it follow
    assert cfg['recent_output_dirs'] == [d, other]
    # Outside the download folder: watched, or the vault would lose it
    assert cfg['watched_folders'] == [d]
    assert cfg['output_dir'] == str(root)
    entries = {e['id']: e for e in analytics.get_library_entries()}
    assert (entries['e1']['folder'], entries['e1']['folder_name']) == (str(elsewhere), 'Wrong Folder')
    assert entries['e2']['folder_name'] == 'Other'               # left alone
    with analytics.get_conn() as con:
        assert con.execute('SELECT file_path FROM downloads').fetchall() == [(str(dest / 'Song [aaaaaaaaaaa].mp3'),)]
        assert con.execute('SELECT folder FROM sync_reports').fetchall() == [(d,)]


def test_moving_back_into_the_download_folder_needs_no_watch(setup):
    root, src, elsewhere = setup
    moved = folder_move.move_folder(str(src), str(elsewhere))
    folder_move.move_folder(moved, str(root))
    cfg = load_config()
    assert str(src) in cfg['vault_playlists']
    assert cfg['watched_folders'] == []          # listed as part of the download folder again


def test_moves_that_cant_be_done_say_why_and_change_nothing(setup, tmp_path):
    root, src, elsewhere = setup
    (elsewhere / 'Wrong Folder').mkdir()
    before = load_config()
    for into, words in ((str(elsewhere), 'already'), (str(src / 'sub'), 'inside itself'),
                        (str(tmp_path / 'nope'), "doesn't exist")):
        with pytest.raises(folder_move.MoveError, match=words):
            folder_move.move_folder(str(src), into)
    with pytest.raises(folder_move.MoveError, match='no longer exists'):
        folder_move.move_folder(str(tmp_path / 'gone'), str(elsewhere))
    assert src.is_dir() and load_config() == before


def test_across_drives_it_copies_then_deletes_and_a_failed_copy_leaves_the_original(setup):
    root, src, elsewhere = setup
    cross = OSError(errno.EXDEV, 'Invalid cross-device link')
    with patch('mellow.folder_move.os.rename', side_effect=cross), \
            patch('mellow.folder_move.shutil.copytree', side_effect=OSError('disk full')):
        with pytest.raises(folder_move.MoveError, match='Nothing was moved'):
            folder_move.move_folder(str(src), str(elsewhere))
    assert src.is_dir() and not (elsewhere / 'Wrong Folder').exists()
    assert str(src) in load_config()['vault_playlists']
    with patch('mellow.folder_move.os.rename', side_effect=cross):
        folder_move.move_folder(str(src), str(elsewhere))
    assert not src.exists() and (elsewhere / 'Wrong Folder' / 'mellow_archive.txt').is_file()


def test_rebase_only_takes_the_folder_and_whats_inside():
    src, dest = os.path.join('a', 'Music'), os.path.join('b', 'Music')
    assert folder_move.rebase(src, src, dest) == dest
    assert folder_move.rebase(os.path.join(src, 'x.mp3'), src, dest) == os.path.join(dest, 'x.mp3')
    assert folder_move.rebase(os.path.join('a', 'Music Videos'), src, dest) is None
    assert folder_move.rebase('', src, dest) is None


def test_the_move_route(client, setup):
    root, src, elsewhere = setup
    assert client.post('/api/vault/move', json={'path': str(src)}).status_code == 400
    with patch.object(jobs.manager, 'uses_folder', return_value=True):
        r = client.post('/api/vault/move', json={'path': str(src), 'into': str(elsewhere)})
        assert r.status_code == 409 and 'queued or running' in r.get_json()['error']
    r = client.post('/api/vault/move', json={'path': str(src), 'into': str(elsewhere)})
    assert r.status_code == 200 and r.get_json()['path'] == str(elsewhere / 'Wrong Folder')
    r = client.post('/api/vault/move', json={'path': str(src), 'into': str(elsewhere)})
    assert r.status_code == 400 and 'no longer exists' in r.get_json()['error']


def test_a_folder_a_job_downloads_into_is_in_use(tmp_path):
    m = jobs.JobManager()
    m._jobs.append({'id': 'j', 'status': 'queued', 'output_dir': str(tmp_path / 'A' / 'sub'), 'sync_path': None})
    assert m.uses_folder(str(tmp_path / 'A'))
    assert not m.uses_folder(str(tmp_path / 'B'))
    m._jobs[0]['status'] = 'complete'
    assert not m.uses_folder(str(tmp_path / 'A'))
    assert Path(tmp_path).is_dir()
