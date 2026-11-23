"""Theme Tactical's window at a big and a small size (#91): the chosen tab's bar spans the tab,
an open Vault folder scrolled to its end shows its last row above the status bar, and the
rail holds no mascot squeezed into a box. The Vault is Tactical's own view (gui/themes/tactical/vault.jsx):
a folder is a bay in the index, its files are .tv-card covers."""
import pytest

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("size", [(1920, 1080), (1100, 780)])
def test_tactical_tab_bar_last_row_and_rail(page, downloads, size):
    from mellow import config
    folder = downloads / "Lofi"
    folder.mkdir()
    for i in range(60):
        (folder / f"track {i:02d}.mp3").write_bytes(b"\0" * 1024)
    config.update_config(lambda c: c.update(ui_theme="tactical"))
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate("localStorage.setItem('mellow-theme', 'tactical')")
    page.reload()
    page.locator(".tac-tab.on").wait_for()
    page.keyboard.press("3")
    page.locator(".tv-bay", has_text="Lofi").click()
    page.locator(".tv-card").first.wait_for()
    page.wait_for_timeout(800)      # the page's entrance
    m = page.evaluate("""() => {
      const tab = document.querySelector('.tac-tab.on');
      const bar = getComputedStyle(tab, '::before');
      const c = document.querySelector('.content.active');
      c.scrollTop = c.scrollHeight;
      const cards = document.querySelectorAll('.tv-card');
      return { tabW: tab.offsetWidth, barLeft: parseFloat(bar.left), barW: parseFloat(bar.width),
               scrolls: c.scrollHeight > c.clientHeight,
               lastBottom: cards[cards.length - 1].getBoundingClientRect().bottom,
               barTop: document.querySelector('.statusbar').getBoundingClientRect().top,
               portraits: document.querySelectorAll('.tac-rail .mascot-wrap, .tac-rail img').length };
    }""")
    assert m["barLeft"] == 0 and abs(m["barW"] - m["tabW"]) < 1, m
    assert m["scrolls"], m           # the test means something: the folder is taller than the window
    assert m["lastBottom"] <= m["barTop"], m
    assert m["portraits"] == 0, m


def _tactical(page):
    from mellow import config
    config.update_config(lambda c: c.update(ui_theme="tactical"))
    page.evaluate("localStorage.setItem('mellow-theme', 'tactical')")
    page.reload()
    page.locator(".tac-tab.on").wait_for()


def test_tactical_intake_sends_what_its_loadout_shows(page, downloads):
    """The Feed's own view: the command line analyzes, the quality ruler, container and lamp switches
    are what DOWNLOAD sends, and the transfer column stands by until a job runs."""
    import json
    import re
    _tactical(page)
    sent = []
    page.route("**/api/info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"title": "A Made-Up Video", "is_playlist": False, "platform": "YouTube", "uploader": "Someone",
         "duration": 95, "webpage_url": "https://www.youtube.com/watch?v=abc", "file_name": "A Made-Up Video"})))
    page.route("**/api/download", lambda r: (sent.append(r.request.post_data_json), r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"status": "queued", "job_id": "j1"})))[1])
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.locator(".tf-xfer")).to_contain_text("STANDBY")
    page.locator(".tf-url").fill("https://www.youtube.com/watch?v=abc")
    page.get_by_role("button", name=re.compile("Analyze", re.I)).click()
    expect(page.locator(".tf-dossier")).to_contain_text("YouTube")
    page.get_by_role("radio", name="720p").click()
    expect(page.get_by_role("radio", name="720p")).to_have_attribute("aria-checked", "true")
    page.get_by_role("radio", name="mkv").click()
    sponsor = page.get_by_role("switch", name="SponsorBlock")
    was = sponsor.get_attribute("aria-checked") == "true"
    sponsor.click()
    expect(sponsor).to_have_attribute("aria-checked", "false" if was else "true")
    page.locator(".tf-go").click()
    for _ in range(50):
        if sent:
            break
        page.wait_for_timeout(100)
    assert sent, "DOWNLOAD sent nothing"
    body = sent[0]
    assert body["url"] == "https://www.youtube.com/watch?v=abc"
    assert (body["mode"], body["quality"], body["container"]) == ("video", "720p", "mkv")
    assert bool(body["sponsorblock"]) is (not was)


def test_tactical_storage_index_opens_a_bay_and_goes_back(page, downloads):
    """The Vault's own view: a bay opens its record, ☰ LIST is a ruled table, ◂ INDEX goes back."""
    expect = pytest.importorskip("playwright.sync_api").expect
    for name in ("Alpha", "Beta"):
        (downloads / name).mkdir()
        for i in range(3):
            (downloads / name / f"{name} {i}.mp3").write_bytes(b"\0" * 2048)
    _tactical(page)
    page.keyboard.press("3")
    expect(page.locator(".tv-bay")).to_have_count(2)
    expect(page.locator(".tv-overview")).to_contain_text("Alpha")
    page.locator(".tv-bay", has_text="Beta").click()
    expect(page.locator(".tv-fname h2")).to_have_text("Beta")
    expect(page.locator(".tv-bay.on")).to_contain_text("Beta")
    page.get_by_role("radio", name="☰ LIST").click()
    expect(page.locator(".tv-row")).to_have_count(3)
    page.locator(".tv-bay", has_text="Alpha").click()          # the index stays: another bay at once
    expect(page.locator(".tv-fname h2")).to_have_text("Alpha")
    page.get_by_role("button", name="◂ INDEX").click()
    expect(page.locator(".tv-overview")).to_be_visible()
