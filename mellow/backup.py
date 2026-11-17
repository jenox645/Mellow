"""Backup & restore — zip the config JSON + DuckDB database, and import it back.

The archive contains at most two well-known members (BACKUP_MEMBERS); restore
refuses anything else, so a crafted zip can't write arbitrary paths.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
import zipfile
from pathlib import Path

from . import analytics
from .config import CONFIG_PATH, write_atomic
from .constants import PRE_RESTORE_KEEP

log = logging.getLogger(__name__)

CONFIG_MEMBER = "mellow_dlp.json"
DB_MEMBER = "mellow_dlp.duckdb"
BACKUP_MEMBERS = (CONFIG_MEMBER, DB_MEMBER)
MAX_RESTORE_BYTES = 512 * 1024 * 1024  # refuse absurdly large uploads
# A DuckDB database file says so at bytes 8-11 (its storage header)
DUCKDB_MAGIC = b"DUCK"
DUCKDB_MAGIC_AT = 8


def backup_filename() -> str:
    return f"mellowdlp_backup_{time.strftime('%Y%m%d_%H%M%S')}.zip"


def create_backup() -> bytes:
    """Zip the current config + analytics DB into an in-memory archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if CONFIG_PATH.exists():
            zf.write(CONFIG_PATH, CONFIG_MEMBER)
        # The live connection locks the file on Windows and may still hold
        # recent rows in the WAL; read it with everything closed.
        with analytics.exclusive_file_access() as db_path:
            if db_path.exists():
                zf.write(db_path, DB_MEMBER)
    return buf.getvalue()


def restore_backup(data: bytes) -> dict:
    """Restore config and/or DB from an uploaded backup zip.

    Both members are checked before anything is replaced (the config is a
    JSON object, the database a DuckDB file). Each replaced file is kept as a
    dated .pre-restore copy (the last PRE_RESTORE_KEEP: a second restore kept
    overwriting the only one), the new file is swapped in whole, and the
    restored database gets this version's columns (a backup from an older
    version lacked them until the next start).
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

    contents = {name: zf.read(name) for name in members}
    problem = _check_members(contents)
    if problem:
        return {"ok": False, "error": problem}

    restored: list[str] = []
    try:
        if CONFIG_MEMBER in contents:
            _replace_file(CONFIG_PATH, contents[CONFIG_MEMBER])
            restored.append(CONFIG_MEMBER)
        if DB_MEMBER in contents:
            # Swap the file with every connection closed (it is locked on
            # Windows otherwise); the next query reopens the restored DB.
            with analytics.exclusive_file_access() as db_path:
                _replace_file(db_path, contents[DB_MEMBER])
                # A WAL left by the old database must not be replayed onto the new one
                Path(str(db_path) + ".wal").unlink(missing_ok=True)
            restored.append(DB_MEMBER)
            analytics.init_db()   # this version's tables and columns
    except OSError as exc:
        return {"ok": False, "error": f"Could not write restored files: {exc}", "restored": restored}
    return {"ok": True, "restored": restored}


def _check_members(contents: dict[str, bytes]) -> str | None:
    """Why the backup can't be restored, or None. Nothing is replaced until both pass."""
    if CONFIG_MEMBER in contents:
        try:
            if not isinstance(json.loads(contents[CONFIG_MEMBER]), dict):
                raise ValueError("not an object")
        except ValueError:
            return f"{CONFIG_MEMBER} in the backup isn't a MellowDLP config (not a JSON object)"
    if DB_MEMBER in contents:
        db = contents[DB_MEMBER]
        if db[DUCKDB_MAGIC_AT:DUCKDB_MAGIC_AT + len(DUCKDB_MAGIC)] != DUCKDB_MAGIC:
            return f"{DB_MEMBER} in the backup isn't a DuckDB database"
    return None


# What follows `<name>` in a copy's name: the time of the restore, and a counter for a second one in the same second
_PRE_RESTORE_NAME = re.compile(r"\.pre-restore-(\d{8}-\d{6})(?:-(\d+))?")


def _stamp() -> str:
    """The restore's time in a copy's name (local time, to the second)."""
    return time.strftime("%Y%m%d-%H%M%S")


def _replace_file(target: Path, data: bytes) -> None:
    """Keep the current file as a dated .pre-restore copy, then swap the new one in whole."""
    if target.exists():
        stamp = _stamp()
        # Another restore within this second: the next counter after the highest one there, never a
        # number pruning freed (that copy would then look like the oldest of the second)
        taken = [order[1] for p in target.parent.glob(f"{target.name}.pre-restore-{stamp}*")
                 if (order := _copy_order(p, target)) is not None and order[0] == stamp]
        n = max(taken, default=0) + 1
        suffix = stamp if n == 1 else f"{stamp}-{n}"
        write_atomic(target.with_name(f"{target.name}.pre-restore-{suffix}"), target.read_bytes())
        _prune_pre_restore(target)
    write_atomic(target, data)


def _copy_order(copy: Path, target: Path) -> tuple[str, int] | None:
    """Where a .pre-restore copy of `target` falls in time, from its name: (stamp, n), the stamp
    `_replace_file` wrote and its counter (1 for none; `-10` after `-9`). None for a name it didn't write.

    Names, not file times: copies made within one tick of the clock (several restores in a second,
    Windows' coarse file times) have equal mtimes, and the newest could be the one pruned."""
    m = _PRE_RESTORE_NAME.fullmatch(copy.name[len(target.name):])
    return (m.group(1), int(m.group(2) or 1)) if m else None


def _prune_pre_restore(target: Path) -> None:
    """Keep the last PRE_RESTORE_KEEP copies of `target`. Files whose name `_replace_file` didn't
    write (the old single `.pre-restore`, a stray temp file) are left alone."""
    dated = [(order, p) for p in target.parent.glob(target.name + ".pre-restore-*")
             if (order := _copy_order(p, target)) is not None]
    copies = [p for _, p in sorted(dated, reverse=True)]
    for old in copies[PRE_RESTORE_KEEP:]:
        try:
            old.unlink()
        except OSError as exc:
            log.warning(f"couldn't remove {old}: {exc}")
