"""Only the windows MellowDLP opened can use its API (mellow/session.py)."""
import json
import os
import re
import stat
import sys
import time

import pytest

from mellow import server, session

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


@pytest.fixture
def instance(isolated_user_files):
    session.start_instance(54321)
    yield
    session.stop_instance()


def _routes():
    """Every (method, url, endpoint) the app answers, with a sample value per URL part."""
    for rule in server.app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        url = re.sub(r"<(?:[^:>]+:)?([^>]+)>", "x", rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield method, url, rule.endpoint


ROUTES = list(_routes())


def test_every_route_is_either_public_or_needs_a_signed_in_window():
    endpoints = {e for _m, _u, e in ROUTES}
    # A public endpoint that isn't a route any more would hide a typo
    assert server.PUBLIC_ENDPOINTS <= endpoints
    assert server.BROWSER_LOADED_ENDPOINTS <= endpoints
    # Nothing under /api/ is public but the second-launch check
    public_api = {u for m, u, e in ROUTES if e in server.PUBLIC_ENDPOINTS and u.startswith("/api/")}
    assert public_api == {"/api/instance/hello"}


@pytest.mark.parametrize("method, url, endpoint",
                         [r for r in ROUTES if r[2] not in server.PUBLIC_ENDPOINTS])
def test_without_signing_in_every_route_is_refused(anon_client, method, url, endpoint):
    r = anon_client.open(url, method=method, json={} if method != "GET" else None)
    assert r.status_code == 401, (method, url)
    assert r.get_json()["signed_in"] is False
    assert "Open MellowDLP from its icon" in r.get_json()["error"]
    # If signing in is what's broken, the way out is a manual download
    assert r.get_json()["download"].startswith("https://github.com/")


@pytest.mark.parametrize("method, url, endpoint",
                         [r for r in ROUTES if r[2] not in server.PUBLIC_ENDPOINTS])
def test_the_session_cookie_alone_is_not_enough(app, method, url, endpoint):
    """A page another program serves on this machine shares the cookie (cookies
    ignore the port), never the header token."""
    sid, _token = session.new_session()
    c = app.test_client()
    c.set_cookie(session.COOKIE, sid)
    headers = {"Sec-Fetch-Site": "same-site"}          # a page on another port
    r = c.open(url, method=method, json={} if method != "GET" else None, headers=headers)
    assert r.status_code == 401, (method, url)


def test_a_wrong_header_token_is_refused(app):
    sid, _token = session.new_session()
    c = app.test_client()
    c.set_cookie(session.COOKIE, sid)
    assert c.get("/api/config", headers={session.HEADER: "guess"}).status_code == 401
    assert c.get("/api/config", headers={session.HEADER: "é" * 43}).status_code == 401
    # Another window's token doesn't fit this cookie either
    _other_sid, other_token = session.new_session()
    assert c.get("/api/config", headers={session.HEADER: other_token}).status_code == 401


def test_what_the_page_loads_itself_needs_the_cookie_and_its_own_page(app, tmp_path):
    """EventSource, <video> and <img> can't add a header."""
    sid, _token = session.new_session()
    c = app.test_client()
    c.set_cookie(session.COOKIE, sid)
    thumb = "/api/vault/thumb?path=" + str(tmp_path / "missing.jpg")
    assert c.get(thumb, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 404   # past sign-in
    assert c.get(thumb, headers={"Sec-Fetch-Site": "same-site"}).status_code == 401
    assert app.test_client().get(thumb, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 401
    # The rest of the API never goes without the header
    assert c.get("/api/config", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 401


def test_the_app_s_files_need_no_sign_in(anon_client):
    # 404 where static/ isn't built (the unit-test CI job): public either way
    for path in ("/", "/favicon.ico", "/app.bundle.js", "/static/index.html"):
        assert anon_client.get(path).status_code in (200, 404), path


# ── signing in ──────────────────────────────────────────────────────────────────

def test_a_launch_token_signs_one_window_in_once(anon_client, instance):
    token = session.launch_token()
    r = anon_client.get(f"/launch?t={token}")
    assert r.status_code == 200
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/" in cookie
    assert r.headers["Cache-Control"] == "no-store"
    header_token = re.search(r'setItem\("mellow-token", "([^"]+)"\)', r.get_data(as_text=True)).group(1)
    # The page stores the header token and opens the app; with both, the API answers
    assert anon_client.get("/api/config", headers={session.HEADER: header_token}).status_code == 200
    # Used once: the same link signs nobody else in
    again = server.app.test_client().get(f"/launch?t={token}")
    assert again.status_code == 403 and "Set-Cookie" not in again.headers


@pytest.mark.parametrize("bad", ["", "nonsense", "a.b.c", "a.99999999999.c", "a.{exp}.é"])
def test_a_made_up_token_signs_nobody_in(anon_client, instance, bad):
    r = anon_client.get(f"/launch?t={bad.format(exp=int(time.time()) + 30)}")
    assert r.status_code == 403 and "Set-Cookie" not in r.headers


def test_a_token_from_another_secret_or_port_is_refused(anon_client, instance):
    assert anon_client.get(f"/launch?t={session.launch_token(b'x' * 32, 54321)}").status_code == 403
    assert anon_client.get(f"/launch?t={session.launch_token(port=1)}").status_code == 403


def test_an_expired_or_overlong_token_is_refused(anon_client, instance, monkeypatch):
    expired = session.launch_token(ttl=-1)
    assert anon_client.get(f"/launch?t={expired}").status_code == 403
    # A token valid for hours would be a standing key: refused even with a good MAC
    overlong = session.launch_token(ttl=10 * 3600)
    assert anon_client.get(f"/launch?t={overlong}").status_code == 403


def test_signing_in_is_allowed_from_the_launch_file(anon_client, instance):
    """The launch page is a file, so the browser calls its link cross-site."""
    r = anon_client.get(f"/launch?t={session.launch_token()}", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200
    # Nothing else is
    assert anon_client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_old_sessions_are_forgotten(monkeypatch):
    monkeypatch.setattr(session, "SESSIONS_KEEP", 3)
    first = session.new_session()
    for _ in range(3):
        session.new_session()
    assert session.header_token(first[0]) is None


# ── the instance file and the second launch ─────────────────────────────────────

@posix
def test_the_secret_is_readable_by_this_account_only(instance):
    folder = session.instance_file().parent
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(session.instance_file().stat().st_mode) == 0o600
    data = json.loads(session.instance_file().read_text())
    assert data["port"] == 54321 and len(bytes.fromhex(data["secret"])) == 32


@posix
def test_a_data_folder_made_readable_by_others_is_tightened(isolated_user_files):
    from mellow import datadir
    folder = datadir.data_dir()
    folder.mkdir(parents=True)
    folder.chmod(0o755)
    datadir.ensure_private()
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_the_running_copy_proves_it_knows_the_secret(anon_client, instance):
    info = session.read_instance()
    r = anon_client.get("/api/instance/hello?nonce=" + "n" * 24).get_json()
    assert r["proof"] == session.instance_proof("n" * 24, info["secret"], info["port"])
    assert r["proof"] != session.instance_proof("n" * 24, b"y" * 32, info["port"])
    assert anon_client.get("/api/instance/hello?nonce=short").status_code == 400


def test_stopping_leaves_a_newer_copy_s_file_alone(isolated_user_files):
    session.start_instance(1111)
    newer = session.instance_file().read_text().replace("1111", "2222")
    session.instance_file().write_text(newer)
    session.stop_instance()
    assert session.instance_file().exists()


@posix
def test_a_launch_page_is_owner_only_and_old_ones_go(instance):
    page = session.launch_page("http://127.0.0.1:54321", session.launch_token())
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    assert "/launch?t=" in page.read_text()
    old = time.time() - 3600
    os.utime(page, (old, old))
    newer = session.launch_page("http://127.0.0.1:54321", session.launch_token())
    assert not page.exists() and newer.exists()
    session.stop_instance()
    assert not newer.exists()
