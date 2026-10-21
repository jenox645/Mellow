"""Two different videos with the same title, downloaded into one folder, with
yt-dlp and ffmpeg against the local media site (no browser; it needs the site)."""
import json
import shutil
import subprocess
from urllib.request import Request, urlopen

import pytest
from conftest import CLIPS, signed_in

pytestmark = pytest.mark.browser
DOWNLOAD_TIMEOUT_SECS = 60


def _download(app_url, url, mode):
    from mellow import jobs
    body = {"url": url, "mode": mode, "quality": "best", "container": "mp4", "audio_format": "mp3"}
    req = Request(app_url + "/api/download", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json", **signed_in()}, method="POST")
    with urlopen(req, timeout=30):
        pass
    assert jobs.manager.wait_idle(DOWNLOAD_TIMEOUT_SECS)


def _seconds(path):
    out = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return round(float(json.loads(out.stdout)["format"]["duration"]))


@pytest.mark.parametrize("mode, ext", [("audio", ".mp3"), ("video", ".mp4")])
def test_a_second_video_with_the_same_title_gets_its_own_file(app_url, media_site, downloads, mode, ext):
    _download(app_url, f"{media_site}/intro/clip", mode)
    _download(app_url, f"{media_site}/intro/second", mode)
    media = sorted(p.name for p in downloads.iterdir() if p.suffix == ext)
    # The first keeps the title; the second adds its id (the site's own, here "second-1")
    assert len(media) == 2, media
    first = next(n for n in media if "[" not in n)
    second = next(n for n in media if n != first)
    assert second.startswith(first[:-len(ext)] + " [second") and second.endswith(f"]{ext}"), media
    # Each file is its own video (the second didn't overwrite the first)
    assert _seconds(downloads / first) == CLIPS["clip"][0]
    assert _seconds(downloads / second) == CLIPS["second"][0]

    # The first video again: recognised, not saved a third time
    _download(app_url, f"{media_site}/intro/clip", mode)
    assert sorted(p.name for p in downloads.iterdir() if p.suffix == ext) == media
