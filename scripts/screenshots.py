"""Screenshots of MellowDLP for the README, from made-up demo data.

    python build_setup.py --frontend-only
    python scripts/screenshots.py              # → assets/screenshots/

Runs the real app in this process with a throw-away home folder: a vault of
demo folders (generated cover art, files of realistic sizes that take no
disk space), two months of download history, linked playlists and a sync
report. A playlist download is played out with the app's own progress
events, through to Mellow's celebration. Titles, channels and art are all
invented; nothing is downloaded. Needs Pillow, ffmpeg (the GIF) and
Playwright's Chromium.
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "screenshots"
VIEWPORT = {"width": 1440, "height": 900}
GIF_CLIP = {"x": 300, "y": 250, "width": 840, "height": 400}   # the celebration, around Mellow
GIF_SECS = 4.2          # the overlay shows for 5 s, then fades
CELEBRATION_STILL_SECS = 1.6
THUMB_SIZE = (480, 270)
CHROMIUM = Path("/opt/pw-browsers/chromium")   # the sandbox's; elsewhere Playwright's own
IMG_HOST = "https://img.mellow.demo/"          # cover art the fake site "serves"

# The app reads ~/.mellow_dlp* at import: point home at the demo first
# A fixed, plain path: it shows in SAVE TO and the status bar
HOME = Path(tempfile.gettempdir()) / "mellow-demo" / "you"
shutil.rmtree(HOME.parent, ignore_errors=True)
HOME.mkdir(parents=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(HOME)
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

rng = random.Random(7)

# ── Cover art ────────────────────────────────────────────────────────────────

PALETTES = {
    "lofi": [((255, 170, 120), (90, 60, 140)), ((250, 200, 150), (70, 90, 160)), ((255, 140, 160), (60, 50, 110)),
             ((240, 210, 170), (110, 80, 130)), ((180, 210, 255), (60, 70, 130))],
    "synth": [((255, 60, 170), (30, 10, 70)), ((255, 120, 40), (60, 0, 90)), ((0, 220, 255), (40, 0, 80))],
    "anime": [((120, 220, 255), (255, 120, 200)), ((255, 220, 120), (255, 90, 120)), ((140, 255, 200), (60, 120, 255)),
              ((255, 170, 220), (120, 90, 255))],
    "code": [((10, 30, 60), (0, 180, 220)), ((20, 20, 40), (90, 60, 200)), ((5, 40, 40), (0, 200, 140))],
    "talk": [((250, 230, 200), (230, 120, 90)), ((210, 240, 230), (60, 140, 140))],
}
MASCOTS = ["chilling", "comfy", "dj", "vibing", "success", "victory"]


def _gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    return img


def _mascot(img, name, scale=0.82, color=(255, 255, 255)):
    art = Image.open(ROOT / "assets" / f"{name}_mellow_vector.png").convert("RGBA")
    h = int(img.height * scale)
    art = art.resize((int(art.width * h / art.height), h), Image.LANCZOS)
    alpha = art.split()[-1]
    tint = Image.new("RGBA", art.size, color + (255,))
    tint.putalpha(alpha)
    glow = tint.filter(ImageFilter.GaussianBlur(6))
    pos = ((img.width - art.width) // 2, img.height - art.height - int(img.height * 0.04))
    img.paste(glow, pos, glow)
    img.paste(tint, pos, tint)


def cover(style, n):
    top, bottom = PALETTES[style][n % len(PALETTES[style])]
    img = _gradient(THUMB_SIZE, top, bottom)
    d = ImageDraw.Draw(img, "RGBA")
    w, h = THUMB_SIZE
    if style == "synth":   # a striped sun over a perspective grid
        r = 70
        cx, cy = w // 2, int(h * 0.55)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 210, 80, 255))
        for i in range(6):
            y = cy + 8 + i * 11
            d.rectangle((cx - r, y, cx + r, y + 3 + i), fill=top + (255,))
        d.rectangle((0, cy + r - 20, w, h), fill=(20, 0, 50, 255))
        for i in range(-12, 13):
            d.line((cx + i * 14, cy + r - 20, cx + i * 70, h), fill=(255, 60, 200, 180), width=1)
        for j in range(8):
            y = cy + r - 20 + int((j / 8) ** 2 * (h - cy - r + 20))
            d.line((0, y, w, y), fill=(255, 60, 200, 160), width=1)
    elif style == "anime":   # bokeh and a mascot
        for _ in range(26):
            r = rng.randint(6, 34)
            x, y = rng.randint(0, w), rng.randint(0, h)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(25, 70)))
        _mascot(img, MASCOTS[n % len(MASCOTS)], 0.9)
    elif style == "code":   # waves of light
        for k in range(5):
            pts = [(x, h * (0.35 + 0.1 * k) + 18 * math.sin(x / 38 + k)) for x in range(0, w + 8, 8)]
            d.line(pts, fill=(255, 255, 255, 70 + 30 * k), width=2)
    else:   # lofi and talk: the mascot, glowing
        for _ in range(40):
            x, y = rng.randint(0, w), rng.randint(0, int(h * 0.45))
            d.point((x, y), fill=(255, 255, 255, 200))
        _mascot(img, MASCOTS[n % len(MASCOTS)], 0.86 if style == "lofi" else 0.78)
    return img.filter(ImageFilter.SMOOTH)


# ── Demo vault, history, config ──────────────────────────────────────────────

FOLDERS = {
    "Lofi Study Beats": ("lofi", "mp3", "Lofi Sheep", [
        "rainy window — lofi beats to study", "late night ramen", "sleepy sheep lullaby", "coffee shop at 3am",
        "cloud nine", "pages & pencils", "snow on the balcony", "tea for two", "vinyl crackle", "moonlit stroll",
        "warm blanket", "bookstore cat", "after the rain", "slow mornings"]),
    "Synthwave Drive": ("synth", "mp3", "Retro Wave FM", [
        "Neon Highway", "Chrome Sunset", "Night Drive 1987", "Laser Grid", "Arcade Hearts", "Palm Coast",
        "Midnight Run", "Outrun the Dawn", "Starlight Motel"]),
    "Anime Openings": ("anime", "mp4", "Studio Kumo", [
        "Starfall Academy — Opening", "Clockwork Hearts — Opening 2", "Moonlit Bakery — Ending",
        "Ronin of the Rain — Opening", "Galaxy Postman — Opening", "Petal Storm — Ending",
        "Mecha Garden — Opening", "Kitsune Café — Opening"]),
    "Deep Focus": ("code", "mp4", "Deep Focus", [
        "4 hours of focus — deep work music", "Synthwave for programming", "Rain & keyboard sounds (3h)",
        "Chill coding session", "Late night debugging mix"]),
    "Jazz Café": ("talk", "mp3", "Blue Note Kitten", [
        "Espresso Swing", "Rainy Window Bossa", "Midnight Croissant", "Saxophone Sunday", "Velvet Steps",
        "Cinnamon Waltz"]),
    "Game Soundtracks": ("synth", "mp3", "Pixel Orchestra", [
        "Title Screen", "Overworld Theme", "Boss Battle", "Save Point", "Credits Roll", "Secret Level",
        "Victory Fanfare"]),
    "Road Trip": ("anime", "mp3", "Open Road", [
        "Windows Down", "Gas Station Snacks", "Coastline", "Sunset Exit", "Desert Radio"]),
    "Podcasts": ("talk", "m4a", "Night Owl Radio", [
        "Ep. 41 — Why we hoard playlists", "Ep. 42 — The sound of rain", "Ep. 43 — Vinyl is back",
        "Ep. 44 — Building a music library", "Ep. 45 — Tapes, CDs, files"]),
}
SIZES = {"mp3": (3.5e6, 9e6), "m4a": (25e6, 70e6), "mp4": (40e6, 900e6)}
DOWNLOADS = HOME / "Downloads" / "MellowDLP"


def build_vault():
    """The demo folders: sparse media files (no disk space) with cover art."""
    for name, (style, ext, _, titles) in FOLDERS.items():
        folder = DOWNLOADS / name
        folder.mkdir(parents=True)
        for i, title in enumerate(titles):
            media = folder / f"{title}.{ext}"
            with open(media, "wb") as f:
                f.truncate(int(rng.uniform(*SIZES[ext])))
            cover(style, i).save(folder / f"{title}.jpg", quality=88)
            age = timedelta(days=rng.uniform(1, 60))
            stamp = (datetime.now() - age).timestamp()
            os.utime(media, (stamp, stamp))


def build_history():
    """Two months of downloads, busiest in the evening."""
    from mellow import analytics
    analytics.init_db()
    platforms = ["YouTube"] * 14 + ["SoundCloud"] * 3 + ["Bandcamp", "Vimeo", "TikTok"]
    names = [(t, FOLDERS[f][2], FOLDERS[f][1]) for f in FOLDERS for t in FOLDERS[f][3]]
    rows = []
    for _ in range(214):
        title, uploader, ext = rng.choice(names)
        audio = ext in ("mp3", "m4a")
        when = datetime.now() - timedelta(days=rng.triangular(0, 60, 2),
                                          hours=rng.choice([0, 1, 2, 3, 4, 10, 11, 12]))
        status = rng.choices(["success", "error", "cancelled"], [92, 5, 3])[0]
        rows.append([f"https://www.youtube.com/watch?v=demo{len(rows):05d}", title, uploader,
                     rng.choice(platforms), rng.randint(150, 4000) if not audio else rng.randint(140, 320),
                     int(rng.uniform(*SIZES[ext])), "audio" if audio else "video",
                     "best" if audio else rng.choice(["1080p", "1080p", "720p", "4k"]), ext,
                     status, int(rng.uniform(2e6, 18e6)), rng.randint(3, 90), when])
    with analytics.get_conn() as con:
        con.executemany("""
            INSERT INTO downloads (id, url, title, uploader, platform, duration_seconds, file_size_bytes,
                format, quality, container, status, download_speed_avg_bps, elapsed_seconds, timestamp)
            VALUES (nextval('downloads_seq'),?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    lofi = str(DOWNLOADS / "Lofi Study Beats")
    # Library entries and their sync runs (Analytics: last sync, sync history)
    for i, (name, slug) in enumerate((("Lofi Study Beats", "Lofi"), ("Synthwave Drive", "Synth"))):
        analytics.upsert_library_entry({
            "id": f"demo-{slug.lower()}", "name": name, "url": f"https://www.youtube.com/playlist?list=PLdemo{slug}",
            "folder": str(DOWNLOADS), "folder_name": name, "mode": "AUDIO", "audio_format": "mp3"})
        for run in range(6):
            synced = datetime.now() - timedelta(days=run * 3 + i, hours=2)
            with analytics.get_conn() as con:
                con.execute("INSERT INTO sync_log (id, library_id, new_items, skipped, errors, duration_seconds, "
                            "synced_at) VALUES (nextval('sync_log_seq'),?,?,?,?,?,?)",
                            [f"demo-{slug.lower()}", rng.randint(0, 4), rng.randint(8, 14), rng.choice([0, 0, 1]),
                             rng.randint(20, 90), synced])
    analytics.record_sync_report(lofi, "complete", {
        "added": ["after the rain", "slow mornings", "bookstore cat"],
        "failed": [{"title": "summer haze", "message": "Private video", "url": None,
                    "hint": "The uploader made it private."}],
        "filtered": [], "archived": 11}, 34)


def build_config():
    from mellow import config
    from mellow.version import APP_VERSION
    now = time.time()
    linked = {
        str(DOWNLOADS / "Lofi Study Beats"): ["https://www.youtube.com/playlist?list=PLdemoLofi"],
        str(DOWNLOADS / "Synthwave Drive"): ["https://www.youtube.com/playlist?list=PLdemoSynth"],
        str(DOWNLOADS / "Anime Openings"): ["https://www.youtube.com/playlist?list=PLdemoAnime"],
    }

    def apply(c):
        c.update(output_dir=str(DOWNLOADS), last_seen_version=APP_VERSION, update_check_on_launch=False,
                 clipboard_watch=False, completion_sound=False, desktop_notifications=False,
                 auto_sync_enabled=False, keep_awake=False, vault_playlists=linked,
                 vault_sync_times={p: time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 7200))
                                   for p in linked},
                 recent_output_dirs=[str(DOWNLOADS / "Lofi Study Beats"), str(DOWNLOADS / "Podcasts")])
    config.update_config(apply)


# ── The fake site the Feed "analyzes" ────────────────────────────────────────

PLAYLIST = ("Rainy Day Lofi", [
    "rain on a tin roof", "puddle jumping", "umbrella for two", "grey skies, warm tea", "the last bus home",
    "foggy window doodles", "thunder far away", "wet pavement glow"])


def site_info(url):
    if "list=" in url:
        name, titles = PLAYLIST
        return {"title": name, "is_playlist": True, "playlist_count": len(titles), "platform": "YouTube",
                "uploader": "Lofi Sheep", "thumbnail": f"{IMG_HOST}rain0.jpg",
                "items": [{"idx": i + 1, "id": f"rain{i}", "title": t, "url": f"https://youtu.be/rain{i}",
                           "thumbnail": f"{IMG_HOST}rain{i}.jpg", "duration": 150 + 17 * i,
                           "uploader": "Lofi Sheep"} for i, t in enumerate(titles)]}
    return {"title": "rainy window — lofi beats to study (2 hour mix)", "id": "demo", "is_playlist": False,
            "platform": "YouTube", "uploader": "Lofi Sheep", "duration": 7262, "webpage_url": url,
            "thumbnail": f"{IMG_HOST}single.jpg",
            "size_estimates": {"video": {"best": 1.41e9, "4k": 1.41e9, "1080p": 612e6, "720p": 318e6,
                                         "480p": 171e6, "360p": 112e6}, "audio": 118e6},
            "chapters": [{"index": i + 1, "title": t, "start": i * 900, "end": (i + 1) * 900}
                         for i, t in enumerate(["drizzle", "downpour", "thunder", "clearing skies"])]}


def covers_for_site(folder: Path):
    folder.mkdir(exist_ok=True)
    cover("lofi", 0).save(folder / "single.jpg", quality=90)
    for i in range(len(PLAYLIST[1])):
        cover("lofi", i + 2).save(folder / f"rain{i}.jpg", quality=90)


# ── A playlist download, played out with the app's own events ────────────────

def play_download(push, upto, job="demo-rain"):
    """Progress events for the fake playlist download, item by item, up to
    item `upto` (0-based) which is left half done."""
    name, titles = PLAYLIST
    base = {"job_id": job, "job_type": "feed", "job_label": name}
    push({**base, "status": "starting"})
    for i, title in enumerate(titles[:upto + 1]):
        for pct in (12, 37, 63, 88) if i < upto else (12, 37, 63):
            push({**base, "status": "downloading", "pct": pct, "speed": rng.uniform(6e6, 14e6),
                  "eta": int((100 - pct) / 9), "current_item_title": title,
                  "current_item_thumb": f"{IMG_HOST}rain{i}.jpg", "playlist_index": i + 1})
            time.sleep(0.05)
        if i < upto:
            push({**base, "status": "item_done", "title": title, "video_id": f"rain{i}",
                  "playlist_index": i + 1, "thumbnail": f"{IMG_HOST}rain{i}.jpg"})


def finish_download(push, start, job="demo-rain"):
    name, titles = PLAYLIST
    base = {"job_id": job, "job_type": "feed", "job_label": name}
    for i in range(start, len(titles)):
        push({**base, "status": "item_done", "title": titles[i], "video_id": f"rain{i}",
              "playlist_index": i + 1, "thumbnail": f"{IMG_HOST}rain{i}.jpg"})
    push({**base, "status": "complete", "title": name})


# ── Capture ──────────────────────────────────────────────────────────────────

def serve(app):
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 0, app, threaded=True)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", server.shutdown


def shoot(page, name):
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"  {name}.png")


def make_gif(frames: Path, fps: float, out: Path):
    vf = "split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-framerate", f"{fps:.2f}",
                    "-i", str(frames / "g%03d.png"), "-vf", vf, "-loop", "0", str(out)], check=True)
    print(f"  {out.name} ({fps:.1f} fps)")


SOCIAL_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{fonts}/fonts.css"><style>
  html, body {{ margin: 0; width: 1280px; height: 640px; overflow: hidden; background: #070b10; }}
  .bg {{ position: absolute; inset: 0; background: url({banner}) center 30% / cover; filter: brightness(.5) saturate(1.1); }}
  .fade {{ position: absolute; inset: 0; background: linear-gradient(90deg, #070b10 0%, rgba(7,11,16,.85) 38%, rgba(7,11,16,.1) 70%); }}
  .text {{ position: absolute; left: 72px; top: 150px; width: 560px; color: #e6f4ff; }}
  h1 {{ font: 800 76px Oxanium, sans-serif; margin: 0; letter-spacing: .02em; color: #00d8ff;
        text-shadow: 0 0 28px rgba(0,216,255,.45); }}
  p {{ font: 400 27px 'Exo 2', sans-serif; line-height: 1.4; margin: 18px 0 0; color: #cfe3f2; }}
  .tags {{ font: 400 17px 'Share Tech Mono', monospace; color: #7fb3cc; margin-top: 34px; letter-spacing: .08em; }}
  .shot {{ position: absolute; right: -60px; top: 120px; width: 700px; border: 1px solid rgba(0,216,255,.5);
           box-shadow: 0 20px 60px rgba(0,0,0,.7), 0 0 30px rgba(0,216,255,.18); transform: perspective(1400px) rotateY(-14deg); }}
</style></head><body>
  <div class="bg"></div><div class="fade"></div>
  <img class="shot" src="{shot}">
  <div class="text"><h1>MellowDLP</h1>
    <p>A desktop app for yt-dlp: paste a link, pick a format, download. Playlists synced into a library.</p>
    <div class="tags">WINDOWS · LINUX · OPEN SOURCE</div></div>
</body></html>"""


def social_preview(browser):
    """The picture link previews show (GitHub → Settings → Social preview)."""
    html = OUT / "_social.html"
    html.write_text(SOCIAL_HTML.format(fonts=(ROOT / "gui" / "fonts").as_uri(),
                                       banner=(ROOT / "assets" / "banner.png").as_uri(),
                                       shot=(OUT / "download.png").as_uri()), encoding="utf-8")
    page = browser.new_page(viewport={"width": 1280, "height": 640})
    page.goto(html.as_uri())
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "social-preview.png"))
    page.close()
    html.unlink()
    print("  social-preview.png")


def main():
    from playwright.sync_api import sync_playwright

    from mellow import jobs, server, session

    build_vault()
    build_history()
    build_config()
    site = HOME / "site"
    covers_for_site(site)
    url, stop = serve(server.init_app())
    session.start_instance(int(url.rsplit(":", 1)[1]), publish=False)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"demo home {HOME}, app {url}")

    # Two downloads waiting for the night (⏾ LATER), for the Queue page
    tonight = jobs.next_time_of_day("02:00")
    for title in ("Synthwave Drive — new uploads", "Galaxy Postman — Opening (4K)"):
        jobs.manager.enqueue(f"https://www.youtube.com/watch?v={title[:6]}", str(DOWNLOADS), {},
                             label=title, not_before=tonight)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(CHROMIUM) if CHROMIUM.exists() else None)
        page = browser.new_page(viewport=VIEWPORT)
        page.route(IMG_HOST + "**", lambda r: r.fulfill(path=str(site / r.request.url.rsplit("/", 1)[1])))
        page.route("**/api/info", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(site_info(r.request.post_data_json["url"]))))
        page.route("**/api/download", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"status": "queued", "job_id": "demo-rain"})))
        page.goto(f"{url}/launch?t={session.launch_token()}")   # signed in, as the app's window is
        page.locator(".nav-item").first.wait_for()
        page.wait_for_timeout(1500)
        box = page.get_by_placeholder("Paste a link")

        # Feed: a video analyzed, with its options
        box.fill("https://www.youtube.com/watch?v=demo")
        page.get_by_text("ANALYZE →").click()
        page.locator(".info-title").wait_for()
        shoot(page, "feed")
        page.locator("[data-tour=feed-options-btn]").click()
        page.wait_for_timeout(500)
        shoot(page, "feed-options")
        page.locator("[data-tour=feed-options-btn]").click()

        # A playlist downloading
        box.fill("https://www.youtube.com/playlist?list=PLdemoRain")
        page.get_by_text("ANALYZE →").click()
        page.locator(".pl-queue-item").first.wait_for()
        page.locator(".info-actions .btn-primary").click()
        page.get_by_text("JUST DOWNLOAD").click()
        play_download(server._push_progress, upto=4)
        page.wait_for_timeout(1200)
        shoot(page, "download")

        page.locator(".nav-item", has_text="QUEUE").click()
        page.wait_for_timeout(800)
        shoot(page, "queue")

        # The end: Mellow celebrates (a GIF of it, and one frame)
        page.locator(".nav-item", has_text="FEED").click()
        frames = Path(tempfile.mkdtemp())
        finish_download(server._push_progress, start=4)
        page.locator(".victory-overlay").wait_for()
        start, stamps, still = time.monotonic(), [], False
        while time.monotonic() - start < GIF_SECS:   # as fast as screenshots go
            stamps.append(time.monotonic() - start)
            if not still and stamps[-1] >= CELEBRATION_STILL_SECS:
                shoot(page, "celebration")
                still = True
                continue
            page.screenshot(path=str(frames / f"f{len(stamps) - 1:03d}.png"), clip=GIF_CLIP)
        for i, f in enumerate(sorted(frames.glob("f*.png"))):   # numbered without gaps
            f.rename(frames / f"g{i:03d}.png")
        make_gif(frames, len(list(frames.glob("g*.png"))) / GIF_SECS, OUT / "celebration.gif")
        page.locator(".victory-overlay").wait_for(state="detached", timeout=10_000)

        # Vault: the folders, one folder, the GUIDE
        page.locator(".nav-item", has_text="VAULT").click()
        page.locator(".vault-folder-card").first.wait_for()
        page.locator(".pill", has_text="LG").click()      # big covers fill the page
        page.wait_for_timeout(1500)
        shoot(page, "vault")
        page.locator(".pill", has_text="MD").click()
        page.locator(".vault-folder-card", has_text="Lofi Study Beats").click()
        page.locator(".lib-card").first.wait_for()
        page.wait_for_timeout(1500)
        shoot(page, "vault-folder")
        page.keyboard.press("g")
        for _ in range(20):
            if "RE-TAG" in page.locator(".tour-title").inner_text():
                break
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(700)
        page.wait_for_timeout(900)
        shoot(page, "guide")
        page.keyboard.press("Escape")

        page.locator(".nav-item", has_text="ANALYTICS").click()
        page.locator(".range-tab", has_text="ALL TIME").click()
        page.wait_for_timeout(1800)
        page.evaluate("document.querySelectorAll('*').forEach(e => { if (e.scrollTop) e.scrollTop = 0; })")
        shoot(page, "analytics")
        social_preview(browser)
        browser.close()
    stop()
    shutil.rmtree(HOME.parent, ignore_errors=True)


if __name__ == "__main__":
    main()
