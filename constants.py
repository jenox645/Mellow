"""Shared constants — extension sets and numeric limits used across modules."""
from __future__ import annotations

MEDIA_EXTS: frozenset[str] = frozenset({
    '.mp3', '.mp4', '.mkv', '.webm', '.flac', '.m4a',
    '.wav', '.opus', '.aac', '.ogg', '.avi', '.mov',
})
VIDEO_EXTS: frozenset[str] = frozenset({'.mp4', '.mkv', '.webm', '.avi', '.mov'})
AUDIO_EXTS: frozenset[str] = MEDIA_EXTS - VIDEO_EXTS
IMAGE_EXTS: frozenset[str] = frozenset({'.jpg', '.jpeg', '.png', '.webp'})

THUMB_CACHE_SECS: int = 86400   # 1 day
THUMB_PREVIEW_LIMIT: int = 4    # max mosaic thumbnails per folder card
FILE_THUMBS_LIMIT: int = 100    # max paths per /api/vault/file-thumbs request
