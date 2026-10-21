"""The API for other programs: scoped keys (api_keys.py) and /api/v1."""
import json
import queue
import stat
import sys
from unittest.mock import patch

import pytest

from mellow import api_keys, jobs, server


def _key(client, *scopes, name="Script"):
    r = client.post("/api/keys", json={"name": name, "scopes": list(scopes)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _auth(key):
    return {"Authorization": f"Bearer {key['key']}"}


# ── keys ────────────────────────────────────────────────────────────────────────

def test_a_key_is_shown_once_and_stored_as_a_hash(client):
    made = _key(client, "queue:read")
    assert made["key"].startswith("mlw_") and made["scopes"] == ["queue:read"]
    listed = client.get("/api/keys").get_json()["keys"]
    assert [k["id"] for k in listed] == [made["id"]]
    assert "key" not in listed[0] and "hash" not in listed[0]
    stored = (api_keys.datadir.data_dir() / api_keys.KEYS_FILE_NAME).read_text()
    assert made["key"].split("_", 2)[2] not in stored


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_key_file_is_owner_only(client):
    _key(client, "queue:read")
    path = api_keys.datadir.data_dir() / api_keys.KEYS_FILE_NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("body", [{"name": "", "scopes": ["queue:read"]},
                                  {"name": "x", "scopes": []},
                                  {"name": "x", "scopes": ["config:write"]}])
def test_a_key_needs_a_name_and_known_scopes(client, body):
    assert client.post("/api/keys", json=body).status_code == 400


def test_only_a_signed_in_window_manages_keys(client, anon_client):
    made = _key(client, "queue:read", "downloads:create")
    for method, url in (("GET", "/api/keys"), ("POST", "/api/keys"), ("DELETE", f"/api/keys/{made['id']}")):
        assert anon_client.open(url, method=method, json={}).status_code == 401
        # A key can't make or revoke keys either
        assert anon_client.open(url, method=method, json={}, headers=_auth(made)).status_code == 401


def test_a_revoked_key_stops_working(client, anon_client):
    made = _key(client, "queue:read")
    other = _key(client, "queue:read", name="Other")
    assert anon_client.get("/api/v1/queue", headers=_auth(made)).status_code == 200
    assert client.delete(f"/api/keys/{made['id']}").status_code == 200
    assert anon_client.get("/api/v1/queue", headers=_auth(made)).status_code == 401
    assert anon_client.get("/api/v1/queue", headers=_auth(other)).status_code == 200   # only that one
    assert client.delete(f"/api/keys/{made['id']}").status_code == 404


def test_a_key_records_when_it_was_last_used(client, anon_client):
    made = _key(client, "queue:read")
    assert client.get("/api/keys").get_json()["keys"][0]["last_used"] is None
    anon_client.get("/api/v1/queue", headers=_auth(made))
    assert client.get("/api/keys").get_json()["keys"][0]["last_used"] is not None


# ── who may call /api/v1 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("header", [None, "Bearer ", "Bearer mlw_nope_nope", "Basic abc",
                                    "Bearer mlw_00000000_é", "Bearer mlw_{real_id}_wrongsecret"])
def test_v1_without_a_valid_key_is_refused(anon_client, client, header):
    made = _key(client, "queue:read")
    header = (header or "").replace("{real_id}", made["id"]) or None
    headers = {"Authorization": header} if header is not None else {}
    r = anon_client.get("/api/v1/queue", headers=headers)
    assert r.status_code == 401 and "API key" in r.get_json()["error"]


def test_a_key_can_only_do_what_its_scopes_say(client, anon_client):
    reader = _key(client, "queue:read")
    assert anon_client.get("/api/v1/queue", headers=_auth(reader)).status_code == 200
    assert anon_client.get("/api/v1/status", headers=_auth(reader)).status_code == 200   # any key
    r = anon_client.post("/api/v1/downloads", json={"url": "https://example.com/v"}, headers=_auth(reader))
    assert r.status_code == 403 and "downloads:create" in r.get_json()["error"]


def test_a_signed_in_window_is_not_a_key(client):
    """The window has the full API; /api/v1 is only for keys (and stays that narrow)."""
    assert client.get("/api/v1/status").status_code == 401


@pytest.mark.parametrize("method, url, endpoint",
                         [r for r in __import__("test_access").ROUTES
                          if r[2] not in server.API_V1_SCOPES and r[2] not in server.PUBLIC_ENDPOINTS])
def test_a_key_reaches_nothing_but_v1(client, anon_client, method, url, endpoint):
    """No SQL, backups, settings, paths or deleting with a key, whatever its scopes."""
    everything = _key(client, *api_keys.SCOPES)
    r = anon_client.open(url, method=method, json={} if method != "GET" else None, headers=_auth(everything))
    assert r.status_code == 401, (method, url)


# ── the endpoints ───────────────────────────────────────────────────────────────

def test_status(client, anon_client):
    d = anon_client.get("/api/v1/status", headers=_auth(_key(client, "queue:read"))).get_json()
    assert set(d) == {"app_version", "ytdlp_version", "queued", "active"}


def test_a_download_goes_to_the_download_folder_with_the_feed_defaults(client, anon_client, tmp_path):
    from mellow.config import update_config
    update_config(lambda c: c.update(output_dir=str(tmp_path / "dl"), default_quality="720p"))
    creator = _key(client, "downloads:create")
    with patch("mellow.downloader.download_video", return_value="success") as dl:
        r = anon_client.post("/api/v1/downloads", json={"url": "https://example.com/watch?v=1", "mode": "audio",
                                                         "audio_format": "opus"}, headers=_auth(creator))
        assert r.status_code == 201
        jobs.manager.wait_idle(timeout=10)
    job_id = r.get_json()["job_id"]
    job = next(j for j in jobs.manager._jobs if j["id"] == job_id)
    assert job["output_dir"] == str(tmp_path / "dl")
    assert (job["opts"]["mode"], job["opts"]["audio_format"], job["opts"]["quality"]) == ("audio", "opus", "720p")
    assert dl.called


@pytest.mark.parametrize("body, why", [
    ({"url": "https://example.com/v", "output_dir": "/tmp"}, "output_dir"),
    ({"url": "https://example.com/v", "filename_template": "x"}, "filename_template"),
    ({"url": "https://example.com/v", "custom_format": "x"}, "custom_format"),
    ({"url": "file:///etc/passwd"}, "url"),
    ({"url": "javascript:alert(1)"}, "url"),
    ({"url": "ftp://example.com/v"}, "url"),
    ({"url": "https://example.com/a https://example.com/b"}, "url"),
    ({"url": "https://example.com/" + "x" * 3000}, "url"),
    ({"url": "https://example.com/v", "quality": "8k"}, "quality"),
    ({"url": "https://example.com/v", "container": "avi"}, "container"),
    ({"url": "https://example.com/v", "mode": "everything"}, "mode"),
    ([], "JSON object"),
])
def test_a_download_takes_only_a_link_and_format_choices(client, anon_client, body, why):
    creator = _key(client, "downloads:create")
    r = anon_client.post("/api/v1/downloads", json=body, headers=_auth(creator))
    assert r.status_code == 400 and why in r.get_json()["error"]


def test_the_queue_never_says_where_files_go(client, anon_client, tmp_path):
    reader = _key(client, "queue:read")
    with patch("mellow.downloader.download_video", return_value="success"):
        client.post("/api/download", json={"url": "https://example.com/v", "output_dir": str(tmp_path / "secret")})
        jobs.manager.wait_idle(timeout=10)
    text = anon_client.get("/api/v1/queue", headers=_auth(reader)).get_data(as_text=True)
    assert "secret" not in text and "output_dir" not in text and "opts" not in text
    assert json.loads(text)["jobs"]


def test_progress_events_for_programs_carry_no_paths():
    full = {"status": "complete", "job_id": "j", "title": "Song", "file_path": "/home/u/Music/Song.mp3",
            "thumbnail": "https://i.ytimg.com/x.jpg", "message": "ERROR: /home/u/x"}
    assert server._v1_event(full) == {"status": "complete", "job_id": "j", "title": "Song"}
    assert server._v1_event({"status": "ffmpeg_install", "path": "/opt/ffmpeg"}) is None
    assert server._v1_event({"status": "sync_plan", "items": []}) is None


def test_program_streams_get_the_filtered_event_and_are_not_pages():
    pages_before = server.open_pages()
    program = server._sse_subscribe(external=True)
    page = server._sse_subscribe()
    try:
        assert server.open_pages() == pages_before + 1
        server._push_progress({"status": "item_saved", "file_path": "/x"})          # not for programs
        server._push_progress({"status": "downloading", "pct": 5, "current_item_thumb": "t"})
        assert program.get_nowait() == {"status": "downloading", "pct": 5}
        with pytest.raises(queue.Empty):
            program.get_nowait()
        assert page.get_nowait()["status"] == "item_saved"
    finally:
        server._sse_unsubscribe(program)
        server._sse_unsubscribe(page)
