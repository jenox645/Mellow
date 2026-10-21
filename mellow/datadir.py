"""The owner-only data folder.

Linux: $XDG_DATA_HOME/mellowdlp (~/.local/share/mellowdlp), Windows:
%LOCALAPPDATA%\\MellowDLP, macOS: ~/Library/Application Support/MellowDLP.
Today it holds only what no other account may read (session.py's instance
file and launch pages); the other per-user files still live in the home
folder.
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path


def data_dir(environ: dict | None = None) -> Path:
    """This account's data folder (`environ`: another process's environment,
    e.g. the throwaway home a build check starts the app with)."""
    env = os.environ if environ is None else environ
    home = Path(env.get("USERPROFILE" if os.name == "nt" else "HOME") or Path.home())
    if os.name == "nt":
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / "MellowDLP"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "MellowDLP"
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / "mellowdlp"


def ensure_private() -> Path:
    """The data folder, created if needed and readable by this account only.

    Windows: %LOCALAPPDATA% is already private to the account. Elsewhere the
    folder is made 0700; one owned by another account is refused.
    """
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        st = folder.stat()
        if st.st_uid != os.geteuid():
            raise PermissionError(f"{folder} belongs to another account")
        if stat.S_IMODE(st.st_mode) != 0o700:
            folder.chmod(0o700)
    return folder


def write_private(path: Path, text: str) -> None:
    """Replace `path` with `text`, whole, readable by this account only (mkstemp: 0600)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
