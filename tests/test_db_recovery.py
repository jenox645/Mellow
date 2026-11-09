"""The analytics DB must open after the app was killed or a disk filled up,
and stay a file older MellowDLP versions open.

DuckDB 1.x could not replay an ALTER TABLE from its write-ahead log when the
table has a DEFAULT now() column. An app killed between a schema migration and
the next checkpoint used to crash on every later launch ("Failure while
replaying WAL file ... GetDefaultDatabase with no default database set").
"""
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from mellow import analytics

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
    """A WAL DuckDB refuses to replay (cut short by a crash or a full disk,
    or DuckDB 1.x's ALTER TABLE bug below) must not stop the app starting."""
    db = Path(analytics.DB_PATH)
    analytics.reset_connections()
    db.unlink()
    _run_and_die(
        "con = duckdb.connect(DB)\n"
        f"con.execute({OLD_LIBRARY!r})\n"
        "con.execute(\"INSERT INTO library (id, name, url) VALUES ('1', 'kept', 'u')\")\n"
        "con.execute('CHECKPOINT')\n"
        "con.execute(\"INSERT INTO library (id, name, url) VALUES ('2', 'unsaved', 'u')\")",
        db)
    wal = Path(str(db) + ".wal")
    torn = bytearray(wal.read_bytes())
    torn[len(torn) // 2:] = bytes(b ^ 0xFF for b in torn[len(torn) // 2:])
    wal.write_bytes(bytes(torn))
    # Precondition: this really is a WAL DuckDB refuses
    with pytest.raises(duckdb.Error, match="replaying WAL"):
        duckdb.connect(str(db))

    analytics.init_db()

    assert len(_wals_set_aside(db)) == 1, "the WAL must be kept aside, not deleted"
    entries = analytics.get_library_entries()
    assert [e["name"] for e in entries] == ["kept"]
    # The migrations init_db() makes are there
    assert entries[0]["container"] == "mp4" and entries[0]["audio_format"] == "mp3"


def test_a_db_killed_mid_migration_opens_with_its_rows(isolated_user_files):
    """Killed right after an ALTER TABLE on a table with a DEFAULT now()
    column: DuckDB 1.x couldn't replay that WAL and every launch crashed."""
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

    analytics.init_db()

    entries = analytics.get_library_entries()
    assert [e["name"] for e in entries] == ["kept"]
    assert entries[0]["container"] == "mp4" and entries[0]["audio_format"] == "mp3"


def _storage_version(db: Path) -> int:
    """The storage format number in a DuckDB file's header (after the DUCK magic)."""
    header = db.read_bytes()[:20]
    assert header[8:12] == b"DUCK"
    return int.from_bytes(header[12:20], "little")


# The newest storage format DuckDB 1.5 opens (MellowDLP 2.14.1 and older)
DUCKDB_1_5_NEWEST_FORMAT = 68


def test_a_new_db_is_one_older_versions_can_open(isolated_user_files):
    """DuckDB 2.0 writes a format 1.5 refuses ("version number 69, but we can
    only read versions between 64 and 68"): an older MellowDLP, reinstalled or
    given a backup made by this one, then crashed before showing a window."""
    db = Path(analytics.DB_PATH)
    analytics.reset_connections()
    db.unlink()
    analytics.init_db()
    analytics.reset_connections()
    assert _storage_version(db) <= DUCKDB_1_5_NEWEST_FORMAT


def test_an_existing_db_keeps_its_format(isolated_user_files):
    db = Path(analytics.DB_PATH)
    analytics.reset_connections()
    db.unlink()
    _run_and_die(
        "con = duckdb.connect(DB, config={'storage_compatibility_version': 'v1.0.0'})\n"
        f"con.execute({OLD_LIBRARY!r})\n"
        "con.execute('CHECKPOINT')",
        db)
    before = _storage_version(db)
    analytics.init_db()          # migrations, writes, a checkpoint
    analytics.reset_connections()
    assert _storage_version(db) == before


def test_migration_survives_being_killed_right_after_init(isolated_user_files):
    """init_db checkpoints, so its own ALTERs never sit in the WAL."""
    db = Path(analytics.DB_PATH)
    analytics.reset_connections()
    db.unlink()
    _run_and_die(
        "con = duckdb.connect(DB)\n"
        f"con.execute({OLD_LIBRARY!r})\n"
        "con.close()\n"
        "from mellow import analytics\n"
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
