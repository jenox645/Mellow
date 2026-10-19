"""Signing in, in a real browser: the launch page MellowDLP opens, a page it
didn't open, and a page another program serves on this machine."""
import pytest
from conftest import _serve
from flask import Flask

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api").expect


def test_the_launch_page_signs_the_window_in(browser, app_url, downloads):
    """What main.py opens: an owner-only file that goes on to /launch."""
    from mellow import session
    page_file = session.launch_page(app_url, session.launch_token())
    context = browser.new_context()
    page = context.new_page()
    page.goto(page_file.as_uri())
    page.locator(".nav-item").first.wait_for(timeout=15_000)
    assert page.url.rstrip("/") == app_url
    # Signed in: the page's own API calls work, and the token is this tab's
    assert page.evaluate("sessionStorage.getItem('mellow-token')")
    assert page.evaluate("fetch('/api/config', {headers: {'X-Mellow-Token': "
                         "sessionStorage.getItem('mellow-token')}}).then(r => r.status)") == 200
    # The link was used: opening it again signs nobody in
    second = context.new_page()
    second.goto(page_file.as_uri())
    expect(second.get_by_text("already been used")).to_be_visible(timeout=15_000)
    context.close()


def test_a_page_mellowdlp_didn_t_open_is_told_how_to_sign_in(browser, app_url, downloads):
    context = browser.new_context()
    page = context.new_page()
    page.goto(app_url)
    expect(page.get_by_text("NOT SIGNED IN")).to_be_visible(timeout=15_000)
    context.close()


def test_a_page_on_another_port_can_t_use_the_session(browser, app_url, downloads):
    """Cookies are shared by every port of 127.0.0.1: a program serving a page
    there gets the cookie sent along, but never the header token."""
    from mellow import config, session
    config.update_config(lambda c: c.update(rate_limit="123K"))
    site = Flask("other_port")

    @site.route("/")
    def page():
        return ("<script>window.results = Promise.all(["
                f"fetch('{app_url}/api/config/reset', {{method: 'POST', credentials: 'include',"
                " headers: {'Content-Type': 'application/json'}, body: '{}'}).then(r => r.status, () => 'blocked'),"
                f"fetch('{app_url}/api/config', {{credentials: 'include'}}).then(r => r.status, () => 'blocked'),"
                "]);</script>")

    other_url, stop = _serve(site)
    try:
        context = browser.new_context()
        app_page = context.new_page()
        app_page.goto(f"{app_url}/launch?t={session.launch_token()}")
        app_page.locator(".nav-item").first.wait_for()
        other = context.new_page()
        other.goto(other_url)
        statuses = other.evaluate("window.results")
        context.close()
    finally:
        stop()
    # The browser may hide the answer (CORS), but the server refused both
    assert all(s in (401, "blocked") for s in statuses), statuses
    assert config.load_config()["rate_limit"] == "123K"
