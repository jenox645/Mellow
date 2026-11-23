"""A page's state lives in its hook (gui/pages/*-logic.js), so it must outlive what a theme swaps around it.

- A theme switch that changes the PageFrame (Classic ↔ Tactical) moves the page instead of remounting it
  (app.jsx's `PageSlot`): unsaved Config edits are still there.
- ✦ WRAPPED's results are page state too: an answer for a year that comes back after the card was closed
  and reopened must not replace the reopened card's.
"""
import json
import re
import time
from datetime import date

import pytest

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api").expect


def _wait_saved(key, value):
    from mellow import config
    for _ in range(50):
        if config.load_config().get(key) == value:
            return
        time.sleep(0.1)
    assert config.load_config().get(key) == value


def test_a_theme_switch_that_changes_the_frame_keeps_unsaved_config_edits(page):
    from mellow import config
    page.locator(".nav-item", has_text=re.compile("config", re.I)).first.click()
    langs = page.locator("input[placeholder='en']")
    langs.fill("fr,de")                                             # typed, not saved
    page.evaluate("document.querySelector('input[placeholder=\"en\"]').dataset.mark = 'same-node'")

    page.get_by_role("button", name="Theme: Tactical").click()      # Tactical has its own PageFrame
    expect(page.locator("html")).to_have_attribute("data-theme", "tactical")
    expect(page.locator(".tac-frame .content.active")).to_have_count(1)   # the page sits in Tactical's frame
    _wait_saved("ui_theme", "tactical")
    expect(langs).to_have_value("fr,de")
    # the very same element: moved into the new frame, not drawn again
    assert page.evaluate("document.querySelector('input[placeholder=\"en\"]').dataset.mark") == "same-node"

    page.get_by_role("button", name="Classic dark").click()         # and back to Classic's (no frame)
    expect(page.locator("html")).to_have_attribute("data-theme", "classic")
    expect(page.locator(".tac-frame")).to_have_count(0)
    _wait_saved("ui_theme", "classic")
    expect(langs).to_have_value("fr,de")
    assert config.load_config().get("sub_langs") != "fr,de"          # still only typed

    page.get_by_role("button", name=re.compile("SAVE CONFIG")).click()   # and it saves as typed
    _wait_saved("sub_langs", "fr,de")


def _wrapped(year, downloads):
    months = [0] * 12
    months[0] = downloads
    return {"year": year, "total_downloads": downloads, "total_duration_seconds": 3600, "total_size_bytes": 1024,
            "success_rate": 100, "top_uploaders": [], "monthly": months, "busiest_day": None}


def test_wrapped_drops_an_answer_that_lands_after_the_card_was_reopened(page):
    this_year = date.today().year
    held = []

    def wrapped(route):
        year = int(re.search(r"year=(\d+)", route.request.url).group(1))
        if year == this_year:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(_wrapped(year, 7)))
        else:
            held.append(route)                                      # last year's answer is slow
    page.route("**/api/analytics/wrapped?*", wrapped)

    page.locator(".nav-item", has_text=re.compile("analytics", re.I)).first.click()
    page.get_by_role("button", name=re.compile("WRAPPED")).click()
    modal = page.locator(".modal-box")
    expect(modal).to_contain_text(f"MELLOW WRAPPED {this_year}")
    expect(modal.locator(".stat-value").first).to_have_text("7")

    modal.get_by_role("button", name=f"‹ {this_year - 1}").click()   # asks for last year...
    expect(modal).to_contain_text(f"MELLOW WRAPPED {this_year - 1}")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "last year's request never went out"
    modal.get_by_role("button", name="CLOSE").click()               # ...then closes and reopens before it lands
    expect(modal).to_have_count(0)
    page.get_by_role("button", name=re.compile("WRAPPED")).click()
    expect(modal).to_contain_text(f"MELLOW WRAPPED {this_year}")
    expect(modal.locator(".stat-value").first).to_have_text("7")

    held[0].fulfill(status=200, content_type="application/json", body=json.dumps(_wrapped(this_year - 1, 999)))
    page.wait_for_timeout(500)
    expect(modal).to_contain_text(f"MELLOW WRAPPED {this_year}")
    expect(modal.locator(".stat-value").first).to_have_text("7")    # not last year's 999
