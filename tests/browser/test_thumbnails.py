"""Vault thumbnails in the window (#126): folder cards ask for their pictures only near the screen,
and a picture the app makes in the background shows up by itself."""
import shutil
import subprocess

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.browser


def test_folder_cards_ask_for_their_pictures_only_near_the_screen(page, downloads):
    for i in range(80):
        folder = downloads / f"Folder {i:02d}"
        folder.mkdir()
        (folder / "clip.mp4").write_bytes(b"\0" * 1024)
        (folder / "clip.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    asked = []
    page.on("request", lambda r: "/api/vault/folder-previews" in r.url and asked.append(r.url))
    page.locator(".nav-item", has_text="VAULT").click()
    page.get_by_title("Refresh vault").click()
    expect(page.locator(".vault-folder-card")).to_have_count(80)
    page.wait_for_timeout(800)
    first_screen = len(set(asked))
    assert 0 < first_screen < 50, first_screen             # 80 used to be asked for at once
    page.locator(".vault-folder-card").last.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    assert len(set(asked)) > first_screen                   # the rest once they come near
    assert any("Folder%2079" in u or "Folder 79" in u for u in asked)


def test_a_videos_frame_made_in_the_background_shows_up_by_itself(page, downloads):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("needs ffmpeg")
    folder = downloads / "Frames"
    folder.mkdir()
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=5", "-t", "2",
                    "-pix_fmt", "yuv420p", str(folder / "clip.mp4")], check=True)
    statuses = []
    page.on("response", lambda r: "/api/vault/thumb" in r.url and "clip.mp4" in r.url and statuses.append(r.status))
    page.locator(".nav-item", has_text="VAULT").click()
    page.get_by_title("Refresh vault").click()
    page.locator(".vault-folder-card", has_text="Frames").click()
    img = page.locator(".lib-card .lib-thumb img").first
    expect(img).to_be_attached()
    page.wait_for_function("img => img.complete && img.naturalWidth > 1", arg=img.element_handle(), timeout=15_000)
    assert statuses[0] == 202 and statuses[-1] == 200, statuses     # a placeholder first, then the frame
    assert (folder / "clip.jpg").exists()                            # kept next to it, as a download's


def test_a_big_folder_opened_again_asks_only_for_the_pictures_on_screen(page, downloads):
    """Opened again from a scrolled vault (the vault and the folder share one scrolled area), a
    2,000-file folder asks again only for what's on screen, and the window keeps what it had."""
    big = downloads / "Big"
    big.mkdir()
    for i in range(2000):
        (big / f"clip {i:04d}.mp4").write_bytes(b"\0" * 64)
        (big / f"clip {i:04d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    for i in range(200):
        other = downloads / f"Folder {i:03d}"
        other.mkdir()
        (other / "song.mp3").write_bytes(b"\0" * 64)
    asked = []
    page.on("request", lambda r: "/api/vault/thumb" in r.url and "clip" in r.url and asked.append(r.url))
    page.locator(".nav-item", has_text="VAULT").click()
    page.get_by_title("Refresh vault").click()
    page.locator(".vault-folder-card", has_text="Big").click()
    expect(page.locator(".lib-card")).to_have_count(2000)
    for _ in range(8):
        page.locator(".content").evaluate("c => c.scrollBy(0, c.clientHeight)")
        page.wait_for_timeout(150)
    page.locator(".vbc-root").click()
    expect(page.locator(".vault-folder-card")).to_have_count(201)
    page.wait_for_timeout(500)
    asked.clear()
    page.locator(".vault-folder-card", has_text="Big").click()
    expect(page.locator(".lib-card")).to_have_count(2000)
    page.wait_for_timeout(2000)
    assert 0 < len(set(asked)) < 100, len(set(asked))
