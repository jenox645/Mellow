# Changelog

What changed in each MellowDLP release, newest first. The app shows these
notes after it updates (and under Config → WHAT'S NEW), and each GitHub
release starts with its section.

Each release is a `## X.Y.Z` heading followed by `- **Title**: what it does`
lines. A pull request that raises `APP_VERSION` adds its section here: CI
fails without one.

## 2.5.1
- **Opens without Chrome or Edge**: on a Linux system with no Chromium-based browser, MellowDLP opens in your default browser instead of starting with no window.

## 2.5.0
- **One-click updates for the portable exe**: the MellowDLP.exe you build with SETUP.bat ("App only") or keep anywhere updates itself too — UPDATE downloads the new exe, checks it, swaps it in when MellowDLP closes and reopens it. No installer, no release page.
- **Why not?**: when a copy can't update itself, the "new version" message says why.

## 2.4.0
- **GET FFMPEG**: no ffmpeg? MellowDLP downloads it for you (Windows and Linux), checks it against its published checksum and uses it right away — no PATH changes, no restart. Offered at launch, in the status bar, in Config → FFmpeg, and on every "ffmpeg missing" message.
- **What's new**: after an update, this list shows up once. Read it again any time from Config → WHAT'S NEW.

## 2.3.0
- **SAVE TO under the URL bar**: pick each download's folder right in the Feed. ↑/↓ step through the folders you used before, like a terminal prompt; typing narrows the list.
- **Updates show up by themselves**: MellowDLP looks for a new version at every launch and every few hours, and keeps an UPDATE button in the status bar until you take it.

## 2.2.0
- **Updates from the app itself**: UPDATE downloads the new version, checks it, installs it and reopens MellowDLP. Downloads that were running are offered again afterwards.

## 2.1.0
- **First self-updating release**: from this version on, new versions install from inside the app.

## 2.0.0
- **Search YouTube from the Feed**: type words instead of a link and pick a result.
- **Normalize Volume**: audio downloads at an even loudness (-14 LUFS).
- **Subtitles**: languages, auto captions and keeping the subtitle files.
- **yt-dlp updates in the installed app**: checked against yt-dlp's published checksums.
- **Chapter picker, download later, per-folder sync reports, retry with the original options** and a size estimate before downloading.
