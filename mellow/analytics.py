from __future__ import annotations

import contextlib
import csv
import io
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from . import formats
from .constants import SYNC_REPORTS_KEEP

log = logging.getLogger(__name__)

DB_PATH = Path.home() / ".mellow_dlp.duckdb"

# One process-wide connection per DB file, handed out as cursors. DuckDB
# rejects opening the same file twice with different configs in one process
# (e.g. read_only vs read-write), which made Signal API queries fail while a
# download was recording. Cursors of a shared parent are safe across threads.
_conns: dict[str, duckdb.DuckDBPyConnection] = {}
_conns_lock = threading.Lock()


def get_conn() -> duckdb.DuckDBPyConnection:
    key = str(DB_PATH)
    with _conns_lock:
        # Evict connections to other paths (tests repoint DB_PATH per run)
        for old_key in [k for k in _conns if k != key]:
            with contextlib.suppress(Exception):
                _conns.pop(old_key).close()
        if key not in _conns:
            _conns[key] = _connect(key)
        return _conns[key].cursor()


def _connect(path: str) -> duckdb.DuckDBPyConnection:
    """Open the database, surviving a write-ahead log DuckDB cannot replay.

    DuckDB fails to replay an ALTER TABLE on a table that has a DEFAULT now()
    column ("GetDefaultDatabase with no default database set"). If the app is
    killed after a schema migration and before a checkpoint, every later
    launch dies on that WAL. The database file itself is intact, so the WAL
    is moved aside (kept, not deleted) and the file is opened without it;
    init_db() then re-applies the migrations.
    """
    try:
        return duckdb.connect(path)
    except duckdb.Error as exc:
        wal = Path(path + ".wal")
        if "WAL" not in str(exc) or not wal.exists():
            raise
        aside = wal.with_name(f"{wal.name}.unreplayable-{time.strftime('%Y%m%d-%H%M%S')}")
        wal.replace(aside)
        log.warning(f"write-ahead log could not be replayed; moved to {aside.name}. "
                    f"Reason: {str(exc).splitlines()[0]}")
        return duckdb.connect(path)


def _add_missing_columns(con: duckdb.DuckDBPyConnection, table: str,
                         columns: list[tuple[str, str]]) -> None:
    existing = {row[1] for row in con.execute(f"PRAGMA table_info('{table}')").fetchall()}
    for col, typ in columns:
        if col not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def _close_all_locked() -> None:
    for key in list(_conns):
        with contextlib.suppress(Exception):
            _conns.pop(key).close()


def reset_connections() -> None:
    """Close all cached connections (the next query reopens the file)."""
    with _conns_lock:
        _close_all_locked()


@contextlib.contextmanager
def exclusive_file_access():
    """Hold the DB file closed for the duration of the block.

    DuckDB keeps the file locked on Windows while a connection is open, so
    backup/restore must read or replace it with every connection closed.
    Closing also checkpoints the WAL, so the file on disk is complete.
    """
    with _conns_lock:
        _close_all_locked()
        yield Path(DB_PATH)


def init_db() -> None:
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT,
                uploader TEXT,
                platform TEXT,
                duration_seconds INTEGER,
                file_size_bytes BIGINT,
                format TEXT,
                quality TEXT,
                container TEXT,
                file_path TEXT,
                timestamp TIMESTAMP DEFAULT now(),
                status TEXT CHECK(status IN ('success','error','cancelled')),
                error_message TEXT,
                download_speed_avg_bps BIGINT,
                elapsed_seconds INTEGER
            )
        """)
        _add_missing_columns(con, "downloads", [
            ("download_speed_avg_bps", "BIGINT"),
            ("elapsed_seconds", "INTEGER"),
            ("thumbnail_url", "TEXT"),
        ])

        con.execute("""
            CREATE TABLE IF NOT EXISTS library (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                folder TEXT,
                folder_name TEXT,
                use_subfolder BOOLEAN DEFAULT true,
                quality TEXT DEFAULT '1080p',
                mode TEXT DEFAULT 'VIDEO',
                embed_thumbnail BOOLEAN DEFAULT true,
                embed_chapters BOOLEAN DEFAULT true,
                embed_metadata BOOLEAN DEFAULT true,
                embed_subs BOOLEAN DEFAULT false,
                sub_langs TEXT DEFAULT 'en',
                sponsorblock BOOLEAN DEFAULT false,
                filename_template TEXT DEFAULT '',
                sync_mode TEXT DEFAULT 'add',
                last_synced TIMESTAMP,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        _add_missing_columns(con, "library", [
            ("container", "TEXT DEFAULT 'mp4'"),
            ("audio_format", "TEXT DEFAULT 'mp3'"),
            # One column per download toggle: a new toggle needs no edit here
            *((key, f"BOOLEAN DEFAULT {str(default).lower()}")
              for key, default in formats.TOGGLES.items()),
        ])

        con.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY,
                library_id TEXT,
                synced_at TIMESTAMP DEFAULT now(),
                new_items INTEGER,
                skipped INTEGER,
                errors INTEGER,
                duration_seconds INTEGER
            )
        """)
        _add_missing_columns(con, "sync_log", [("duration_seconds", "INTEGER")])
        # What each vault/library sync of a folder did, item by item
        con.execute("""
            CREATE TABLE IF NOT EXISTS sync_reports (
                id INTEGER PRIMARY KEY,
                folder TEXT NOT NULL,
                finished_at TIMESTAMP DEFAULT now(),
                status TEXT,
                duration_seconds INTEGER,
                details TEXT
            )
        """)
        con.execute("CREATE SEQUENCE IF NOT EXISTS downloads_seq START 1")
        con.execute("CREATE SEQUENCE IF NOT EXISTS sync_log_seq START 1")
        con.execute("CREATE SEQUENCE IF NOT EXISTS sync_reports_seq START 1")
        # Flush schema changes into the database file now: an ALTER TABLE left
        # in the WAL is exactly what DuckDB cannot replay (see _connect), and
        # a desktop app is often killed rather than closed.
        with contextlib.suppress(duckdb.Error):
            con.execute("CHECKPOINT")


def record_download(meta: dict) -> None:
    with get_conn() as con:
        con.execute("""
            INSERT INTO downloads (
                id, url, title, uploader, platform, duration_seconds,
                file_size_bytes, format, quality, container, file_path,
                status, error_message, download_speed_avg_bps, elapsed_seconds,
                thumbnail_url
            ) VALUES (nextval('downloads_seq'),?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            meta.get("url", ""),
            meta.get("title"),
            meta.get("uploader"),
            meta.get("platform"),
            meta.get("duration_seconds"),
            meta.get("file_size_bytes"),
            meta.get("format"),
            meta.get("quality"),
            meta.get("container"),
            meta.get("file_path"),
            meta.get("status", "success"),
            meta.get("error_message"),
            meta.get("download_speed_avg_bps"),
            meta.get("elapsed_seconds"),
            meta.get("thumbnail_url"),
        ])


def get_stats(time_range: str = "30d") -> dict[str, Any]:
    _days_map = {"7d": 7, "30d": 30}
    _days = _days_map.get(time_range)
    if _days:
        cutoff = datetime.now() - timedelta(days=_days)
        ts_filter = "AND timestamp >= ?"
        ts_params: list = [cutoff]
    else:
        ts_filter = ""
        ts_params = []

    with get_conn() as con:
        r = con.execute(
            f"SELECT COUNT(*), COALESCE(SUM(file_size_bytes),0) FROM downloads WHERE status='success' {ts_filter}",
            ts_params,
        ).fetchone()
        total_downloads = r[0] if r else 0
        total_size = r[1] if r else 0

        by_platform = con.execute(f"""
            SELECT platform, COUNT(*) as cnt FROM downloads
            WHERE status='success' AND platform IS NOT NULL {ts_filter}
            GROUP BY platform ORDER BY cnt DESC
        """, ts_params).fetchall()

        by_format = con.execute(f"""
            SELECT format, COUNT(*) as cnt FROM downloads
            WHERE status='success' AND format IS NOT NULL {ts_filter}
            GROUP BY format ORDER BY cnt DESC
        """, ts_params).fetchall()

        by_day = con.execute(f"""
            SELECT strftime(timestamp,'%Y-%m-%d') as day, COUNT(*) as cnt
            FROM downloads WHERE status='success' {ts_filter}
            GROUP BY day ORDER BY day
        """, ts_params).fetchall()

        top_uploaders = con.execute(f"""
            SELECT uploader, COUNT(*) as cnt FROM downloads
            WHERE status='success' AND uploader IS NOT NULL {ts_filter}
            GROUP BY uploader ORDER BY cnt DESC LIMIT 10
        """, ts_params).fetchall()

        storage_by_format = con.execute(f"""
            SELECT format, COALESCE(SUM(file_size_bytes),0) as sz FROM downloads
            WHERE status='success' AND format IS NOT NULL {ts_filter}
            GROUP BY format ORDER BY sz DESC
        """, ts_params).fetchall()

        recent_errors = con.execute("""
            SELECT title, url, error_message, timestamp FROM downloads
            WHERE status='error' ORDER BY timestamp DESC LIMIT 10
        """).fetchall()

        by_hour = con.execute(f"""
            SELECT EXTRACT(hour FROM timestamp)::INTEGER as hr, COUNT(*) as cnt
            FROM downloads WHERE status='success' {ts_filter}
            GROUP BY hr ORDER BY hr
        """, ts_params).fetchall()

        sp = con.execute(f"""
            SELECT AVG(download_speed_avg_bps), MAX(download_speed_avg_bps)
            FROM downloads WHERE status='success'
            AND download_speed_avg_bps IS NOT NULL {ts_filter}
        """, ts_params).fetchone()

        lib_row = con.execute("SELECT COUNT(*) FROM library").fetchone()
        lib_count = lib_row[0] if lib_row else 0

        recent_records = con.execute(f"""
            SELECT id, title, url, platform, format, quality,
                   file_size_bytes, timestamp, status
            FROM downloads WHERE status='success' {ts_filter}
            ORDER BY timestamp DESC LIMIT 10
        """, ts_params).fetchall()

        status_counts = con.execute(f"""
            SELECT status, COUNT(*) FROM downloads
            WHERE status IS NOT NULL {ts_filter}
            GROUP BY status
        """, ts_params).fetchall()

        failures_by_day = con.execute(f"""
            SELECT strftime(timestamp,'%Y-%m-%d') as day, COUNT(*) as cnt
            FROM downloads WHERE status='error' {ts_filter}
            GROUP BY day ORDER BY day
        """, ts_params).fetchall()

        dur_row = con.execute(f"""
            SELECT COALESCE(SUM(duration_seconds),0) FROM downloads
            WHERE status='success' {ts_filter}
        """, ts_params).fetchone()
        total_duration = dur_row[0] if dur_row else 0

        storage_growth = con.execute(f"""
            SELECT day, SUM(sz) OVER (ORDER BY day) as cum FROM (
                SELECT strftime(timestamp,'%Y-%m-%d') as day,
                       COALESCE(SUM(file_size_bytes),0) as sz
                FROM downloads WHERE status='success' {ts_filter}
                GROUP BY day
            ) ORDER BY day
        """, ts_params).fetchall()

        speed_by_day = con.execute(f"""
            SELECT strftime(timestamp,'%Y-%m-%d') as day,
                   AVG(download_speed_avg_bps) as avg_bps
            FROM downloads
            WHERE status='success' AND download_speed_avg_bps IS NOT NULL {ts_filter}
            GROUP BY day ORDER BY day
        """, ts_params).fetchall()

        dow_hour = con.execute(f"""
            SELECT EXTRACT(dow FROM timestamp)::INTEGER as dow,
                   EXTRACT(hour FROM timestamp)::INTEGER as hr,
                   COUNT(*) as cnt
            FROM downloads WHERE status='success' {ts_filter}
            GROUP BY dow, hr
        """, ts_params).fetchall()

        sync_runs = con.execute("""
            SELECT sl.synced_at, COALESCE(l.name, sl.library_id) as name,
                   sl.new_items, sl.skipped, sl.errors, sl.duration_seconds
            FROM sync_log sl LEFT JOIN library l ON l.id = sl.library_id
            ORDER BY sl.synced_at DESC LIMIT 10
        """).fetchall()

    hour_map = {row[0]: row[1] for row in by_hour}
    hourly = [hour_map.get(h, 0) for h in range(24)]

    dow_hour_map = {(r[0], r[1]): r[2] for r in dow_hour}
    # 7 rows (Sun..Sat per DuckDB dow) × 24 cols
    dow_hourly = [[dow_hour_map.get((d, h), 0) for h in range(24)] for d in range(7)]

    st_map = {r[0]: r[1] for r in status_counts}
    attempts = sum(st_map.values())

    return {
        "total_downloads": total_downloads,
        "total_size_bytes": total_size,
        "library_playlists": lib_count,
        "by_platform": [{"platform": r[0], "count": r[1]} for r in by_platform],
        "by_format": [{"format": r[0], "count": r[1]} for r in by_format],
        "by_day_last_30": [{"day": r[0], "count": r[1]} for r in by_day],
        "top_uploaders": [{"uploader": r[0], "count": r[1]} for r in top_uploaders],
        "storage_by_format": [{"format": r[0], "bytes": r[1]} for r in storage_by_format],
        "recent_errors": [
            {"title": r[0], "url": r[1], "error_message": r[2],
             "timestamp": str(r[3]) if r[3] else None}
            for r in recent_errors
        ],
        "hourly_activity": hourly,
        "avg_speed_bps": sp[0] if sp and sp[0] else 0,
        "peak_speed_bps": sp[1] if sp and sp[1] else 0,
        "recent_records": [
            {
                "id": r[0], "title": r[1], "url": r[2], "platform": r[3],
                "format": r[4], "quality": r[5], "file_size_bytes": r[6],
                "timestamp": str(r[7]) if r[7] else None, "status": r[8],
            }
            for r in recent_records
        ],
        "status_counts": st_map,
        "success_rate": round(st_map.get("success", 0) / attempts * 100, 1) if attempts else None,
        "failures_by_day": [{"day": r[0], "count": r[1]} for r in failures_by_day],
        "total_duration_seconds": int(total_duration or 0),
        "storage_growth": [{"day": r[0], "bytes": int(r[1] or 0)} for r in storage_growth],
        "speed_by_day": [{"day": r[0], "avg_bps": int(r[1] or 0)} for r in speed_by_day],
        "dow_hourly": dow_hourly,
        "sync_runs": [
            {"synced_at": str(r[0]) if r[0] else None, "name": r[1],
             "new_items": r[2], "skipped": r[3], "errors": r[4],
             "duration_seconds": r[5]}
            for r in sync_runs
        ],
    }


def get_wrapped(year: int) -> dict:
    """Year-in-review stats for the Wrapped card — one pass over downloads."""
    with get_conn() as con:
        r = con.execute("""
            SELECT COUNT(*),
                   COALESCE(SUM(file_size_bytes), 0),
                   COALESCE(SUM(duration_seconds), 0)
            FROM downloads
            WHERE status='success' AND EXTRACT(year FROM timestamp) = ?
        """, [year]).fetchone()
        total, size_bytes, duration = (r or (0, 0, 0))

        top_uploaders = con.execute("""
            SELECT uploader, COUNT(*) as cnt FROM downloads
            WHERE status='success' AND uploader IS NOT NULL
              AND EXTRACT(year FROM timestamp) = ?
            GROUP BY uploader ORDER BY cnt DESC LIMIT 5
        """, [year]).fetchall()

        by_month = con.execute("""
            SELECT EXTRACT(month FROM timestamp)::INTEGER as m, COUNT(*) as cnt
            FROM downloads WHERE status='success' AND EXTRACT(year FROM timestamp) = ?
            GROUP BY m ORDER BY m
        """, [year]).fetchall()

        busiest_day = con.execute("""
            SELECT strftime(timestamp, '%Y-%m-%d') as day, COUNT(*) as cnt
            FROM downloads WHERE status='success' AND EXTRACT(year FROM timestamp) = ?
            GROUP BY day ORDER BY cnt DESC LIMIT 1
        """, [year]).fetchone()

        statuses = con.execute("""
            SELECT status, COUNT(*) FROM downloads
            WHERE EXTRACT(year FROM timestamp) = ?
            GROUP BY status
        """, [year]).fetchall()

        fmt_split = con.execute("""
            SELECT COALESCE(format, 'video'), COUNT(*) FROM downloads
            WHERE status='success' AND EXTRACT(year FROM timestamp) = ?
            GROUP BY 1
        """, [year]).fetchall()

    month_map = {row[0]: row[1] for row in by_month}
    st_map = {row[0]: row[1] for row in statuses}
    attempts = sum(st_map.values())
    return {
        "year": year,
        "total_downloads": total,
        "total_size_bytes": int(size_bytes),
        "total_duration_seconds": int(duration),
        "top_uploaders": [{"uploader": r[0], "count": r[1]} for r in top_uploaders],
        "monthly": [month_map.get(m, 0) for m in range(1, 13)],
        "busiest_day": {"day": busiest_day[0], "count": busiest_day[1]} if busiest_day else None,
        "success_rate": round(st_map.get("success", 0) / attempts * 100, 1) if attempts else None,
        "format_split": {r[0]: r[1] for r in fmt_split},
    }


def get_history(
    limit: int = 50,
    offset: int = 0,
    type_filter: str | None = None,
    search: str | None = None,
) -> list[dict]:
    conditions: list[str] = []
    params: list[Any] = []
    if type_filter and type_filter != "all":
        conditions.append("format = ?")
        params.append(type_filter)
    if search:
        conditions.append("(title ILIKE ? OR url ILIKE ? OR uploader ILIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_conn() as con:
        rows = con.execute(f"""
            SELECT id, url, title, uploader, platform,
                   duration_seconds, file_size_bytes, format,
                   quality, container, file_path, timestamp,
                   status, error_message
            FROM downloads {where}
            ORDER BY timestamp DESC LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()
    return [
        {
            "id": r[0], "url": r[1], "title": r[2], "uploader": r[3],
            "platform": r[4], "duration_seconds": r[5], "file_size_bytes": r[6],
            "format": r[7], "quality": r[8], "container": r[9],
            "file_path": r[10],
            "timestamp": str(r[11]) if r[11] else None,
            "status": r[12], "error_message": r[13],
        }
        for r in rows
    ]


def delete_history(
    ids: list[int] | None = None,
    older_than_days: int | None = None,
    delete_all: bool = False,
) -> int:
    with get_conn() as con:
        if delete_all:
            result = con.execute("SELECT COUNT(*) FROM downloads").fetchone()
            count = result[0] if result else 0
            con.execute("DELETE FROM downloads")
            return count
        if older_than_days is not None:
            cutoff = datetime.now() - timedelta(days=int(older_than_days))
            result = con.execute(
                "SELECT COUNT(*) FROM downloads WHERE timestamp < ?", [cutoff]
            ).fetchone()
            count = result[0] if result else 0
            con.execute("DELETE FROM downloads WHERE timestamp < ?", [cutoff])
            return count
        if ids:
            placeholders = ",".join(["?" for _ in ids])
            result = con.execute(
                f"SELECT COUNT(*) FROM downloads WHERE id IN ({placeholders})", ids
            ).fetchone()
            count = result[0] if result else 0
            con.execute(f"DELETE FROM downloads WHERE id IN ({placeholders})", ids)
            return count
    return 0


def find_previous_download(urls: list[str], video_id: str | None = None) -> dict | None:
    """Latest successful download of the same video, or None.

    Matches any of the given URLs exactly; for an 11-character (YouTube-style)
    id also any history URL that contains it, since the same video arrives as
    watch?v=, youtu.be/ or a playlist entry URL.
    """
    urls = [u for u in urls if u]
    if not urls and not video_id:
        return None
    conditions = ["url = ?"] * len(urls)
    params: list[Any] = list(urls)
    if video_id and len(video_id) == 11:
        conditions.append("url LIKE ?")
        params.append(f"%{video_id}%")
    with get_conn() as con:
        row = con.execute(f"""
            SELECT title, file_path, timestamp FROM downloads
            WHERE status = 'success' AND file_path IS NOT NULL
              AND ({' OR '.join(conditions)})
            ORDER BY timestamp DESC LIMIT 1
        """, params).fetchone()
    if not row:
        return None
    title, file_path, ts = row
    return {
        "title": title,
        "file_path": file_path,
        "timestamp": str(ts) if ts else None,
        "exists": bool(file_path) and Path(file_path).is_file(),
    }


def delete_history_by_path(file_path: str) -> int:
    """Delete download rows whose file_path matches (used by vault file delete)."""
    if not file_path:
        return 0
    with get_conn() as con:
        result = con.execute(
            "SELECT COUNT(*) FROM downloads WHERE file_path = ?", [file_path]
        ).fetchone()
        count = result[0] if result else 0
        if count:
            con.execute("DELETE FROM downloads WHERE file_path = ?", [file_path])
    return count


# Leading "-- line" and "/* block */" comments, skipped when checking what
# kind of statement a query is
_LEADING_SQL_COMMENTS = re.compile(r"\A(?:\s+|--[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.DOTALL)


def run_query(sql: str) -> dict:
    stripped = sql.strip()
    body = _LEADING_SQL_COMMENTS.sub("", stripped, count=1)
    first_word = body.split(None, 1)[0].upper() if body else ""
    if first_word not in ("SELECT", "WITH"):
        return {"error": "Only SELECT statements (including WITH ... SELECT) are permitted.",
                "columns": [], "rows": [], "time_ms": 0}
    t0 = time.monotonic()
    try:
        # Shared connection (a separate read_only connection conflicts with the
        # process-wide read-write one). Run inside a rolled-back transaction so
        # anything that slips past the SELECT/WITH check can't persist writes.
        with get_conn() as con:
            con.begin()
            try:
                res = con.execute(stripped)
                columns = [d[0] for d in res.description] if res.description else []
                rows = res.fetchall()
            finally:
                with contextlib.suppress(Exception):
                    con.rollback()
        elapsed = round((time.monotonic() - t0) * 1000, 1)
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "time_ms": elapsed,
            "row_count": len(rows),
            "error": None,
        }
    except Exception as exc:
        return {"error": str(exc), "columns": [], "rows": [], "time_ms": 0}


def export_csv() -> str:
    with get_conn() as con:
        rows = con.execute("""
            SELECT id, url, title, uploader, platform, duration_seconds,
                   file_size_bytes, format, quality, container, file_path,
                   timestamp, status, error_message,
                   download_speed_avg_bps, elapsed_seconds
            FROM downloads ORDER BY timestamp DESC
        """).fetchall()
    cols = [
        "id","url","title","uploader","platform","duration_seconds",
        "file_size_bytes","format","quality","container","file_path",
        "timestamp","status","error_message","download_speed_avg_bps","elapsed_seconds",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(rows)
    return buf.getvalue()


def clear_library() -> None:
    with get_conn() as con:
        con.execute("DELETE FROM library")
        con.execute("DELETE FROM sync_log")


def vacuum() -> None:
    with get_conn() as con:
        con.execute("VACUUM")


def get_db_size() -> int:
    try:
        return DB_PATH.stat().st_size
    except OSError:
        return 0


def record_sync_log(
    library_id: str, new_items: int, skipped: int, errors: int, duration_seconds: int = 0
) -> None:
    with contextlib.suppress(Exception):
        with get_conn() as con:
            con.execute("""
                INSERT INTO sync_log (id, library_id, new_items, skipped, errors, duration_seconds)
                VALUES (nextval('sync_log_seq'),?,?,?,?,?)
            """, [library_id, new_items, skipped, errors, duration_seconds])


def record_sync_report(folder: str, status: str, report: dict, duration_seconds: int,
                       error: str | None = None) -> None:
    """Store what a sync of `folder` did; keeps the last SYNC_REPORTS_KEEP per folder.

    report: {"added": [titles], "failed": [{message, url, title, hint}],
             "filtered": [titles], "archived": count}
    """
    details = json.dumps({**report, "error": error})
    with get_conn() as con:
        con.execute(
            "INSERT INTO sync_reports (id, folder, status, duration_seconds, details) "
            "VALUES (nextval('sync_reports_seq'), ?, ?, ?, ?)",
            [folder, status, duration_seconds, details])
        con.execute("""
            DELETE FROM sync_reports WHERE folder = ? AND id NOT IN (
                SELECT id FROM sync_reports WHERE folder = ? ORDER BY id DESC LIMIT ?)
        """, [folder, folder, SYNC_REPORTS_KEEP])


def get_sync_report(folder: str) -> dict | None:
    """The latest sync report for a folder, or None."""
    with get_conn() as con:
        row = con.execute(
            "SELECT finished_at, status, duration_seconds, details FROM sync_reports "
            "WHERE folder = ? ORDER BY id DESC LIMIT 1", [folder]).fetchone()
    if not row:
        return None
    finished_at, status, duration, details = row
    return {"finished_at": str(finished_at) if finished_at else None, "status": status,
            "duration_seconds": duration, **json.loads(details or "{}")}


# Library columns besides the toggles (formats.TOGGLES), in upsert order
_LIBRARY_COLUMNS = (
    "id", "name", "url", "folder", "folder_name", "use_subfolder", "quality", "mode",
    "sub_langs", "filename_template", "sync_mode", "last_synced", "created_at",
    "container", "audio_format",
)
_LIBRARY_DEFAULTS = {
    "use_subfolder": True, "quality": "1080p", "mode": "VIDEO", "sub_langs": "en",
    "filename_template": "", "sync_mode": "add", "container": "mp4", "audio_format": "mp3",
}


def get_library_entries() -> list[dict]:
    with get_conn() as con:
        cur = con.execute("SELECT * FROM library ORDER BY created_at DESC")
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
    entries = []
    for row in rows:
        entry = {k: row.get(k) for k in _LIBRARY_COLUMNS}
        entry["container"] = entry["container"] or "mp4"
        entry["audio_format"] = entry["audio_format"] or "mp3"
        for k in ("last_synced", "created_at"):
            entry[k] = str(entry[k]) if entry[k] else None
        entries.append({**entry, **formats.toggles(row)})
    return entries


def get_library_entry(entry_id: str) -> dict | None:
    return next((e for e in get_library_entries() if e["id"] == entry_id), None)


def upsert_library_entry(entry: dict) -> None:
    columns = (*_LIBRARY_COLUMNS, *formats.TOGGLES)
    values = {**{k: entry.get(k, _LIBRARY_DEFAULTS.get(k)) for k in _LIBRARY_COLUMNS},
              **formats.toggles(entry)}
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("id", "created_at"))
    with get_conn() as con:
        con.execute(
            f"INSERT INTO library ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) "
            f"ON CONFLICT (id) DO UPDATE SET {updates}",
            [values[c] for c in columns])


def delete_library_entry(entry_id: str) -> None:
    with get_conn() as con:
        con.execute("DELETE FROM library WHERE id = ?", [entry_id])


def update_library_last_synced(entry_id: str) -> None:
    with get_conn() as con:
        con.execute("UPDATE library SET last_synced = now() WHERE id = ?", [entry_id])
