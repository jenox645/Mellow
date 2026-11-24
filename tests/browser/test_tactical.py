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


def _tour_steps(tour, theme):
    """The steps the GUIDE shows (gui/lib/tours.js tourSteps), read with node."""
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("node isn't installed")
    root = Path(__file__).resolve().parents[2]
    out = subprocess.run([node, "--input-type=module", "-e",
                          "import { tourSteps } from './gui/lib/tours.js';"
                          f"console.log(JSON.stringify(tourSteps({json.dumps(tour)}, 'tactical')))"],
                         cwd=root, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


SETTLED = "() => { const c = document.querySelector('.tour-card'); return c && !c.classList.contains('moving'); }"
MEASURE = """(target) => {
  const spot = document.querySelector('.tour-spot');
  const el = target && document.querySelector('[data-tour="' + target + '"]');
  const r = el && el.getBoundingClientRect();
  return { title: document.querySelector('.tour-card .tour-title').textContent,
           missing: !!document.querySelector('.tour-card .tour-missing'),
           none: spot.classList.contains('none'),
           spot: ['left', 'top', 'width', 'height'].map(k => parseFloat(spot.style[k])),
           part: r && r.width > 4 && r.height > 4 ? [r.left, r.top, r.width, r.height] : null };
}"""


def _walk_guide(page, tour, absent):
    """Press G, step through the whole tour at a reading pace and check every step: its words are
    Tactical's, a part on screen is lit (the spotlight frames it), and only the parts in `absent`
    (not on screen in this state) fall back to their "shows up when…" note."""
    steps = _tour_steps(tour, "tactical")
    page.keyboard.press("g")
    seen_absent = set()
    for i, step in enumerate(steps):
        if i:
            page.keyboard.press("ArrowRight")
        # The card shows the step at once, then opens and scrolls to its part ("moving" until it's there)
        page.wait_for_function("t => document.querySelector('.tour-card .tour-title').textContent === t", arg=step["title"])
        page.wait_for_timeout(100)
        page.wait_for_function(SETTLED)
        page.wait_for_timeout(450)       # the spotlight follows the part while the page settles
        m = page.evaluate(MEASURE, step["target"])
        where = f"{tour} step {i + 1} ({step['title']})"
        assert m["title"] == step["title"], where
        if not step["target"]:
            assert m["none"], where
            continue
        if m["part"] is None:
            assert step["target"] in absent and step.get("missing") and m["missing"], where + ": not on screen"
            seen_absent.add(step["target"])
            continue
        assert step["target"] not in absent, where + ": expected it absent in this state"
        assert not m["none"] and not m["missing"], where + ": on screen but not lit"
        pad = 6
        sx, sy, sw, sh = m["spot"]
        px, py, pw, ph = m["part"]
        assert abs(sx + pad - px) < 3 and abs(sy + pad - py) < 3, (where, m)
        assert abs(sw - 2 * pad - pw) < 3 and abs(sh - 2 * pad - ph) < 3, (where, m)
    assert seen_absent == set(absent), (tour, seen_absent)
    page.keyboard.press("Escape")
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.locator(".tour-root")).to_have_count(0)


def test_tactical_guide_lights_its_own_parts(page, downloads):
    """GUIDE (G) in Tactical's own Feed, Vault index and an open bay: every step lands on Tactical's part,
    says it in Tactical's words, and its reveal still opens EXTENDED (closed again at the end)."""
    expect = pytest.importorskip("playwright.sync_api").expect
    (downloads / "Lofi").mkdir()
    for i in range(6):
        (downloads / "Lofi" / f"track {i}.mp3").write_bytes(b"\0" * 2048)
    _tactical(page)
    page.set_viewport_size({"width": 1440, "height": 900})
    expect(page.locator(".tf-drawer.open")).to_have_count(0)
    _walk_guide(page, "feed", {"feed-info", "feed-file-name", "feed-from-list"})
    expect(page.locator(".tf-drawer.open")).to_have_count(0)     # EXTENDED, opened by its step, closed again
    page.keyboard.press("3")
    page.locator(".tv-bay", has_text="Lofi").wait_for()
    _walk_guide(page, "vault", set())
    page.locator(".tv-bay", has_text="Lofi").click()
    page.locator(".tv-fname").wait_for()
    _walk_guide(page, "vault_folder", {"vault-sync", "vault-sync-options", "vault-report"})


def test_tactical_index_dialogs_work_beside_an_open_bay(page, downloads, isolated_user_files):
    """The index stays beside an open bay, so its DUPES and + WATCH must still open their dialogs."""
    import json
    expect = pytest.importorskip("playwright.sync_api").expect
    (downloads / "Lofi").mkdir()
    (downloads / "Lofi" / "a.mp3").write_bytes(b"\0" * 2048)
    elsewhere = isolated_user_files / "Elsewhere"
    elsewhere.mkdir()
    (elsewhere / "old.mp3").write_bytes(b"\0" * 2048)
    page.route("**/api/browse-folder", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"path": str(elsewhere)})))
    _tactical(page)
    page.keyboard.press("3")
    page.locator(".tv-bay", has_text="Lofi").click()
    page.locator(".tv-fname").wait_for()
    page.locator(".tv-index").get_by_role("button", name="Dupes").click()
    expect(page.locator(".modal-box")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.locator(".modal-box")).to_have_count(0)
    page.locator(".tv-index").get_by_role("button", name="+ Watch").click()
    prompt = page.locator(".modal-box", has_text="ARCHIVE FILE")
    expect(prompt).to_be_visible()
    prompt.get_by_role("button", name="NO ARCHIVE").click()
    expect(page.locator(".tv-bay", has_text="Elsewhere")).to_be_visible()
    expect(page.locator(".tv-fname h2")).to_have_text("Lofi")              # the open bay stays open
    expect(page.locator(".modal-box")).to_have_count(0)
