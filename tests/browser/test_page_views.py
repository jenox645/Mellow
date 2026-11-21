"""A theme's own page views: the Feed and the Vault draw what their hooks return.

The app is bundled again with tests/browser/page_views/, which registers two minimal
views for Classic (as gui/themes/slots.jsx registers a theme's), and that bundle is
served in place of static/app.bundle.js. The views' buttons call the hooks' handlers,
which must do what Classic's buttons do.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api").expect

ESBUILD = ROOT / "node_modules" / ".bin" / ("esbuild.cmd" if sys.platform == "win32" else "esbuild")
# What a view of each page can count on (a part of what the hooks return: see CLAUDE.md)
FEED_KEYS = {"url", "setUrl", "handleAnalyze", "analyzing", "info", "mode", "setMode", "quality", "toggles",
             "setToggle", "handleDownload", "dlState", "config", "playlistItems", "searchResults", "pickSearchResult"}
VAULT_KEYS = {"vaultFolders", "selectedFolder", "setSelectedFolder", "folderName", "files", "shownFiles",
              "onFileClick", "selectedFiles", "handleSync", "handleOpenFile", "syncReport", "marquee", "refreshAll"}


@pytest.fixture(scope="module")
def dummy_bundle(tmp_path_factory):
    if not ESBUILD.exists():
        pytest.fail(f"{ESBUILD} is missing: run `npm ci`")
    out = tmp_path_factory.mktemp("bundle") / "app.bundle.js"
    subprocess.run([str(ESBUILD), str(ROOT / "tests" / "browser" / "page_views" / "entry.jsx"), "--bundle",
                    f"--outfile={out}", "--loader:.jsx=jsx", "--target=es2020", "--platform=browser",
                    "--format=iife", "--jsx=transform", "--jsx-factory=React.createElement",
                    "--jsx-fragment=React.Fragment", "--log-level=warning"], check=True)
    return out.read_text(encoding="utf-8")


@pytest.fixture
def dummy_page(browser, app_url, downloads, dummy_bundle):
    from mellow import session
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/app.bundle.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=dummy_bundle))
    page.goto(f"{app_url}/launch?t={session.launch_token()}")
    page.locator(".nav-item").first.wait_for()
    yield page
    context.close()
    assert not errors, errors


def _keys(page, selector):
    return set(page.locator(selector).get_attribute("data-keys").split())


def test_a_feed_view_gets_the_feeds_data_and_its_analyze_works(dummy_page):
    page = dummy_page
    analyzed = []

    def info(route):
        analyzed.append(route.request.post_data_json["url"])
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"title": "A Made-Up Video", "is_playlist": False, "platform": "YouTube",
                                       "webpage_url": analyzed[-1]}))
    page.route("**/api/info", info)
    expect(page.locator("#dummy-feed")).to_be_visible()
    assert page.locator(".url-input").count() == 0          # Classic's view isn't drawn
    assert FEED_KEYS <= _keys(page, "#dummy-feed")
    expect(page.locator("#dummy-mode")).to_have_text("video 1080p")   # the Feed's defaults
    page.locator("#dummy-url").fill("https://www.youtube.com/watch?v=abc")
    page.locator("#dummy-analyze").click()
    expect(page.locator("#dummy-title")).to_have_text("A Made-Up Video")
    assert analyzed == ["https://www.youtube.com/watch?v=abc"]
    # Kept like Classic's Feed keeps it: back from another page, the analysis is still there
    page.keyboard.press("2")
    page.keyboard.press("1")
    expect(page.locator("#dummy-title")).to_have_text("A Made-Up Video")


def test_a_vault_view_gets_the_folders_and_opening_one_loads_its_files(dummy_page, downloads):
    page = dummy_page
    (downloads / "Lofi").mkdir()
    (downloads / "Lofi" / "rain.mp3").write_bytes(b"\0" * 2048)
    (downloads / "Lofi" / "snow.mp3").write_bytes(b"\0" * 2048)
    page.keyboard.press("3")
    expect(page.locator("#dummy-vault")).to_be_visible()
    assert VAULT_KEYS <= _keys(page, "#dummy-vault")
    expect(page.locator("#dummy-open")).to_have_text("ROOT")
    page.locator("#dummy-refresh").click()       # Classic's ↻ REFRESH: the new folder shows
    page.locator(".dummy-folder", has_text="Lofi").click()
    expect(page.locator("#dummy-open")).to_have_text("Lofi")
    expect(page.locator(".dummy-file")).to_have_text(["rain.mp3", "snow.mp3"])


def test_classic_views_are_what_a_theme_without_its_own_gets(page):
    # The normal bundle: Classic's Feed, and nothing of the dummies
    expect(page.locator(".url-input")).to_be_visible()
    assert page.locator("#dummy-feed").count() == 0
    assert Path(ROOT / "static" / "app.bundle.js").read_text(encoding="utf-8").count("dummy-feed") == 0
