"""WebKitGTK form controls (#117): the Tauri window on Linux draws what the page leaves to the
system with the GTK theme, light unless the page declares a colour scheme, and a select's box in
GTK's own colours: Classic's Config showed white boxes with near-invisible light text.

index.html's early script marks the engine (`data-engine="webkitgtk"`) and only that engine gets
the rules (ENGINE: WEBKITGTK in index.html). Chromium can't run WebKitGTK; these tests give it
WebKitGTK's user agent, so the page applies the same rules, and check what they set. The real
window was checked by hand (screenshots in the PR). With Chromium's own user agent nothing
changes: Windows' WebView2 keeps drawing Classic as before."""
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.browser

# WebKitGTK 2.52's own (Ubuntu 24.04; Fedora says "Fedora" there); the Tauri shell doesn't change it
WEBKITGTK_UA = ("Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/60.5 Safari/605.1.15")
WEBVIEW2_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0")
THEMES = {"classic": "dark", "classic-light": "light", "tactical": "dark", "archive": "light"}

# Every select on the page: what WebKitGTK is asked to draw
_SELECTS_JS = """() => [...document.querySelectorAll('select')].filter(s => s.offsetParent).map(s => {
  const cs = getComputedStyle(s);
  return {appearance: cs.appearance, image: cs.backgroundImage, color: cs.color, bg: cs.backgroundColor};
})"""


def _rgb(css: str) -> tuple[float, ...]:
    return tuple(float(v) for v in re.findall(r"[\d.]+", css)[:3])


def _contrast(a: str, b: str) -> float:
    def lum(rgb):
        c = [v / 255 for v in rgb]
        c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(_rgb(a)), lum(_rgb(b))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _open_config(browser, app_url, theme: str, user_agent: str):
    from mellow import config, session
    config.update_config(lambda c: c.update(ui_theme=theme))
    context = browser.new_context(viewport={"width": 1280, "height": 900}, user_agent=user_agent)
    page = context.new_page()
    page.add_init_script(f"try {{ localStorage.setItem('mellow-theme', {theme!r}) }} catch (e) {{}}")
    page.goto(f"{app_url}/launch?t={session.launch_token()}")
    page.locator(".nav-item").first.wait_for()
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("6")                                    # Config
    page.locator("select.sel").first.wait_for()
    return context, page


@pytest.mark.parametrize("theme", list(THEMES))
def test_webkitgtk_draws_every_select_in_the_themes_colours(browser, app_url, downloads, theme):
    context, page = _open_config(browser, app_url, theme, WEBKITGTK_UA)
    try:
        expect(page.locator("html")).to_have_attribute("data-engine", "webkitgtk")
        # The scheme GTK draws checkboxes, number/time fields and scrollbars in
        assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == THEMES[theme]
        selects = page.evaluate(_SELECTS_JS)
        assert len(selects) >= 8, selects                       # Default Mode … Auto-Sync Interval
        for s in selects:
            assert s["appearance"] == "none", s                 # its own box, not GTK's
            assert s["image"].count("linear-gradient") == 2, s  # and its own arrow
            assert _contrast(s["color"], s["bg"]) >= 4.5, s
        # The open list's rows too (where the engine honours them)
        option = page.evaluate("""() => { const o = getComputedStyle(document.querySelector('select.sel option'));
                                          return {color: o.color, bg: o.backgroundColor}; }""")
        assert _contrast(option["color"], option["bg"]) >= 4.5, option
    finally:
        context.close()


def test_chromium_and_webview2_draw_classic_as_before(browser, app_url, downloads):
    """Windows' WebView2 (and the Chrome window) already draw the selects as the CSS asks: the
    engine rules leave them alone, so Classic's Config is what it was."""
    context, page = _open_config(browser, app_url, "classic", WEBVIEW2_UA)
    try:
        assert page.evaluate("document.documentElement.dataset.engine") is None
        assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "normal"
        for s in page.evaluate(_SELECTS_JS):
            assert s["appearance"] != "none" and s["image"] == "none", s
    finally:
        context.close()
