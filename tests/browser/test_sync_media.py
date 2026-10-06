"""Vault syncs with real downloads: yt-dlp + ffmpeg against the local media site.

The videos of /playlist-dash come as separate video and audio streams, like
YouTube, so every item is two parts merged by ffmpeg. No browser involved;
these run with the browser tests because they need the same media site.
"""
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest
from conftest import DASH_AUDIO_REFUSED, DASH_CLIPS

pytestmark = pytest.mark.browser
SYNC_TIMEOUT_SECS = 120


def _api(app_url, path, body=None):
    req = Request(app_url + path, data=None if body is None else json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _sync(app_url, folder):
    from mellow import jobs
    _api(app_url, "/api/vault/sync", {"path": str(folder), "sync_audio": False, "container": "mp4"})
    assert jobs.manager.wait_idle(SYNC_TIMEOUT_SECS)


def _streams(path):
    out = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return sorted(s["codec_type"] for s in json.loads(out.stdout)["streams"])


@pytest.fixture
def linked_folder(app_url, media_site, downloads):
    from mellow import config
    folder = downloads / "Dash Mix"
    folder.mkdir()
    url = f"{media_site}/playlist-dash"
    config.update_config(lambda c: c.update(vault_playlists={str(folder): [url]}))
    yield folder
    DASH_AUDIO_REFUSED.clear()


def test_a_sync_merges_video_and_audio(app_url, linked_folder):
    _sync(app_url, linked_folder)
    files = _api(app_url, "/api/vault/folder?path=" + quote(str(linked_folder)))["files"]
    assert len(files) == len(DASH_CLIPS)
    for f in files:
        assert _streams(f["path"]) == ["audio", "video"], f["name"]
    # Nothing but the finished files (and their archive) is left behind
    leftovers = [p.name for p in linked_folder.iterdir() if ".f" in p.stem and p.suffix != ".jpg"]
    assert leftovers == []


def test_an_item_whose_audio_fails_is_finished_by_the_next_sync(app_url, linked_folder):
    """The silent-video bug: the failed item's video part stayed behind, showed
    in the vault as a finished video with no sound, and was never redone."""
    DASH_AUDIO_REFUSED.add("dash-two")
    _sync(app_url, linked_folder)

    on_disk = sorted(p.name for p in linked_folder.iterdir())
    assert any(".f" in Path(n).stem for n in on_disk), on_disk   # yt-dlp kept the video part
    listed = _api(app_url, "/api/vault/folder?path=" + quote(str(linked_folder)))["files"]
    assert [_streams(f["path"]) for f in listed] == [["audio", "video"]]   # the part isn't listed
    report = _api(app_url, "/api/vault/sync-report?path=" + quote(str(linked_folder)))
    assert "403" in json.dumps(report)                                      # and the report says why

    DASH_AUDIO_REFUSED.clear()
    _sync(app_url, linked_folder)
    listed = _api(app_url, "/api/vault/folder?path=" + quote(str(linked_folder)))["files"]
    assert len(listed) == len(DASH_CLIPS)
    for f in listed:
        assert _streams(f["path"]) == ["audio", "video"], f["name"]
    assert not [p.name for p in linked_folder.iterdir() if ".f" in p.stem and p.suffix != ".jpg"]


def test_a_second_sync_downloads_nothing_already_there(app_url, linked_folder):
    _sync(app_url, linked_folder)
    before = {p.name: p.stat().st_mtime for p in linked_folder.iterdir()}
    _sync(app_url, linked_folder)
    assert {p.name: p.stat().st_mtime for p in linked_folder.iterdir()} == before
    report = _api(app_url, "/api/vault/sync-report?path=" + quote(str(linked_folder)))["report"]
    assert report["added"] == [] and report["archived"] == len(DASH_CLIPS), report


def test_an_audio_sync_saves_mp3s(app_url, linked_folder):
    from mellow import jobs
    _api(app_url, "/api/vault/sync", {"path": str(linked_folder), "sync_audio": True, "audio_format": "mp3"})
    assert jobs.manager.wait_idle(SYNC_TIMEOUT_SECS)
    files = _api(app_url, "/api/vault/folder?path=" + quote(str(linked_folder)))["files"]
    assert len(files) == len(DASH_CLIPS) and all(f["ext"] == "mp3" for f in files), files
    for f in files:
        assert "audio" in _streams(f["path"]), f["name"]
    # The folder remembers its format: a sync without options (auto-sync, SYNC ALL) stays MP3
    assert _api(app_url, "/api/config")["vault_sync_formats"][str(linked_folder)]["sync_audio"] is True
