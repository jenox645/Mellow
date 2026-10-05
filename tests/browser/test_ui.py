"""Browser smoke tests: the main flows, clicked through the real UI.

Real downloads (yt-dlp + ffmpeg) from the local media site; only the YouTube
search itself is faked. See conftest.py for what they need.
"""
import json
import re
import time
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


def _wait_for_file(folder, prefix, timeout=DOWNLOAD_TIMEOUT_MS / 1000):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if folder.exists() and any(n.startswith(prefix) and n.endswith(".mp4") for n in _files(folder)):
            return
        time.sleep(0.3)
    raise AssertionError(f"no {prefix}*.mp4 in {folder}")


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


def test_save_to_a_folder_then_recall_it_with_the_arrows(page, media_site, downloads):
    music, videos = downloads / "Music", downloads / "Videos"
    save_to = page.locator(".save-to-row input")
    for folder, clip in ((music, "clip"), (videos, "third")):
        save_to.fill(str(folder))
        save_to.press("Enter")
        _analyze(page, f"{media_site}/{clip}.mp4")
        page.locator(".info-actions .btn-primary").click()
        _wait_for_file(folder, clip)
    assert not any(p.suffix == ".mp4" for p in downloads.glob("*"))    # nothing in the default folder

    # Like a terminal prompt: ↑ older, ↓ newer, Esc back to what was typed
    save_to.fill("")
    menu = page.locator(".folder-menu .folder-opt")
    expect(menu).to_have_count(2)
    save_to.press("ArrowUp")
    expect(save_to).to_have_value(str(videos))
    expect(page.locator(".folder-opt.active")).to_contain_text("Videos")
    save_to.press("ArrowUp")
    expect(save_to).to_have_value(str(music))
    save_to.press("ArrowUp")                         # the oldest: stays
    expect(save_to).to_have_value(str(music))
    save_to.press("ArrowDown")
    expect(save_to).to_have_value(str(videos))
    save_to.press("Escape")
    expect(save_to).to_have_value("")
    expect(page.locator(".folder-menu")).to_have_count(0)

    # Typing narrows the list; Enter keeps the pick
    save_to.fill("mus")
    expect(menu).to_have_count(1)
    save_to.press("ArrowUp")
    save_to.press("Enter")
    expect(save_to).to_have_value(str(music))
    expect(page.locator(".folder-menu")).to_have_count(0)

    # The history is the server's: it survives a reload (and a restart)
    page.reload()
    save_to.fill("")
    save_to.press("ArrowUp")
    expect(save_to).to_have_value(str(videos))
    page.locator(".folder-opt", has_text="Music").click()
    expect(save_to).to_have_value(str(music))


def test_a_new_release_shows_in_the_status_bar_and_updates_from_there(page, app_url):
    offer = {"current": "2.3.0", "latest": "9.9.9", "update_available": True, "can_install": True,
             "install_kind": "windows-installer", "install_note": None, "download_size": 40_000_000}
    installs = []
    page.route("**/api/check-app-update", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(offer)))
    page.route("**/api/app-update/install", lambda r: (installs.append(r.request.post_data_json),
               r.fulfill(status=200, content_type="application/json", body='{"status": "updating"}')))
    page.reload()                                  # the launch check
    chip = page.locator(".sb-update")
    expect(chip).to_contain_text("9.9.9")
    expect(page.locator(".notif", has_text="9.9.9 Available")).to_be_visible()
    chip.click()
    for _ in range(50):
        if installs:
            break
        page.wait_for_timeout(100)
    assert installs == [{"force": False}]


def test_get_ffmpeg_from_the_prompt_with_progress_in_the_status_bar(page, app_url):
    from mellow import server
    system = dict(_get(app_url, "/api/system"), ffmpeg=False, ffmpeg_path=None, ffmpeg_installable=True)
    installs = []
    page.route("**/api/system", lambda r: r.fulfill(status=200, content_type="application/json",
                                                    body=json.dumps(system)))
    page.route("**/api/ffmpeg/install", lambda r: (installs.append(1), r.fulfill(
        status=200, content_type="application/json", body='{"status": "installing"}')))
    page.reload()
    prompt = page.locator(".notif", has_text="FFmpeg Missing")
    expect(prompt).to_be_visible()
    prompt.get_by_text("GET FFMPEG").click()
    assert installs == [1]

    # The server's progress events drive the status bar
    segment = page.locator(".statusbar .sb-seg:not(.sb-path)", has_text="FFMPEG")
    for event in ({"stage": "downloading", "pct": 42, "version": "9.0"},
                  {"stage": "installing", "version": "9.0"}):
        server._push_progress({"status": "ffmpeg_install", **event})
        expect(segment).to_contain_text("42%" if event["stage"] == "downloading" else "INSTALLING")
    system.update(ffmpeg=True, ffmpeg_path="/home/me/.mellow_dlp_ffmpeg/ffmpeg", ffmpeg_installed_by_app=True)
    server._push_progress({"status": "ffmpeg_install", "stage": "done", "version": "9.0",
                           "detail": "ffmpeg version n9.0.2"})
    expect(page.locator(".notif", has_text="FFmpeg Installed")).to_be_visible()
    expect(segment).to_contain_text("FFmpeg OK")


def test_whats_new_shows_once_after_an_update_and_from_config(page, app_url):
    from mellow import config
    from mellow.version import APP_VERSION
    config.update_config(lambda c: c.update(last_seen_version="0.0.1"))   # as if just updated
    page.reload()
    modal = page.locator(".modal-box", has_text="WHAT'S NEW")
    expect(modal).to_be_visible()
    expect(modal.locator(".wn-version").first).to_contain_text(APP_VERSION)
    expect(modal.locator(".wn-current")).to_have_count(1)
    modal.get_by_text("NICE").click()
    expect(modal).to_have_count(0)

    page.reload()                                                          # once only
    page.locator(".nav-item").first.wait_for()
    page.wait_for_timeout(1000)
    expect(modal).to_have_count(0)

    page.locator(".nav-item", has_text=re.compile("config", re.I)).first.click()
    page.get_by_text("WHAT'S NEW", exact=True).click()                     # every release
    expect(modal.locator(".wn-release")).to_have_count(len(__import__("mellow.changelog").changelog.load()))
