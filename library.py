"""Library entry business logic — creation and sync opts."""
from __future__ import annotations

from pathlib import Path

from config import download_settings


def build_entry(data: dict, entry_id: str, now: str) -> dict:
    """Build a library entry dict from request data."""
    mode = (data.get("mode") or "VIDEO").upper()
    container = (data.get("container") or "mp4").lower()
    # Older clients stuffed the audio format into "container" for AUDIO entries
    audio_format = (data.get("audio_format") or (container if mode == "AUDIO" else "mp3")).lower()
    if mode == "AUDIO" and container == audio_format:
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
        "embed_thumbnail": data.get("embed_thumbnail", True),
        "embed_chapters": data.get("embed_chapters", True),
        "embed_metadata": data.get("embed_metadata", True),
        "embed_subs": data.get("embed_subs", False),
        "sub_langs": data.get("sub_langs", "en"),
        "sponsorblock": data.get("sponsorblock", False),
        "filename_template": data.get("filename_template", ""),
        "sync_mode": data.get("sync_mode", "add"),
        "last_synced": None,
        "created_at": now,
    }


def folder_path_for_entry(entry: dict) -> str:
    """Resolve the output folder path for a library entry."""
    if entry.get("use_subfolder") and entry.get("folder") and entry.get("folder_name"):
        return str(Path(entry["folder"]) / entry["folder_name"])
    return entry.get("folder", "")


def build_sync_opts(entry: dict, cfg: dict, sync_mode: str) -> tuple[dict, str]:
    """Return (yt-dlp opts dict, output_dir) for a library entry sync."""
    base_folder = entry.get("folder") or cfg.get("output_dir", str(Path.home() / "Downloads"))
    if entry.get("use_subfolder") and entry.get("folder_name"):
        output_dir = str(Path(base_folder) / entry["folder_name"])
    else:
        output_dir = base_folder
    is_audio = (entry.get("mode") or "").upper() == "AUDIO"
    opts = {
        "mode": "library",
        "quality": entry.get("quality", "1080p"),
        "container": (entry.get("container") or "mp4").lower(),
        "sync_audio": is_audio,
        "audio_format": (entry.get("audio_format") or "mp3").lower(),
        "embed_thumbnail": entry.get("embed_thumbnail", True),
        "embed_chapters": entry.get("embed_chapters", True),
        "embed_metadata": entry.get("embed_metadata", True),
        "embed_subs": entry.get("embed_subs", False),
        "sub_langs": entry.get("sub_langs", "en"),
        "sponsorblock": entry.get("sponsorblock", False),
        "audio_quality": cfg.get("default_audio_quality", "best"),
        # Same naming as every other download unless the entry sets its own
        "filename_template": entry.get("filename_template") or cfg.get("filename_template", ""),
        "sync_mode": sync_mode,
        **download_settings(cfg),
    }
    return opts, output_dir
