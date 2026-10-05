<div align="center">

![MellowDLP Banner](assets/banner.png)

# MellowDLP

A desktop app for [yt-dlp](https://github.com/yt-dlp/yt-dlp): paste a link, pick a format, download.
YouTube, SoundCloud and the [thousands of sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) yt-dlp supports.
Windows and Linux.

[**Download**](https://github.com/jenox645/Mellow/releases/latest) · [What's new](CHANGELOG.md) · [Build from source](#build-from-source)

> A personal project, shared as is.

![Welcome screen](assets/welcome_screen.png)

</div>

---

## Contents

- [Download](#download)
- [Features](#features)
- [ffmpeg](#ffmpeg)
- [Staying up to date](#staying-up-to-date)
- [Troubleshooting](#troubleshooting)
- [Your files](#your-files)
- [Build from source](#build-from-source)
- [Development](#development)
- [Releasing](#releasing)

---

## Download

Get the newest release from the [Releases page](https://github.com/jenox645/Mellow/releases/latest):

| File | For |
|---|---|
| `MellowDLP-X.Y.Z-windows-setup.exe` | Windows installer: Start menu entry, uninstaller. **Recommended on Windows** |
| `MellowDLP-X.Y.Z-windows-portable.exe` | Windows, no install: one exe you keep anywhere |
| `MellowDLP-X.Y.Z-x86_64.AppImage` | Linux, any distro: `chmod +x` it and run it |
| `MellowDLP-X.Y.Z-linux-x86_64` | Linux, a plain binary |
| `SHA256SUMS.txt` | Checksums of the files above |

Every copy updates itself from inside the app afterwards ([below](#staying-up-to-date)), so you only download once.

**Windows says "Windows protected your PC"?** The exe isn't code-signed, and SmartScreen warns about unsigned downloads it hasn't seen many times. Click **More info → Run anyway**. To check the file is the published one first, compare its checksum with the one in `SHA256SUMS.txt`:

```
certutil -hashfile MellowDLP-2.5.1-windows-portable.exe SHA256
```

(Linux: `sha256sum -c SHA256SUMS.txt --ignore-missing`.) Updates installed by the app don't trigger the warning, and the app checks their checksums itself.

The window is a Chrome, Edge, Brave or Chromium app window (Windows always has Edge). A Linux system with none of them opens MellowDLP in your default browser instead.

---

## Features

**Downloading**
- **Feed**: paste a link (or Ctrl+V / drop it anywhere in the window), ANALYZE, pick format and quality, DOWNLOAD. Videos, whole playlists, audio only, or several links at once. Type words instead of a link to **search YouTube**.
- **SAVE TO** under the URL bar: this download's folder. ↑/↓ step through the folders you used before, like a terminal prompt; typing narrows the list. Empty = the default folder from Config.
- **Before you download**: a size estimate (and a warning when it won't fit the drive), and a note when you already have that video, with a shortcut to the file.
- **Options**: embed cover art, metadata, chapters and subtitles; cut out sponsor segments ([SponsorBlock](https://sponsor.ajay.app/)); even out the volume (-14 LUFS); pick chapters or a time range to save only part of a video.
- **Formats**: video as MP4, MKV or WebM at best, 4K, 1080p, 720p, 480p or 360p. Audio as MP3, M4A, AAC or Opus (best, 320, 256, 192 or 128 kbps), FLAC or WAV.

**The queue**
- Live progress per job (speed, ETA, thumbnails). Pause, resume, reorder, cancel; run up to 3 downloads at once (Config → `download_workers`).
- **Download later**: ⏾ LATER queues a download for a set time of day, like the middle of the night (Config → "Later" Downloads Start At; the app must be running).
- Unfinished jobs survive a restart; failed items retry with their original options.
- Optional desktop notification and chime when a download finishes or fails in the background.

**Your library**
- **Vault**: browse what you downloaded by folder, with thumbnails, file stats, OPEN and FOLDER buttons.
- **Library sync**: link a folder to a playlist or channel and keep it in step, add-only or mirror (removes files no longer in the playlist). Syncs run on a schedule if you like, and each one leaves a report: what came in, what was skipped, what failed.
- **Archive file**: each folder's `mellow_archive.txt` lists what's in it, so nothing downloads twice. Import it on another computer to rebuild the same library.
- **Analytics**: your download history by platform, format and uploader, with CSV export and custom SQL.

**When things go wrong**
- **Plain-language errors**: outdated yt-dlp, bot checks, private or removed videos, geo-blocks, network trouble, a full disk… each explained with the fix, often a one-click button.
- **Cookies** from your browser for age-restricted or members-only videos, with a TEST button.
- **Network**: proxy, rate limit, and Force IPv4 for connections where IPv6 hangs.
- **Backup & Restore** (Config): your settings and history as one zip.

---

## ffmpeg

ffmpeg does the merging, converting, trimming and embedding. It isn't bundled, but MellowDLP gets it for you on Windows and Linux: when it's missing, click **GET FFMPEG** (offered at launch, in the status bar and in Config → FFmpeg). It downloads a static build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), checks it against the published checksums and keeps `ffmpeg` and `ffprobe` in `~/.mellow_dlp_ffmpeg`. No PATH changes, no restart.

Or install it yourself:

| OS | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Debian/Ubuntu | `sudo apt install ffmpeg` |

MellowDLP looks on `PATH`, next to the app (`ffmpeg/`), in `~/.mellow_dlp_ffmpeg`, and in the usual winget / Chocolatey / Scoop / Homebrew folders, and picks up a fresh install without a restart. For another location, set `"ffmpeg_location"` in `~/.mellow_dlp.json` to the binary or its folder. The status bar shows whether it was found.

Without ffmpeg the app still works, with limits it tells you about: audio stays in its original format (usually `.m4a`), and sites that serve video and audio separately (YouTube) can't be saved as video.

---

## Staying up to date

- **MellowDLP** looks for a new release at launch and every 6 hours, and keeps an **UPDATE** button in the status bar. One click downloads it, checks it against the release's checksums, installs it and restarts; downloads that were running are offered again afterwards. This works for the installer, the portable exe (including one you built with SETUP.bat), the AppImage and the Linux binary. A copy that can't replace itself (say, installed system-wide) says why and links the release page.
- **What's new**: after an update the app shows that release's notes once. Config → WHAT'S NEW lists every release ([CHANGELOG.md](CHANGELOG.md)).
- **yt-dlp** changes as often as the sites do. Config → yt-dlp Version → UPDATE downloads yt-dlp's official release (checksum-verified) and uses it from the next start, in the installed app too.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `HTTP Error 403`, "Sign in to confirm", "Unable to extract" | yt-dlp is out of date: Config → yt-dlp Version → UPDATE, then restart MellowDLP |
| "ffmpeg missing", audio stays `.m4a` | GET FFMPEG ([above](#ffmpeg)) |
| Age-restricted or members-only videos fail | Config → Browser Cookies: pick the browser you're signed in with, then TEST |
| Downloads hang on some networks | Config → Force IPv4 |
| SmartScreen blocks the exe | [More info → Run anyway](#download) |
| Something else | The log is `~/.mellow_dlp.log` (`%USERPROFILE%\.mellow_dlp.log` on Windows). Updates log to `~/.mellow_dlp_update.log` |

---

## Your files

Everything MellowDLP keeps lives in your home folder (`%USERPROFILE%` on Windows):

| File | What |
|---|---|
| `.mellow_dlp.json` | Settings |
| `.mellow_dlp.duckdb` | Download history, library, sync reports |
| `.mellow_dlp_queue.json` | Unfinished jobs, resumed at the next launch |
| `.mellow_dlp.log`, `.mellow_dlp_update.log` | Logs |
| `.mellow_dlp_ffmpeg/` | ffmpeg from GET FFMPEG |
| `.mellow_dlp_ytdlp.zip` | yt-dlp from UPDATE |

Downloads go to `Downloads/MellowDLP` unless you choose another folder. Uninstalling leaves these files; delete them to start over.

---

## Build from source

Needs Python 3.12+ and Node.js 20+.

**Windows**: run `SETUP.bat` and pick:

1. Full installer: `dist\MellowDLP_Setup.exe`
2. App only: `dist\MellowDLP.exe` and a Desktop shortcut (it updates itself like the portable exe)
3. Frontend only: rebuilds `static\` in seconds, for UI work
4. Run tests

**Linux**:
```bash
git clone https://github.com/jenox645/Mellow
cd Mellow
bash setup.sh
./dist/MellowDLP
```

Or as a `.deb` (after `setup.sh`): `python3 build_linux_deb.py && sudo dpkg -i dist/mellowdlp_*.deb`. A `.deb` install is updated by installing the next `.deb`.

Both run `python build_setup.py`, which creates `.venv`, installs the pinned dependencies (`requirements.txt`, `requirements-build.txt`, `package-lock.json`), bundles the frontend with esbuild and packages the app with PyInstaller (plus Inno Setup for the Windows installer).

**Run without packaging** (`static/` is build output, so build the frontend once first):
```bash
python build_setup.py --frontend-only
python main.py               # in a window
python main.py --no-window   # just the server; open the printed URL in any browser
```
On Linux, `python3-tk` gives you the native BROWSE dialogs, and `xclip` the "copied a link?" suggestion.

---

## Development

| Layer | Tech |
|---|---|
| Backend | Python 3.12+, Flask, yt-dlp (Python API), DuckDB |
| Frontend | React 18 (UMD) in ES modules, bundled by esbuild; fonts bundled, no CDN |
| Window | [FlaskWebGUI](https://github.com/ClimenteA/flaskwebgui): a Chromium-based browser in app mode |
| Packaging | PyInstaller (one file), Inno Setup, appimagetool |

`main.py` starts the app, the backend is in `mellow/` (`server.py` is the routes only), the frontend source in `gui/`. [CLAUDE.md](CLAUDE.md) is the detailed developer guide: architecture, events, and the rules the code keeps.

**Tests and lint**
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -m "not e2e and not slow and not browser"
ruff check .
npm ci
npm test            # frontend unit tests (node:test)
npm run lint        # ESLint
```

Tests never touch your real config, database or queue: every test runs in a temp folder.

- `python -m pytest tests/browser -m browser` clicks through the main flows (download, playlist, search, cancel, vault) in Chromium, downloading from a local test site. Needs the frontend built, ffmpeg, and `python -m playwright install chromium`.
- The `e2e` and `slow` markers download from real sites; run them by hand.
- `python scripts/canary.py` checks extraction against live sites; CI runs it weekly on the yt-dlp pre-release.

CI runs the Python, JavaScript and browser tests on every pull request; pull requests that touch packaging also build the Windows and Linux apps, smoke-test them, install GET FFMPEG for real, and update an old copy to the new build.

---

## Releasing

1. Raise `APP_VERSION` in `mellow/version.py` (and the fallback `AppVersion` in `installer.iss`).
2. Add a `## X.Y.Z` section at the top of [CHANGELOG.md](CHANGELOG.md), as `- **Title**: what it does` lines. CI fails without it; the app shows it after updating, and the GitHub release starts with it.
3. Merge the pull request. GitHub Actions builds the Windows installer, portable exe, Linux binary and AppImage, tests them, and publishes `vX.Y.Z` with `SHA256SUMS.txt`. Installed copies offer the update within hours.

Pushing a tag `vX.Y.Z` that matches `APP_VERSION` does the same by hand; a `-suffix` tag makes a pre-release.
