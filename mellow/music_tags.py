"""Music tags: a synced playlist plays as one album, in playlist order.

YouTube gives most videos no album and no track number, and the channel
name as the artist ("Rick Astley - Topic", "RickAstleyVEVO"). In a music
player the songs of a synced folder then scatter over "Unknown album",
sorted by title. For audio downloads (the `music_tags` option) a missing
album becomes the playlist's name, a missing track number its position, the
album artist "Various Artists", and a channel used as the artist loses its
" - Topic" / "VEVO" suffix. A real album (YouTube Music tracks) is kept with
its own numbers.

tags_for() decides them from yt-dlp's info at download time (MusicTagsPP
hands them to FFmpegMetadata); retag_folder() writes them into files already
on disk, in the linked playlist's current order, with mutagen.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from yt_dlp.postprocessor.common import PostProcessor

log = logging.getLogger(__name__)

VARIOUS_ARTISTS = "Various Artists"
# Files mutagen can tag: ID3 (mp3), MP4 (m4a/aac), Vorbis comments (flac, opus, ogg)
TAGGABLE_EXTS = frozenset({".mp3", ".m4a", ".aac", ".mp4a", ".flac", ".opus", ".ogg"})

_TOPIC_RE = re.compile(r"\s+-\s+Topic$", re.IGNORECASE)
_VEVO_RE = re.compile(r"\s*VEVO$")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def clean_artist(name: str | None) -> str | None:
    """A channel name as an artist: "Rick Astley - Topic" → "Rick Astley",
    "RickAstleyVEVO" → "Rick Astley". Anything else is returned as it is."""
    if not name:
        return name
    cleaned = _TOPIC_RE.sub("", name.strip())
    vevo = _VEVO_RE.sub("", cleaned)
    if vevo != cleaned and vevo:
        # VEVO channels glue the words together: split "RickAstley"
        cleaned = vevo if " " in vevo else _CAMEL_RE.sub(" ", vevo)
    return cleaned or name


def tags_for(info: dict) -> dict[str, str]:
    """The tags to add for one downloaded item (only those it lacks)."""
    tags: dict[str, str] = {}
    playlist = info.get("playlist_title") or info.get("playlist")
    index = info.get("playlist_index")
    if not info.get("album") and playlist and index:
        tags["album"] = str(playlist)
        tags["track"] = str(index)
        if not info.get("album_artist") and not info.get("album_artists"):
            tags["album_artist"] = VARIOUS_ARTISTS
    if not any(info.get(k) for k in ("artist", "artists", "creator", "creators")):
        channel = info.get("uploader") or info.get("channel")
        cleaned = clean_artist(channel)
        if cleaned and cleaned != channel:
            tags["artist"] = cleaned
    return tags


class MusicTagsPP(PostProcessor):
    """Puts tags_for() into the info as meta_* fields, which FFmpegMetadata
    writes over its own choices. Runs before the download (pre_process)."""

    def run(self, info):
        for key, value in tags_for(info).items():
            info.setdefault(f"meta_{key}", value)
        return [], info


# ── Re-tag files already on disk ─────────────────────────────────────────────

def _open(path: Path):
    """The file's tags through mutagen's common "easy" names, or None."""
    import mutagen
    try:
        audio = mutagen.File(str(path), easy=True)
    except Exception as exc:
        log.warning(f"retag: can't read {path.name}: {exc}")
        return None
    if audio is None:
        return None
    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception:
            return None
    return audio


def _first(audio, key: str) -> str:
    try:
        values = audio.get(key) or []
    except Exception:
        return ""
    return str(values[0]) if values else ""


def retag_file(path: Path, album: str | None, track: int | None) -> bool:
    """Tag one file like a download would be: album and track from the
    playlist unless it has a real album of its own, the artist cleaned.
    True when something changed."""
    audio = _open(path)
    if audio is None:
        return False
    changes: dict[str, str] = {}
    current_album = _first(audio, "album")
    # An album that isn't the playlist's is a real one (YouTube Music): keep it
    if album and (not current_album or current_album == album):
        changes["album"] = album
        if track:
            changes["tracknumber"] = str(track)
        if not _first(audio, "albumartist"):
            changes["albumartist"] = VARIOUS_ARTISTS
    artist = _first(audio, "artist")
    cleaned = clean_artist(artist)
    if artist and cleaned != artist:
        changes["artist"] = cleaned
    changes = {k: v for k, v in changes.items() if _first(audio, k) != v}
    if not changes:
        return False
    for key, value in changes.items():
        audio[key] = value
    audio.save()
    return True


def retag_folder(folder: Path, album: str | None, order: dict[str, int]) -> dict:
    """Re-tag every audio file in `folder`.

    `order` maps file names to their position in the linked playlist; a file
    it doesn't name (gone from the playlist, or no playlist) keeps its track
    number. Returns {"tagged", "unchanged", "skipped", "failed"} counts.
    """
    from .vault import is_media
    result = {"tagged": 0, "unchanged": 0, "skipped": 0, "failed": 0}
    for f in sorted(folder.iterdir()):
        if not f.is_file() or not is_media(f):
            continue
        if f.suffix.lower() not in TAGGABLE_EXTS:
            result["skipped"] += 1      # video, or a format without tags (wav)
            continue
        try:
            changed = retag_file(f, album, order.get(f.name))
        except Exception as exc:
            log.warning(f"retag: {f.name} failed: {exc}")
            result["failed"] += 1
            continue
        result["tagged" if changed else "unchanged"] += 1
    log.info(f"retag {folder}: {result}")
    return result
