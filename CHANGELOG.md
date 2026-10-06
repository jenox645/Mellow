# Changelog

What changed in each MellowDLP release, newest first. The app shows these
notes after it updates (and under Config → WHAT'S NEW), and each GitHub
release starts with its section.

Each release is a `## X.Y.Z` heading followed by `- **Title**: what it does`
lines. A pull request that raises `APP_VERSION` adds its section here: CI
fails without one.

## 2.7.0
- **A deeper GUIDE**: more steps on every page (the archive file, add-only vs mirror, budgets, randomize, presets, file names, cookies…), a tip on almost every step, and made-up examples of what a part looks like before it shows up.
- **Private playlists explained**: a playlist that "does not exist" is usually private. MellowDLP now says so and how to fix it (your browser's sign-in, in Config → Authentication), with an OPEN CONFIG button on the Feed.
- **Clearer cookie errors**: when Chrome, Edge or Brave won't share their cookies, the message says what to use instead (Firefox, or a cookies.txt), without repeating yt-dlp's raw error.
- **No more silent videos in the vault**: when a playlist item failed halfway, the video part yt-dlp had already downloaded ("Title.f399.mp4", no sound) showed up as a finished video and was marked as downloaded. It's now ignored, and the next sync finishes that video properly.
- **Messages stay up long enough to read**: long explanations no longer vanish after 6 seconds.

## 2.6.0
- **GUIDE on every page**: click **? GUIDE** at the top (or press G) and MellowDLP walks you through the page you're on, one part at a time: it lights the part up, scrolls to it, opens collapsed panels, and says what it does. ← / → to step, Esc to stop.

## 2.5.1
- **Opens without Chrome or Edge**: on a Linux system with no Chromium-based browser, MellowDLP opens in your default browser instead of starting with no window.
- **GET FFMPEG and antivirus**: when an antivirus scan briefly locks the new ffmpeg on Windows, GET FFMPEG waits for it instead of failing with "Access is denied".

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
