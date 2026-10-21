"""Config → API ACCESS in a real browser: a key made there works for a
program, and stops working once revoked."""
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api").expect


def _status(app_url, key):
    req = Request(app_url + "/api/v1/status", headers={"Authorization": f"Bearer {key}"})
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except HTTPError as exc:
        return exc.code, None


def test_make_use_and_revoke_a_key(page, app_url):
    page.locator(".nav-item", has_text=re.compile("config", re.I)).first.click()
    panel = page.locator("[data-tour=config-api]")
    panel.scroll_into_view_if_needed()
    panel.get_by_placeholder("What will use it").fill("Home script")
    panel.get_by_text("MAKE KEY").click()

    key = page.get_by_test_id("new-api-key").inner_text()
    assert key.startswith("mlw_")
    status, body = _status(app_url, key)
    assert status == 200 and body["app_version"]

    page.get_by_text("DONE").click()
    expect(page.get_by_test_id("new-api-key")).to_have_count(0)
    expect(panel.get_by_text("Home script")).to_be_visible()      # listed, the key itself never again
    assert key not in page.content()

    panel.get_by_text("REVOKE").click()
    expect(panel.get_by_text("Home script")).to_have_count(0)
    assert _status(app_url, key)[0] == 401
