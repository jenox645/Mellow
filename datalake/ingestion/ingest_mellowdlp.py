"""
Ingestion job — Source 1: MellowDLP DuckDB
Reads download history from ~/.mellow_dlp.duckdb and dumps it as raw JSON
into data/raw/mellowdlp/downloads/YYYY-MM-DD/downloads.json
"""

import json
import os
from datetime import date, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", "~/.mellow_dlp.duckdb")).expanduser()
DATALAKE_ROOT = Path(os.getenv("DATALAKE_ROOT", "./data"))


def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def ingest(target_date: date | None = None) -> Path:
    target_date = target_date or date.today()
    out_dir = DATALAKE_ROOT / "raw" / "mellowdlp" / "downloads" / target_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "downloads.json"

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    rows = con.execute(
        """
        SELECT
            id, url, title, uploader, platform,
            duration_seconds, file_size_bytes, format, quality, container,
            file_path, timestamp, status, error_message,
            download_speed_avg_bps, elapsed_seconds, thumbnail_url
        FROM downloads
        WHERE date_trunc('day', timestamp) = ?
        ORDER BY timestamp
        """,
        [target_date],
    ).fetchall()
    cols = [d[0] for d in con.description]
    con.close()

    records = [dict(zip(cols, row)) for row in rows]
    out_file.write_text(json.dumps(records, default=_json_serial, indent=2), encoding="utf-8")
    print(f"[mellowdlp] {len(records)} records → {out_file}")
    return out_file


def ingest_all() -> None:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    dates = con.execute(
        "SELECT DISTINCT date_trunc('day', timestamp)::DATE FROM downloads ORDER BY 1"
    ).fetchall()
    con.close()
    for (d,) in dates:
        ingest(d)


if __name__ == "__main__":
    import sys
    if "--all" in sys.argv:
        ingest_all()
    else:
        ingest()
