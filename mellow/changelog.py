"""What's new: the CHANGELOG.md the app ships with.

The packaged app carries CHANGELOG.md (MellowDLP.spec), so the notes are
there offline and match the version that runs. After an update the UI shows
the sections between the version last seen (config `last_seen_version`) and
this one, once; release.yml publishes each version's section as the start of
its GitHub release notes.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .version import APP_VERSION
from .ytdlp_update import parse_version

# Next to the mellow package: the repo root, or the one-file build's unpack folder
CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

_HEADING = re.compile(r"^##\s+v?(\d+(?:\.\d+)*)\s*$")
_ITEM = re.compile(r"^-\s+(?:\*\*(.+?)\*\*:?\s*)?(.*)$")


def parse(text: str) -> list[dict]:
    """[{version, items: [{title, text}]}] in file order (newest first).

    Items are `- **Title**: text` lines (the title is optional); indented
    lines continue the item above.
    """
    entries: list[dict] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = _HEADING.match(line)
        if heading:
            entries.append({"version": heading.group(1), "items": []})
            continue
        if not entries or not line.strip():
            continue
        item = _ITEM.match(line)
        if item:
            entries[-1]["items"].append({"title": item.group(1), "text": item.group(2).strip()})
        elif raw[:1].isspace() and entries[-1]["items"]:
            entries[-1]["items"][-1]["text"] += " " + line.strip()
    return entries


def load() -> list[dict]:
    try:
        return parse(CHANGELOG_PATH.read_text(encoding="utf-8"))
    except OSError:
        return []


def section(version: str) -> str | None:
    """The raw Markdown of one version's section (the release notes)."""
    try:
        lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    out: list[str] | None = None
    for line in lines:
        heading = _HEADING.match(line.rstrip())
        if heading:
            if out is not None:
                break
            if heading.group(1) == version:
                out = []
            continue
        if out is not None:
            out.append(line)
    text = "\n".join(out or []).strip()
    return text or None


def entries_between(after: str | None, upto: str | None = None) -> list[dict]:
    """The sections newer than `after` (None: every one) up to `upto` (this version)."""
    low = parse_version(after) if after else None
    high = parse_version(upto or APP_VERSION)
    return [e for e in load()
            if parse_version(e["version"]) <= high and (low is None or parse_version(e["version"]) > low)]


def whats_new() -> dict:
    """What to show after an update: {current, show, entries}.

    A copy updated from before this existed has no `last_seen_version`: it
    gets this version's notes if it was set up before (its config file
    exists); a fresh install starts quiet.
    """
    last_seen = config.load_config().get("last_seen_version")
    if not last_seen:
        if not config.CONFIG_PATH.exists():
            mark_seen()
            return {"current": APP_VERSION, "show": False, "entries": []}
        entries = [e for e in load() if e["version"] == APP_VERSION]
    elif parse_version(last_seen) >= parse_version(APP_VERSION):
        entries = []
    else:
        entries = entries_between(last_seen)
    return {"current": APP_VERSION, "show": bool(entries), "entries": entries}


def mark_seen() -> None:
    config.update_config(lambda c: c.update(last_seen_version=APP_VERSION))
