"""Browser smoke tests: the main flows, clicked through the real UI.

Real downloads (yt-dlp + ffmpeg) from the local media site; only the YouTube
search itself is faked. See conftest.py for what they need.
"""
import json
import re
from unittest.mock import patch
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api").expect

DOWNLOAD_TIMEOUT_MS = 60_000


def _analyze(page, url):
    page.get_by_placeholder(re.compile("youtube", re.I)).fill(url)
    page.get_by_text("ANALYZE →").click()
    page.locator(".info-actions .btn-primary").wait_for(timeout=30_000)


def _notification(page, pattern):
    toast = page.locator(".notif", has_text=re.compile(pattern))
    toast.last.wait_for(timeout=DOWNLOAD_TIMEOUT_MS)
    return toast.last.inner_text()


def _files(folder):
    return sorted(p.name for p in folder.rglob("*") if p.is_file() and p.suffix != ".jpg")


def _get(app_url, path):
    with urlopen(app_url + path) as resp:
        return json.loads(resp.read())


def test_download_a_video(page, media_site, downloads):
    _analyze(page, f"{media_site}/clip.mp4")
    page.locator(".info-actions .btn-primary").click()
    assert "clip" in _notification(page, "Download Complete")
    assert any(name.startswith("clip") for name in _files(downloads))
    # The finished item is listed with its file
    page.locator(".nav-item", has_text=re.compile("queue", re.I)).first.click()
    page.get_by_text("clip", exact=False).first.wait_for()


def test_playlist_without_a_removed_item(page, media_site, downloads):
    _analyze(page, f"{media_site}/playlist")
    rows = page.locator(".pl-queue-item")
    expect(rows).to_have_count(3)
    rows.nth(1).locator(".pl-queue-remove").click()
    expect(rows).to_have_count(2)
    page.locator(".info-actions .btn-primary").click()
    page.get_by_text("JUST DOWNLOAD").click()
    _notification(page, "Download Complete")
    names = _files(downloads)
    assert len(names) == 2, names
    assert not any("second" in name for name in names), names


def test_search_then_pick_a_result(page, media_site):
    results = [
        {"idx": i, "id": name, "title": f"Lofi beats — {name}", "url": f"{media_site}/{name}.mp4",
         "thumbnail": "", "duration": 2, "uploader": "Mellow Records", "view_count": 1000 * i}
        for i, name in enumerate(["clip", "third"], start=1)
    ]
    with patch("mellow.downloader.search", return_value=results) as search:
        box = page.get_by_placeholder(re.compile("youtube", re.I))
        box.fill("lofi beats")
        box.press("Enter")
        rows = page.locator(".search-result")
        expect(rows).to_have_count(2)
        assert search.call_args.args[0] == "lofi beats"
    rows.nth(1).click()
    page.locator(".info-actions .btn-primary").wait_for(timeout=30_000)
    assert box.input_value() == f"{media_site}/third.mp4"
    expect(page.locator(".info-title")).to_contain_text("third")


def test_cancel_a_running_download(page, app_url, media_site, downloads):
    _analyze(page, f"{media_site}/slow/long.mp4")   # served at ~250 KB/s
    page.locator(".info-actions .btn-primary").click()
    page.get_by_text("CANCEL", exact=True).click(timeout=30_000)
    _notification(page, "Cancelled")
    statuses = [job["status"] for job in _get(app_url, "/api/queue/status")["jobs"]]
    assert "cancelled" in statuses, statuses
    assert not any(name.endswith(".mp4") for name in _files(downloads))


def test_add_a_playlist_to_the_vault(page, app_url, media_site, downloads):
    page.locator(".nav-item", has_text=re.compile("vault", re.I)).first.click()
    page.get_by_text("ADD PLAYLIST", exact=True).click()
    page.get_by_placeholder("My Playlist").fill("Test Mix")
    page.get_by_placeholder("https://youtube.com/playlist?list=...").fill(f"{media_site}/playlist")
    page.get_by_text("ADD TO VAULT", exact=True).click()
    page.get_by_text("Test Mix").first.wait_for()
    entry = next(e for e in _get(app_url, "/api/library") if e["name"] == "Test Mix")
    assert entry["url"] == f"{media_site}/playlist"
