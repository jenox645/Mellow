"""The Feed's SAVE TO history: folders downloads went to, newest first."""
import os
from unittest.mock import patch

from mellow import config, jobs
from mellow.constants import RECENT_OUTPUT_DIRS_KEEP


def test_newest_first_without_duplicates(tmp_path):
    a, b = str(tmp_path / 'Music'), str(tmp_path / 'Videos')
    config.remember_output_dir(a)
    config.remember_output_dir(b)
    assert config.remember_output_dir(a + os.sep) == [a + os.sep, b]   # same folder, kept once
    assert config.load_config()['recent_output_dirs'] == [a + os.sep, b]


def test_keeps_only_the_latest_folders(tmp_path):
    for i in range(RECENT_OUTPUT_DIRS_KEEP + 3):
        config.remember_output_dir(str(tmp_path / f'f{i}'))
    recent = config.load_config()['recent_output_dirs']
    assert len(recent) == RECENT_OUTPUT_DIRS_KEEP
    assert recent[0].endswith(f'f{RECENT_OUTPUT_DIRS_KEEP + 2}')


def test_blank_changes_nothing():
    assert config.remember_output_dir('  ') == []
    assert config.load_config()['recent_output_dirs'] == []


def test_reset_defaults_keeps_the_history(tmp_path):
    config.remember_output_dir(str(tmp_path / 'Music'))
    config.reset_settings()
    assert config.load_config()['recent_output_dirs'] == [str(tmp_path / 'Music')]


def test_a_download_with_a_folder_remembers_it(client, tmp_path):
    folder = str(tmp_path / 'Picked')
    with patch('mellow.downloader.download_video', return_value='success'):
        with_folder = client.post('/api/download', json={'url': 'https://example.com/v', 'output_dir': folder})
        default = client.post('/api/download', json={'url': 'https://example.com/w'})
        jobs.manager.wait_idle()
    assert with_folder.get_json()['recent_output_dirs'] == [folder]
    assert 'recent_output_dirs' not in default.get_json()     # the default folder isn't history
    assert config.load_config()['recent_output_dirs'] == [folder]
