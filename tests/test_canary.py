"""The canary must fail on extractor breakage but not on a blocked runner."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    'canary', Path(__file__).resolve().parent.parent / 'scripts' / 'canary.py')
canary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canary)


def _run(video_side_effect, playlist_side_effect=None):
    with patch('mellow.downloader.get_video_info', side_effect=video_side_effect), \
            patch('mellow.downloader.get_playlist_items',
                  side_effect=playlist_side_effect or (lambda url: [{'id': 'x'}])):
        return canary.main()


def test_all_probes_ok():
    assert _run(lambda url: {'title': 'T'}) == 0


def test_login_wall_is_a_warning_not_a_failure(capsys):
    def video(url):
        if 'archive.org' in url:
            raise RuntimeError('ERROR: [vimeo] 1: The web client only works when logged-in. '
                               'Use --cookies, --cookies-from-browser ...')
        return {'title': 'T'}
    assert _run(video) == 0
    assert '::warning title=Canary probe blocked::' in capsys.readouterr().out


def test_bot_check_on_every_probe_is_inconclusive_not_red(capsys):
    def blocked(url):
        raise RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot.")
    assert _run(blocked, blocked) == 0
    assert 'Canary inconclusive' in capsys.readouterr().out


def test_extractor_breakage_fails_the_run(capsys):
    def video(url):
        raise RuntimeError('ERROR: [youtube] x: Unable to extract player response')
    assert _run(video) == 1
    assert '::error title=Canary probe failed::' in capsys.readouterr().out


def test_empty_result_counts_as_breakage():
    assert _run(lambda url: {}) == 1
    assert _run(lambda url: {'title': 'T'}, lambda url: []) == 1
