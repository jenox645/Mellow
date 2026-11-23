"""Make the desktop app's icons from Mellow's sheep-face badge.

    python scripts/make_icons.py                    # every icon file, from the two masters
    python scripts/make_icons.py --cut <art.svg>    # first cut the masters again from her art

The badge is the round sheep face on the sleeve of the owner's line art of Mellow asleep
(`assets/sleeping_mellow_vector.svg`): her own lines cut out along the badge, levelled, with
the sleeve's ink around it as a rim, so it reads on a dark and on a light taskbar. Not a new
drawing. Two masters, 512 x 512, transparent outside the badge:

- `assets/mellow-badge-source.png`: the badge as drawn, for 32 px and up;
- `assets/mellow-badge-small-source.png`: the same cut with its eyes, mouth and rim thickened,
  so they survive at 16-24 px (the tray, small icons). Optional: without it the first is used.

To swap the badge, replace the masters with any square PNG with a transparent background
(256 px or more) and run this again. It writes:

- `src-tauri/icons/tray.png` (32 px, small master): the tray; the shell draws download progress
  over its bottom rows;
- `assets/mellow-badge.png` (18 px, small) and `assets/mellow-badge@2x.png` (36 px): the title
  bar's mark (the build copies both into static/);
- `src-tauri/icons/icon.ico`: the exe's icon, so also the window's, the taskbar's and the
  shortcuts': the badge from 16 to 64 px, Mellow's app icon art (`assets/mellow.ico`) at 128 px
  for Explorer's large views;
- `src-tauri/icons/32x32.png`, `64x64.png`: the badge for Linux (the window, menus and docks).

`--cut` renders the art with Playwright's Chromium (requirements-dev.txt, then
`python -m playwright install chromium`).
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = ROOT / "src-tauri" / "icons"
MASTER = ASSETS / "mellow-badge-source.png"
SMALL_MASTER = ASSETS / "mellow-badge-small-source.png"
APP_ICON = ASSETS / "mellow.ico"
MASTER_PX = 512
SMALL_UP_TO = 24             # sizes up to this use the small master

# The cut, in the art's viewBox units (sleeping_mellow_vector.svg: viewBox 71.7 168.3 451.9 586.9)
REGION = (383.0, 338.5, 48.0, 48.0)    # x, y, width, height around the badge on her sleeve
SEED = (391.4, 362.25)                 # a point on the badge's white wool
LEVEL_DEG = 10.0                       # the sleeve tilts it ~10 degrees clockwise
RIM = 1.6                              # the sleeve's ink kept around the badge
SMALL_RIM = 2.6
SMALL_GROW = 0.47                      # how much the small master's eyes and mouth grow
RENDER_PX = 2048


def _render(svg_file: Path) -> Image.Image:
    from playwright.sync_api import sync_playwright
    svg = svg_file.read_text(encoding="utf-8")
    x, y, w, h = REGION
    svg = re.sub(r'viewBox="[^"]+"', f'viewBox="{x} {y} {w} {h}" width="{RENDER_PX}" height="{RENDER_PX}"',
                 svg, count=1)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": RENDER_PX, "height": RENDER_PX})
        page.set_content(f"<html><body style='margin:0;background:#fff;color:#000'>{svg}</body></html>")
        shot = Path(tmp) / "region.png"
        page.screenshot(path=str(shot), clip={"x": 0, "y": 0, "width": RENDER_PX, "height": RENDER_PX})
        browser.close()
        return Image.open(shot).convert("L")              # ink 0 .. paper 255


def _grow(mask: Image.Image, px: float) -> Image.Image:
    """`mask` widened by about `px` (a blur, then a low threshold: round, unlike a max filter)."""
    return mask.filter(ImageFilter.GaussianBlur(px)).point(lambda v: 255 if v > 40 else 0)


def cut(svg_file: Path) -> None:
    art = _render(svg_file)
    scale = RENDER_PX / REGION[2]
    paper = art.point(lambda v: 255 if v > 127 else 0)
    seed = (round((SEED[0] - REGION[0]) * scale), round((SEED[1] - REGION[1]) * scale))
    if paper.getpixel(seed) != 255:
        sys.exit(f"The seed {SEED} isn't on the badge's wool: has the art changed? Adjust REGION/SEED.")
    marked = paper.copy()
    ImageDraw.floodfill(marked, seed, 128)
    wool = marked.point(lambda v: 255 if v == 128 else 0)
    box = wool.getbbox()
    if not box or box[0] == 0 or box[1] == 0 or box[2] == RENDER_PX or box[3] == RENDER_PX:
        sys.exit("The wool runs off the cut: has the art changed? Adjust REGION/SEED.")
    outside = wool.copy()
    ImageDraw.floodfill(outside, (0, 0), 64)
    badge = outside.point(lambda v: 0 if v == 64 else 255)          # the wool and the face inside it
    face = ImageChops.subtract(badge, wool)
    features = ImageChops.multiply(paper, face)                      # the face's eyes and mouth

    def master(rim: float, grow: float) -> Image.Image:
        ink = Image.composite(art, Image.new("L", art.size, 0), badge)   # outside the badge: the sleeve's ink
        if grow:
            ink = ImageChops.lighter(ink, ImageChops.multiply(_grow(features, grow * scale), face))
        alpha = badge.filter(ImageFilter.GaussianBlur(rim * scale / 2)).point(lambda v: 255 if v > 8 else 0)
        return Image.merge("RGBA", (ink, ink, ink, alpha)).rotate(LEVEL_DEG, resample=Image.BICUBIC, expand=True)

    big, small = master(RIM, 0), master(SMALL_RIM, SMALL_GROW)
    frame = small.getchannel("A").getbbox()                          # one frame for both: same place, same size
    for im, out in ((big, MASTER), (small, SMALL_MASTER)):
        im = im.crop(frame)
        side = max(im.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.alpha_composite(im, ((side - im.width) // 2, (side - im.height) // 2))
        square.resize((MASTER_PX, MASTER_PX), Image.LANCZOS).save(out)
        print(f"{out.relative_to(ROOT)} ({MASTER_PX}x{MASTER_PX}, cut from {svg_file.name})")


def _app_icon(size: int) -> Image.Image:
    ico = Image.open(APP_ICON)
    ico.size = (size, size)
    return ico.convert("RGBA")


def make() -> None:
    big = Image.open(MASTER).convert("RGBA")
    small = Image.open(SMALL_MASTER).convert("RGBA") if SMALL_MASTER.exists() else big

    def badge(size: int) -> Image.Image:
        return (small if size <= SMALL_UP_TO else big).resize((size, size), Image.LANCZOS)

    outputs = {ICONS / "tray.png": small.resize((32, 32), Image.LANCZOS),   # always shown at 16-32 px
               ASSETS / "mellow-badge.png": badge(18),
               ASSETS / "mellow-badge@2x.png": badge(36),
               ICONS / "32x32.png": badge(32),
               ICONS / "64x64.png": badge(64)}
    for out, im in outputs.items():
        im.save(out)
        print(f"{out.relative_to(ROOT)} ({im.width}x{im.height})")
    sizes = (16, 20, 24, 32, 40, 48, 64)
    large = _app_icon(128)
    large.save(ICONS / "icon.ico", sizes=[(s, s) for s in (*sizes, 128)], append_images=[badge(s) for s in sizes])
    print(f"{(ICONS / 'icon.ico').relative_to(ROOT)} (the badge at {', '.join(map(str, sizes))} px; "
          f"{APP_ICON.name}'s art at 128 px)")


def main(argv: list[str]) -> None:
    if argv[:1] == ["--cut"]:
        if len(argv) != 2:
            sys.exit(__doc__)
        cut(Path(argv[1]))
    elif argv:
        sys.exit(__doc__)
    make()


if __name__ == "__main__":
    main(sys.argv[1:])
