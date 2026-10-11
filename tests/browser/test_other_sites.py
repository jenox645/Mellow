"""A web page from another site must not be able to use MellowDLP's local
server: not load a file from it, not make it run ffmpeg, not frame it.

The app listens on 127.0.0.1; the "other site" here is served as localhost,
which a browser counts as a different site."""
import shutil
import time

import pytest
from conftest import ROOT, _serve
from flask import Flask

pytestmark = pytest.mark.browser


@pytest.fixture
def other_site(app_url, downloads):
    private = downloads / "private.png"
    shutil.copy(ROOT / "assets" / "banner.png", private)
    clip = downloads / "holiday.mp4"
    shutil.copy(next(ROOT.glob("assets/*.png")), clip)   # any file: ffmpeg would be asked to read it
    site = Flask("other_site")

    @site.route("/")
    def page():
        return (f'<img id="photo" src="{app_url}/api/vault/thumb?path={private}">'
                f'<img id="video" src="{app_url}/api/vault/thumb?path={clip}">'
                f'<iframe id="app" src="{app_url}/"></iframe>')

    url, stop = _serve(site)
    yield url.replace("127.0.0.1", "localhost"), clip
    stop()


def test_another_site_cannot_load_or_frame_the_app(browser, other_site):
    url, clip = other_site
    context = browser.new_context()
    page = context.new_page()
    page.goto(url)
    page.wait_for_function("[...document.images].every(i => i.complete)")
    time.sleep(1)
    widths = page.evaluate("[...document.images].map(i => i.naturalWidth)")
    assert widths == [0, 0], "a page from another site displayed a file from this computer"
    # The thumbnail request never reached the code that writes a sidecar
    assert not (clip.parent / (clip.stem + ".jpg")).exists()
    framed = page.frame_locator("#app").locator(".nav-item")
    assert framed.count() == 0, "another site framed the app"
    context.close()
