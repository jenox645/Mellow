"""A triage's findings: custom SQL, backup restore, the saved queue, yt-dlp
updates and the write guard's origin check."""
from __future__ import annotations

import io
import json
import threading
import time
import zipfile
from unittest.mock import patch

import duckdb
import pytest

from mellow import analytics, backup, jobs, ytdlp_update
from mellow.constants import PRE_RESTORE_KEEP

# ── Custom SQL: one SELECT ────────────────────────────────────────────────────


def test_a_select_followed_by_other_statements_is_refused(tmp_path):
    analytics.init_db()
    out = tmp_path / "leak.csv"
    result = analytics.run_query(f"SELECT 1; COMMIT; COPY (SELECT 1) TO '{out}'")
    assert result["error"] and "One SELECT" in result["error"]
    assert not out.exists()          # nothing after the SELECT ran


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM downloads",
    "SELECT COUNT(*) FROM downloads;",
    "WITH d AS (SELECT * FROM downloads) SELECT COUNT(*) FROM d",
    "-- how many\nSELECT COUNT(*) FROM downloads",
])
def test_one_select_still_runs(sql):
    analytics.init_db()
    result = analytics.run_query(sql)
    assert result["error"] is None and result["rows"] == [[0]]


# ── Backup restore ────────────────────────────────────────────────────────────

def _backup_zip(config: bytes | None = None, db: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if config is not None:
            zf.writestr(backup.CONFIG_MEMBER, config)
        if db is not None:
            zf.writestr(backup.DB_MEMBER, db)
    return buf.getvalue()


def _config_path():
    return backup.CONFIG_PATH


def test_each_restore_keeps_its_own_copy_of_what_it_replaced():
    cfg = _config_path()
    for n in range(PRE_RESTORE_KEEP + 2):
        cfg.write_text(json.dumps({"output_dir": f"before-{n}"}), encoding="utf-8")
        assert backup.restore_backup(_backup_zip(config=b'{"output_dir": "restored"}'))["ok"]
    copies = sorted(cfg.parent.glob(cfg.name + ".pre-restore-*"))
    assert len(copies) == PRE_RESTORE_KEEP           # the newest ones, never just one
    kept = {json.loads(c.read_text(encoding="utf-8"))["output_dir"] for c in copies}
    assert kept == {f"before-{n}" for n in range(2, PRE_RESTORE_KEEP + 2)}
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"output_dir": "restored"}


@pytest.mark.parametrize("members, error", [
    ({"db": b"this is not a database at all, honestly"}, "isn't a DuckDB database"),
    ({"config": b"[1, 2, 3]"}, "isn't a MellowDLP config"),
    ({"config": b"{not json"}, "isn't a MellowDLP config"),
    # A good config with a bad database: neither is replaced
    ({"config": b'{"output_dir": "new"}', "db": b"garbage" * 10}, "isn't a DuckDB database"),
])
def test_a_bad_backup_replaces_nothing(members, error):
    cfg = _config_path()
    cfg.write_text('{"output_dir": "mine"}', encoding="utf-8")
    result = backup.restore_backup(_backup_zip(members.get("config"), members.get("db")))
    assert result["ok"] is False and error in result["error"]
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"output_dir": "mine"}
    assert not list(cfg.parent.glob(cfg.name + ".pre-restore-*"))


def test_a_backup_from_an_older_version_gets_this_versions_columns(tmp_path):
    old = tmp_path / "old.duckdb"
    con = duckdb.connect(str(old))      # a database before video_id was recorded
    con.execute("CREATE TABLE downloads (id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT, "
                "timestamp TIMESTAMP DEFAULT now(), status TEXT)")
    con.execute("INSERT INTO downloads (id, url, title, status) VALUES (1, 'https://x/v', 'Old', 'success')")
    con.close()
    assert backup.restore_backup(_backup_zip(db=old.read_bytes()))["ok"]
    with analytics.get_conn() as c:
        columns = {row[1] for row in c.execute("PRAGMA table_info('downloads')").fetchall()}
        title = c.execute("SELECT title FROM downloads").fetchone()[0]
    assert "video_id" in columns and title == "Old"     # usable right away, the row kept


# ── The saved queue ───────────────────────────────────────────────────────────

def test_queue_saves_never_overlap(monkeypatch):
    """Two threads saving at once could write the older snapshot last: a
    cancelled job came back at the next start."""
    inside, overlaps = [0], []
    real = jobs.write_atomic

    def slow_write(path, data):
        inside[0] += 1
        overlaps.append(inside[0])
        time.sleep(0.05)
        real(path, data)
        inside[0] -= 1

    monkeypatch.setattr(jobs, "write_atomic", slow_write)
    m = jobs.JobManager()
    m._pending = [{"id": "a", "url": "https://x/a", "status": "queued"}]
    threads = [threading.Thread(target=m._persist) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlaps and max(overlaps) == 1


def test_a_save_while_a_worker_saves_with_the_queue_locked_never_deadlocks():
    """A worker saves with the queue lock held (a job just finished); a
    download being added saves too. Holding the save lock while waiting for
    the queue lock froze both, and the whole app with them."""
    m = jobs.JobManager()
    m._pending = [{"id": "a", "url": "https://x/a", "status": "queued"}]
    real = m._persist_lock
    saving, worker_holds_queue = threading.Event(), threading.Event()

    class SaveLock:
        """The real save lock; the first thread in waits for the worker to take the queue lock."""
        def __enter__(self):
            real.acquire()
            if not saving.is_set():
                saving.set()
                worker_holds_queue.wait(2)
            return self

        def __exit__(self, *exc):
            real.release()

    m._persist_lock = SaveLock()

    def worker_finishing_a_job():
        saving.wait(2)
        with m._cv:
            worker_holds_queue.set()
            m._persist()

    worker = threading.Thread(target=worker_finishing_a_job, daemon=True)
    adding = threading.Thread(target=m._persist, daemon=True)
    worker.start()
    adding.start()
    adding.join(5)
    worker.join(5)
    assert not adding.is_alive() and not worker.is_alive(), "the two saves deadlocked"
    assert json.loads(jobs.QUEUE_STATE_PATH.read_text(encoding="utf-8"))[0]["id"] == "a"


def test_a_failed_save_keeps_the_last_saved_queue(monkeypatch):
    m = jobs.JobManager()
    m._pending = [{"id": "a", "url": "https://x/a", "status": "queued"}]
    m._persist()
    saved = jobs.QUEUE_STATE_PATH.read_text(encoding="utf-8")
    m._pending.append({"id": "b", "url": "https://x/b", "status": "queued"})
    with patch("mellow.config.os.replace", side_effect=OSError("disk full")):
        m._persist()
    assert jobs.QUEUE_STATE_PATH.read_text(encoding="utf-8") == saved     # whole, the old one
    assert not list(jobs.QUEUE_STATE_PATH.parent.glob(jobs.QUEUE_STATE_PATH.name + "*.tmp"))


# ── yt-dlp update: one at a time ──────────────────────────────────────────────

def test_a_second_ytdlp_update_is_refused_while_one_runs(client):
    started, release = threading.Event(), threading.Event()

    def slow_download():
        started.set()
        release.wait(5)
        return "2099.01.01"

    events = []
    with patch("mellow.ytdlp_update.download_latest", side_effect=slow_download), \
            patch("mellow.server._push_progress", side_effect=events.append):
        assert client.post("/api/update-ytdlp", json={}).status_code == 200
        assert started.wait(5)
        second = client.post("/api/update-ytdlp", json={})
        assert second.status_code == 409 and "already" in second.get_json()["error"]
        release.set()
        for _ in range(100):
            if not ytdlp_update.updating():
                break
            time.sleep(0.02)
    assert [e["ok"] for e in events] == [True]       # one result, no "Update failed"


# ── Write guard: the whole origin ─────────────────────────────────────────────

@pytest.mark.parametrize("origin, allowed", [
    (None, True),
    ("http://localhost", True),                   # the app's own page (the test client's port)
    ("http://127.0.0.1", True),
    ("http://localhost:3000", False),             # another program's page on this machine
    ("http://evil.example", False),
    ("null", False),
])
def test_a_write_from_another_origin_is_refused_port_included(client, origin, allowed):
    headers = {"Origin": origin} if origin else {}
    r = client.post("/api/analytics/overrides", json={}, headers=headers)
    assert (r.status_code != 403) is allowed, r.get_json()
