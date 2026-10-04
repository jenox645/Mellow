# MellowDLP — Developer Guide for Claude Code

## Layout
```
main.py            desktop entry point (single-instance guard, FlaskWebGUI window)
mellow/            backend package — modules import each other relatively (`from . import jobs`)
gui/               frontend source (React ES modules + index.html/CSS; fonts/ = bundled woff2 + OFL licenses)
static/            build output only (gitignored): bundle, React, index.html, mascots.js
assets/            icons, mascot art (*_vector used by the build), installer images;
                   originals/ holds unused source art
tests/             pytest suite (imports `from mellow import …`, patches `mellow.<module>.<name>`);
                   tests/js/ = frontend unit tests (node:test); tests/browser/ = Chromium smoke tests (marker `browser`)
scripts/canary.py  live-site extraction probe; scripts/smoke_binary.py starts a build headless and checks it
build_setup.py     the build (SETUP.bat / setup.sh call it); MellowDLP.spec, installer.iss,
                   build_linux_deb.py are its packaging inputs
```

## Architecture
- Backend modules (Python, in `mellow/`):
  - `server.py` — Flask routes only; business logic lives in the modules below
  - `jobs.py` — download job queue: worker pool (`download_workers` config, max `MAX_DOWNLOAD_WORKERS`), per-job cancel events, reordering, restart persistence (`~/.mellow_dlp_queue.json`)
  - `downloader.py` — yt-dlp Python API wrapper (returns `success|cancelled|error`; never raises — setup failures become an `error` event)
  - `desktop.py` — OS integration: show in file manager, open with default app, clipboard, native Tk file/folder dialogs
  - `app_update.py` — newer MellowDLP on GitHub releases, and installing it: `install_kind()` (`windows-installer` / `appimage` / `linux-binary`, else the release page), `install()` downloads the asset named in `constants.APP_ASSET_NAMES`, checks `SHA256SUMS.txt`, swaps the file or stages the installer, and hands over to a detached helper that waits for this PID to exit, runs the installer silently and relaunches
  - `ytdlp_update.py` — yt-dlp version check (PyPI) and in-app update: downloads the release zipapp to `~/.mellow_dlp_ytdlp.zip`; `activate_overlay()` (main.py, before any yt_dlp import) runs it instead of the bundled copy when it's newer
  - `applog.py` — rotating log file `~/.mellow_dlp.log` (the packaged app has no console); modules log via `logging.getLogger(__name__)`, never `print`
  - `ffmpeg_locate.py` — the one ffmpeg lookup (config override → PATH → next to the app → known install folders), shared by downloader, vault and `/api/system`
  - `errors.py` — `explain()` maps raw yt-dlp errors to `{code, title, hint, action}`; `jobs._make_cb` annotates every `error`/`item_failed` event, `/api/info` errors too
  - `analytics.py` — DuckDB only (shared per-path connection handed out as cursors); filesystem scans live in `vault.py`
  - `scheduler.py` — vault auto-sync loop (config: `auto_sync_enabled`, `vault_sync_schedule`)
  - `vault.py` / `library.py` — vault & library business logic
  - `backup.py` — config+DB zip export/restore (touches the DB file only inside `analytics.exclusive_file_access()`; DuckDB locks an open file on Windows)
  - `config.py` — atomic config persistence + `update_config()` for read-modify-write; `load_config()` layers the saved file over `_DEFAULTS`, so new keys need no per-caller fallback. `download_root(cfg)` is the download folder (never re-derive `~/Downloads/MellowDLP`); `request_settings()` / `download_settings()` are the cookie/network/tuning opts every yt-dlp call and job copies
  - `formats.py` — the on/off download options (`TOGGLES`: embed_*, sponsorblock, normalize_audio) and `toggles(source, fallback)`; every download, sync format and library entry takes them from here
  - `constants.py` / `version.py` — all tuning knobs and the single APP_VERSION
- Frontend (React UMD, bundled by esbuild from ES modules):
  - `gui/app.jsx` — App root: routing, clipboard watcher, shortcuts; feeds SSE events to `downloadsReducer` and runs the effects it queues
  - `gui/lib/` — `api.js`, `util.js`, `constants.js`, `formats.js` (FORMAT_TOGGLES as one `{key: bool}`), `hooks.js` (`useSessionState`), `downloads.js` (the progress-event reducer), `mascots.js`, `sound.js`. The root `package.json` (`"type": "module"`) lets node test them directly
  - `gui/components/` — `common.jsx`, `icons.jsx`, `chrome.jsx`, `loading.jsx`, `vault-modals.jsx`
  - `gui/pages/` — `feed.jsx`, `queue.jsx`, `vault.jsx`, `analytics.jsx`, `signal.jsx`, `config.jsx`
- Communication: SSE (`EventSource('/api/progress')`) for download progress; HTTP for everything else
- Build: `python build_setup.py` → esbuild **bundles** `gui/app.jsx` (+imports) → `static/app.bundle.js`; copies `gui/index.html` → `static/index.html` and `gui/fonts/` → `static/fonts/` (fonts are bundled: the app makes no requests to Google Fonts or any other CDN)
- Config: JSON at `~/.mellow_dlp.json`; analytics DB at `~/.mellow_dlp.duckdb`
- Desktop wrapper: FlaskWebGUI (Tkinter-based, NOT Electron); `main.py` has a single-instance guard via `~/.mellow_dlp.port`

## Key State That Must Persist
- Feed: url, analyzed info, format/quality/options (`useSessionState('feed_*')`, JSON in sessionStorage); defaults seeded from config `default_*` keys when no session state exists
- Feed SAVE TO (`feed_downloadPath`, empty = `download_root`): `<FolderInput>` (common.jsx) recalls config `recent_output_dirs` with ↑/↓ like a terminal prompt (narrowed by what's typed; helpers `matchFolders`/`stepHistory` in util.js). `/api/download` with an `output_dir` records it (`config.remember_output_dir`, newest first, `RECENT_OUTPUT_DIRS_KEEP`) and returns the new list; RESET DEFAULTS keeps it. Its menu is `position: fixed` because `.panel` clips its content
- Queue: `playlistItems` (pending) and `completedItems` (done) — both at App root
- Options (format, quality, checkboxes): survive URL change AND section navigation via sessionStorage
- Victory overlay: state at App root, triggered by `item_done` events accumulating then `complete`
- Unfinished jobs (running or queued) survive restarts (resume prompt on launch)

## Download Flow
1. User pastes URL → ANALYZE → POST `/api/info` → yt-dlp `--dump-json` (a playlist's items come back in the same answer). Words instead of a link (`util.isLinkLike`) → SEARCH → POST `/api/search` (`downloader.search`, `ytsearchN:`), and a picked result is analyzed
2. User clicks DOWNLOAD → POST `/api/download` with `{url, format, quality, options}`
3. `server.py` enqueues via `jobs.manager`; worker pool calls `downloader.download_video()` with a per-job cancel event
4. Progress emitted per-item via SSE: `downloading` → `item_done` (on each file finish) → `processing` → repeat → `complete`
5. `item_done` event: frontend moves item from `playlistItems` → `completedItems`, increments counter
6. `complete` event: clears remaining `playlistItems`, triggers victory overlay if playlist

## SSE Event Types (server → frontend)
All job-originated events carry `job_id`, `job_type`, `job_label` (multi-worker attribution).
The frontend handles them in one place: `gui/lib/downloads.js` `applyEvent(state, event)` is a pure
reducer over the download state (dlState, activeJobs, playlist/completed/failed items, pause, counts).
Side effects (toasts, chime, desktop notification, refreshes, the victory overlay) are queued in
`state.effects`, and the App runs them in order and acknowledges them (`effects_done`). Pages change this
state through setState-style setters (`{type:'set', key, value}`) or `playlist_started` / `playlist_items`.
A new event = a case in `applyEvent` + a test in `tests/js/downloads.test.mjs`.
- `starting` — download started
- `downloading` — progress update with `pct`, `speed`, `eta`, `current_item_title`, `current_item_thumb`
- `item_done` — one file finished: `title`, `thumbnail`, `video_id`, `playlist_index`
- `item_failed` — one item failed: `reason` (`geo_blocked`/`error`), `message`
- `item_saved` — an item's final file after every postprocessor (yt-dlp `post_hooks`): `file_path`, `file_size`; the UI attaches it to the job's newest finished item (OPEN / FOLDER)
- `processing` — postprocessing (ffmpeg)
- `warning` — non-fatal notice with `code` + `message` (today: `ffmpeg_missing`, `sponsorblock_skipped`)
- `complete` — entire download finished: `title`, `file_path`, `file_size`, `warning` (set when it was saved with limits)
- `error` (includes `url` for retry, `code: ffmpeg_missing` when that is the likely cause) / `cancelled` — terminal states
- `error` and `item_failed` also carry `code`, `title`, `hint` and `action` (`update_ytdlp` | `open_config` | null) when `errors.explain()` recognises the message; the UI shows title + hint and a button for the action
- `paused` / `resumed` — pause toggles
- `ytdlp_updated` — after yt-dlp self-update
- `app_update` — MellowDLP updating itself: `stage` `downloading` (`pct`) → `installing` → `restarting` (the app then exits; `AppUpdateOverlay` covers the page), or `error` with `message`

## Known Architectural Rules
- Never reset download options on URL change — only reset `info` and `playlistItems`
- `completedItems` populated by `item_done` events, NOT by `complete` (which only fires once)
- Vault thumbnails: `.jpg` sidecars saved at download time (`_save_thumbnail_sidecar`), ffmpeg frame-grab fallback in `vault.get_thumb_bytes`, served via `/api/vault/thumb?path=...`
- The App root pins the main progress panel to one "primary" job; concurrent jobs render in the Queue page jobs list via `activeJobs`
- Mutating `/api/` requests require a JSON content type (CSRF guard); `/api/backup/restore` is the only multipart exception
- `gui/lib/api.js`: every `API.*` call rejects on a 4xx/5xx with `Error(body.error)` plus `err.data` (full body) and `err.status` — handle failures in `.catch`, never by checking `d.error` in `.then`
- A library entry's folder is `library.folder_path_for_entry(entry, download_root(cfg))` — used by syncs, the vault listing and entry↔folder matching alike
- Deleting a media file goes through `vault.delete_media_file()` (sidecars + history rows too)
- All magic numbers live in `constants.py` (backend) / `gui/lib/constants.js` (frontend)
- Stats polling: 3s during active download, 30s idle (frontend constants)
- Format lists (qualities, containers, audio formats, bitrates) live only in `gui/lib/constants.js`
- A new on/off download option is one entry in `formats.TOGGLES` and one in `FORMAT_TOGGLES` (constants.js; a test compares them) plus its effect in `downloader`. Downloads, sync formats (`SYNC_FORMAT_KEYS`), library entries (one DB column per toggle, added by `init_db`) and the `<FormatToggles>` checkboxes in the Feed and both vault dialogs pick it up
- A vault folder's sync format: request → `vault_sync_formats[path]` (last choice, saved by the sync dialog and the Feed's vault link) → its library entry → `infer_folder_format()` (what the files are). Auto-sync and "sync all" send no format, so this chain decides them
- Every yt-dlp call (analyze, playlist items, mirror preview, cookie test, downloads) goes through `_apply_cookie_opts` + `_apply_network_opts` (proxy, `force_ipv4`, socket timeout); build them with `config.request_settings(cfg)`
- Mirror preview proposes no deletions when any linked playlist failed to load; ids for "%(title)s"-named files come from the download history
- Sidecar thumbnails share the media file's full stem (`p.parent / (p.stem + ".jpg")`), never `with_suffix("")`
- `/api/info` returns `previous_download` for single videos (history match by URL or YouTube id); `/api/download` returns `disk_warning` when the target drive is low
- `/api/info` also returns `size_estimates` for single videos (`{video: {quality: bytes}, audio: bytes}`), computed by running yt-dlp's own format selector with the download's format strings; the Feed turns it into "≈ size" (`util.estimateDownloadBytes`) and flags a file that won't fit the drive
- `skip_shorts` / `skip_live` (config, copied by `download_settings`) become a yt-dlp `match_filter` only on playlist-like runs (`ignoreerrors`); a single pasted link is never filtered
- `/api/cookies/test` loads cookies from the request's (unsaved) settings; `/api/filename-preview` validates a template and names a sample video with it. Cookie failures are explained by `errors.py` (`cookies_locked` / `cookies_encrypted` / `cookies_not_found`)
- Victory overlay at App root (outside all page components), z-index 9999
- Every job must end in exactly one terminal event (`complete`/`error`/`cancelled`) — the UI has no timeout; `jobs._worker` pushes `error` if a job crashes
- `jobs.run_job` holds back each downloader run's terminal event and emits the job's one terminal itself: with several URLs, a failed one becomes `item_failed` + a `warning` on `complete` (all failed → one `error`)
- Sync timestamps (`vault_sync_times`, library `last_synced`) are written by `JobManager._on_finished` when a sync completes, never on enqueue
- No ffmpeg → `downloader` requests single-file formats and no ffmpeg postprocessors, and says so via `warning`; never build a `a+b` format or an `FFmpeg*` postprocessor without checking `find_ffmpeg()`
- Cancel is per job (`job["cancel_event"]`); pause is one flag for all running downloads, owned by `JobManager` (cleared when the queue goes idle)
- A job can carry `not_before` (epoch seconds; `/api/download` with `scheduled: true` sets it from config `schedule_start` via `jobs.next_time_of_day`). Workers take the first *due* job in queue order and sleep until the next one is due; `/api/queue/<job>/start-now` clears it; it survives restarts. `wait_idle()` ignores jobs that aren't due
- Sync reports: the downloader's logger turns yt-dlp's "already recorded in the archive" / "does not pass filter" lines into `item_skipped` events, which `jobs._make_cb` collects (with `item_done` titles and `item_failed` details) into `job["report"]` without pushing them to the UI; `_on_finished` stores every sync's report (`analytics.record_sync_report`, table `sync_reports`, last `SYNC_REPORTS_KEEP` per folder), shown by the vault folder view via `/api/vault/sync-report`. `/api/vault/retry-item` re-downloads one item into a folder in the folder's sync format
- When the queue runs dry after downloading something, `JobManager` calls `on_idle(done)` → `server._queue_finished` pushes `queue_done` and, with config `on_queue_done: "open_folder"`, opens the last job's folder
- Retry goes through `/api/queue/<job>/retry` (`JobManager.retry`): one item (`url`) is re-queued as a plain download with the job's options and folder; no `url` re-runs the whole job as it was. `item_failed` carries `url` when `downloader.item_url_from_error()` can map the error's `[extractor] id` to a public URL
- A run where yt-dlp logged errors and no file finished (`_download_retcode` set, `speed_tracker["finished"]` == 0) is an `error`, never `complete` — that is a dead/private playlist or every item refused (HTTP 403 from a stale yt-dlp). No errors and no files is an up-to-date archive sync and stays a success; so is a run with errors where the archive or a skip filter passed over other items (the playlist is alive, one item went private)
- History rows are only written for files that exist on disk; the recorded `container` is the real file extension
- Cover art: yt-dlp only embeds a thumbnail it wrote itself, so `embed_thumbnail` sets `writethumbnail` + a jpg convertor and adds `_EmbedThumbnailBestEffort` (keeps the `.jpg` as the vault sidecar, never fails the download). Needs `mutagen` for mp4/m4a/flac/opus
- webm can't hold m4a/h264: `_merged_format()` asks for webm streams and lets an impossible merge fall back to mkv (`merge_output_format="webm/mkv"`)
- SponsorBlock (`sponsorblock` option) *removes* `SPONSORBLOCK_REMOVE_CATEGORIES` from the file. The `SponsorBlock` postprocessor only looks segments up (`when: after_filter`, YouTube only); `ModifyChapters` does the cutting and must sit after `FFmpegEmbedSubtitle` and before `FFmpegMetadata` — `_build_postprocessors()` keeps the yt-dlp CLI order. Skipped with a `sponsorblock_skipped` warning on a trimmed download (segment times refer to the whole video)
- `download_range_func` takes `(start, end)` tuples, not dicts
- Normalize Volume (`normalize_audio`, an audio-only toggle): `_ExtractAudioNormalized.replacing(ydl)` swaps the FFmpegExtractAudio instance in `ydl._pps["post_process"]` (same slot, so later steps keep their order) for one that adds `LOUDNORM_FILTER` to the conversion. Where yt-dlp would only copy the stream it re-encodes with the file's own codec, at the source sample rate (opus: 48 kHz)
- Subtitles (video only, the `embed_subs` option): languages, auto captions and "keep the files" are config (`sub_langs`, `auto_subs`, `keep_sub_files`, copied by `download_settings`). Kept files are converted to `.srt` before the embed step (`FFmpegSubtitlesConvertor`), except for webm, which only embeds WebVTT; `FFmpegEmbedSubtitle.already_have_subtitle` is what keeps them. `vault.delete_media_file` removes a file's `<stem>.<lang>.srt|vtt` sidecars too
- Chapter picker: `/api/info` returns `chapters` ([{index, title, start, end}]); a download's `chapters` option (checked by `_chosen_chapters`) becomes `download_ranges=_chapter_ranges(...)` — one section per chapter, named `<template stem> - %(section_number)02d %(section_title)s.%(ext)s`, with clip start/end and SponsorBlock skipped. A single video records one history row per file on disk (`requested_downloads`)
- yt-dlp's ffmpeg downloader ignores `ffmpeg_location`; `find_ffmpeg()` therefore also prepends the folder to `PATH`
- yt-dlp update: UPDATE downloads yt-dlp's release zipapp (the `yt-dlp` asset, checked against the release's SHA2-256SUMS) to `ytdlp_update.OVERLAY_PATH`. On the next start `activate_overlay()` puts a meta-path finder first (ahead of PyInstaller's importer) that loads `yt_dlp` and its submodules from the zip — only when it is newer than the bundled version (`importlib.metadata`, hence `copy_metadata("yt-dlp")` in the spec) and it imports cleanly. It takes effect after a restart (`restart_required`; `check()` reports `pending_restart`). Nothing else may import yt_dlp before main.py calls it. The build no longer bundles the yt-dlp executable (nothing used it)
- DuckDB cannot replay an `ALTER TABLE` from its WAL when the table has a `DEFAULT now()` column (all three tables do). `init_db()` therefore only ALTERs columns that are missing and ends with `CHECKPOINT`; `analytics._connect()` moves an unreplayable WAL aside (`*.wal.unreplayable-<time>`, never deleted) and reopens. Any new migration goes through `_add_missing_columns()` inside `init_db()`

## Build Sequence
```bash
# Frontend only (fast dev loop — also SETUP.bat option [3]):
python build_setup.py --frontend-only

# Full build + installer (runs inside .venv, created automatically):
python build_setup.py

# Run tests via the build venv (SETUP.bat option [4]):
python build_setup.py --run-tests

# Start a built binary headless and check it serves the app (CI + release do this):
python scripts/smoke_binary.py dist/MellowDLP
```
- Dependencies are pinned: `requirements.txt` (runtime; yt-dlp has a floor only, on purpose), `requirements-dev.txt`, `requirements-build.txt` (PyInstaller, Pillow), and `package.json` + `package-lock.json` (esbuild, ESLint, React — the build copies React's UMD files from `node_modules`; React 19 has none, so stay on 18). The build runs `npm ci` when the lockfile changed. Dependabot proposes bumps weekly
- flaskwebgui ≥ 1.1.9 (1.1.8 crashes at import without a browser installed); it needs Python 3.12
- `main.py --no-window` serves on 127.0.0.1 without opening a window (use your own browser; the smoke test uses it)
- Release asset names are an API: installed copies look them up (`constants.APP_ASSET_NAMES`, `APP_ASSET_SUMS`); `tests/test_app_update.py` checks release.yml publishes exactly those. `scripts/update_e2e.py <app> <kind>` lets a build older than the latest release update itself for real (release.yml's `update-windows` job does it with the installer on PRs)
- The App looks for a newer MellowDLP at every launch and every `APP_UPDATE_POLL_MS` (6 h) while open (config `update_check_on_launch`); the offer stays in the status bar (`appUpdateOffer`, UPDATE → `takeAppUpdate`), the toast comes once per version
- Self-update restarts through a helper started with `PYINSTALLER_RESET_ENVIRONMENT=1` (a one-file build must not inherit the old copy's unpack folder); `/api/app-update/install` answers 409 while downloads run unless `force` (they're saved and offered again after the restart)
- Releases: merging a change of `APP_VERSION` into main publishes `vX.Y.Z` by itself (release.yml runs on main when `mellow/version.py` changes, skips a version whose tag exists, and `gh release create --target` makes the tag); pushing a tag `vX.Y.Z` equal to `APP_VERSION` does the same by hand. A feature PR that should reach installed copies bumps `APP_VERSION` (and installer.iss's fallback). Either way `.github/workflows/release.yml` builds the Windows installer and the Linux binary + AppImage, smoke-tests each, and publishes the GitHub release with `SHA256SUMS.txt` (a `-suffix` tag is a pre-release). PRs touching packaging run the builds without publishing

## Tests
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -m "not e2e and not slow and not browser"
python -m pytest tests/browser -m browser   # UI smoke tests in Chromium (needs static/ built, ffmpeg, `python -m playwright install chromium`)
python scripts/canary.py        # live-site extraction probe (also the weekly CI canary)
npm test                        # frontend unit tests via node:test (util, formats, the progress-event reducer)
```
- `tests/conftest.py` redirects config, DB and queue files to a temp dir for every test (autouse) and drains `jobs.manager` on teardown — tests must never read or write `~/.mellow_dlp*`
- When a test enqueues through the API with `downloader.download_video` mocked, call `jobs.manager.wait_idle()` inside the `patch` block so the worker can't run the real downloader afterwards

## Lint
```bash
ruff check .                       # backend
npm ci && npm run lint             # frontend (jsx-uses-vars shim in eslint.config.js)
```
