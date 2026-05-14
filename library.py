"""Library entry business logic — creation and sync opts."""
from __future__ import annotations

from pathlib import Path


def build_entry(data: dict, entry_id: str, now: str) -> dict:
    """Build a library entry dict from request data."""
    return {
        "id": entry_id,
        "name": data.get("name", ""),
        "url": data.get("url", ""),
        "folder": data.get("folder", ""),
        "folder_name": data.get("folder_name", ""),
        "use_subfolder": data.get("use_subfolder", True),
        "quality": data.get("quality", "1080p"),
        "mode": data.get("mode", "VIDEO"),
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
    opts = {
        "mode": "library",
        "quality": entry.get("quality", "1080p"),
        "embed_thumbnail": entry.get("embed_thumbnail", True),
        "embed_chapters": entry.get("embed_chapters", True),
        "embed_metadata": entry.get("embed_metadata", True),
        "embed_subs": entry.get("embed_subs", False),
        "sub_langs": entry.get("sub_langs", "en"),
        "sponsorblock": entry.get("sponsorblock", False),
        "filename_template": entry.get("filename_template", ""),
        "sync_mode": sync_mode,
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
        "retries": cfg.get("retries", 3),
    }
    return opts, output_dir
