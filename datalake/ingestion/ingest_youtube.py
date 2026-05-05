"""
Ingestion job — Source 2: YouTube Data API v3
Reads YouTube URLs from today's raw MellowDLP JSON, fetches video statistics
and snippet metadata, saves to data/raw/youtube/video_stats/YYYY-MM-DD/video_stats.json
"""

import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
DATALAKE_ROOT = Path(os.getenv("DATALAKE_ROOT", "./data"))

_YT_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"
)


def _extract_video_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def _fetch_video_stats(youtube, video_ids: list[str]) -> list[dict]:
    results = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = (
            youtube.videos()
            .list(
                part="statistics,snippet,contentDetails",
                id=",".join(batch),
            )
            .execute()
        )
        for item in resp.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            results.append(
                {
                    "video_id": item["id"],
                    "title": snippet.get("title"),
                    "channel_title": snippet.get("channelTitle"),
                    "channel_id": snippet.get("channelId"),
                    "published_at": snippet.get("publishedAt"),
                    "category_id": snippet.get("categoryId"),
                    "tags": snippet.get("tags", []),
                    "description_length": len(snippet.get("description", "")),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration_iso": content.get("duration"),
                }
            )
    return results


def ingest(target_date: date | None = None) -> Path:
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is not set in .env")

    target_date = target_date or date.today()
    raw_mellow = (
        DATALAKE_ROOT / "raw" / "mellowdlp" / "downloads" / target_date.isoformat() / "downloads.json"
    )
    if not raw_mellow.exists():
        raise FileNotFoundError(f"Run ingest_mellowdlp.py first: {raw_mellow}")

    records = json.loads(raw_mellow.read_text(encoding="utf-8"))
    yt_records = [r for r in records if (r.get("platform") or "").lower() == "youtube"]

    video_ids = []
    url_to_id: dict[str, str] = {}
    for r in yt_records:
        vid = _extract_video_id(r.get("url", ""))
        if vid and vid not in url_to_id.values():
            video_ids.append(vid)
            url_to_id[r["url"]] = vid

    out_dir = DATALAKE_ROOT / "raw" / "youtube" / "video_stats" / target_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "video_stats.json"

    if not video_ids:
        out_file.write_text(json.dumps([], indent=2), encoding="utf-8")
        print("[youtube] 0 YouTube URLs found — wrote empty file")
        return out_file

    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    stats = _fetch_video_stats(youtube, video_ids)

    out_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"[youtube] {len(stats)} videos fetched → {out_file}")
    return out_file


if __name__ == "__main__":
    ingest()
