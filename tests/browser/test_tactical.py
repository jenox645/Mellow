"""Theme Tactical's window at a big and a small size (#91): the chosen tab's bar spans the tab,
an open Vault folder scrolled to its end shows its last row above the status bar, and the
rail holds no mascot squeezed into a box."""
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
    page.locator(".vault-folder-card", has_text="Lofi").click()
    page.locator(".lib-card").first.wait_for()
    page.wait_for_timeout(800)      # the page's entrance
    m = page.evaluate("""() => {
      const tab = document.querySelector('.tac-tab.on');
      const bar = getComputedStyle(tab, '::before');
      const c = document.querySelector('.content.active');
      c.scrollTop = c.scrollHeight;
      const cards = document.querySelectorAll('.lib-card');
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
