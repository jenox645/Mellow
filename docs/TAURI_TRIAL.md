# Tauri trial

Does a Tauri window work for MellowDLP, and what does it cost and gain compared with today's
FlaskWebGUI window (Chrome/Edge started with `--app`)? Flask and the React UI stay as they are.
This trial ran on Windows 11 (WebView2 157, Chrome 157), Python 3.14, Rust 1.99, Tauri 2.12.

- [What was built](#what-was-built)
- [How to run it](#how-to-run-it)
- [Checks](#checks)
- [Numbers](#numbers)
- [What Tauri gives us next](#what-tauri-gives-us-next)
- [Risks](#risks)
- [Recommendation](#recommendation)

## What was built

**`main.py --shell`** (the only backend change; nothing changes without the flag):

- serves on 127.0.0.1 on a free port (or config `api_port`), no window;
- once the server listens, prints exactly one line on stdout:
  `MELLOW_READY http://127.0.0.1:<port>/launch?t=<token>`. The token is the same one-time launch
  token FlaskWebGUI's window gets (`session.launch_token()`, `LAUNCH_TOKEN_TTL_SECS` = 60 s, single
  use). It travels through the shell's pipe, never a command line, and `/launch` replaces itself
  with `/`, so the token doesn't stay in the window's history;
- quits when the shell closes its stdin (the shell exited or died): it removes its instance file,
  as a normal exit does;
- with a MellowDLP already running for this account (the single-instance guard,
  `_running_instance()`), it prints that copy's launch URL followed by ` attached` and exits 0.

One Windows trap found on the way: a child process that inherits a pipe as stdin while another
thread is blocked reading that pipe hangs at start until the read ends. yt-dlp starts ffmpeg/deno
when analyzing, so ANALYZE hung until the window closed. `--shell` therefore reads a duplicate of
the pipe and points stdin itself at the null device (`main._detach_stdin`).

**`src-tauri/`**, a Tauri v2 app (product name MellowDLP, `assets/mellow.ico`):

- shows `src-tauri/ui/index.html` ("Starting MellowDLP…") and spawns `python main.py --shell`
  (repo root = `MELLOW_ROOT`, else the folder above `src-tauri`; interpreter = `MELLOW_PYTHON`,
  else `python`), without a console window;
- reads the ready line and navigates the window to the launch URL; if the backend dies first,
  the window says so;
- the window is 1100×780 like today's: Chrome's `--window-size` is the whole window, Tauri's size
  is the page area, so the page area is shrunk by the frame (page 1084×741 at 100 %, as in Chrome);
  title MellowDLP, and the page's title (`▼ 42% — MellowDLP` while downloading) follows into the
  title bar and taskbar like the `--app` window;
- closing the window closes the backend's stdin, waits up to 3 s, then kills whatever is left.
  The backend runs in a Windows **job object** with KILL_ON_JOB_CLOSE, so its children (ffmpeg,
  deno…) die with it, and if the shell itself crashes or is killed, Windows ends the whole tree
  (Unix: the backend leads its own process group, killed with `killpg`; not tested here);
- `tauri-plugin-single-instance`: a second launch of the Tauri app focuses the open window;
- the window may only go to the bundled page and 127.0.0.1/localhost; new-window requests are
  refused (there's one `target="_blank"` link, in the signed-out screen);
- Tauri's own drag-and-drop handler is off (`disable_drag_drop_handler`): with it on, Windows never
  gives the page drop events, and the app uses them (a link dropped anywhere, files on the Vault);
- no Tauri IPC is exposed: the remote page has no capabilities, the bundled page needs none;
- `MELLOW_TIMING_LOG=<file>` appends `shell_start` / `backend_spawned` / `ready` / `navigated`
  timestamps (epoch ms), for the numbers below.

Tests: `tests/test_main_window.py` (the ready line comes after the server is bound, signs a window
in once, a second `--shell` attaches with the running copy's secret, stdin EOF quits) and
`tests/browser/test_shell_process.py` (marker `browser`: the real `python main.py --shell` with a
throwaway home: ready line, `/launch` once then 403, an ANALYZE that starts ffmpeg, a second
launch that attaches, stdin closed → exit 0 and no instance file).

## How to run it

```bash
python build_setup.py --frontend-only          # static/, as for any run from source
cd src-tauri
npx @tauri-apps/cli@2 dev                      # or: cargo run
```

`tauri dev` / `cargo run` build the debug shell and start it; it starts the backend itself.
Release binary (just the shell; it still runs the backend from source):

```bash
cd src-tauri
npx @tauri-apps/cli@2 build                    # → src-tauri/target/release/mellowdlp-shell.exe
```

`bundle.active` is `false`: no installer is made in this trial. The Tauri CLI wasn't added to the
root `package.json` (`npx` fetches it). Rust (stable) and, on Windows, the WebView2 runtime
(part of Windows 11) are needed; on Linux the `webkit2gtk-4.1` development packages.

To try it without touching your own config, database and downloads, start it with a throwaway
home, as the checks below did (PowerShell):

```powershell
$env:USERPROFILE = "$env:TEMP\mellow-trial"; $env:LOCALAPPDATA = "$env:USERPROFILE\AppData\Local"
.\src-tauri\target\release\mellowdlp-shell.exe
```

(For `tauri dev` / `cargo run` with such a home, also set `RUSTUP_HOME` and `CARGO_HOME` to your
real `.rustup` / `.cargo` folders: rustup finds its toolchain through the home folder.)

The backend alone: `python main.py --shell` prints the ready line; open it in a browser within
60 s; Ctrl+Z, Enter (Windows) or Ctrl+D ends it.

## Checks

Every check ran in the Tauri window (debug build, then the release build for the numbers) with a
throwaway home, against a local media site (ffmpeg-made 12 s 640×360 clips, served slowly so
progress shows; no network). The page was driven over the DevTools protocol
(`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`: Playwright's
`connect_over_cdp` drives WebView2, so the existing browser tests could later run against the
Tauri window on Windows). Screenshots are pictures of the real window (`PrintWindow`).

| | Check | Result |
|---|---|---|
| ✅ | Feed loads, signed in | Launch page → `/launch` → `/`; status bar, stats, yt-dlp / FFmpeg / disk all filled |
| ✅ | Analyze + download, live progress over SSE | H.264/AAC mp4 and VP9/Opus webm, each analyzed and downloaded end to end. The progress panel moves (`▼ 42%`, speed, ETA) and the title bar follows. A second `EventSource` on `/api/progress` counted 17 events for one download: `starting`, `downloading`×n, `item_done`, `processing`, `item_saved`, `complete`, `queue_done` |
| ✅ | Vault: open a folder, play in the built-in player | The folder opens with ffmpeg thumbnails. ⋯ → *Preview in App*: **H.264/AAC mp4** and **VP9/Opus webm** both play (`readyState` 4, no error, 640×360, 78 frames decoded in 3 s, audio bytes decoded). `canPlayType`: H.264/AAC, VP9/Opus and AV1 all `probably` |
| ✅ | File download through the UI (Config → ⬇ BACKUP) | `mellowdlp_backup_<time>.zip` (the server's file name) lands in the Downloads folder without asking, as WebView2 does by default (its download flyout opens). An `on_download` handler could pick the folder or ask with a save dialog |
| ✅ | Native file/folder dialogs (Tk, unchanged) | Config → BROWSE opens Windows' folder picker, Feed → IMPORT FILE the file picker (`Text files (*.txt)`). Like today they are separate windows of the Python process, not owned by the app window |
| ✅ | Clipboard paste | Ctrl+V with the real keyboard into the link box works; the PASTE button (backend `/api/clipboard`, Tk) works |
| ✅ | Closing the window | Backend logs "the desktop shell closed: quitting", removes its instance file; shell gone in 0.4 s; 0 processes left over in every measured run |
| ✅ | Second launch | Tauri already open → the new process hands over to it (single-instance plugin) and exits; still one shell and one backend. Today's app (FlaskWebGUI) running → the Tauri window signs in to *that* copy (`attached`, the `--shell` process exits); closing the Tauri window leaves that copy running. The reverse (Tauri running, then today's app launched) is unchanged: main.py's guard opens a browser window on the running server |
| ⚠️ | Drag and drop of a link / of files | Tauri's handler is off so the page gets HTML5 drop events (Tauri docs: required on Windows). Not tried with a real drag from another app |
| ❌ | Desktop notifications (`new Notification`, Config opt-in) | `Notification.requestPermission()` answers `denied` at once, no prompt (asked from script; WebView2 leaves the permission to the host app and wry doesn't grant it). Today's Chrome window can ask. Needs `tauri-plugin-notification` or a permission handler |
| ⚠️ | External links | Refused (logged). Today they open a browser tab; `tauri-plugin-opener` would open them in the default browser |

Not checked: Linux and macOS (no machine), the Unix kill path, an installer (`bundle.active`
false), a first-ever start (WebView2 profile creation), Windows 10 without the WebView2 runtime.

Screenshots were kept outside the repo (a `shots` folder in the system temp folder; the trial
report lists the full paths): `00_flaskwebgui_chrome_feed.png` (today's window, for size), `01_tauri_feed.png`,
`02_tauri_ctrl_v_paste.png`, `03_tauri_analyzed.png`, `03_tauri_downloading.png`,
`03_tauri_complete.png`, `04_tauri_vault_folder.png`, `04_tauri_vault_play_mp4.png`,
`04_tauri_vault_play_webm.png`, `05_tauri_backup.png`, `06_tauri_tk_folder_dialog.png`,
`06_tauri_tk_file_dialog.png`, `07_tauri_attached_to_flaskwebgui_copy.png`,
`08_tauri_notification_permission.png` (the release build's window: 1100×780, page 1084×741).

## Numbers

Both from source with the same Python and the same throwaway home; Tauri = release shell; today =
`main.py` with FlaskWebGUI, which picks **Chrome** on this machine (Chrome 157, its own temporary
profile). Each: one unrecorded warm-up run, then 3 runs. Times are from the moment the launcher
started the process; "first data" is when the page's first `/api/` answer arrived
(`performance.timeOrigin + responseEnd`, read over DevTools after the page settled). Memory is the
whole process tree 12 s after launch (`Get-Process`, working set summed: shared pages count once
per process, so it overstates both a little).

| | Tauri (WebView2) | Today (Chrome `--app`) |
|---|---|---|
| Shell process started | 21 / 21 / 21 ms | — |
| `MELLOW_READY` (server listening) | 1555 / 1671 / 1602 ms | — |
| First data in the page | **1727 / 1848 / 1796 ms** | **1823 / 2014 / 2021 ms** |
| Same, after the previous run was closed with the window's X | 3894 ms (1 run, see below) | **3823 / 3914 / 3938 ms** |
| Working set, whole tree | **558.5 / 561.4 / 559.2 MB** | **804.5 / 682.6 / 686.8 MB** |
| Private bytes, whole tree | 721.8 / 729.1 / 731.0 MB | 854.4 / 782.4 / 788.8 MB |
| Processes | 9: shell 25 MB, msedgewebview2 ×6 372 MB, python 154 MB, conhost 8 MB | 12–14: chrome ×10–12 518 MB, python 154 MB, conhost 10 MB |
| Shell binary | `mellowdlp-shell.exe` **3.07 MiB** (3,219,456 bytes; release, LTO, `opt-level = "s"`, stripped) | — (uses the installed browser) |

- Startup: about the same, Tauri ~0.2 s ahead (median 1.80 s vs 2.01 s). Python's start (imports,
  DuckDB, yt-dlp) is most of it in both.
- **Today's app loses ~2 s at every start after a normal close.** FlaskWebGUI ends the server with
  a kill (`kill_port` → SIGTERM, which is TerminateProcess on Windows), so atexit never removes the
  instance file; the next start probes the dead port, and on Windows a connection to a closed
  local port takes ~2 s to be refused (`INSTANCE_PROBE_TIMEOUT_SECS` is 2). The Tauri backend
  exits cleanly and removes its file, so its next start doesn't pay that (the 3894 ms run followed
  a Chrome run). Fixable today too (remove the file in FlaskWebGUI's `on_shutdown`, or probe with a
  shorter connect timeout).
- Memory: ~125 MB less with Tauri (−18 % working set), all on the browser side (~405 MB vs ~528 MB);
  the Python backend is 154 MB either way. WebView2 shares its binaries with Edge, which is
  usually running anyway.
- Size: the shell adds ~3 MB. Today's builds add nothing for the window (Chrome/Edge must be
  installed). The backend's PyInstaller build stays what it is.

## What Tauri gives us next

All Tauri v2, Rust crate / JS package:

| Want | Tauri v2 | Notes |
|---|---|---|
| Native dialogs instead of Tk | `tauri-plugin-dialog` / `@tauri-apps/plugin-dialog` (open, save, folder, message) | Two ways in: the page calls it (needs IPC for a remote URL: a capability with `remote.urls: ["http://127.0.0.1:*"]`), or the backend asks the shell over the pipe it already has (`DIALOG {...}` line out, answer in) and `gui/` doesn't change. The second keeps IPC off the page. Drops Tk from the build, and the dialogs get owned by the window |
| Save-as for downloads (backup, exports) | `on_download` on the webview builder (+ `tauri-plugin-dialog`) | Pick the destination or ask |
| Drag and drop | Built in: `DragDropEvent` (`onDragDropEvent` in JS), `dragDropEnabled` | Gives full file paths (the HTML5 drop gives only names). Turning it on turns HTML5 drops off on Windows: move both drop handlers at once |
| Tray icon (keep downloading with the window closed) | Built in: `tray-icon` feature, `TrayIconBuilder` + `tauri::menu` | Close-to-tray changes the "close = quit" rule; the job object makes either safe |
| Single instance | `tauri-plugin-single-instance` (used here) | Could replace main.py's guard once Tauri is the only launcher; with `deep-link` it passes on `mellowdlp://` links |
| Self-update | `tauri-plugin-updater` / `@tauri-apps/plugin-updater` | Signed update manifests (its own minisign key). Would replace `app_update.py`'s installer swap; the Python sidecar is inside the bundle, so one update moves both |
| Open files, folders, links | `tauri-plugin-opener` (`open_url`, `open_path`, `reveal_item_in_dir`) | Replaces desktop.py's explorer/xdg-open/open calls and fixes external links |
| Clipboard | `tauri-plugin-clipboard-manager` | Replaces Tk's clipboard |
| Notifications | `tauri-plugin-notification` | Desktop notifications that work in the webview |
| Remember window size/place | `tauri-plugin-window-state` | |
| Start with the system | `tauri-plugin-autostart` | For scheduled "later" downloads |
| Spawning the sidecar | `tauri-plugin-shell` (`Command::sidecar`) | std::process is enough (this trial); the plugin adds nothing we need except the sidecar path lookup |

## Risks

**Linux video (WebKitGTK + GStreamer).** WebKitGTK plays `<video>` through GStreamer; what it can
decode is what the system's plugins can. For the Vault's player:

| Needed for | Debian / Ubuntu | Fedora | Arch |
|---|---|---|---|
| playback pipeline, audio/video convert, Opus, typefind | `gstreamer1.0-plugins-base` | `gstreamer1-plugins-base` | `gst-plugins-base` |
| mp4 (`qtdemux`), webm/mkv (`matroskademux`), VP8/VP9 (`vpxdec`), PulseAudio/autoaudiosink | `gstreamer1.0-plugins-good` (+ `gstreamer1.0-pulseaudio` on older releases) | `gstreamer1-plugins-good` | `gst-plugins-good` |
| **H.264 and AAC decoding** (most YouTube mp4/m4a) | `gstreamer1.0-libav` | `gstreamer1-plugin-libav` (RPM Fusion's for full codecs) or `gstreamer1-plugin-openh264` + `gstreamer1-plugins-bad-free` | `gst-libav` |
| parsers some streams need (`h264parse`), AV1 (`dav1d`) | `gstreamer1.0-plugins-bad` | `gstreamer1-plugins-bad-free` | `gst-plugins-bad` |
| GL video sink WebKit renders through | `gstreamer1.0-gl` | (in plugins-base) | (in gst-plugins-base) |

Without `libav`, H.264/AAC files show nothing (WebKit reports a decode error); hardware decoding
(VA-API) isn't used by WebKitGTK, so it's software decoding. How the packages would carry it:

- **AppImage**: `bundle.linux.appimage.bundleMediaFramework: true` copies GStreamer and the
  plugins present on the build machine into the AppImage (+15–35 MB). The build machine must have
  `plugins-base`/`good`/`libav` installed. Bundling `libav` puts FFmpeg's H.264/AAC decoders in
  our download (patent questions in some countries; the same FFmpeg we already tell users to
  install, but now we'd ship it).
- **deb**: `bundle.linux.deb.depends: ["gstreamer1.0-plugins-base", "gstreamer1.0-plugins-good",
  "gstreamer1.0-libav", "gstreamer1.0-gl"]` (and `recommends` for `plugins-bad`); the
  distribution brings the codecs. `packaging/build_linux_deb.py` would add the same.
- **rpm** (if ever): `bundle.linux.rpm.depends`; Fedora's H.264 needs RPM Fusion or OpenH264.

The Chrome `--app` window has none of this: Chrome brings its own decoders. On Windows WebView2
uses the same decoders as Edge (H.264/AAC/VP9/Opus/AV1 all played here); on macOS WKWebView plays
H.264/AAC everywhere and VP9/Opus webm only on recent macOS versions (Safari 14.1/15 era): check
the oldest macOS we'd support.

**SSE in WebKitGTK.** `EventSource` is long supported by WebKit; the app's stream is plain
`text/event-stream` over HTTP/1.1 to 127.0.0.1, which WebKit handles like Safari. Two things to
check on a real Linux box: (1) the per-host connection limit (6) is shared by the SSE stream,
video streams and thumbnails, as in Chrome today; (2) the session guard lets `/api/progress`,
video and thumbnails through on the cookie with `Sec-Fetch-Site: same-origin` *or no header*
(`server._session_guard`), so a WebKitGTK that doesn't send Fetch Metadata still works. The
cross-site navigation from the bundled page (`tauri://localhost`; `http://tauri.localhost` on
Windows) to `/launch` is allowed on purpose. A browser test run against `webkit2gtk` (or Playwright's WebKit as a stand-in) is the
cheap way to find out.

**Packaging the Python backend as a sidecar.** Tauri's `bundle.externalBin` takes binaries named
`<name>-<target triple>` (e.g. `mellow-backend-x86_64-pc-windows-msvc.exe`); a PyInstaller
**one-folder** build is a folder, not one binary. Options: (a) `externalBin` points at the
folder's launcher exe and the rest of `_internal/` goes in `bundle.resources` (the launcher finds
it next to itself only if both land in the same directory: check Tauri's resource layout per
platform; on macOS resources go to `Contents/Resources`, sidecars to `Contents/MacOS`); (b) a
one-file PyInstaller build as the sidecar (simple, but unpacks itself at every start: ~2.5×
slower than one-folder, as the spec notes); (c) ship the one-folder build as resources and spawn
its exe by path (no `externalBin`). (c) is likely simplest. Either way the Python process remains
~150 MB and its start time is most of the startup; Tauri doesn't change that. The shell also
needs a "packaged" mode: spawn the sidecar instead of `python main.py`. Auto-update of yt-dlp
(the overlay zip in the home folder) is unaffected.

**Code signing.** Today's unsigned Python exe already meets SmartScreen; Tauri adds a second exe
(the shell) and its installer. Windows: Tauri signs during `tauri build` with
`bundle.windows.certificateThumbprint` / `signCommand` (Azure Trusted Signing works through
`signCommand`); the sidecar and every exe in the one-folder build should be signed too, or
antivirus heuristics hit the unsigned Python exe the signed shell starts. macOS: Developer ID +
notarization are required for a downloaded app; every binary inside (the PyInstaller sidecar and
its `.so`/`.dylib` files) must be signed with the hardened runtime, and Python may need the
`allow-unsigned-executable-memory` / `disable-library-validation` entitlements. Linux: none
needed (AppImage can carry a GPG signature). The Tauri updater needs its own signing key pair
(separate from code signing) and its private key in CI secrets.

**Smaller ones.** WebView2 must exist (Windows 11 and up-to-date Windows 10 have it; the Tauri
installer can bootstrap it: `bundle.windows.webviewInstallMode`). The page-area size now depends
on our code, not Chrome's flag (done here). `tauri.localhost` → `127.0.0.1` navigation means the
bundled page and the app are different origins; nothing is shared between them, by design.

## Recommendation

**Go**, in steps. On Windows the trial window does what today's window does (sign-in, SSE,
downloads, both video formats, file downloads, dialogs, paste, single instance) with ~125 MB
less memory, about the same startup, a 3 MB shell, and a process tree that can't outlive it.
It needed one backend flag and no UI change. Two gaps to close before shipping it: desktop
notifications (denied in WebView2 until the shell handles them) and external links (refused
until the shell opens them in the browser), both one plugin each. What it buys later (native dialogs, tray, real
drag-and-drop paths, a signed updater, no dependence on an installed Chrome/Edge, which is today's
"no Chromium browser → default browser tab" fallback) is the real gain. The cost is on Linux
(GStreamer codecs to depend on or bundle) and in packaging (sidecar layout, signing two kinds of
binaries).

Steps for "full Tauri":

1. Keep `--shell` as the backend's contract; give the shell a packaged mode that spawns the
   PyInstaller one-folder backend (resources, spawned by path) instead of `python main.py`;
   `MELLOW_ROOT`/`MELLOW_PYTHON` stay for development.
2. `build_setup.py`: build the backend one-folder, then `tauri build` with bundles on (NSIS on
   Windows to replace Inno Setup, AppImage + deb on Linux, dmg/app on macOS). Keep the
   `APP_ASSET_NAMES` contract or migrate installed copies with one last release of the old updater.
3. Linux: `deb.depends` as above; AppImage with `bundleMediaFramework` (decide on bundling
   `libav`); run the browser tests against WebKitGTK in CI (`xvfb`), including the Vault player
   with an H.264 and a webm file.
4. Move OS integration to the shell, one at a time, over the stdin/stdout channel (no IPC on the
   page): dialogs (`plugin-dialog`, drop Tk), open/reveal (`plugin-opener`), clipboard
   (`plugin-clipboard-manager`), notifications (`plugin-notification`), save-as for downloads
   (`on_download`).
5. Replace `app_update.py`'s installer swap with `tauri-plugin-updater` (signed manifest on GitHub
   releases); keep yt-dlp's overlay update as is.
6. Signing: Windows (Trusted Signing via `signCommand`, the sidecar's exes included), macOS
   (Developer ID + notarization, hardened runtime for the Python parts).
7. Then the extras: tray (close to tray while downloading), `window-state`, `autostart`,
   `deep-link` (`mellowdlp://` from a browser extension).
8. Retire FlaskWebGUI and main.py's own window code once every platform ships the Tauri build;
   keep `--no-window` for headless use and the smoke test.
