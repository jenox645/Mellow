"""The analytics DB must open after the app was killed mid-migration.

DuckDB cannot replay an ALTER TABLE from its write-ahead log when the table
has a DEFAULT now() column. An app killed between a schema migration and the
next checkpoint used to crash on every later launch ("Failure while replaying
WAL file ... GetDefaultDatabase with no default database set").
"""
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

import analytics

REPO = Path(__file__).resolve().parent.parent

# The library table as shipped before the container/audio_format columns
OLD_LIBRARY = (
    "CREATE TABLE library (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, "
    "folder TEXT, folder_name TEXT, use_subfolder BOOLEAN DEFAULT true, "
    "quality TEXT DEFAULT '1080p', mode TEXT DEFAULT 'VIDEO', "
    "embed_thumbnail BOOLEAN DEFAULT true, embed_chapters BOOLEAN DEFAULT true, "
    "embed_metadata BOOLEAN DEFAULT true, embed_subs BOOLEAN DEFAULT false, "
    "sub_langs TEXT DEFAULT 'en', sponsorblock BOOLEAN DEFAULT false, "
    "filename_template TEXT DEFAULT '', sync_mode TEXT DEFAULT 'add', "
    "last_synced TIMESTAMP, created_at TIMESTAMP DEFAULT now())"
)


def _run_and_die(code: str, db: Path) -> None:
    """Run code against db in a child process that exits without closing it."""
    script = (
        "import os, sys, duckdb\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        f"DB = {str(db)!r}\n"
        f"{code}\n"
        "os._exit(0)\n"
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=60)


def _wals_set_aside(db: Path) -> list[Path]:
    return list(db.parent.glob(db.name + ".wal.unreplayable-*"))


def test_unreplayable_wal_is_set_aside_and_the_db_opens(isolated_user_files):
    db = Path(analytics.DB_PATH)
    analytics.reset_connections()
    db.unlink()
    _run_and_die(
        "con = duckdb.connect(DB)\n"
        f"con.execute({OLD_LIBRARY!r})\n"
        "con.execute(\"INSERT INTO library (id, name, url) VALUES ('1', 'kept', 'u')\")\n"
        "con.execute('CHECKPOINT')\n"
        "con.execute(\"ALTER TABLE library ADD COLUMN container TEXT DEFAULT 'mp4'\")",
        db)
    # Precondition: this really is the crash the user saw
    with pytest.raises(duckdb.Error, match="replaying WAL"):
        duckdb.connect(str(db))

    analytics.init_db()

    assert len(_wals_set_aside(db)) == 1, "the WAL must be kept aside, not deleted"
    entries = analytics.get_library_entries()
    assert [e["name"] for e in entries] == ["kept"]
    # The migration the lost WAL held has been re-applied
    assert entries[0]["container"] == "mp4" and entries[0]["audio_format"] == "mp3"


def test_migration_survives_being_killed_right_after_init(isolated_user_files):
    """init_db checkpoints, so its own ALTERs never sit in the WAL."""
    db = Path(analytics.DB_PATH)
    analytics.reset_connections()
    db.unlink()
    _run_and_die(
        "con = duckdb.connect(DB)\n"
        f"con.execute({OLD_LIBRARY!r})\n"
        "con.close()\n"
        "import analytics\n"
        "from pathlib import Path\n"
        "analytics.DB_PATH = Path(DB)\n"
        "analytics.init_db()",
        db)

    con = duckdb.connect(str(db))  # plain connect: no recovery needed
    columns = {row[1] for row in con.execute("PRAGMA table_info('library')").fetchall()}
    con.close()
    assert {"container", "audio_format"} <= columns
    assert _wals_set_aside(db) == []


def test_other_open_errors_are_not_swallowed(tmp_path):
    bogus = tmp_path / "not_a_database.duckdb"
    bogus.write_bytes(b"this is not a duckdb file")
    with pytest.raises(duckdb.Error):
        analytics._connect(str(bogus))
    assert list(tmp_path.glob("*.unreplayable-*")) == []
