"""Shared constants — extension sets, numeric limits, and timing values.

Anything that reads like a tuning knob lives here, not inline at call sites.
"""
from __future__ import annotations

# ── File extensions ───────────────────────────────────────────────────────────
MEDIA_EXTS: frozenset[str] = frozenset({
    '.mp3', '.mp4', '.mkv', '.webm', '.flac', '.m4a',
    '.wav', '.opus', '.aac', '.ogg', '.avi', '.mov',
})
VIDEO_EXTS: frozenset[str] = frozenset({'.mp4', '.mkv', '.webm', '.avi', '.mov'})
AUDIO_EXTS: frozenset[str] = MEDIA_EXTS - VIDEO_EXTS
IMAGE_EXTS: frozenset[str] = frozenset({'.jpg', '.jpeg', '.png', '.webp'})

# MIME types for streaming/preview
MEDIA_MIME: dict[str, str] = {
    '.mp4': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/x-matroska',
    '.avi': 'video/x-msvideo', '.mov': 'video/quicktime',
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac',
    '.flac': 'audio/flac', '.wav': 'audio/wav', '.opus': 'audio/opus',
    '.ogg': 'audio/ogg',
}

# ── Thumbnails ────────────────────────────────────────────────────────────────
THUMB_CACHE_SECS: int = 86400        # browser cache lifetime for /api/vault/thumb
THUMB_PREVIEW_LIMIT: int = 4         # max mosaic thumbnails per folder card
FILE_THUMBS_LIMIT: int = 100         # max paths per /api/vault/file-thumbs request
THUMB_FETCH_TIMEOUT_SECS: int = 15   # sidecar download timeout
THUMB_FFMPEG_TIMEOUT_SECS: int = 20  # on-demand frame extraction timeout
THUMB_FFMPEG_SEEK_SECS: int = 30     # frame position for generated thumbnails
THUMB_FFMPEG_WIDTH: int = 480        # generated thumbnail width

# ── Job queue ─────────────────────────────────────────────────────────────────
MAX_DOWNLOAD_WORKERS: int = 3        # hard ceiling for concurrent downloads
DEFAULT_DOWNLOAD_WORKERS: int = 1    # config default (sequential, original behavior)
JOB_HISTORY_KEEP: int = 20           # finished jobs retained in /api/queue/status
SSE_QUEUE_MAXSIZE: int = 500         # per-subscriber event buffer
SSE_PING_INTERVAL_SECS: int = 25     # keepalive ping cadence

# ── Scheduler (vault auto-sync) ───────────────────────────────────────────────
SCHEDULER_TICK_SECS: int = 300       # how often the auto-sync loop wakes up
SYNC_INTERVALS: dict[str, int] = {   # interval key → seconds
    "6h": 6 * 3600,
    "daily": 24 * 3600,
    "weekly": 7 * 24 * 3600,
}

# ── History / API limits ──────────────────────────────────────────────────────
HISTORY_MAX_LIMIT: int = 500
HISTORY_DEFAULT_LIMIT: int = 50
PAUSE_POLL_SECS: float = 0.2         # progress-hook pause loop cadence

# ── Misc ──────────────────────────────────────────────────────────────────────
WEBHOOK_TIMEOUT_SECS: int = 5
PYPI_CHECK_TIMEOUT_SECS: int = 30
M3U8_TEMP_MAX_AGE_SECS: int = 86400  # playlist temp files older than this are swept
LOW_DISK_WARN_BYTES: int = 2 * 1024 ** 3  # warn when output drive has < 2 GB free
