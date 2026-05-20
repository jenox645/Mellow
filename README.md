<div align="center">

![MellowDLP Banner](assets/Ai%20made%20banner.png)

# MellowDLP

Personal desktop GUI for [yt-dlp](https://github.com/yt-dlp/yt-dlp). Download audio and video from YouTube, SoundCloud, and anything yt-dlp supports.

> Personal project, not designed to be maintained for others.

</div>

---

## Preview

<div align="center">

![Welcome screen](assets/welcome_screen.png)

</div>

---

## Features

- **Feed**: paste a URL, analyze it, pick format/quality, download. Supports videos, playlists, audio-only, and multi-URL batch jobs.
- **Queue**: serial download jobs with live progress (speed, ETA, per-item thumbnails). Pause, resume, or cancel mid-download.
- **Vault**: browse your local media library by folder. Thumbnail previews, file stats, direct media player launch.
- **Library sync**: link a vault folder to a playlist URL. Add-only or mirror mode (deletes local files no longer in the playlist).
- **Archive file**: `mellow_archive.txt` per folder tracks downloaded URLs so yt-dlp skips duplicates. Auto-updated on download, sync, and delete. Import in Feed to reproduce the same library on another device.
- **Analytics**: download history with stats by platform, format, and uploader. CSV export and custom SQL.
- **Cookies**: pull cookies from your browser for age-restricted content.
- **yt-dlp self-update**: update yt-dlp from the Config page without rebuilding.

Formats: MP4, MKV, WebM, MP3, FLAC, M4A, OGG, Opus / Quality: best, 4K, 1080p, 720p, 480p, 360p, 128k, 320k.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, Flask, yt-dlp |
| Frontend | React (UMD, no npm), esbuild |
| Desktop window | FlaskWebGUI (Tkinter) |

---

## Requirements

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/)
- Node.js + esbuild (build step only)
- **Linux:** `python3-tk` (`sudo apt install python3-tk`)

---

## Installation

**Windows** — download the `.exe` installer from Releases. ffmpeg is bundled.

**Linux:**
```bash
git clone https://github.com/jenox645/MellowDLP
cd MellowDLP
bash setup.sh
./dist/MellowDLP
```

Or build a `.deb` package:
```bash
python3 build_linux_deb.py
sudo dpkg -i dist/mellowdlp_*.deb
```

---

## Build from source

```bash
pip install -r requirements.txt pyinstaller pillow
npm install -g esbuild
python3 build_setup.py
```

Rebuild frontend only (after editing `gui/app.jsx` or `gui/index.html`):
```bash
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

## Limitations

- One download at a time (serial queue, no parallelism).
- No auto-update for MellowDLP itself — pull and rebuild manually.
- Desktop window uses Tkinter via FlaskWebGUI, not a real browser engine.
- yt-dlp can break when platforms change their APIs — update it from the Config page.
