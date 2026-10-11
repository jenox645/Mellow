"""A download whose title is too long for a file name, with yt-dlp and ffmpeg
against the local media site (no browser; it needs the same site)."""
import json
from urllib.request import Request, urlopen

import pytest
from conftest import LONG_TITLE

pytestmark = pytest.mark.browser
DOWNLOAD_TIMEOUT_SECS = 60


def _api(app_url, path, body=None):
    req = Request(app_url + path, data=None if body is None else json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


@pytest.mark.parametrize("mode", ["video", "audio"])
def test_a_title_too_long_for_a_file_name_is_shortened(app_url, media_site, downloads, mode):
    from mellow import jobs
    _api(app_url, "/api/download", {"url": f"{media_site}/titled/clip", "mode": mode,
                                     "quality": "best", "container": "mp4", "audio_format": "mp3"})
    assert jobs.manager.wait_idle(DOWNLOAD_TIMEOUT_SECS)

    media = [p for p in downloads.iterdir() if p.suffix in (".mp4", ".mp3")]
    assert len(media) == 1, sorted(p.name for p in downloads.iterdir())
    name = media[0].name
    assert len(name.encode()) <= 255
    assert name.startswith(LONG_TITLE[:20])          # still the video's title, cut short
    # The history knows the file
    rows = _api(app_url, "/api/history?limit=5")
    assert [r["status"] for r in rows] == ["success"], rows
