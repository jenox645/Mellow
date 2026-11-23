"""The desktop shell's channel (mellow/shell.py): messages to the shell, its
commands, what the tray shows, when closing keeps MellowDLP in the tray, and
which notifications the shell shows when no window is open."""
import io
import json
import threading
import time
from unittest.mock import patch

import pytest

from mellow import jobs, shell
from mellow.config import load_config, update_config
from mellow.constants import SHELL_TITLE_MAX_CHARS


@pytest.fixture
def channel():
    """An attached shell: what the backend writes to it."""
    out = io.StringIO()
    shell.attach(out, open_pages=lambda: 0)
    yield out
    shell.detach()


def sent(out: io.StringIO) -> list[dict]:
    lines = [ln for ln in out.getvalue().splitlines() if ln]
    assert all(ln.startswith(shell.EVENT_PREFIX) for ln in lines), lines
    return [json.loads(ln[len(shell.EVENT_PREFIX):]) for ln in lines]


def wait_for(pred, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_without_a_shell_nothing_is_sent():
    assert shell.active() is False
    assert shell.send("notify", title="x") is False
    assert shell.notify("x") is False


def test_each_message_is_one_line(channel):
    assert shell.send("notify", title="Done", body="two\nlines")
    msgs = [m for m in sent(channel) if m["type"] == "notify"]
    assert msgs == [{"type": "notify", "title": "Done", "body": "two\nlines"}]


def test_a_broken_pipe_detaches_the_shell():
    class Broken(io.StringIO):
        def write(self, _):
            raise OSError("pipe closed")
    shell.attach(Broken(), open_pages=lambda: 0)
    try:
        assert shell.send("notify", title="x") is False
        assert shell.active() is False
    finally:
        shell.detach()


def test_commands_run_their_handler_and_unknown_ones_are_refused():
    got = []
    done = threading.Event()
    shell.register("test_cmd", lambda msg: (got.append(msg), done.set()))
    assert shell.dispatch('{"cmd": "test_cmd", "value": 3}\n')
    assert done.wait(3) and got == [{"cmd": "test_cmd", "value": 3}]
    for line in ("", "not json", '"a string"', '{"cmd": "nope"}', '{"no": "cmd"}'):
        assert shell.dispatch(line) is False, line


def _queue(*jobs_):
    return {"jobs": list(jobs_)}


def test_state_idle_with_nothing_to_do_quits_on_close():
    st = shell.state(_queue(), paused=False, cfg=load_config())
    assert st["phase"] == "idle" and st["pct"] is None
    assert st["keep_running"] is False and st["daily_sync"] is None


def test_state_shows_the_running_download_and_the_queue():
    shell._progress.observe({"status": "downloading", "job_id": "a", "pct": 42.37,
                             "current_item_title": "A song"})
    later = time.time() + 3600
    st = shell.state(_queue({"id": "a", "status": "active", "label": "https://x/a"},
                            {"id": "b", "status": "queued"},
                            {"id": "c", "status": "queued", "not_before": later}),
                     paused=False, cfg=load_config())
    assert (st["phase"], st["pct"], st["title"]) == ("downloading", 42.4, "A song")
    assert (st["active"], st["queued"], st["scheduled"]) == (1, 1, 1)
    assert st["next_start"] == time.strftime("%H:%M", time.localtime(later))
    assert st["keep_running"] is True
    st = shell.state(_queue({"id": "a", "status": "active"}), paused=True, cfg=load_config())
    assert st["phase"] == "paused"
    shell._progress.observe({"status": "complete", "job_id": "a"})


def test_a_daily_sync_keeps_it_running_unless_background_is_off():
    update_config(lambda c: c.update(auto_sync_enabled=True, auto_sync_time="04:30",
                                     vault_playlists={"/music/A": ["https://x/pl"], "/music/B": []}))
    st = shell.state(_queue(), paused=False)
    assert st["daily_sync"] == {"time": "04:30", "folders": 1, "other_folders": 0}
    assert st["keep_running"] is True
    update_config(lambda c: c.update(run_in_background=False))
    assert shell.state(_queue(), paused=False)["keep_running"] is False
    update_config(lambda c: c.update(run_in_background=True, vault_sync_schedule={"/music/A": "off"}))
    assert shell.state(_queue(), paused=False)["daily_sync"] is None


def test_long_titles_are_cut_for_the_tooltip():
    shell._progress.observe({"status": "downloading", "job_id": "t", "pct": 1, "current_item_title": "x" * 300})
    st = shell.state(_queue({"id": "t", "status": "active"}), paused=False, cfg=load_config())
    assert len(st["title"]) == SHELL_TITLE_MAX_CHARS and st["title"].endswith("…")
    shell._progress.observe({"status": "error", "job_id": "t"})


def test_the_shell_gets_the_state_when_something_changes(channel):
    assert wait_for(lambda: any(m["type"] == "state" for m in sent(channel)))
    before = len(sent(channel))
    update_config(lambda c: c.update(start_with_system=True))
    shell.changed()
    assert wait_for(lambda: any(m["type"] == "state" and m["start_with_system"] for m in sent(channel)[before:]))


def test_attached_again_at_once_the_shell_still_gets_its_state():
    # detach() then attach() at once (one test after another; a shell restart):
    # the old pump hadn't woken up yet and quit, and no state came any more
    for _ in range(5):
        out = io.StringIO()
        shell.attach(out, open_pages=lambda: 0)
        try:
            assert wait_for(lambda: any(m["type"] == "state" for m in sent(out)))
        finally:
            shell.detach()


def test_a_queue_change_reaches_the_shell_at_once(channel):
    # A download for later emits no progress: without this the tray (and the close
    # button's "keep running") learned of it only at the next refresh
    from mellow import server  # noqa: F401  (wires the queue to the shell)
    later = time.time() + 3600
    job = jobs.manager.enqueue("https://example.com/later", "/tmp/x", {}, not_before=later)
    try:
        assert wait_for(lambda: any(m["type"] == "state" and m["scheduled"] == 1 and m["keep_running"]
                                    for m in sent(channel)), 2.0)
    finally:
        jobs.manager.cancel(job["id"])


def _notes(out):
    return [m for m in sent(out) if m["type"] == "notify"]


def test_a_background_sync_that_found_items_notifies(channel):
    shell.observe({"status": "complete", "job_id": "s", "job_type": "sync",
                   "job_label": "Sync — Lo-fi (2 playlist(s))", "sync_summary": {"new": 3}, "auto": True})
    assert _notes(channel) == [{"type": "notify", "title": "3 new items in Lo-fi",
                                "body": "Synced in the background."}]


def test_quiet_when_nothing_new_a_page_is_open_or_notifications_are_off(channel):
    shell.observe({"status": "complete", "job_type": "sync", "job_id": "s", "sync_summary": {"new": 0}})
    with patch.object(shell._pump, "open_pages", lambda: 1):
        shell.observe({"status": "error", "job_id": "e", "title": "x"})
    update_config(lambda c: c.update(background_notifications=False))
    shell.observe({"status": "error", "job_id": "e", "title": "x"})
    assert _notes(channel) == []


def test_a_window_hidden_in_the_tray_lets_the_shell_notify(channel):
    # Its page is still connected, but nobody sees it: the shell notifies
    with patch.object(shell._pump, "open_pages", lambda: 1):
        shell.dispatch('{"cmd": "window", "visible": false}')
        assert wait_for(lambda: not shell._window_visible.is_set())
        shell.observe({"status": "error", "job_id": "e", "title": "x"})
        shell.queue_finished([{"type": "feed"}], open_pages=1)
        shell.dispatch('{"cmd": "window", "visible": true}')
        assert wait_for(lambda: shell._window_visible.is_set())
        shell.observe({"status": "error", "job_id": "e", "title": "y"})
    assert [n["title"] for n in _notes(channel)] == ["Download failed", "Downloads finished"]


def test_started_with_no_window_the_shell_notifies_at_once():
    out = io.StringIO()
    shell.attach(out, open_pages=lambda: 0, window_visible=False)
    try:
        assert shell.nobody_sees_the_page(1)
    finally:
        shell.detach()
        shell.set_window_visible(True)


def test_a_failed_download_notifies_with_its_hint(channel):
    shell.observe({"status": "error", "job_id": "e", "title": "Video unavailable",
                   "hint": "It was removed or made private."})
    assert _notes(channel)[-1] == {"type": "notify", "title": "Download failed",
                                   "body": "Video unavailable — It was removed or made private."}


def test_the_queue_running_dry_says_what_the_downloads_saved(channel):
    shell.queue_finished([{"type": "sync"}], open_pages=0)
    assert _notes(channel) == []                    # a sync already said what it found
    shell.queue_finished([{"type": "feed"}, {"type": "sync"}, {"type": "feed"}], open_pages=0)
    shell.queue_finished([{"type": "feed"}], open_pages=1)
    assert _notes(channel) == [{"type": "notify", "title": "Downloads finished", "body": "2 downloads saved."}]


@pytest.mark.parametrize("label, name", [
    ("Sync — Lo-fi (2 playlist(s))", "Lo-fi"),
    ("Sync — A (b) (1 playlist(s))", "A (b)"),
    ("", "a vault folder"),
])
def test_a_sync_is_named_after_its_folder(label, name):
    assert shell.sync_folder_name(label) == name


# ── The commands server.py registers ─────────────────────────────────────────

def _run(cmd: str, **message):
    """Run a registered command's handler as the channel would, and wait for it."""
    from mellow import server  # noqa: F401  (registers the handlers)
    shell._handlers[cmd]({"cmd": cmd, **message})


def test_download_the_copied_link_queues_it_with_the_feeds_defaults(channel):
    update_config(lambda c: c.update(default_mode="audio", default_audio_format="m4a"))
    with patch("mellow.downloader.download_video", return_value="success") as dl:
        _run("download", url="  https://example.com/watch?v=1 ")
        assert jobs.manager.wait_idle(10)
    url, folder, opts = dl.call_args.args[:3]
    assert url == "https://example.com/watch?v=1" and opts["mode"] == "audio" and opts["audio_format"] == "m4a"
    assert folder.endswith("MellowDLP")
    assert _notes(channel)[0] == {"type": "notify", "title": "Downloading", "body": "https://example.com/watch?v=1"}


@pytest.mark.parametrize("text", ["", "hello there", "ftp://x/y", "javascript:alert(1)", "https://x y"])
def test_a_clipboard_without_a_link_says_so(channel, text):
    with patch("mellow.server._enqueue_job") as enqueue:
        _run("download", url=text)
    enqueue.assert_not_called()
    assert _notes(channel)[0]["title"] == "No link to download"


def test_pause_and_resume_from_the_tray():
    from mellow import downloader
    with patch("mellow.jobs.manager.has_active", return_value=True), patch("mellow.server._push_progress") as push:
        _run("pause")
        assert downloader.is_paused()
        _run("resume")
    assert not downloader.is_paused()
    assert [c.args[0]["status"] for c in push.call_args_list] == ["paused", "resumed"]
    with patch("mellow.jobs.manager.has_active", return_value=False):
        _run("pause")                               # nothing runs: no stray pause flag
    assert not downloader.is_paused()


def test_sync_all_from_the_tray(channel):
    with patch("mellow.server._enqueue_vault_sync", return_value=None) as enqueue:
        _run("sync_all")
    enqueue.assert_not_called()
    assert _notes(channel)[0]["title"] == "Nothing to sync"
    update_config(lambda c: c.update(vault_playlists={"/music/A": ["https://x/pl"], "/music/B": []}))
    with patch("mellow.server._enqueue_vault_sync", return_value={"id": "j"}) as enqueue:
        _run("sync_all")
    assert [c.args[0] for c in enqueue.call_args_list] == ["/music/A"]


def test_the_shell_reports_settings_back():
    _run("tray_notice_seen", value=True)
    _run("start_with_system", value=False)
    cfg = load_config()
    assert cfg["tray_notice_seen"] is True and cfg["start_with_system"] is False


def test_the_page_learns_it_is_in_the_desktop_app(client, channel):
    assert client.get("/api/system").get_json()["shell"] == "tauri"


def test_without_the_shell_the_page_is_in_a_browser_window(client):
    assert client.get("/api/system").get_json()["shell"] is None


def test_the_schedulers_syncs_are_marked_automatic():
    from mellow import server
    update_config(lambda c: c.update(vault_playlists={"/music/A": ["https://x/pl"]}))
    with patch("mellow.server._enqueue_job") as enqueue:
        server._enqueue_vault_sync("/music/A", auto=True)
        server._enqueue_vault_sync("/music/A")
    assert enqueue.call_args_list[0].args[2]["auto_sync"] is True
    assert "auto_sync" not in enqueue.call_args_list[1].args[2]


# ── Phase 3: the title bar and native dialogs ─────────────────────────────────

def test_a_native_dialog_is_asked_of_the_shell(channel):
    from mellow import desktop

    def shell_side():
        assert wait_for(lambda: any(m["type"] == "dialog" for m in sent(channel)))
        q = next(m for m in sent(channel) if m["type"] == "dialog")
        assert (q["kind"], q["initial"]) == ("folder", "/music")
        shell.dispatch(json.dumps({"cmd": "answer", "id": q["id"], "path": "/music/Lo-fi"}))
    t = threading.Thread(target=shell_side)
    t.start()
    assert desktop.dialogs_available() and desktop.ask_folder("/music") == "/music/Lo-fi"
    t.join()


def test_a_dialog_nobody_answers_gives_up(channel):
    assert shell.ask("dialog", 0.2, kind="file") is None
    shell.dispatch('{"cmd": "answer", "id": 999999, "path": "x"}')     # an answer nobody asked for


def test_the_title_bar_buttons_go_to_the_shell(client, channel):
    for op in ("minimize", "maximize", "close"):
        assert client.post("/api/window", json={"op": op}).status_code == 200
        assert {"type": "window_op", "op": op} in sent(channel)
    assert client.post("/api/window", json={"op": "explode"}).status_code == 400


def test_the_title_bar_buttons_without_a_shell(client):
    assert client.post("/api/window", json={"op": "close"}).status_code == 409


def test_the_page_learns_its_window_has_no_frame(client, channel, monkeypatch):
    monkeypatch.setenv("MELLOW_SHELL_FRAME", "custom")
    assert client.get("/api/system").get_json()["window_frame"] == "custom"


def test_a_mellowdlp_link_goes_to_the_page(channel):
    from mellow import server
    q = server._sse_subscribe()
    try:
        _run("open_link", url="https://example.com/watch?v=1")
        assert q.get(timeout=2) == {"status": "open_link", "url": "https://example.com/watch?v=1"}
    finally:
        server._sse_unsubscribe(q)


def test_a_mellowdlp_link_waits_for_the_window_to_connect(channel):
    from mellow import server
    _run("open_link", url="https://example.com/watch?v=2")
    _run("open_link", url="javascript:alert(1)")              # never a page
    q = server._sse_subscribe()
    server._sse_unsubscribe(q)
    assert server._pending_open_link == ["https://example.com/watch?v=2"]
    server._pending_open_link.clear()


def test_the_shell_gets_the_global_shortcut(channel):
    update_config(lambda c: c.update(global_shortcut="Ctrl+Alt+M"))
    assert shell.state({"jobs": []}, paused=False)["global_shortcut"] == "Ctrl+Alt+M"


def test_the_shells_splash_hands_over_without_a_second_loading_screen(anon_client):
    from mellow import session
    session.start_instance(5123, publish=False)
    page = anon_client.get("/launch?t=" + session.launch_token() + "&splash=1").get_data(as_text=True)
    assert 'sessionStorage.setItem("mellow-splash-done", "1")' in page
    plain = anon_client.get("/launch?t=" + session.launch_token()).get_data(as_text=True)
    assert "mellow-splash-done" not in plain
    # Classic's background on both: nothing flashes white between the splash and the app
    assert "background:#07090F" in page and "background:#07090F" in plain
