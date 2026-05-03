"""
build_linux_deb.py — Build a .deb package from the compiled MellowDLP binary.

Run AFTER build_setup.py has produced dist/MellowDLP:
    python3 build_linux_deb.py
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

APP_NAME = "mellowdlp"
VERSION  = "2.0.0"
ARCH     = "amd64"

DEB_ROOT  = HERE / "dist" / "deb" / f"{APP_NAME}_{VERSION}_{ARCH}"
BINARY    = HERE / "dist" / "MellowDLP"
ICON_PNG  = HERE / "assets" / "mellow_256.png"


def fail(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str]) -> None:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        fail(f"Command failed: {cmd[0]}")


# ── Preflight ─────────────────────────────────────────────────────────────────
if not BINARY.exists():
    fail(f"dist/MellowDLP not found — run build_setup.py first")

if not shutil.which("dpkg-deb"):
    fail("dpkg-deb not found — install with: sudo apt install dpkg")

# ── Directory layout ──────────────────────────────────────────────────────────
dirs = [
    DEB_ROOT / "DEBIAN",
    DEB_ROOT / "usr" / "bin",
    DEB_ROOT / "usr" / "share" / "applications",
    DEB_ROOT / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps",
    DEB_ROOT / "usr" / "share" / APP_NAME,
]
for d in dirs:
    d.mkdir(parents=True, exist_ok=True)

# ── DEBIAN/control ────────────────────────────────────────────────────────────
control = f"""Package: {APP_NAME}
Version: {VERSION}
Architecture: {ARCH}
Maintainer: Jenis <jenisvarnadesu@gmail.com>
Description: MellowDLP — Data Lake Commander
 Download and manage media with a cyberpunk interface.
 Supports YouTube, SoundCloud, and hundreds of other platforms via yt-dlp.
Depends: ffmpeg
Recommends: python3
"""
(DEB_ROOT / "DEBIAN" / "control").write_text(control)

# ── Binary ────────────────────────────────────────────────────────────────────
dest_bin = DEB_ROOT / "usr" / "bin" / APP_NAME
shutil.copy2(BINARY, dest_bin)
dest_bin.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

# ── .desktop file ─────────────────────────────────────────────────────────────
desktop = (
    "[Desktop Entry]\n"
    "Name=MellowDLP\n"
    "Comment=Data Lake Commander\n"
    f"Exec={APP_NAME}\n"
    "Icon=mellowdlp\n"
    "Terminal=false\n"
    "Type=Application\n"
    "Categories=AudioVideo;Network;\n"
)
(DEB_ROOT / "usr" / "share" / "applications" / f"{APP_NAME}.desktop").write_text(desktop)

# ── Icon ──────────────────────────────────────────────────────────────────────
if ICON_PNG.exists():
    shutil.copy2(ICON_PNG, DEB_ROOT / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "mellowdlp.png")
else:
    print(f"  WARNING: {ICON_PNG} not found — icon will be missing from package")

# ── Build .deb ────────────────────────────────────────────────────────────────
run(["dpkg-deb", "--build", "--root-owner-group", str(DEB_ROOT)])

deb_path = HERE / "dist" / "deb" / f"{APP_NAME}_{VERSION}_{ARCH}.deb"
if deb_path.exists():
    print(f"\n  Built: {deb_path}  ({deb_path.stat().st_size:,} bytes)")
    print(f"  Install with: sudo dpkg -i {deb_path.name}")
else:
    fail(f"dpkg-deb ran but .deb not found at {deb_path}")
