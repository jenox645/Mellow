"""Install ffmpeg the way GET FFMPEG does, for real, and use it.

    python scripts/ffmpeg_e2e.py

Downloads the current BtbN build for this system into a temporary folder
(checked against its published checksums), then makes an MP3 with the
installed ffmpeg and reads it back with the installed ffprobe. Run by
release.yml on Windows and Linux for pull requests that touch the installer.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mellow import ffmpeg_install, ffmpeg_locate  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        ffmpeg_locate.MANAGED_DIR = Path(tmp) / ".mellow_dlp_ffmpeg"
        started, last = time.monotonic(), {}

        def push(event: dict) -> None:
            if event["stage"] != "downloading" or event["pct"] % 20 == 0:
                print(f"  {time.monotonic() - started:6.1f}s {json.dumps(event)}", flush=True)
            last.update(event)

        ffmpeg_install.install(push)
        if last.get("stage") != "done":
            print(f"FAILED: {last}")
            return 1
        exe = ".exe" if sys.platform == "win32" else ""
        installed = sorted(p.name for p in ffmpeg_locate.MANAGED_DIR.iterdir())
        print("  installed:", installed)
        if installed != sorted([f"ffmpeg{exe}", f"ffprobe{exe}"]):
            print("FAILED: expected exactly ffmpeg and ffprobe")
            return 1
        ffmpeg = ffmpeg_locate.MANAGED_DIR / f"ffmpeg{exe}"
        ffprobe = ffmpeg_locate.MANAGED_DIR / f"ffprobe{exe}"
        mp3 = Path(tmp) / "tone.mp3"
        subprocess.run([str(ffmpeg), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2",
                        "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True, timeout=60)
        codec = subprocess.run([str(ffprobe), "-v", "error", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", str(mp3)], capture_output=True, text=True,
                               check=True, timeout=60).stdout.strip()
        print("  made", mp3.name, "->", codec)
        if codec != "mp3":
            print("FAILED: the installed ffmpeg didn't make an mp3")
            return 1
    print("ffmpeg install test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
