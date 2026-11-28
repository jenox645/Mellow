"""What the backend loads at start (#124): no Tk under the desktop shell, and
DuckDB opened by its first use, with this version's migrations before any query."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import duckdb
import pytest

from mellow import analytics, formats

ROOT = Path(__file__).resolve().parents[1]

# The backend as the Tauri shell runs it: MELLOW_SHELL=tauri, a shell attached
# to its channel (faked: it answers the dialog and clipboard questions), and the
# page's dialog and clipboard routes called by a signed-in window
_UNDER_THE_SHELL = r"""
import io, json, sys, threading
from mellow import server, session, shell

class FakeShell(io.TextIOBase):
    asked = []
    def write(self, text):
        for line in text.splitlines():
            if not line.startswith(shell.EVENT_PREFIX):
                continue
            message = json.loads(line[len(shell.EVENT_PREFIX):])
            if message["type"] in ("dialog", "clipboard"):
                self.asked.append(message["type"])
                answer = {"cmd": "answer", "id": message["id"],
                          "path": "/picked/" + message.get("kind", ""), "text": " https://example.com/v \n"}
                threading.Thread(target=shell.dispatch, args=(json.dumps(answer),)).start()
        return len(text)
    def flush(self):
        pass

app = server.init_app()
fake = FakeShell()
shell.attach(fake, open_pages=lambda: 0)
sid, token = session.new_session()
client = app.test_client()
client.set_cookie(session.COOKIE, sid, domain="localhost")
headers = {session.HEADER: token}
answers = {
    "folder": client.post("/api/browse-folder", json={"initial": "/music"}, headers=headers).get_json(),
    "file": client.post("/api/browse-file", json={"filter": ".txt"}, headers=headers).get_json(),
    "clipboard": client.get("/api/clipboard", headers=headers).get_json(),
}
shell.detach()
print(json.dumps({"answers": answers, "asked": fake.asked,
                  "tk": sorted(m for m in sys.modules if m.split(".")[0] in ("tkinter", "_tkinter"))}))
"""

# Start as main.py does, up to the server listening: nothing opens the database
_AT_START = r"""
import json, sys
from pathlib import Path
from mellow import analytics, server
server.init_app()
print(json.dumps({"duckdb": "duckdb" in sys.modules, "open": analytics.is_open(),
                  "file": Path(analytics.DB_PATH).exists()}))
"""


def _run(code: str, home: Path, **env) -> dict:
    """`code` in a fresh Python (nothing imported yet, unlike this test run), in `home`."""
    full_env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
                "LOCALAPPDATA": str(home / "AppData" / "Local"),
                "XDG_DATA_HOME": str(home / ".local" / "share"), **env}
    full_env.pop("MELLOW_SHELL", None)
    full_env.update(env)
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=full_env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


# ── No Tk under the shell ────────────────────────────────────────────────────

def test_under_the_shell_dialogs_and_the_clipboard_never_import_tkinter(tmp_path):
    result = _run(_UNDER_THE_SHELL, tmp_path, MELLOW_SHELL="tauri")
    assert result["tk"] == []
    assert result["asked"] == ["dialog", "dialog", "clipboard"]
    assert result["answers"] == {"folder": {"path": "/picked/folder"}, "file": {"path": "/picked/file"},
                                 "clipboard": {"text": "https://example.com/v"}}


def test_without_the_shell_tk_is_still_the_dialogs(monkeypatch):
    # FlaskWebGUI's window (and --no-window): unchanged, Tk shows the dialogs
    from mellow import desktop
    tk = sys.modules["tkinter"]          # conftest's stand-in
    tk.filedialog.askdirectory.return_value = "/music/Lo-fi"
    monkeypatch.setattr(desktop, "tkinter_available", True)
    assert desktop.dialogs_available()
    assert desktop.ask_folder("/music") == "/music/Lo-fi"
    tk.filedialog.askdirectory.assert_called_with(initialdir="/music", mustexist=False)


def test_tk_is_found_without_being_imported(tmp_path):
    code = ("import json, sys, importlib.util; from mellow import desktop; "
            "print(json.dumps({'available': desktop.tkinter_available, 'imported': 'tkinter' in sys.modules, "
            "'installed': importlib.util.find_spec('tkinter') is not None}))")
    result = _run(code, tmp_path)
    assert result["available"] == result["installed"]
    assert result["imported"] is False
    under_shell = _run(code, tmp_path, MELLOW_SHELL="tauri")
    assert under_shell["available"] is False and under_shell["imported"] is False


def test_a_shell_that_doesnt_answer_the_clipboard_gives_nothing_on_windows(monkeypatch):
    from mellow import desktop, shell
    monkeypatch.setattr(shell, "active", lambda: True)
    monkeypatch.setattr(shell, "ask", lambda *a, **k: None)     # an older shell ignores the question
    monkeypatch.setattr(desktop.platform, "system", lambda: "Windows")
    monkeypatch.setattr(desktop, "tkinter_available", False)
    assert desktop.clipboard_text() == ""


# ── DuckDB on first use ──────────────────────────────────────────────────────

def test_starting_the_server_opens_no_database(tmp_path):
    assert _run(_AT_START, tmp_path) == {"duckdb": False, "open": False, "file": False}


def _old_database(path: Path) -> None:
    """A database from an older version: this version's first tables, without
    the columns (and the sync_reports table) that came later."""
    con = duckdb.connect(str(path))
    con.execute("""CREATE TABLE downloads (id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT,
                   uploader TEXT, platform TEXT, duration_seconds INTEGER, file_size_bytes BIGINT,
                   format TEXT, quality TEXT, container TEXT, file_path TEXT,
                   timestamp TIMESTAMP DEFAULT now(),
                   status TEXT CHECK(status IN ('success','error','cancelled')), error_message TEXT)""")
    con.execute("CREATE SEQUENCE downloads_seq START 2")
    con.execute("INSERT INTO downloads (id, url, title, status, file_path) "
                "VALUES (1, 'https://example.com/a', 'Old one', 'success', '/music/a.mp3')")
    con.execute("""CREATE TABLE library (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                   folder TEXT, folder_name TEXT, use_subfolder BOOLEAN DEFAULT true,
                   quality TEXT DEFAULT '1080p', mode TEXT DEFAULT 'VIDEO',
                   embed_thumbnail BOOLEAN DEFAULT true, embed_chapters BOOLEAN DEFAULT true,
                   embed_metadata BOOLEAN DEFAULT true, embed_subs BOOLEAN DEFAULT false,
                   sub_langs TEXT DEFAULT 'en', sponsorblock BOOLEAN DEFAULT false,
                   filename_template TEXT DEFAULT '', sync_mode TEXT DEFAULT 'add',
                   last_synced TIMESTAMP, created_at TIMESTAMP DEFAULT now())""")
    con.execute("""CREATE TABLE sync_log (id INTEGER PRIMARY KEY, library_id TEXT,
                   synced_at TIMESTAMP DEFAULT now(), new_items INTEGER, skipped INTEGER, errors INTEGER)""")
    con.close()


# Everything that can be the first to ask for the database: the page's first
# requests (stats, the vault's library and sync reports), a download's history
# row, the scheduler's backoff, Signal's SQL, the history browser
FIRST_CALLERS = {
    "get_stats": lambda: analytics.get_stats("all"),
    "get_history": lambda: analytics.get_history(),
    "get_library_entries": lambda: analytics.get_library_entries(),
    "get_sync_report": lambda: analytics.get_sync_report("/music"),
    "recent_sync_outcomes": lambda: analytics.recent_sync_outcomes("/music"),
    "sources_of": lambda: analytics.sources_of("/music/a.mp3"),
    "is_recorded": lambda: analytics.is_recorded("/music/a.mp3"),
    "find_previous_download": lambda: analytics.find_previous_download(["https://example.com/a"]),
    "run_query": lambda: analytics.run_query("SELECT video_id FROM downloads"),
    "export_csv": lambda: analytics.export_csv(),
    "record_download": lambda: analytics.record_download(
        {"url": "https://example.com/b", "title": "New", "status": "success", "video_id": "b"}),
}


@pytest.fixture
def unopened(tmp_path, monkeypatch):
    """A database path this process hasn't opened yet (conftest opened another)."""
    analytics.reset_connections()
    path = tmp_path / "first-use.duckdb"
    monkeypatch.setattr(analytics, "DB_PATH", path)
    yield path
    analytics.reset_connections()


@pytest.mark.parametrize("caller", FIRST_CALLERS, ids=list(FIRST_CALLERS))
@pytest.mark.parametrize("start", ["new", "old"])
def test_every_first_caller_gets_this_versions_tables(unopened, caller, start):
    if start == "old":
        _old_database(unopened)
    assert not analytics.is_open()
    result = FIRST_CALLERS[caller]()
    assert analytics.is_open()
    if caller == "run_query":
        assert result["error"] is None, result
    with analytics.get_conn() as con:
        columns = {t: {r[1] for r in con.execute(f"PRAGMA table_info('{t}')").fetchall()}
                   for t in ("downloads", "library", "sync_log", "sync_reports")}
    assert {"video_id", "thumbnail_url", "elapsed_seconds"} <= columns["downloads"]
    assert {"container", "audio_format", *formats.TOGGLES} <= columns["library"]
    assert "duration_seconds" in columns["sync_log"] and columns["sync_reports"]


def test_the_old_rows_survive_the_first_use(unopened):
    _old_database(unopened)
    rows = analytics.get_history()
    assert any(r.get("title") == "Old one" for r in (rows.get("items") if isinstance(rows, dict) else rows))


def test_the_pages_first_requests_open_it(unopened, client):
    _old_database(unopened)
    for path in ("/api/stats", "/api/history", "/api/vault/sync-report?path=/music"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/stats").get_json()["total_downloads"] == 1


def test_many_first_users_at_once_migrate_it_once(unopened):
    _old_database(unopened)
    opened = []
    real_connect = analytics._connect

    def counting_connect(path):
        opened.append(path)
        return real_connect(path)
    errors = []

    def first_use():
        try:
            analytics.get_stats("all")
            analytics.get_library_entries()
        except Exception as exc:     # noqa: BLE001 — reported below
            errors.append(exc)
    analytics._connect, saved = counting_connect, analytics._connect
    try:
        threads = [threading.Thread(target=first_use) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        analytics._connect = saved
    assert errors == [] and opened == [str(unopened)]


def test_a_migration_that_fails_leaves_nothing_half_open(unopened, monkeypatch):
    def broken(_con):
        raise duckdb.IOException("disk full")
    monkeypatch.setattr(analytics, "_migrate", broken)
    with pytest.raises(duckdb.IOException):
        analytics.get_stats("all")
    assert not analytics.is_open()
    monkeypatch.undo()
    monkeypatch.setattr(analytics, "DB_PATH", unopened)
    assert analytics.get_history() is not None     # the next use opens and migrates it


def test_a_restored_database_is_migrated_when_it_is_next_used(unopened):
    analytics.get_stats("all")
    with analytics.exclusive_file_access() as db_path:
        db_path.unlink()
        _old_database(db_path)
    assert not analytics.is_open()
    assert "video_id" in analytics.run_query("SELECT * FROM downloads")["columns"]
