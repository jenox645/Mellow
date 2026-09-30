# MellowDLP — Developer Guide for Claude Code

## Architecture
- Backend modules (Python):
  - `server.py` — Flask routes only; business logic lives in the modules below
  - `jobs.py` — download job queue: worker pool (`download_workers` config, max `MAX_DOWNLOAD_WORKERS`), per-job cancel events, reordering, restart persistence (`~/.mellow_dlp_queue.json`)
  - `downloader.py` — yt-dlp Python API wrapper (returns `success|cancelled|error`; never raises — setup failures become an `error` event)
  - `ffmpeg_locate.py` — the one ffmpeg lookup (config override → PATH → next to the app → known install folders), shared by downloader, vault and `/api/system`
  - `analytics.py` — DuckDB (shared per-path connection handed out as cursors)
  - `scheduler.py` — vault auto-sync loop (config: `auto_sync_enabled`, `vault_sync_schedule`)
  - `vault.py` / `library.py` — vault & library business logic
  - `backup.py` — config+DB zip export/restore (touches the DB file only inside `analytics.exclusive_file_access()`; DuckDB locks an open file on Windows)
  - `config.py` — atomic config persistence + `update_config()` for read-modify-write; `load_config()` layers the saved file over `_DEFAULTS`, so new keys need no per-caller fallback
  - `constants.py` / `version.py` — all tuning knobs and the single APP_VERSION
- Frontend (React UMD, bundled by esbuild from ES modules):
  - `gui/app.jsx` — App root: SSE hub, routing, clipboard watcher, shortcuts
  - `gui/lib/` — `api.js`, `util.js`, `constants.js`, `mascots.js`, `sound.js`
  - `gui/components/` — `common.jsx`, `icons.jsx`, `chrome.jsx`, `loading.jsx`, `vault-modals.jsx`
  - `gui/pages/` — `feed.jsx`, `queue.jsx`, `vault.jsx`, `analytics.jsx`, `signal.jsx`, `config.jsx`
- Communication: SSE (`EventSource('/api/progress')`) for download progress; HTTP for everything else
- Build: `python build_setup.py` → esbuild **bundles** `gui/app.jsx` (+imports) → `static/app.bundle.js`; copies `gui/index.html` → `static/index.html`
- Config: JSON at `~/.mellow_dlp.json`; analytics DB at `~/.mellow_dlp.duckdb`
- Desktop wrapper: FlaskWebGUI (Tkinter-based, NOT Electron); `main.py` has a single-instance guard via `~/.mellow_dlp.port`

## Key State That Must Persist
- Feed: url, analyzed info, format/quality/options (sessionStorage `feed_*` keys); defaults seeded from config `default_*` keys when no session state exists
- Queue: `playlistItems` (pending) and `completedItems` (done) — both at App root
- Options (format, quality, checkboxes): survive URL change AND section navigation via sessionStorage
- Victory overlay: state at App root, triggered by `item_done` events accumulating then `complete`
- Queued jobs survive restarts (resume prompt on launch)

## Download Flow
1. User pastes URL → ANALYZE → POST `/api/info` → yt-dlp `--dump-json`
2. User clicks DOWNLOAD → POST `/api/download` with `{url, format, quality, options}`
3. `server.py` enqueues via `jobs.manager`; worker pool calls `downloader.download_video()` with a per-job cancel event
4. Progress emitted per-item via SSE: `downloading` → `item_done` (on each file finish) → `processing` → repeat → `complete`
5. `item_done` event: frontend moves item from `playlistItems` → `completedItems`, increments counter
6. `complete` event: clears remaining `playlistItems`, triggers victory overlay if playlist

## SSE Event Types (server → frontend)
All job-originated events carry `job_id`, `job_type`, `job_label` (multi-worker attribution).
- `starting` — download started
- `downloading` — progress update with `pct`, `speed`, `eta`, `current_item_title`, `current_item_thumb`
- `item_done` — one file finished: `title`, `thumbnail`, `video_id`, `playlist_index`
- `item_failed` — one item failed: `reason` (`geo_blocked`/`error`), `message`
- `processing` — postprocessing (ffmpeg)
- `warning` — non-fatal notice with `code` + `message` (today: `ffmpeg_missing`, `sponsorblock_skipped`)
- `complete` — entire download finished: `title`, `file_path`, `file_size`, `warning` (set when it was saved with limits)
- `error` (includes `url` for retry, `code: ffmpeg_missing` when that is the likely cause) / `cancelled` — terminal states
- `paused` / `resumed` — pause toggles
- `ytdlp_updated` — after yt-dlp self-update

## Known Architectural Rules
- Never reset download options on URL change — only reset `info` and `playlistItems`
- `completedItems` populated by `item_done` events, NOT by `complete` (which only fires once)
- Vault thumbnails: `.jpg` sidecars saved at download time (`_save_thumbnail_sidecar`), ffmpeg frame-grab fallback in `vault.get_thumb_bytes`, served via `/api/vault/thumb?path=...`
- The App root pins the main progress panel to one "primary" job; concurrent jobs render in the Queue page jobs list via `activeJobs`
- Mutating `/api/` requests require a JSON content type (CSRF guard); `/api/backup/restore` is the only multipart exception
- All magic numbers live in `constants.py` (backend) / `gui/lib/constants.js` (frontend)
- Stats polling: 3s during active download, 30s idle (frontend constants)
- Victory overlay at App root (outside all page components), z-index 9999
- Every job must end in exactly one terminal event (`complete`/`error`/`cancelled`) — the UI has no timeout; `jobs._worker` pushes `error` if a job crashes
- No ffmpeg → `downloader` requests single-file formats and no ffmpeg postprocessors, and says so via `warning`; never build a `a+b` format or an `FFmpeg*` postprocessor without checking `find_ffmpeg()`
- Cancel is per job (`job["cancel_event"]`); pause is one flag for all running downloads, owned by `JobManager` (cleared when the queue goes idle)
- A run where yt-dlp logged errors and no file finished (`_download_retcode` set, `speed_tracker["finished"]` == 0) is an `error`, never `complete` — that is a dead/private playlist or every item refused (HTTP 403 from a stale yt-dlp). No errors and no files is an up-to-date archive sync and stays a success
- History rows are only written for files that exist on disk; the recorded `container` is the real file extension
- Cover art: yt-dlp only embeds a thumbnail it wrote itself, so `embed_thumbnail` sets `writethumbnail` + a jpg convertor and adds `_EmbedThumbnailBestEffort` (keeps the `.jpg` as the vault sidecar, never fails the download). Needs `mutagen` for mp4/m4a/flac/opus
- webm can't hold m4a/h264: `_merged_format()` asks for webm streams and lets an impossible merge fall back to mkv (`merge_output_format="webm/mkv"`)
- SponsorBlock (`sponsorblock` option) *removes* `SPONSORBLOCK_REMOVE_CATEGORIES` from the file. The `SponsorBlock` postprocessor only looks segments up (`when: after_filter`, YouTube only); `ModifyChapters` does the cutting and must sit after `FFmpegEmbedSubtitle` and before `FFmpegMetadata` — `_build_postprocessors()` keeps the yt-dlp CLI order. Skipped with a `sponsorblock_skipped` warning on a trimmed download (segment times refer to the whole video)
- `download_range_func` takes `(start, end)` tuples, not dicts
- yt-dlp's ffmpeg downloader ignores `ffmpeg_location`; `find_ffmpeg()` therefore also prepends the folder to `PATH`
- yt-dlp update: a pip upgrade only takes effect after a restart (`restart_required`); the frozen app can't replace its bundled yt-dlp at all and says so

## Build Sequence
```bash
# Frontend only (fast dev loop — also SETUP.bat option [3]):
python build_setup.py --frontend-only

# Full build + installer (runs inside .venv, created automatically):
python build_setup.py

# Run tests via the build venv (SETUP.bat option [4]):
python build_setup.py --run-tests
```

## Tests
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -m "not e2e and not slow"
python scripts/canary.py        # live-site extraction probe (also the weekly CI canary)
```
- `tests/conftest.py` redirects config, DB and queue files to a temp dir for every test (autouse) and drains `jobs.manager` on teardown — tests must never read or write `~/.mellow_dlp*`
- When a test enqueues through the API with `downloader.download_video` mocked, call `jobs.manager.wait_idle()` inside the `patch` block so the worker can't run the real downloader afterwards

## Lint
```bash
ruff check .                       # backend
npx eslint "gui/**/*.jsx" "gui/**/*.js"   # frontend (jsx-uses-vars shim in eslint.config.js)
```
