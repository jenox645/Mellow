# Changelog

What changed in each MellowDLP release, newest first. The app shows these
notes after it updates (and under Config → WHAT'S NEW), and each GitHub
release starts with its section.

Each release is a `## X.Y.Z` heading followed by `- **Title**: what it does`
lines. A pull request that raises `APP_VERSION` adds its section here: CI
fails without one.

## 2.14.0
- **YouTube works with Node.js**: YouTube hides its video links behind a small puzzle that needs a JavaScript runtime to solve. yt-dlp only looked for Deno, so with Node.js (or Bun, or QuickJS) installed it had none, and YouTube offered fewer formats or none at all. MellowDLP now uses whichever one is installed. Config → JavaScript Runtime says which one it found; without one, GET NODE.JS opens its download page.
- **A list view in the Vault**: ☰ LIST, next to SM / MD / LG in an open folder, shows one line per file (name, type, size, date), so a big folder fits on a screen. SM cards are smaller too.
- **Select files like in a file explorer**: drag a rectangle over files, Ctrl+click to add one, Shift+click for a range, Ctrl+A for all, Esc to let go. ▶ PLAY plays them together; DELETE (or the Delete key) removes them, and now always asks first.
- **▶ PLAY ALL**: plays every file shown in a folder, in the order shown (search and sort apply), even a folder of hundreds of songs.
- **RANDOMIZE takes a number**: type how many files to pick instead of clicking + up to it.
- **Sync options stay with the folder**: format and options picked in a folder's SYNC OPTIONS were lost if you closed the dialog without syncing, and the next sync used the ones the playlist was first downloaded with. They're now saved as you pick them, for SYNC NOW, SYNC ALL and auto-sync alike.
- **Easier to read**: the small grey-blue labels and notes were too faint on the dark background. They're brighter now, in the same colours.
- **GitHub in the app**: Config → MellowDLP Version has a GITHUB button that opens the project page.

## 2.13.0
- **Only your MellowDLP window can use MellowDLP**: the app now signs in the window it opens, and anything else on your computer that talks to it (another program, a web page in your browser) is turned away. You don't have to do anything: opening MellowDLP signs you in. Starting it a second time brings up the running copy, as before.
- **API keys for your scripts**: a program that added downloads through MellowDLP needs a key now. Make one in Config → API ACCESS, tick only what it may do (add downloads, read the queue, follow progress) and revoke it any time. A fixed port in the same panel lets your script always find the app. The new `/api/v1` and how to move an old script over are in docs/API.md.
- **The speed limit holds**: Rate Limit in Config was applied to each connection, so a video downloaded in several pieces at once, or two downloads side by side, used several times the limit you set. It is now one limit for all downloads together.
- **Two videos with the same title keep both**: a second video called like one already in the folder (an "Intro", a live version) overwrote it or was skipped, and the lost one never came back. It is now saved next to it with its id in the name.
- **Titles that look like download leftovers stay**: a song called e.g. "Ferrari.f40" was taken for a half-finished download, hidden in the vault and deleted a week later. It's a song again, and files the download history knows are never cleared as leftovers.
- **Purging the history keeps your library**: PURGE HISTORY in Config also forgot every folder linked to a playlist and its sync settings. It now clears the download history only.
- **No downloading twice**: downloading something already in the folder fetched and converted it again (audio) and added a second history entry. It is now found already there.
- **Auto-sync backs off a failing folder**: a folder whose sync kept failing was retried every hour, forever, and a cancelled sync started again at the next check. Failures now wait longer each time (up to a day), a cancel waits for the folder's next turn, and the folder card says how many syncs failed and when it will try again.
- **A faster Vault**: big folders open and count quicker, most of all on Windows.

## 2.12.0
- **Pick what to download**: an analyzed playlist lists its items with checkboxes: untick the ones you don't want, or use ALL / NONE / INVERT. The list shows how many are ticked and how long they last together.
- **Several search results at once**: tick results in a YouTube search and LIST them: they become one list you download together, with the format and options you choose.
- **✕ really skips**: removing a pending item from a download that had already started only hid it; it was downloaded anyway. ✕ now leaves it out (one already downloading finishes). In a vault sync it skips the item this time; the next sync tries again.
- **Move a folder**: picked the wrong folder for a playlist? ⇄ MOVE in the folder (or Move to… in a folder card's ⋯ menu) puts it somewhere else, with its linked playlists, sync settings, name, budget, history and archive file, so nothing downloads again.
- **The open folder shows a sync's new files**: a folder open in the vault stayed "no media here" after a sync filled it, until REFRESH.
- **Sync banner fix**: the "sync in progress" notice in the Feed had taken the look of 2.11.0's new sync banner.

## 2.11.0
- **See what a sync is doing**: a vault sync used to list its playlist's every song as QUEUED, the ones already in the folder too. It now reads the playlist first and the Queue says what it found: "✓ playlist read · 65 · ✓ 63 already in folder · ↓ 2 to download". PENDING lists only the songs it will download; a new IN FOLDER tab lists the rest. This works for SYNC NOW, SYNC ALL and the periodic auto-sync alike.
- **Every sync says how it went**: when a sync ends, a toast says "2 new · 63 already in the folder" or "up to date, nothing new", so you can tell the periodic sync is doing its job. Only a sync that brought something new plays the sound and shows a desktop notification.
- **The celebration counts the right songs**: a SYNC NOW started from the vault was celebrated with the whole playlist's count, even when nothing new came in. It now counts the songs that were actually downloaded.

## 2.10.1
- **Syncs are celebrated too**: Mellow's celebration only came after a playlist downloaded from the Feed. A vault sync (SYNC NOW, SYNC ALL, auto-sync) that brought new songs now ends with it as well, with the folder's name and how many came in; an up-to-date sync stays quiet. Config → Sync Completion Animation turns it off.
- **Folder covers line up**: in the Vault, a folder linked to a playlist showed a smaller cover than the others (its extra line squeezed it). Every cover now has the same shape.

## 2.10.0
- **Synced music plays as one album**: songs saved as audio from a playlist now carry the playlist's name as their album and their place in it as the track number, so a music app or your phone groups the folder as one album, in playlist order. Artists lose YouTube's " - Topic" and "VEVO" (e.g. "RickAstleyVEVO" becomes "Rick Astley"). A song with a real album of its own (YouTube Music) keeps it. The Album Tags option (on by default) turns it off.
- **♪ RE-TAG**: a vault folder with songs has a RE-TAG button that gives the songs already there the same tags, numbered in the linked playlist's current order, so a reordered playlist is renumbered too. Only the tags change: the files, their names and the sound stay as they are.
- **Open in Explorer shows the song, in front**: in a folder whose path has a space, Explorer opened Documents instead of the song's folder, and its window came up behind MellowDLP. It now opens on the song, selected, in front of MellowDLP.
- **Card menus stay in the window**: the ⋯ menu of a vault card in the last column or row opened past the window's edge, showing only its icons.

## 2.9.0
- **A video copied from a Mix or playlist is downloaded alone**: a link copied while a YouTube Mix or playlist plays ("watch?v=…&list=…") used to load the whole list, some 50 songs for a Mix. MellowDLP now takes just that video, and THE WHOLE MIX (or PLAYLIST) next to it reads the list instead.
- **Long titles no longer fail downloads**: a title too long for a file name (a TikTok or Instagram caption, a long Japanese title, a deep folder on Windows) is cut short to fit, instead of failing with "File name too long" or "No such file or directory".
- **The computer stays awake while downloading**: a laptop no longer goes to sleep in the middle of a playlist, and a ⏾ LATER download can start at night. The screen can still turn off, and closing the lid still sleeps. Config → App Behavior → Keep the Computer Awake turns it off.
- **"This video is not available" explained**: YouTube's catch-all refusal now says what usually lifts it (a signed-in browser's cookies, in Config → Authentication), with an OPEN CONFIG button, instead of the raw error.
- **Web pages can't reach into MellowDLP**: a site you visit could point an image tag at MellowDLP's local server and show your own pictures inside its page, or make it run ffmpeg on a video. The server now refuses anything a browser marks as coming from another site, and no other page may embed or frame it.
- **Releases you can check**: every file of a release now has a signed build provenance, so `gh attestation verify <file> --repo jenox645/Mellow` proves it was built by this repository's public workflow, not uploaded by hand. The README's new Safety and privacy section says what MellowDLP connects to (no telemetry) and how updates are checked.
- **Cancelled downloads don't lower the success rate**: Analytics leaves the ones you cancelled out of it.
- **What's new reads properly**: one 2.8.0 note showed as "— , once nothing is downloading".

## 2.8.0
- **Starts faster**: the installed app is now a folder of files instead of one exe that unpacked itself (and was scanned by the antivirus) at every launch. It starts about 2.5× faster, more on a laptop with Windows Defender. The portable exe stays a single file.
- **Big vault folders open about 4× faster**: only the thumbnails on screen load (the rest as you scroll), each one once, and cards off screen cost nothing until you scroll to them.
- **GET FFMPEG keeps your ffmpeg if an update can't finish**: the one already installed is set aside and put back, instead of being deleted first.
- **Unfinished parts are cleaned up**: a part of a video that no sync could finish for a week (the video left the playlist or stays private) is deleted, so it doesn't take space unseen.
- **YouTube Mixes aren't called private**: "This playlist type is unviewable" no longer suggests setting up cookies, which can't open a Mix.
- **Closing the tab quits MellowDLP**: when it runs in a browser tab (no Chrome or Edge on Linux), once nothing is downloading.
- **The GUIDE tidies up**: it closes the panels it opened, and fast key presses no longer close OPTIONS on it.

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
