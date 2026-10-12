"""Moving a vault folder somewhere else, with everything that names it.

A folder is known by its path in many places: the config (linked
playlists, sync format, last sync time, display name, budget, schedule,
the watched/hidden lists, the SAVE TO history), its library entry, the
download history and the sync reports. move_folder() moves it on disk and
rewrites each of them, so the folder keeps its playlists and its syncs,
and its archive file (it moves along) keeps the next sync from downloading
everything again. Picked the wrong folder for a playlist: move it.
"""
from __future__ import annotations

import errno
import logging
import os
import shutil
from pathlib import Path

from . import analytics
from .config import download_root, update_config
from .library import folder_path_for_entry

log = logging.getLogger(__name__)

# Config keys holding {folder path: value}, and lists of folder paths
_PATH_KEYED = ("vault_playlists", "vault_sync_formats", "vault_sync_times", "vault_names",
               "vault_budgets", "vault_sync_schedule")
_PATH_LISTS = ("watched_folders", "vault_hidden", "recent_output_dirs")


class MoveError(Exception):
    """A move that can't be done, in words for the user."""


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def rebase(path: str, src: str, dest: str) -> str | None:
    """`path` moved along with `src` to `dest` when it is `src` or inside
    it, else None. Windows paths compare without case."""
    if not path:
        return None
    p, s = _norm(path), _norm(src)
    if p == s:
        return dest
    if p.startswith(s.rstrip(os.sep) + os.sep):
        return os.path.join(dest, os.path.normpath(path)[len(os.path.normpath(src)):].lstrip("\\/"))
    return None


def is_inside(path: str, folder: str) -> bool:
    """Whether `path` is `folder` or somewhere inside it."""
    return rebase(path, folder, folder) is not None


def move_folder(src: str, into: str) -> str:
    """Move folder `src` into folder `into` (keeping its name) and rewrite
    every reference to it. Returns the new path; raises MoveError."""
    source, parent = Path(src), Path(into)
    if not source.is_dir():
        raise MoveError("That folder no longer exists.")
    if not parent.is_dir():
        raise MoveError("The destination folder doesn't exist.")
    if is_inside(str(parent), src):
        raise MoveError("A folder can't be moved inside itself.")
    dest = parent / source.name
    if dest.exists():
        raise MoveError(f'There is already a "{source.name}" there.')
    _move_on_disk(source, dest)
    rewrite_references(str(source), str(dest))
    log.info(f"moved vault folder {source} -> {dest}")
    return str(dest)


def _move_on_disk(source: Path, dest: Path) -> None:
    """Rename on the same drive; across drives copy, then delete the
    original only once the copy is whole (a failed copy is removed and the
    original left as it was)."""
    try:
        os.rename(source, dest)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise MoveError(f"Couldn't move it ({exc.strerror or exc}). "
                            "Is a file in it open in another program?") from exc
    try:
        shutil.copytree(source, dest)
    except OSError as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise MoveError(f"Couldn't copy it to the other drive ({exc}). Nothing was moved.") from exc
    try:
        shutil.rmtree(source)
    except OSError as exc:
        # The copy is whole and everything points at it now; the leftovers
        # of the original are only a duplicate
        log.warning(f"moved {source} but could not delete all of the original: {exc}")


def rewrite_references(src: str, dest: str) -> None:
    """Point everything that names `src` (or a folder inside it) at `dest`."""
    def _config(cfg: dict) -> None:
        for key in _PATH_KEYED:
            values = cfg.get(key)
            if isinstance(values, dict):
                cfg[key] = {(rebase(k, src, dest) or k): v for k, v in values.items()}
        for key in _PATH_LISTS:
            values = cfg.get(key)
            if isinstance(values, list):
                moved = [rebase(v, src, dest) or v if isinstance(v, str) else v for v in values]
                cfg[key] = list(dict.fromkeys(moved))
        new_root = rebase(cfg.get("output_dir") or "", src, dest)
        if new_root:
            cfg["output_dir"] = new_root
        # Outside the download folder the vault only lists watched folders;
        # inside it, it lists them anyway
        root = download_root(cfg)
        watched = [w for w in cfg.get("watched_folders") or [] if _norm(w) != _norm(dest)]
        if not is_inside(dest, root):
            watched.append(dest)
        cfg["watched_folders"] = watched
    cfg = update_config(_config)

    root = download_root(cfg)
    for entry in analytics.get_library_entries():
        moved = rebase(folder_path_for_entry(entry, root), src, dest)
        if moved:
            p = Path(moved)
            analytics.upsert_library_entry({**entry, "folder": str(p.parent), "folder_name": p.name,
                                            "use_subfolder": True})
    analytics.move_paths(lambda path: rebase(path, src, dest))
