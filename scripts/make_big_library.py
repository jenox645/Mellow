"""A made-up big library, to measure MellowDLP with one (#127).

    python scripts/make_big_library.py <home>               # 20,000 files, 50,000 history rows
    python scripts/make_big_library.py <home> --files 2000 --folders 30 --history 5000 --reports 200

<home> is a folder that plays a user's home: it gets the download folder
(<home>/Downloads/MellowDLP), the config (<home>/.mellow_dlp.json) and the
database (<home>/.mellow_dlp.duckdb). Start the app on it with HOME (Linux,
macOS) or USERPROFILE (Windows) set to <home>:

    HOME=<home> python main.py --no-window

What it makes (the same every time: a fixed random seed):
- `--folders` vault folders under the download folder, holding `--files` media
  files of a few bytes with real extensions (mp4, webm, mkv, m4a, mp3, opus,
  flac); the first folder holds `--big-folder` of them, the rest share the
  others. Half the files have a .jpg sidecar (a real 16×9 picture); a few
  folders keep yt-dlp format parts (Title.f399.mp4); every 50th file has a
  copy in the next folder (DUPES). Modification times are spread over three
  years.
- Two thirds of the folders are linked to a playlist (config
  `vault_playlists`, `vault_sync_times`), half of those as library entries too.
- `--history` download history rows (through analytics' own tables): one per
  file on disk, the rest for files deleted since, failed and cancelled
  downloads, over three years.
- `--reports` sync reports over the linked folders (analytics.record_sync_report:
  at most SYNC_REPORTS_KEEP per folder are kept, as the app keeps them).
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mellow import analytics, config  # noqa: E402
from mellow.constants import SYNC_REPORTS_KEEP  # noqa: E402
from mellow.version import APP_VERSION  # noqa: E402

SEED = 127
DAY = 86400
# A real 16×9 JPEG (632 bytes): sidecars the vault can serve
SIDECAR = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hn"
    "Pk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2Nj"
    "Y2P/wAARCAAJABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQID"
    "AAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlq"
    "c3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3"
    "+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEI"
    "FEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImK"
    "kpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDm"
    "6KKK6DE//9k=")
VIDEO_EXTS = ("mp4", "mp4", "mp4", "webm", "mkv")
AUDIO_EXTS = ("m4a", "mp3", "mp3", "opus", "flac")
PLATFORMS = ("youtube", "youtube", "youtube", "youtube", "soundcloud", "bandcamp", "vimeo")
WORDS = ("Night", "Drive", "Lo-fi", "Rain", "Static", "Neon", "Summer", "Tape", "Echo", "Velvet",
         "Orbit", "Signal", "Coffee", "Harbor", "Glass", "Paper", "Midnight", "Garden", "Dust", "Pulse")
ARTISTS = ("Mellow Waves", "Kana", "The Quiet Hours", "Dj Tide", "Saint Ivo", "Lumen", "North Pier",
           "Velour", "Sora Lane", "Analog Club")


def _title(rng: random.Random) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 4)))


def _video_id(rng: random.Random) -> str:
    return "".join(rng.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") for _ in range(11))


def make(home: Path, files: int, folders: int, big_folder: int, history: int, reports: int) -> dict:
    rng = random.Random(SEED)
    now = time.time()
    root = home / "Downloads" / "MellowDLP"
    root.mkdir(parents=True, exist_ok=True)
    config.CONFIG_PATH = home / ".mellow_dlp.json"
    analytics.DB_PATH = home / ".mellow_dlp.duckdb"
    analytics.reset_connections()

    # ── Folders and files ──
    counts = [big_folder] + [0] * (folders - 1)
    for i in range(files - big_folder):
        counts[1 + i % (folders - 1)] += 1
    folder_paths: list[Path] = []
    on_disk: list[dict] = []       # what the history records for each file
    for n, count in enumerate(counts):
        audio = n % 3 != 0
        folder = root / (f"{'Mix' if audio else 'Channel'} {n:03d} - {_title(rng)}")
        folder.mkdir(exist_ok=True)
        folder_paths.append(folder)
        for k in range(count):
            vid = _video_id(rng)
            ext = rng.choice(AUDIO_EXTS if audio else VIDEO_EXTS)
            title = f"{rng.choice(ARTISTS)} - {_title(rng)} {k:04d}"
            media = folder / f"{title} [{vid}].{ext}"
            media.write_bytes(b"\0" * rng.randint(8, 64))
            mtime = now - rng.random() ** 2 * 3 * 365 * DAY
            os.utime(media, (mtime, mtime))
            if k % 2 == 0:
                (folder / f"{media.stem}.jpg").write_bytes(SIDECAR)
            on_disk.append({"path": media, "title": title, "video_id": vid, "ext": ext,
                            "audio": audio, "time": mtime})
        if n % 25 == 5:
            for k in range(3):       # a playlist item that failed halfway: the video alone
                (folder / f"Broken {k} [{_video_id(rng)}].f399.mp4").write_bytes(b"\0" * 16)

    # The same video in two folders (DUPES finds them): every 50th file, copied
    # into the next folder. Not in the history, as a copy made by hand isn't
    for item in on_disk[::50]:
        n = folder_paths.index(item["path"].parent)
        copy = folder_paths[(n + 1) % folders] / item["path"].name
        copy.write_bytes(b"\0" * 4)

    # ── Config: linked folders, sync times, a few names ──
    linked = folder_paths[: folders * 2 // 3]
    cfg = {
        "output_dir": str(root),
        "vault_playlists": {str(f): [f"https://www.youtube.com/playlist?list=PL{_video_id(rng)}"]
                            for f in linked},
        "vault_sync_times": {str(f): time.strftime("%Y-%m-%dT%H:%M:%S",
                                                   time.localtime(now - rng.randint(1, 30) * DAY))
                             for f in linked},
        "vault_names": {str(f): f"★ {f.name}" for f in folder_paths[::40]},
        "auto_sync_enabled": True,
        "last_seen_version": APP_VERSION,     # an up-to-date install: no "What's new" at start
    }
    config.CONFIG_PATH.write_text(json.dumps(cfg, indent=1), encoding="utf-8")

    # ── The database: library entries, history, sync reports ──
    analytics.init_db()
    for f in linked[::2]:
        analytics.upsert_library_entry({
            "id": f"lib-{f.name[:12]}-{_video_id(rng)}", "name": f.name, "url": cfg["vault_playlists"][str(f)][0],
            "folder": str(f.parent), "folder_name": f.name, "use_subfolder": True,
            "mode": "AUDIO" if f.name.startswith("Mix") else "VIDEO"})

    rows = []
    for item in on_disk:
        rows.append(_history_row(rng, item["title"], item["video_id"], item["ext"], item["audio"],
                                 str(item["path"]), "success", item["time"]))
    while len(rows) < history:
        audio = rng.random() < 0.6
        ext = rng.choice(AUDIO_EXTS if audio else VIDEO_EXTS)
        status = rng.choices(("success", "error", "cancelled"), (90, 7, 3))[0]
        title = f"{rng.choice(ARTISTS)} - {_title(rng)}"
        path = str(rng.choice(folder_paths) / f"{title} (deleted).{ext}") if status == "success" else None
        rows.append(_history_row(rng, title, _video_id(rng), ext, audio, path, status,
                                 now - rng.random() ** 2 * 3 * 365 * DAY))
    rows = rows[:history]
    rows.sort(key=lambda r: r["timestamp"])
    csv_path = home / ".big_library_history.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    columns = ", ".join(rows[0])
    with analytics.get_conn() as con:
        con.execute(f"INSERT INTO downloads (id, {columns}) "
                    f"SELECT nextval('downloads_seq'), {columns} FROM read_csv(?, header=true, "
                    f"columns={_csv_types(rows[0])})", [str(csv_path)])
        con.execute("CHECKPOINT")
    csv_path.unlink()

    made_reports = 0
    for k in range(reports):
        folder = linked[k % len(linked)]
        # Every 20th folder's playlist is gone: its syncs keep failing (the card says so)
        status = ("failed" if linked.index(folder) % 20 == 3
                  else rng.choices(("completed", "failed", "cancelled"), (85, 10, 5))[0])
        added = [f"{rng.choice(ARTISTS)} - {_title(rng)}" for _ in range(rng.randint(0, 6))]
        analytics.record_sync_report(str(folder), status, {
            "added": added, "failed": [], "filtered": [], "archived": rng.randint(10, 200)},
            rng.randint(3, 400), "HTTP Error 403: Forbidden" if status == "failed" else None)
        made_reports += 1
    analytics.reset_connections()
    kept = min(made_reports, len(linked) * SYNC_REPORTS_KEEP)
    return {"folders": folders, "files": len(on_disk), "copies": len(on_disk[::50]),
            "history": len(rows), "linked": len(linked),
            "library_entries": len(linked[::2]), "sync_reports_kept": kept,
            "big_folder": str(folder_paths[0])}


def _history_row(rng: random.Random, title: str, video_id: str, ext: str, audio: bool,
                 path: str | None, status: str, when: float) -> dict:
    platform = rng.choice(PLATFORMS)
    url = (f"https://www.youtube.com/watch?v={video_id}" if platform == "youtube"
           else f"https://{platform}.com/{video_id}")
    return {
        "url": url, "title": title, "uploader": title.split(" - ", 1)[0], "platform": platform,
        "duration_seconds": rng.randint(60, 3600), "file_size_bytes": rng.randint(2, 900) * 2**20,
        "format": "audio" if audio else "video", "quality": "best" if audio else rng.choice(("720p", "1080p", "4k")),
        "container": ext, "file_path": path,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)),
        "status": status, "error_message": "HTTP Error 403: Forbidden" if status == "error" else None,
        "download_speed_avg_bps": rng.randint(200, 20000) * 1024, "elapsed_seconds": rng.randint(2, 600),
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if platform == "youtube" else None,
        "video_id": video_id,
    }


def _csv_types(row: dict) -> str:
    ints = {"duration_seconds", "file_size_bytes", "download_speed_avg_bps", "elapsed_seconds"}
    types = {k: ("BIGINT" if k in ints else "TIMESTAMP" if k == "timestamp" else "VARCHAR") for k in row}
    return "{" + ", ".join(f"'{k}': '{v}'" for k, v in types.items()) + "}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("home", help="the folder that plays the user's home (made if missing)")
    parser.add_argument("--files", type=int, default=20000)
    parser.add_argument("--folders", type=int, default=300)
    parser.add_argument("--big-folder", type=int, default=2000, help="files in the first folder")
    parser.add_argument("--history", type=int, default=50000)
    parser.add_argument("--reports", type=int, default=2000)
    args = parser.parse_args()
    home = Path(args.home).resolve()
    if (home / ".mellow_dlp.duckdb").exists() or (home / "Downloads" / "MellowDLP").exists():
        print(f"{home} already holds a MellowDLP library: pick an empty folder")
        return 1
    if args.folders < 2 or args.big_folder > args.files:
        print("--folders must be at least 2, --big-folder at most --files")
        return 2
    started = time.monotonic()
    made = make(home, args.files, args.folders, args.big_folder, args.history, args.reports)
    print(json.dumps(made, indent=1))
    print(f"made in {time.monotonic() - started:.0f} s. Start the app on it: HOME={home} python main.py "
          f"(Windows: set USERPROFILE={home})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
