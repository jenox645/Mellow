"""Downloading what is already in the folder again, with yt-dlp and ffmpeg
against the local media site (no browser; it needs the site)."""
import json
import os
from unittest.mock import patch
from urllib.request import Request, urlopen

import pytest

pytestmark = pytest.mark.browser
DOWNLOAD_TIMEOUT_SECS = 60


def _download(app_url, url, mode):
    from mellow import jobs
    body = {"url": url, "mode": mode, "quality": "best", "container": "mp4", "audio_format": "mp3"}
    req = Request(app_url + "/api/download", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=30):
        pass
    assert jobs.manager.wait_idle(DOWNLOAD_TIMEOUT_SECS)


def _history():
    from mellow import analytics
    return [h for h in analytics.get_history(limit=100) if h["status"] == "success"]


def test_audio_already_there_is_neither_converted_nor_recorded_again(app_url, media_site, downloads):
    _download(app_url, f"{media_site}/clip.mp4", "audio")
    (song,) = [p for p in downloads.iterdir() if p.suffix == ".mp3"]
    first = os.stat(song)
    assert len(_history()) == 1

    import yt_dlp
    with patch.object(yt_dlp.YoutubeDL, "dl", autospec=True, side_effect=yt_dlp.YoutubeDL.dl) as dl:
        _download(app_url, f"{media_site}/clip.mp4", "audio")
    # Found already there: nothing downloaded (and so nothing converted) a second time
    dl.assert_not_called()
    assert os.path.getsize(song) == first.st_size
    assert sorted(p.name for p in downloads.iterdir() if p.suffix in (".mp3", ".mp4")) == [song.name]
    assert len(_history()) == 1


def test_a_playlist_downloaded_twice_is_recorded_once(app_url, media_site, downloads):
    _download(app_url, f"{media_site}/playlist", "video")
    assert len(_history()) == 3
    _download(app_url, f"{media_site}/playlist", "video")
    assert len(_history()) == 3
