"""How fast the vault's thumbnails show (#126): a made-up vault, the real app, a real browser.

    python scripts/thumb_bench.py                     # 2,000-file folder + 200 folders, cold then warm
    python scripts/thumb_bench.py --files 400 --folders 40 --json out.json

It makes a vault under a throwaway home (nothing of yours is read or written):
- one folder of --files media files: half with a sidecar thumbnail (a 1280x720 jpg, as a
  download leaves), a quarter videos with none (a frame has to be made: ffmpeg), a quarter
  audio files, half of them with a cover inside;
- --folders more folders of 8 files each, mixed the same way, for the vault's folder cards.

Then it starts MellowDLP (`main.py --no-window`) and Chromium at the window's size, and measures,
cold (nothing made yet) and warm (a new window, the same app: what was made is kept):
- the vault page: until every folder card on screen shows its pictures;
- the big folder (MD cards): until the first picture shows, until every card on screen has settled
  (a picture, or no picture to show), then each step of scrolling down a screen at a time;
- an API call made while the folder's pictures load (does the server keep answering?);
- the app's CPU time (with ffmpeg and the other programs it ran) and the bytes of pictures sent.

Needs ffmpeg and Playwright's Chromium (requirements-dev.txt). Linux and Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWPORT = {"width": 1100, "height": 780}      # main.py's window
SETTLE_TIMEOUT_S = 120

# Measured inside the page, frame by frame (requestAnimationFrame): Playwright's own calls can stall
# while a page lays out 2,000 cards, which a user never sees. Only the cards are measured, top to
# bottom until one is below the screen: asking where an image inside a skipped card is (the folder's
# cards are `content-visibility: auto`) would lay that card out, 2,000 layouts a frame.
# An on-screen card's pictures are settled once loaded (a picture) or failed (hidden: none to show);
# a 1-pixel image is a placeholder, not settled.
_MEASURE_JS = """async ([act, cardSel, timeoutMs]) => {
  const visible = () => {
    // The page's scrolled area: what lies below it (behind the status bar) isn't on screen
    const area = document.querySelector('.content'), box = area ? area.getBoundingClientRect() : null;
    const h = box ? box.bottom : innerHeight, w = innerWidth, imgs = [];
    for (const card of document.querySelectorAll(cardSel)) {
      const r = card.getBoundingClientRect();
      // Not laid out yet (or below the screen): stop. Asking every card where it is would lay each
      // out, and Chrome then loads the lazy pictures of all 2,000
      if (r.top >= h || r.width === 0) break;
      if (r.bottom <= (box ? box.top : 0) || r.left >= w) continue;
      imgs.push(...[...card.querySelectorAll('img')].filter(i => {
        const b = i.getBoundingClientRect();
        return b.top < h && b.bottom > (box ? box.top : 0);
      }));
    }
    const hidden = i => i.style.display === 'none';
    return {total: imgs.length,
            shown: imgs.filter(i => i.complete && i.naturalWidth > 1 && !hidden(i)).length,
            settled: imgs.filter(i => hidden(i) || (i.complete && i.naturalWidth > 1)).length};
  };
  const t0 = performance.now();
  let first = null, longest = 0, last = t0;
  new Function(act)();
  return await new Promise(resolve => {
    const tick = () => {
      const now = performance.now();
      longest = Math.max(longest, now - last); last = now;
      const s = visible();
      if (first === null && s.shown > 0) first = now - t0;
      const done = s.total > 0 && s.settled === s.total;
      if (done || now - t0 > timeoutMs) {
        resolve({first_s: first === null ? null : +(first / 1000).toFixed(3),
                 all_visible_s: +((now - t0) / 1000).toFixed(3), longest_frame_ms: Math.round(longest), ...s});
      } else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}"""
FILE_CARDS = ".lib-grid .lib-card"
FOLDER_CARDS = ".vault-folder-card"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def make_vault(root: Path, files: int, folders: int) -> dict:
    """The made-up vault; returns what it holds."""
    src = root / "_src"
    src.mkdir(parents=True)
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=1", "-frames:v", "1", "-q:v", "3", str(src / "side.jpg"))
    # 40 s: a frame is grabbed 30 s in (THUMB_FFMPEG_SEEK_SECS), as from a real video
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10", "-f", "lavfi", "-i", "sine=f=440",
            "-t", "40", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(src / "clip.mp4"))
    _ffmpeg("-f", "lavfi", "-i", "sine=f=330", "-t", "2", "-c:a", "libmp3lame", str(src / "plain.mp3"))
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=1000x1000:rate=1", "-frames:v", "1", "-q:v", "2", str(src / "cover.jpg"))
    _ffmpeg("-i", str(src / "plain.mp3"), "-i", str(src / "cover.jpg"), "-map", "0", "-map", "1", "-c", "copy",
            "-id3v2_version", "3", "-metadata:s:v", "comment=Cover (front)", str(src / "cover.mp3"))

    def put(name: str, folder: Path, target: str) -> None:
        """A hard link where the disk allows (thousands of files, no space), else a copy."""
        try:
            os.link(src / name, folder / target)
        except OSError:
            shutil.copyfile(src / name, folder / target)

    def fill(folder: Path, n: int, tag: str) -> dict:
        folder.mkdir(parents=True)
        counts = {"sidecar": 0, "frame": 0, "cover": 0, "none": 0}
        for i in range(n):
            name = f"{tag} {i:05d} [x{i:07d}]"
            kind = ("sidecar", "sidecar", "frame", "audio")[i % 4]
            if kind == "audio":
                kind = "cover" if (i // 4) % 2 == 0 else "none"
            if kind in ("sidecar", "frame"):
                put("clip.mp4", folder, f"{name}.mp4")
                if kind == "sidecar":
                    put("side.jpg", folder, f"{name}.jpg")
            else:
                put("cover.mp3" if kind == "cover" else "plain.mp3", folder, f"{name}.mp3")
            counts[kind] += 1
        return counts

    big = fill(root / "Big Folder", files, "Clip")
    for f in range(folders):
        fill(root / f"Folder {f:03d}", 8, f"F{f:03d}")
    src.rename(root.parent / "_src")             # the links' first names, outside the vault
    return {"big_folder": big, "folders": folders + 1}


class App:
    """main.py --no-window under a throwaway home; signed in through its one-time link."""

    def __init__(self, home: Path, out_dir: Path):
        cfg = {"output_dir": str(out_dir), "update_check_on_launch": False, "last_seen_version": "9.9.9",
               "tour_seen": True, "clipboard_watch": False}
        (home / ".mellow_dlp.json").write_text(json.dumps(cfg))
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "LOCALAPPDATA": str(home / "AppData")}
        env.pop("XDG_CACHE_HOME", None)
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "--no-window"], cwd=str(ROOT), env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 60
        self.link = None
        while time.time() < deadline and self.link is None:
            line = self.proc.stdout.readline()
            if not line and self.proc.poll() is not None:
                break
            m = re.search(r"(http://127\.0\.0\.1:\d+/launch\?\S+)", line)
            if m:
                self.link = m.group(1)
        if not self.link:
            raise SystemExit("the app didn't print its sign-in link")
        self.env = env
        # Keep reading its output so it never blocks on a full pipe
        import threading
        threading.Thread(target=lambda: [None for _ in self.proc.stdout], daemon=True).start()

    def new_link(self) -> str:
        """A fresh one-time sign-in link (each new window needs its own), from the instance file."""
        sys.path.insert(0, str(ROOT))
        from mellow import datadir, session
        inst = session.read_instance(datadir.data_dir(self.env) / session.INSTANCE_FILE_NAME)
        base = self.link.split("/launch", 1)[0]
        return f"{base}/launch?t={session.launch_token(inst['secret'], inst['port'])}"

    def cpu_s(self) -> float:
        """CPU seconds of the app and the programs it ran and waited for (ffmpeg)."""
        if sys.platform.startswith("linux"):
            fields = Path(f"/proc/{self.proc.pid}/stat").read_text().rsplit(")", 1)[1].split()
            return sum(int(v) for v in fields[11:15]) / os.sysconf("SC_CLK_TCK")
        try:
            import psutil
            p = psutil.Process(self.proc.pid)
            t = p.cpu_times()
            return t.user + t.system + getattr(t, "children_user", 0) + getattr(t, "children_system", 0)
        except Exception:
            return float("nan")

    def read_bytes(self) -> int:
        try:
            if sys.platform.startswith("linux"):
                io = Path(f"/proc/{self.proc.pid}/io").read_text()
                return int(re.search(r"read_bytes: (\d+)", io).group(1))
            import psutil
            return psutil.Process(self.proc.pid).io_counters().read_bytes
        except Exception:
            return -1

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _measure(page, act: str, sel: str) -> dict:
    """Run `act` (JavaScript) in the page and time its thumbnails from there."""
    return page.evaluate(_MEASURE_JS, [act, sel, SETTLE_TIMEOUT_S * 1000])


def run(browser, app: App, label: str) -> dict:
    out: dict = {"run": label}
    context = browser.new_context(viewport=VIEWPORT)
    page = context.new_page()
    thumb_bytes = [0]
    thumb_count = [0]

    def on_thumb(req):
        """Bytes that came from the app (a picture the window kept counts nothing)."""
        if "/api/vault/thumb" in req.url:
            thumb_count[0] += 1
            try:
                thumb_bytes[0] += max(0, req.sizes()["responseBodySize"])
            except Exception:
                pass
    page.on("requestfinished", on_thumb)
    api_times: dict = {}

    def on_finished(req):
        for key in ("/api/vault/file-thumbs", "/api/vault/folder?"):
            if key in req.url:
                t = req.timing
                api_times[key.strip("/?")] = {"waited_ms": round(t["requestStart"]), "total_ms": round(t["responseEnd"])}
    page.on("requestfinished", on_finished)
    page.goto(app.link if label == "cold" else app.new_link())
    page.locator(".nav-item").first.wait_for()
    page.wait_for_timeout(500)
    cpu0, io0 = app.cpu_s(), app.read_bytes()

    # The vault page: the folder cards
    out["vault_page"] = _measure(page, """[...document.querySelectorAll('.nav-item')]
        .find(n => /vault/i.test(n.textContent)).click()""", FOLDER_CARDS)

    # The big folder, MD cards
    # ...and, 300 ms in, an API call while its pictures are being made: does the server still answer?
    out["big_folder"] = _measure(page, """[...document.querySelectorAll('.vault-folder-card')]
        .find(c => c.textContent.includes('Big Folder')).click();
      window.__apiMs = null;
      setTimeout(async () => {
        const token = sessionStorage.getItem('mellow-token'), t = performance.now();
        await fetch('/api/queue/status', {headers: token ? {'X-Mellow-Token': token} : {}});
        window.__apiMs = Math.round(performance.now() - t);
      }, 300);""", FILE_CARDS)
    page.wait_for_function("window.__apiMs !== null")
    out["api_while_loading_ms"] = page.evaluate("window.__apiMs")
    steps = []
    for _ in range(8):
        r = _measure(page, "const c = document.querySelector('.content'); c.scrollBy(0, c.clientHeight)", FILE_CARDS)
        steps.append(r["all_visible_s"])
    out["scroll_steps_s"] = steps

    # Back to the vault and into the folder again, twice, in the same window. The first time, a
    # picture first sent full-size comes as its small copy; then what the window kept isn't sent again
    for reopen in ("reopen", "reopen_again"):
        page.wait_for_timeout(1500)
        sent_before = thumb_bytes[0]
        _measure(page, "document.querySelector('.vbc-root').click()", FOLDER_CARDS)
        page.locator(".vault-folder-card", has_text="Big Folder").first.wait_for()
        out[reopen] = _measure(page, """[...document.querySelectorAll('.vault-folder-card')]
            .find(c => c.textContent.includes('Big Folder')).click()""", FILE_CARDS)
        out[reopen]["thumb_mb_sent"] = round((thumb_bytes[0] - sent_before) / 1e6, 2)
    out["cpu_s"] = round(app.cpu_s() - cpu0, 2)
    read = app.read_bytes()
    out["disk_read_mb"] = round((read - io0) / 1e6, 1) if read >= 0 and io0 >= 0 else None
    out["api_timing"] = api_times
    out["thumb_requests"] = thumb_count[0]
    out["thumb_mb_sent"] = round(thumb_bytes[0] / 1e6, 2)
    context.close()
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--files", type=int, default=2000)
    ap.add_argument("--folders", type=int, default=200)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--keep", action="store_true", help="keep the made-up vault and home")
    args = ap.parse_args(argv)
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is needed to make the vault")
    from playwright.sync_api import sync_playwright

    work = Path(tempfile.mkdtemp(prefix="mellow-thumb-bench-"))
    home, vault = work / "home", work / "vault"
    home.mkdir()
    t = time.perf_counter()
    made = make_vault(vault, args.files, args.folders)
    print(f"vault made in {time.perf_counter() - t:.1f}s: {made}", flush=True)
    app = App(home, vault)
    results = {"vault": made, "platform": sys.platform, "runs": []}
    try:
        with sync_playwright() as pw:
            exe = os.environ.get("MELLOW_CHROMIUM")
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
            for label in ("cold", "warm"):
                r = run(browser, app, label)
                print(json.dumps(r), flush=True)
                results["runs"].append(r)
            browser.close()
    finally:
        app.stop()
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"kept: {work}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
