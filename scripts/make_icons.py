"""Make the desktop app's small mascot badge: the tray icon and the title bar's mark.

    python scripts/make_icons.py

Writes `src-tauri/icons/tray.png` (the tray; the shell draws download progress along
its bottom edge) and `assets/mellow-badge.png` (the title bar's mark; the build copies it
into static/), both 32 × 32, from Mellow's own art:

- `assets/tray-source.png`, when it exists, used as it is (a ready-made square badge:
  drop the official one there, e.g. a sheep-face badge, and run this again);
- else the head of the mascot in `assets/mellow.ico` (its largest frame: horns, hair,
  face), cropped and with its lines thickened once, which keeps the face readable at
  the tray's 16 px.

Not a new drawing: the app's own icon art, made small.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "tray-source.png"
ICO = ROOT / "assets" / "mellow.ico"
OUTPUTS = (ROOT / "src-tauri" / "icons" / "tray.png", ROOT / "assets" / "mellow-badge.png")
SIZE = 32
HEAD = (0.12, 0.0, 0.88, 0.62)   # the icon's head: left, top, right, bottom (fractions)


def from_icon() -> Image.Image:
    ico = Image.open(ICO)
    ico.size = max(ico.info.get("sizes", [ico.size]), key=lambda s: s[0])
    art = ico.convert("RGBA")
    w, h = art.size
    head = art.crop((int(HEAD[0] * w), int(HEAD[1] * h), int(HEAD[2] * w), int(HEAD[3] * h)))
    big = head.resize((SIZE * 4, SIZE * 4), Image.LANCZOS)
    lines = big.convert("L").filter(ImageFilter.MinFilter(3))     # thicker dark lines
    big = Image.merge("RGBA", (lines, lines, lines, big.getchannel("A")))
    return big.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    badge = Image.open(SOURCE).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS) if SOURCE.exists() else from_icon()
    for out in OUTPUTS:
        badge.save(out)
        print(f"{out.relative_to(ROOT)} ({SIZE}x{SIZE}, from {(SOURCE if SOURCE.exists() else ICO).name})")


if __name__ == "__main__":
    main()
