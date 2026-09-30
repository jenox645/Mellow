# MellowDLP — Developer Guide for Claude Code

## Architecture
- Backend modules (Python):
  - `server.py` — Flask routes only; business logic lives in the modules below
  - `jobs.py` — download job queue: worker pool (`download_workers` config, max `MAX_DOWNLOAD_WORKERS`), per-job cancel events, reordering, restart persistence (`~/.mellow_dlp_queue.json`)
  - `downloader.py` — yt-dlp Python API wrapper (returns `success|cancelled|error`)
  - `analytics.py` — DuckDB (shared per-path connection handed out as cursors)
  - `scheduler.py` — vault auto-sync loop (config: `auto_sync_enabled`, `vault_sync_schedule`)
  - `vault.py` / `library.py` — vault & library business logic
  - `backup.py` — config+DB zip export/restore
  - `config.py` — atomic config persistence + `update_config()` for read-modify-write
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
- `complete` — entire download finished: `title`, `file_path`, `file_size`
- `error` (includes `url` for retry) / `cancelled` — terminal states
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
python -m pytest tests/ -v -m "not e2e and not slow"
```

## Lint
```bash
ruff check .                       # backend
npx eslint "gui/**/*.jsx" "gui/**/*.js"   # frontend (jsx-uses-vars shim in eslint.config.js)
```
