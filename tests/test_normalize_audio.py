"""Normalize Volume: loudness evened out during the audio conversion."""
import re
import shutil
import subprocess

import pytest
import yt_dlp

from mellow import analytics, config, downloader, library, vault

needs_ffmpeg = pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg not installed')


def test_the_extract_audio_step_is_swapped_keeping_its_settings():
    with yt_dlp.YoutubeDL({'quiet': True, 'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
            {'key': 'FFmpegMetadata'}]}) as ydl:
        assert downloader._ExtractAudioNormalized.replacing(ydl)
        pps = ydl._pps['post_process']
        assert type(pps[0]) is downloader._ExtractAudioNormalized
        assert pps[0].mapping == 'mp3' and pps[0]._preferredquality == 192
        assert type(pps[1]).__name__ == 'FFmpegMetadataPP'      # order kept
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        assert not downloader._ExtractAudioNormalized.replacing(ydl)


def _lufs(path):
    err = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-af', 'ebur128',
                          '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', err)[-1])


@needs_ffmpeg
@pytest.mark.parametrize('target, source', [('mp3', 'wav'), ('m4a', 'm4a')])
def test_quiet_audio_comes_out_at_the_target_loudness(tmp_path, target, source):
    # m4a → m4a is the case yt-dlp would only copy: it is re-encoded instead
    src = tmp_path / ('quiet.' + source)
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
                    '-af', 'volume=0.05', '-ar', '44100', *(['-c:a', 'aac'] if source == 'm4a' else []),
                    str(src)], check=True)
    assert _lufs(src) < -30
    with yt_dlp.YoutubeDL({'quiet': True, 'ffmpeg_location': shutil.which('ffmpeg')}) as ydl:
        pp = downloader._ExtractAudioNormalized(ydl, preferredcodec=target, preferredquality=0)
        _, info = pp.run({'filepath': str(src), 'ext': source})
    out = tmp_path / ('quiet.' + target)
    assert info['filepath'] == str(out) and out.exists()
    assert abs(_lufs(out) - (-14)) < 1.5


def test_the_option_reaches_vault_syncs_and_library_entries(tmp_dir):
    cfg = config.load_config()
    assert vault.build_sync_opts({'sync_audio': True, 'normalize_audio': True}, None, cfg, tmp_dir)['normalize_audio']
    assert not vault.build_sync_opts({}, None, cfg, tmp_dir)['normalize_audio']
    analytics.upsert_library_entry({'id': 'n1', 'name': 'Lofi', 'url': 'https://x/pl', 'folder': tmp_dir,
                                    'mode': 'AUDIO', 'normalize_audio': True})
    entry = analytics.get_library_entry('n1')
    assert entry['normalize_audio'] is True
    opts, _ = library.build_sync_opts(entry, cfg, 'add')
    assert opts['normalize_audio'] is True
    assert vault.default_sync_format('', entry, cfg)['normalize_audio'] is True
