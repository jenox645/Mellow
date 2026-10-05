"""Downloading files the app installs (its own updates, ffmpeg).

Each download streams to disk with progress and comes back with its SHA-256,
to be compared with the checksum list its publisher puts next to it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .constants import DOWNLOAD_CHUNK_BYTES, DOWNLOAD_READ_TIMEOUT_SECS
from .version import APP_VERSION

HEADERS = {"User-Agent": f"MellowDLP/{APP_VERSION}"}


class DownloadError(Exception):
    """A download that can't be used; the message is shown to the user."""


def text(url: str, timeout: float) -> str:
    with urlopen(Request(url, headers=HEADERS), timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def checksum_for(sums: str, name: str) -> str | None:
    """The SHA-256 a `sha256sum`-style list gives for `name`."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def download(url: str, dest: Path, size: int, on_pct: Callable[[int], None]) -> str:
    """Stream `url` to `dest`; returns its sha256. Reports whole percents.

    `size` (0 when unknown) is checked: a connection that drops early must
    not leave a short file that only the checksum would catch.
    """
    sha = hashlib.sha256()
    done, last_pct = 0, -1
    with urlopen(Request(url, headers=HEADERS), timeout=DOWNLOAD_READ_TIMEOUT_SECS) as resp, \
            open(dest, "wb") as out:
        total = size or int(resp.headers.get("Content-Length") or 0)
        while chunk := resp.read(DOWNLOAD_CHUNK_BYTES):
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            pct = min(100, done * 100 // total) if total else 0
            if pct != last_pct:
                last_pct = pct
                on_pct(pct)
    if total and done != total:
        raise DownloadError(f"The download stopped early ({done:,} of {total:,} bytes)")
    return sha.hexdigest()
