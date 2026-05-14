# MellowDLP

A personal desktop GUI for [yt-dlp](https://github.com/yt-dlp/yt-dlp). Download audio and video from YouTube, SoundCloud, and most sites yt-dlp supports — with a queue, a local library browser, and download history.

> **Personal project.** Not designed to be a general-purpose tool or maintained for others. Use it if it fits your needs.

---

## What it does

- **Feed** — paste a URL, pick format and quality, download. Supports single videos, full playlists, and audio-only.
- **Queue** — download jobs run one at a time with live SSE progress (speed, ETA, per-item thumbnails).
- **Vault** — browse your local media library by folder. Thumbnail previews, file stats, folder size.
- **Library sync** — link a local folder to a playlist URL and sync new uploads on demand.
- **Archive file** — each vault folder can have a `mellow_archive.txt` that tracks every URL downloaded into it. Created when you first add a folder to the vault (prompted), or any time via right-click → **Generate Archive File** on an existing folder card. Updates automatically on download, sync, and delete. Import it in the Feed section on any device to reproduce the same library.
- **Analytics** — download history stored in DuckDB; basic stats on what you've downloaded over time.

Formats: MP4, MKV, WebM, MP3, FLAC, M4A, OGG, Opus. Quality: best, 1080p, 720p, 480p, 360p, 128k, 320k.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, Flask, yt-dlp, DuckDB |
| Frontend | React (UMD, no npm), esbuild for bundling |
| Desktop window | FlaskWebGUI (Tkinter-based — not Electron) |
| Analytics | DuckDB (local file at `~/.mellow_dlp.duckdb`) |
| Config | JSON at `~/.mellow_dlp.json` |

---

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (required for audio extraction and postprocessing)
- Node.js + esbuild (build step only)
- yt-dlp binary (downloaded automatically by the build scripts)
- **Linux only:** `python3-tk` for the GUI window (`sudo apt install python3-tk`)

---

## Installation

### Windows

Download the `.exe` installer from Releases and run it. ffmpeg is bundled.

### Linux

```bash
git clone https://github.com/your-username/MellowDLP
cd MellowDLP
bash setup.sh
./dist/MellowDLP
```

`setup.sh` installs Python deps, downloads yt-dlp, and runs the build. A `.deb` package can also be built:

```bash
python3 build_linux_deb.py
sudo dpkg -i dist/mellowdlp_*.deb
```

> **Note:** The Linux build runs and produces a binary in CI (GitHub Actions, Ubuntu). Locally it depends on your distro having a working Tkinter/webview setup. If the window doesn't open, make sure `python3-tk` is installed and try running `python3 main.py` directly (Flask dev mode, then open `http://localhost:<port>` in your browser as a fallback).

---

## Build from source

```bash
# Install Python deps
pip install -r requirements.txt pyinstaller pillow

# Install esbuild (once)
npm install -g esbuild

# Full build (bundles JSX, encodes assets, produces binary)
python3 build_setup.py

# Or just rebuild the frontend after editing gui/app.jsx or gui/index.html:
esbuild gui/app.jsx --outfile=static/app.bundle.js --bundle=false --loader:.jsx=jsx \
  --target=es2017 --jsx=transform --jsx-factory=React.createElement --jsx-fragment=React.Fragment
cp gui/index.html static/index.html
```

Run without building a binary:

```bash
python3 main.py
```

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## Config

On first launch a config file is created at `~/.mellow_dlp.json`. You can set:

- `output_dir` — default download folder
- `cookies_browser` — browser to pull cookies from (for age-restricted content)
- `theme` — `dark` (only dark is implemented)

---

## Limitations

- One download at a time (queue is serial, not parallel).
- No built-in update mechanism — pull and rebuild manually.
- The desktop window uses Tkinter via FlaskWebGUI, not a proper browser engine. Complex pages may behave differently than in a real browser; this is a known FlaskWebGUI constraint.
- yt-dlp can break when platforms change their APIs. Update yt-dlp from the Config page or replace the binary manually.
