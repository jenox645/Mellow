from __future__ import annotations

import contextlib
import csv
import io
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from constants import MEDIA_EXTS

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
            _conns[key] = duckdb.connect(key)
        return _conns[key].cursor()


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
        for col, typ in [
            ("download_speed_avg_bps", "BIGINT"),
            ("elapsed_seconds", "INTEGER"),
            ("thumbnail_url", "TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE downloads ADD COLUMN {col} {typ}")
            except Exception:
                pass

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
        for col, typ in [
            ("container", "TEXT DEFAULT 'mp4'"),
            ("audio_format", "TEXT DEFAULT 'mp3'"),
        ]:
            try:
                con.execute(f"ALTER TABLE library ADD COLUMN {col} {typ}")
            except Exception:
                pass

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
        try:
            con.execute("ALTER TABLE sync_log ADD COLUMN duration_seconds INTEGER")
        except Exception:
            pass
        con.execute("CREATE SEQUENCE IF NOT EXISTS downloads_seq START 1")
        con.execute("CREATE SEQUENCE IF NOT EXISTS sync_log_seq START 1")


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


def run_query(sql: str) -> dict:
    stripped = sql.strip()
    first_word = stripped.split(None, 1)[0].upper() if stripped else ""
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


def get_vault_folders(base_path: str) -> list[dict]:
    root = Path(base_path)
    if not root.exists():
        return []
    result = []
    try:
        for item in sorted(root.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                try:
                    all_files = [f for f in item.rglob("*") if f.is_file() and not f.name.startswith(".")]
                    media_files = [f for f in all_files if f.suffix.lower() in MEDIA_EXTS]
                    size = sum(f.stat().st_size for f in media_files if f.exists())
                    st = item.stat()
                except PermissionError:
                    all_files, media_files, size, st = [], [], 0, None
                result.append({
                    "name": item.name,
                    "path": str(item),
                    "item_count": len(media_files),
                    "size_bytes": size,
                    "created_at": st.st_ctime if st else None,
                    "modified_at": st.st_mtime if st else None,
                })
    except PermissionError:
        pass
    return result


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


def get_library_entries() -> list[dict]:
    with get_conn() as con:
        rows = con.execute("""
            SELECT id, name, url, folder, folder_name, use_subfolder,
                   quality, mode, embed_thumbnail, embed_chapters,
                   embed_metadata, embed_subs, sub_langs, sponsorblock,
                   filename_template, sync_mode, last_synced, created_at,
                   container, audio_format
            FROM library ORDER BY created_at DESC
        """).fetchall()
    return [
        {
            "id": r[0], "name": r[1], "url": r[2], "folder": r[3],
            "folder_name": r[4], "use_subfolder": r[5], "quality": r[6],
            "mode": r[7], "embed_thumbnail": r[8], "embed_chapters": r[9],
            "embed_metadata": r[10], "embed_subs": r[11], "sub_langs": r[12],
            "sponsorblock": r[13], "filename_template": r[14],
            "sync_mode": r[15],
            "last_synced": str(r[16]) if r[16] else None,
            "created_at": str(r[17]) if r[17] else None,
            "container": r[18] or "mp4",
            "audio_format": r[19] or "mp3",
        }
        for r in rows
    ]


def upsert_library_entry(entry: dict) -> None:
    with get_conn() as con:
        con.execute("""
            INSERT INTO library
                (id,name,url,folder,folder_name,use_subfolder,quality,mode,
                 embed_thumbnail,embed_chapters,embed_metadata,embed_subs,sub_langs,
                 sponsorblock,filename_template,sync_mode,last_synced,created_at,
                 container,audio_format)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (id) DO UPDATE SET
                name=excluded.name, url=excluded.url, folder=excluded.folder,
                folder_name=excluded.folder_name, use_subfolder=excluded.use_subfolder,
                quality=excluded.quality, mode=excluded.mode,
                embed_thumbnail=excluded.embed_thumbnail,
                embed_chapters=excluded.embed_chapters,
                embed_metadata=excluded.embed_metadata,
                embed_subs=excluded.embed_subs, sub_langs=excluded.sub_langs,
                sponsorblock=excluded.sponsorblock,
                filename_template=excluded.filename_template,
                sync_mode=excluded.sync_mode, last_synced=excluded.last_synced,
                container=excluded.container, audio_format=excluded.audio_format
        """, [
            entry["id"], entry["name"], entry["url"],
            entry.get("folder"), entry.get("folder_name"),
            entry.get("use_subfolder", True), entry.get("quality", "1080p"),
            entry.get("mode", "VIDEO"), entry.get("embed_thumbnail", True),
            entry.get("embed_chapters", True), entry.get("embed_metadata", True),
            entry.get("embed_subs", False), entry.get("sub_langs", "en"),
            entry.get("sponsorblock", False), entry.get("filename_template", ""),
            entry.get("sync_mode", "add"), entry.get("last_synced"),
            entry.get("created_at"),
            entry.get("container", "mp4"), entry.get("audio_format", "mp3"),
        ])


def delete_library_entry(entry_id: str) -> None:
    with get_conn() as con:
        con.execute("DELETE FROM library WHERE id = ?", [entry_id])


def update_library_last_synced(entry_id: str) -> None:
    with get_conn() as con:
        con.execute("UPDATE library SET last_synced = now() WHERE id = ?", [entry_id])
