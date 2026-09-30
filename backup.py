"""Backup & restore — zip the config JSON + DuckDB database, and import it back.

The archive contains at most two well-known members (BACKUP_MEMBERS); restore
refuses anything else, so a crafted zip can't write arbitrary paths.
"""
from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import analytics
from config import CONFIG_PATH

CONFIG_MEMBER = "mellow_dlp.json"
DB_MEMBER = "mellow_dlp.duckdb"
BACKUP_MEMBERS = (CONFIG_MEMBER, DB_MEMBER)
MAX_RESTORE_BYTES = 512 * 1024 * 1024  # refuse absurdly large uploads


def backup_filename() -> str:
    return f"mellowdlp_backup_{time.strftime('%Y%m%d_%H%M%S')}.zip"


def create_backup() -> bytes:
    """Zip the current config + analytics DB into an in-memory archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if CONFIG_PATH.exists():
            zf.write(CONFIG_PATH, CONFIG_MEMBER)
        db_path = Path(analytics.DB_PATH)
        if db_path.exists():
            zf.write(db_path, DB_MEMBER)
    return buf.getvalue()


def restore_backup(data: bytes) -> dict:
    """Restore config and/or DB from an uploaded backup zip.

    The current files are kept as .pre-restore copies so a bad import is
    reversible by hand.
    """
    if len(data) > MAX_RESTORE_BYTES:
        return {"ok": False, "error": "Backup file too large"}
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Not a valid backup zip"}

    members = [n for n in zf.namelist() if n in BACKUP_MEMBERS]
    if not members:
        return {"ok": False, "error": f"Zip contains none of {', '.join(BACKUP_MEMBERS)}"}

    restored: list[str] = []
    db_path = Path(analytics.DB_PATH)
    targets = {CONFIG_MEMBER: CONFIG_PATH, DB_MEMBER: db_path}
    for member in members:
        target = targets[member]
        if target.exists():
            target.with_suffix(target.suffix + ".pre-restore").write_bytes(target.read_bytes())
        target.write_bytes(zf.read(member))
        restored.append(member)

    if DB_MEMBER in restored:
        # Drop the cached connection so the next query opens the new file
        analytics.reset_connections()
    return {"ok": True, "restored": restored}
