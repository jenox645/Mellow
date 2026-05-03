# MellowDLP — Developer Guide for Claude Code

## Architecture
- Backend: Python (`server.py` = Flask server, `downloader.py` = yt-dlp wrapper, `analytics.py` = DuckDB)
- Frontend: Single-page app in `gui/app.jsx` (React UMD, no npm/webpack), styles in `gui/index.html`
- Communication: SSE (`EventSource('/api/progress')`) for download progress; HTTP for everything else
- Build: `python build_setup.py` → esbuild bundles `gui/app.jsx` → `static/app.bundle.js`; copy `gui/index.html` → `static/index.html`
- Config: JSON at `~/.mellow_dlp.json`; analytics DB at `~/.mellow_dlp.duckdb`
- Desktop wrapper: FlaskWebGUI (Tkinter-based, NOT Electron)

## Key State That Must Persist
- Feed: url, analyzed info, format/quality/options (persisted in sessionStorage with `feed_*` keys)
- Queue: `playlistItems` (pending) and `completedItems` (done) — both at App root
- Options (format, quality, checkboxes): survive URL change AND section navigation via sessionStorage
- Victory overlay: state at App root, triggered by `item_done` events accumulating then `complete`

## Download Flow
1. User pastes URL → ANALYZE → POST `/api/info` → yt-dlp `--dump-json`
2. User clicks DOWNLOAD → POST `/api/download` with `{url, format, quality, options}`
3. `server.py` calls `downloader.download_in_thread()` → yt-dlp subprocess
4. Progress emitted per-item via SSE: `downloading` → `item_done` (on each file finish) → `processing` → repeat → `complete`
5. `item_done` event: frontend moves item from `playlistItems` → `completedItems`, increments counter
6. `complete` event: clears remaining `playlistItems`, triggers victory overlay if playlist

## SSE Event Types (server → frontend)
- `starting` — download thread launched
- `downloading` — progress update with `pct`, `speed`, `eta`, `current_item_title`, `current_item_thumb`
- `item_done` — one file finished: `title`, `thumbnail`, `playlist_index`
- `processing` — postprocessing (ffmpeg)
- `complete` — entire download finished: `title`, `file_path`, `file_size`
- `error` / `cancelled` — terminal states
- `ytdlp_updated` — after yt-dlp self-update

## Known Architectural Rules
- Never reset download options on URL change — only reset `info` and `playlistItems`
- `completedItems` populated by `item_done` events, NOT by `complete` (which only fires once)
- Vault thumbnails: local `.jpg` sidecar files saved at download time via `_save_thumbnail_sidecar()`, served via `/api/vault/thumb?path=...`
- Stats polling: 3s interval during active download, 30s when idle
- Victory overlay at App root (outside all page components), z-index 9999

## Build Sequence
```bash
# Bundle JSX (requires esbuild):
esbuild gui/app.jsx --outfile=static/app.bundle.js --bundle=false --loader:.jsx=jsx \
  --target=es2017 --jsx=transform --jsx-factory=React.createElement --jsx-fragment=React.Fragment

# Copy HTML:
cp gui/index.html static/index.html

# Full build + installer:
python build_setup.py
```

## Tests
```bash
python -m pytest tests/ -v
```
