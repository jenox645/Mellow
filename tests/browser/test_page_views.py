"""A theme's own page views: every page draws what its hook returns.

The app is bundled again with tests/browser/page_views/, which registers a minimal
view of each page for Classic (as gui/themes/slots.jsx registers a theme's), and that bundle is
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
QUEUE_KEYS = {"dlState", "activeJobs", "playlistItems", "completedItems", "failedItems", "syncPlan", "jobs",
              "activeCount", "queuedJobsCount", "handleCancelJob", "startJobNow", "retryJob", "handleReorder",
              "handleCancel", "qTab", "setQTab", "handleRetryFailed", "handleRetryAll", "onPause", "onResume"}
ANALYTICS_KEYS = {"stats", "range", "setRange", "localStats", "statVal", "saveOverride", "hourly", "dailyTrend",
                  "dailyFailures", "handleExport", "wrappedOpen", "openWrapped", "wrappedData", "historyRows",
                  "searchHistory", "historyNext", "redownloadHistoryRow", "deleteHistoryRow"}
SIGNAL_KEYS = {"presets", "activePreset", "pickPreset", "sql", "editSql", "runQuery", "running", "result",
               "schemaText", "baseUrl", "webhooks", "saveWebhooks", "removeWebhook", "eventsOpen", "liveEvents"}
CONFIG_KEYS = {"config", "setConfig", "sysInfo", "local", "set", "handleSave", "handleReset", "browseFolder",
               "namePreview", "testCookies", "doVacuum", "downloadBackup", "handleRestoreFile", "checkAppUpdate",
               "checkUpdate", "updateYtdlp", "openReleasePage", "currentTheme", "pickTheme", "doPurge",
               "setDesktopNotifications"}


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


def _wait_for(page, check, timeout_ms=5000):
    for _ in range(timeout_ms // 100):
        if check():
            return
        page.wait_for_timeout(100)
    assert check()


def _json(body):
    return lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def test_a_queue_view_gets_the_jobs_and_start_now_works(dummy_page):
    page = dummy_page
    started = []
    later = 4_102_444_800   # 2100: a ⏾ job that isn't due
    page.route("**/api/queue/status", _json({"jobs": [
        {"id": "j1", "type": "feed", "label": "Tonight's download", "url": "https://youtu.be/x", "status": "queued",
         "queue_position": 0, "not_before": later}]}))

    def start_now(route):
        started.append(route.request.url.rsplit("/api/queue/", 1)[1])
        route.fulfill(status=200, content_type="application/json", body="{}")
    page.route("**/api/queue/*/start-now", start_now)
    page.keyboard.press("2")
    expect(page.locator("#dummy-queue")).to_be_visible()
    assert page.locator("[data-tour=queue-stats]").count() == 0      # Classic's isn't drawn
    assert QUEUE_KEYS <= _keys(page, "#dummy-queue")
    expect(page.locator("#dummy-counts")).to_have_text("0 active · 1 queued · tab pending")
    page.locator(".dummy-job", has_text="Tonight's download").click()
    _wait_for(page, lambda: started)
    assert started == ["j1/start-now"]


def test_an_analytics_view_gets_its_range_and_history(dummy_page):
    page = dummy_page
    ranges, searches = [], []

    def stats(route):
        rng = route.request.url.split("range=")[1] if "range=" in route.request.url else None
        ranges.append(rng)
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"total_downloads": {"7d": 7, "30d": 30}.get(rng, 0)}))

    def history(route):
        search = (route.request.url.split("search=")[1].split("&")[0] if "search=" in route.request.url else "")
        searches.append(search)
        rows = [{"id": 1, "title": "rain on a tin roof"}, {"id": 2, "title": "snow day"}]
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps([r for r in rows if search in r["title"]]))
    page.route("**/api/stats?range=*", stats)
    page.route("**/api/history?*", history)
    page.keyboard.press("4")
    expect(page.locator("#dummy-analytics")).to_be_visible()
    assert page.locator(".range-tabs").count() == 0
    assert ANALYTICS_KEYS <= _keys(page, "#dummy-analytics")
    expect(page.locator("#dummy-range")).to_have_text("30d 30")
    page.locator("#dummy-7d").click()
    expect(page.locator("#dummy-range")).to_have_text("7d 7")
    assert ranges == ["30d", "7d"]
    expect(page.locator(".dummy-row")).to_have_text(["rain on a tin roof", "snow day"])
    page.locator("#dummy-history-search").fill("rain")
    expect(page.locator(".dummy-row")).to_have_text(["rain on a tin roof"])
    assert searches[-1] == "rain"


def test_a_signal_view_runs_a_preset_query(dummy_page):
    page = dummy_page
    sent = []
    page.on("request", lambda r: sent.append(r.post_data_json["sql"]) if r.url.endswith("/api/analytics/query") else None)
    page.keyboard.press("5")
    expect(page.locator("#dummy-signal")).to_be_visible()
    assert page.locator(".query-textarea").count() == 0
    assert SIGNAL_KEYS <= _keys(page, "#dummy-signal")
    expect(page.locator("#dummy-result")).to_have_text("NO RESULT")
    page.locator(".dummy-preset", has_text="Storage by format").click()
    page.locator("#dummy-run").click()
    expect(page.locator("#dummy-result")).to_have_text("0 rows")      # the real query, on this test's empty DB
    assert len(sent) == 1 and sent[0].startswith("SELECT format, COUNT(*)")


def test_a_config_view_edits_and_saves_a_setting(dummy_page):
    from mellow import config
    page = dummy_page
    page.keyboard.press("6")
    expect(page.locator("#dummy-config")).to_be_visible()
    assert page.locator(".cfg-layout").count() == 0
    assert CONFIG_KEYS <= _keys(page, "#dummy-config")
    expect(page.locator("#dummy-theme")).to_have_text("classic")
    page.locator("#dummy-template").fill("%(uploader)s - %(title)s.%(ext)s")
    # The server's /api/filename-preview names its sample video with what's typed
    expect(page.locator("#dummy-preview")).to_have_text("Rick Astley - Never Gonna Give You Up (Official Video).mp4")
    page.locator("#dummy-save").click()
    _wait_for(page, lambda: config.load_config().get("filename_template") == "%(uploader)s - %(title)s.%(ext)s")


def test_classic_views_are_what_a_theme_without_its_own_gets(page):
    # The normal bundle: Classic's Feed, and nothing of the dummies
    expect(page.locator(".url-input")).to_be_visible()
    assert page.locator("#dummy-feed").count() == 0
    assert Path(ROOT / "static" / "app.bundle.js").read_text(encoding="utf-8").count("dummy-feed") == 0
