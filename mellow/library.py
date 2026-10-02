"""Library entry business logic — creation and sync opts."""
from __future__ import annotations

from pathlib import Path

from . import formats
from .config import download_root, download_settings
from .constants import AUDIO_FORMATS


def build_entry(data: dict, entry_id: str, now: str) -> dict:
    """Build a library entry dict from request data."""
    mode = (data.get("mode") or "VIDEO").upper()
    container = (data.get("container") or "mp4").lower()
    audio_format = (data.get("audio_format") or "").lower()
    if not audio_format:
        # Older clients stuffed the audio format into "container" for AUDIO
        # entries. Only an actual audio format counts: the default "mp4"
        # container used to become the entry's audio format.
        legacy = mode == "AUDIO" and container in AUDIO_FORMATS
        audio_format = container if legacy else "mp3"
        if legacy:
            container = "mp4"
    return {
        "id": entry_id,
        "name": data.get("name", ""),
        "url": data.get("url", ""),
        "folder": data.get("folder", ""),
        "folder_name": data.get("folder_name", ""),
        "use_subfolder": data.get("use_subfolder", True),
        "quality": data.get("quality", "1080p"),
        "mode": mode,
        "container": container,
        "audio_format": audio_format,
        **formats.toggles(data),
        "filename_template": data.get("filename_template", ""),
        "sync_mode": data.get("sync_mode", "add"),
        "last_synced": None,
        "created_at": now,
    }


def folder_path_for_entry(entry: dict, default_root: str = "") -> str:
    """The folder a library entry downloads into, which is also its vault folder.

    An entry without a folder of its own lives in the download folder
    (`default_root`). The sync, the vault listing and the playlist links
    each worked this out themselves and disagreed: the vault never listed
    such an entry, and with the Config download folder cleared its sync
    went to a relative path under the app's working directory.
    """
    folder = entry.get("folder") or default_root
    if folder and entry.get("folder_name") and entry.get("use_subfolder", True):
        return str(Path(folder) / entry["folder_name"])
    return folder


def build_sync_opts(entry: dict, cfg: dict, sync_mode: str) -> tuple[dict, str]:
    """Return (yt-dlp opts dict, output_dir) for a library entry sync."""
    output_dir = folder_path_for_entry(entry, download_root(cfg))
    is_audio = (entry.get("mode") or "").upper() == "AUDIO"
    opts = {
        "mode": "library",
        "quality": entry.get("quality", "1080p"),
        "container": (entry.get("container") or "mp4").lower(),
        "sync_audio": is_audio,
        "audio_format": (entry.get("audio_format") or "mp3").lower(),
        **formats.toggles(entry),
        "audio_quality": cfg.get("default_audio_quality", "best"),
        # Same naming as every other download unless the entry sets its own
        "filename_template": entry.get("filename_template") or cfg.get("filename_template", ""),
        "sync_mode": sync_mode,
        **download_settings(cfg),
    }
    return opts, output_dir
