"""The cover art inside an audio file, read with mutagen (no ffmpeg needed).

FLAC's PICTURE blocks, the base64 METADATA_BLOCK_PICTURE comment of Ogg
Vorbis / Opus (and the older COVERART one), ID3's APIC frames (MP3, AIFF,
WAV), MP4's `covr` atom (M4A, M4B, AAC in MP4) and ASF's WM/Picture (WMA).
The vault shows it as the file's thumbnail; ffmpeg is only the fallback for
what mutagen can't read (Matroska audio, a damaged tag).
"""
from __future__ import annotations

import base64
import binascii
import logging
import struct
from pathlib import Path

log = logging.getLogger(__name__)

FRONT_COVER = 3     # the picture type every format borrows from ID3: "Cover (front)"


class NoCoverError(Exception):
    """mutagen read the file's tags and there is no picture in them."""


def sniff_mime(data: bytes) -> str | None:
    """What a picture really is (a tag's own MIME is often missing or wrong),
    among the formats a page can show; None for anything else."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def embedded_cover(path: str | Path) -> tuple[bytes, str] | None:
    """(picture bytes, MIME) of the file's front cover, else its first picture.

    None when mutagen can't read the file (not a format it knows, a broken
    tag): ffmpeg may still find one. Raises NoCoverError when the tags were read
    and hold no picture: nothing else will find one either.
    """
    try:
        import mutagen
        audio = mutagen.File(str(path))
    except Exception as exc:     # mutagen raises its own errors for a damaged file
        log.debug(f"no tags read from {path}: {exc}")
        return None
    if audio is None:
        return None
    found = [(kind, data) for kind, data in _pictures(audio) if data and sniff_mime(data)]
    if not found:
        raise NoCoverError(str(path))
    found.sort(key=lambda p: p[0] != FRONT_COVER)    # front cover first, else the order they're in
    data = found[0][1]
    return data, sniff_mime(data) or "image/jpeg"


def _pictures(audio) -> list[tuple[int, bytes]]:
    """(picture type, bytes) of every picture in the file, whatever its tag format."""
    pics: list[tuple[int, bytes]] = []
    # FLAC's own PICTURE metadata blocks
    for pic in getattr(audio, "pictures", None) or []:
        pics.append((pic.type, pic.data))
    tags = audio.tags
    if tags is None:
        return pics
    # ID3 (MP3, AIFF, WAV): APIC frames; mutagen loads ID3v2.2's PIC as APIC
    if callable(getattr(tags, "getall", None)):
        for frame in tags.getall("APIC"):
            pics.append((frame.type, frame.data))
        return pics
    keys = {k.lower(): k for k in tags.keys()} if hasattr(tags, "keys") else {}
    # MP4: covr (a list of MP4Cover, which are bytes)
    if "covr" in keys:
        for cover in tags[keys["covr"]]:
            pics.append((FRONT_COVER, bytes(cover)))
    # Vorbis comments (Ogg Vorbis, Opus, Speex, FLAC in Ogg): base64 FLAC picture blocks
    if "metadata_block_picture" in keys:
        from mutagen.flac import Picture
        for value in tags[keys["metadata_block_picture"]]:
            try:
                pic = Picture(base64.b64decode(value))
                pics.append((pic.type, pic.data))
            except Exception as exc:       # bad base64, or mutagen's own error for a bad block
                log.debug(f"unreadable METADATA_BLOCK_PICTURE: {exc}")
    if "coverart" in keys:           # the older, unofficial way: the image itself, base64
        for value in tags[keys["coverart"]]:
            try:
                pics.append((FRONT_COVER, base64.b64decode(value)))
            except (binascii.Error, ValueError, TypeError):
                pass
    # ASF (WMA): WM/Picture
    if "wm/picture" in keys:
        for value in tags[keys["wm/picture"]]:
            pic = _asf_picture(getattr(value, "value", value))
            if pic:
                pics.append(pic)
    return pics


def _asf_picture(raw) -> tuple[int, bytes] | None:
    """WM/Picture's layout: picture type (1 byte), data size (uint32 LE), MIME
    and description (each UTF-16LE, NUL-terminated), then the data."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 9:
        return None
    raw = bytes(raw)
    kind = raw[0]
    (size,) = struct.unpack_from("<I", raw, 1)
    pos = 5
    for _ in range(2):          # skip MIME, then description
        while pos + 1 < len(raw) and raw[pos:pos + 2] != b"\0\0":
            pos += 2
        pos += 2
    data = raw[pos:pos + size]
    return (kind, data) if len(data) == size and size else None
