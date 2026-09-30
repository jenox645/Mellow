"""yt-dlp canary — do the app's extraction paths still work on the newest yt-dlp?

Run by .github/workflows/canary.yml against the yt-dlp pre-release, and
runnable locally:  python scripts/canary.py

A probe can fail for two very different reasons:
  * yt-dlp (or our wrapper) broke          -> that is what the canary is for
  * the site refused this machine          -> bot checks and login walls, which
    CI runners on datacenter IPs hit all the time; says nothing about the app
Only the first kind fails the run. The second is reported as a warning so a
blocked runner doesn't page anyone every Monday.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mellow import downloader  # noqa: E402

# Long-lived public videos. Every target must be fetchable anonymously —
# Vimeo was dropped because it now requires a login for any extraction.
VIDEO_URLS = [
    "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # "Me at the zoo"
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://archive.org/details/BigBuckBunny_124",  # non-YouTube control
]
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLBCF2DAC6FFB574DE"

# The site turned this machine away; not an extraction bug.
ACCESS_DENIED_RE = re.compile(
    r"sign in to confirm|not a bot|logged.in|log in|login required|use --cookies"
    r"|http error 429|too many requests|rate.limit|http error 403",
    re.IGNORECASE,
)


def _probe_video(url: str) -> str:
    info = downloader.get_video_info(url)
    if not info.get("title"):
        raise RuntimeError("no title in info dict")
    return repr(info["title"])


def _probe_playlist(url: str) -> str:
    items = downloader.get_playlist_items(url)
    if not items:
        raise RuntimeError("0 items returned")
    return f"{len(items)} items"


def main() -> int:
    probes = [(url, _probe_video) for url in VIDEO_URLS] + [(PLAYLIST_URL, _probe_playlist)]
    broken: list[tuple[str, str]] = []
    blocked: list[tuple[str, str]] = []
    for url, probe in probes:
        try:
            print(f"OK       {url} -> {probe(url)}")
        except Exception as exc:
            err = " ".join(str(exc).split())
            if ACCESS_DENIED_RE.search(err):
                blocked.append((url, err))
                print(f"BLOCKED  {url}: {err}")
            else:
                broken.append((url, err))
                print(f"BROKEN   {url}: {err}")

    for url, err in blocked:
        # GitHub Actions annotation; harmless noise when run locally
        print(f"::warning title=Canary probe blocked::{url} refused this runner ({err[:200]})")
    if blocked and len(blocked) == len(probes):
        print("::warning title=Canary inconclusive::Every probe was blocked, so this run "
              "proves nothing either way. Run `python scripts/canary.py` from a home connection.")
    if broken:
        print("\nCANARY FAILURES (the newest yt-dlp may have broken extraction):")
        for url, err in broken:
            print(f"  {url}: {err}")
            print(f"::error title=Canary probe failed::{url}: {err[:200]}")
        return 1
    print(f"\n{len(probes) - len(blocked)}/{len(probes)} probes passed, {len(blocked)} blocked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
