# Tauri trial

Does a Tauri window work for MellowDLP, and what does it cost and gain compared with today's
FlaskWebGUI window (Chrome/Edge started with `--app`)? Flask and the React UI stay as they are.
This trial ran on Windows 11 (WebView2 157, Chrome 157), Python 3.14, Rust 1.99, Tauri 2.12;
a second run on Linux (Ubuntu 24.04, WebKitGTK 2.52, GStreamer 1.24) is in [Linux run](#linux-run).

- [What was built](#what-was-built)
- [How to run it](#how-to-run-it)
- [Checks](#checks)
  - [Linux run](#linux-run)
  - [Packaged mode](#packaged-mode)
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

- shows `src-tauri/ui/index.html` ("Starting MellowDLP…") and starts the backend with `--shell`,
  without a console window (`backend.rs`): the installed app runs the PyInstaller build it carries
  (`backend/mellowdlp-backend[.exe]` in its resources, see [Packaged mode](#packaged-mode)); from a
  checkout it runs `python main.py --shell` (repo root = `MELLOW_ROOT`, else the folder above
  `src-tauri`; interpreter = `MELLOW_PYTHON`, else `python`). `MELLOW_BACKEND=<exe>` runs a built
  backend with any shell (e.g. the debug one). The backend gets `MELLOW_SHELL=tauri`;
- reads the ready line and navigates the window to the launch URL; if the backend dies first,
  the window says so;
- the window is 1100×780 like today's: Chrome's `--window-size` is the whole window, Tauri's size
  is the page area, so the page area is shrunk by the frame (page 1084×741 at 100 %, as in Chrome);
  title MellowDLP, and the page's title (`▼ 42% — MellowDLP` while downloading) follows into the
  title bar and taskbar like the `--app` window;
- closing the window closes the backend's stdin, waits up to 3 s, then kills whatever is left.
  The backend runs in a Windows **job object** with KILL_ON_JOB_CLOSE, so its children (ffmpeg,
  deno…) die with it, and if the shell itself crashes or is killed, Windows ends the whole tree
  (Unix: the backend leads its own process group, killed with `killpg`; checked on Linux, and
  if the shell itself is killed the backend ends that group on its way out, see [Linux run](#linux-run));
- `tauri-plugin-single-instance`: a second launch of the Tauri app focuses the open window;
- the window may only go to the bundled page and 127.0.0.1/localhost. Any other `http(s)` or
  `mailto` link, followed or opened in a new window (`target="_blank"`, `window.open`), goes to the
  default browser through `tauri-plugin-opener` (`open_url`, called from Rust); other schemes
  (`file:`, `javascript:`, `ftp:`, custom ones) and a new window for the app itself are refused and
  logged (`route()` in `links.rs`, with unit tests). See [Links and notifications](#links-and-notifications-69);
- desktop notifications: the shell answers the page's permission requests (`on_permission_request`):
  **Notifications → allow, only for the backend's page (its exact origin, port included, taken
  from the ready line: another service on 127.0.0.1 is denied); everything else (camera,
  microphone, location, clipboard read…) → deny**. Each time the backend's page has loaded, the shell runs
  `Notification.requestPermission()` in it, so `Notification.permission` is `granted` from the
  first load (the engine forgets a grant when the app exits, and the port, part of the origin,
  changes every launch). Config → Desktop Notifications still decides whether the page notifies;
- Tauri's own drag-and-drop handler is off (`disable_drag_drop_handler`): with it on, Windows never
  gives the page drop events, and the app uses them (a link dropped anywhere, files on the Vault);
- no Tauri IPC is exposed: the remote page has no capabilities, the bundled page needs none.
  The opener plugin's click script is turned off (`open_js_links_on_click(false)`): it sends
  `target="_blank"` links to the plugin's IPC command, which the page can't call, so with it on
  those clicks did nothing at all;
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

`bundle.active` is `false` in `tauri.conf.json`, so `cargo build` / `cargo test` never need a
backend build. Rust (stable) and, on Windows, the WebView2 runtime (part of Windows 11) are
needed; on Linux the `webkit2gtk-4.1` development packages. The installable app:

```bash
python build_setup.py --tauri    # → dist/tauri/: MellowDLP_<v>_x64-setup.exe (Windows), .AppImage + .deb (Linux)
```

It builds the backend with PyInstaller as for today's app, then `tauri build` with
`src-tauri/tauri.bundle.conf.json` (bundles on, the backend as resources) and the version from
`mellow/version.py`. The Tauri CLI is pinned in `package.json` (`@tauri-apps/cli`, installed by
`npm ci`). See [Packaged mode](#packaged-mode).

Linux (Debian/Ubuntu), from the repo root:

```bash
sudo apt-get install libwebkit2gtk-4.1-dev build-essential libssl-dev libayatana-appindicator3-dev librsvg2-dev \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl
(cd src-tauri && cargo build --release)       # → src-tauri/target/release/mellowdlp-shell
HOME=/tmp/mellow-trial MELLOW_PYTHON=$PWD/.venv/bin/python ./src-tauri/target/release/mellowdlp-shell
```

The single-instance plugin talks over the D-Bus session bus, which every desktop session has; a
bare X server (Xvfb) needs one started (`dbus-run-session`), or a second launch opens a second
window (see [Linux run](#linux-run)).

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

| | Check | Windows 11 (WebView2) | Linux (WebKitGTK) |
|---|---|---|---|
| ✅ | Feed loads, signed in | Launch page → `/launch` → `/`; status bar, stats, yt-dlp / FFmpeg / disk all filled | ✅ Same: launch page → `/launch` → `/`, status bar filled (yt-dlp, FFmpeg OK, disk) |
| ✅ | Analyze + download, live progress over SSE | H.264/AAC mp4 and VP9/Opus webm, each analyzed and downloaded end to end. The progress panel moves (`▼ 42%`, speed, ETA) and the title bar follows. A second `EventSource` on `/api/progress` counted 17 events for one download: `starting`, `downloading`×n, `item_done`, `processing`, `item_saved`, `complete`, `queue_done` | ✅ A VP9/Opus webm from the slow local site, analyzed and downloaded. The progress panel moves (14 %, 55 KB/s, ETA 12 s) and the title bar follows: sampled every 0.25 s it went `▼ 0%`, `▼ 2%` … `▼ 97%`, `⚙ processing — MellowDLP`, `MellowDLP`; *Download Complete* toast with OPEN FILE / FOLDER. Nothing changed for WebKit |
| ✅ | Vault: open a folder, play in the built-in player | The folder opens with ffmpeg thumbnails. ⋯ → *Preview in App*: **H.264/AAC mp4** and **VP9/Opus webm** both play (`readyState` 4, no error, 640×360, 78 frames decoded in 3 s, audio bytes decoded). `canPlayType`: H.264/AAC, VP9/Opus and AV1 all `probably` | ✅ The folder opens with ffmpeg thumbnails (the cookie-only image route works). ⋯ → *Preview in App*: **H.264/AAC mp4** and **VP9/Opus webm** both play, started by the click with sound on (frames advance between screenshots). Codecs per package: [Linux run](#linux-run) |
| ✅ | File download through the UI (Config → ⬇ BACKUP) | `mellowdlp_backup_<time>.zip` (the server's file name) lands in the Downloads folder without asking, as WebView2 does by default (its download flyout opens). An `on_download` handler could pick the folder or ask with a save dialog | ⚠️ No file appeared anywhere after a click on ⬇ BACKUP. wry connects WebKitGTK's download signals only when the app sets `on_download`; not investigated further. Plan an `on_download` handler on Linux |
| ✅ | Native file/folder dialogs (Tk, unchanged) | Config → BROWSE opens Windows' folder picker, Feed → IMPORT FILE the file picker (`Text files (*.txt)`). Like today they are separate windows of the Python process, not owned by the app window | — not checked |
| ✅ | Clipboard paste | Ctrl+V with the real keyboard into the link box works; the PASTE button (backend `/api/clipboard`, Tk) works | — not checked |
| ✅ | Closing the window | Backend logs "the desktop shell closed: quitting", removes its instance file; shell gone in 0.4 s; 0 processes left over in every measured run | ✅ With ffmpeg running in the backend's group: shell, backend and ffmpeg gone in 1.4–1.9 s, instance file removed, 0 processes left. Shell killed with SIGKILL: the backend quit, but **its ffmpeg kept running** until the fix in this run (`main._end_own_group`); now all gone in ~2 s |
| ✅ | Second launch | Tauri already open → the new process hands over to it (single-instance plugin) and exits; still one shell and one backend. Today's app (FlaskWebGUI) running → the Tauri window signs in to *that* copy (`attached`, the `--shell` process exits); closing the Tauri window leaves that copy running. The reverse (Tauri running, then today's app launched) is unchanged: main.py's guard opens a browser window on the running server | ✅ With a D-Bus session bus: the new process exits 0 in 55 ms, the first window comes back from minimized and takes focus; one shell, one backend. ⚠️ Without one (bare Xvfb) the plugin can't hand over: a second window opens, signed in to the running backend through main.py's guard |
| ⚠️ | Drag and drop of a link / of files | Tauri's handler is off so the page gets HTML5 drop events (Tauri docs: required on Windows). Not tried with a real drag from another app | — not checked |
| ⚠️ | Desktop notifications (`new Notification`, Config opt-in) | Before #69: `Notification.requestPermission()` answered `denied` at once, no prompt (WebView2 leaves the permission to the host app and wry didn't grant it). #69's permission handler answers WebView2's `PermissionRequested` the same way as on Linux (built and type-checked for `x86_64-pc-windows-msvc`); **not yet run on Windows** | ✅ A finished download with the window minimized and Config's toggle on: the app's own `new Notification` reached the notification daemon (`Notify` "Download complete" / "clip" on D-Bus). `Notification.permission` is `granted` right after every launch, without a click; geolocation is denied. [Details](#links-and-notifications-69) |
| ✅ | Installed app (NSIS installer) | `MellowDLP_2.14.2_x64-setup.exe` installed silently; started with a throwaway home and **no Python, ffmpeg or node on `PATH`**: shell, `mellowdlp-backend.exe`, 6 WebView2 processes, no python.exe; signed in, a clip analyzed and downloaded with live progress (`▼ 22%` → `▼ 80%` → `⚙ processing`); the window's X → shell gone in 0.09 s, nothing left after 0.5 s, instance file removed. [Packaged mode](#packaged-mode) | 🔧 Built and smoke-tested in CI (`tauri.yml`, ubuntu-22.04): AppImage + deb, the bundled backend started as the shell starts it. Not run in a window |
| ⚠️ | External links | Before #69: refused (logged). #69 opens them in the default browser through `tauri-plugin-opener`; same code on Windows, **not yet run there** | ✅ The signed-out screen's `target="_blank"` link opened `https://github.com/jenox645/Mellow/releases/latest` in the default browser; `mailto:`, links and `window.open` too; `file:`, `ftp:` and a new window for the app refused. [Details](#links-and-notifications-69) |

Not checked: macOS (no machine), #69's links and notifications on Windows, the Linux bundles in a window, a first-ever start
(WebView2 profile creation), Windows 10 without the WebView2 runtime; on Linux the rows marked —,
Wayland and a full desktop (GNOME, KDE): the Linux run used Xvfb with openbox.

Screenshots were kept outside the repo (a `shots` folder in the system temp folder; the trial
report lists the full paths): `00_flaskwebgui_chrome_feed.png` (today's window, for size), `01_tauri_feed.png`,
`02_tauri_ctrl_v_paste.png`, `03_tauri_analyzed.png`, `03_tauri_downloading.png`,
`03_tauri_complete.png`, `04_tauri_vault_folder.png`, `04_tauri_vault_play_mp4.png`,
`04_tauri_vault_play_webm.png`, `05_tauri_backup.png`, `06_tauri_tk_folder_dialog.png`,
`06_tauri_tk_file_dialog.png`, `07_tauri_attached_to_flaskwebgui_copy.png`,
`08_tauri_notification_permission.png` (the release build's window: 1100×780, page 1084×741).

### Linux run

Ubuntu 24.04 (cloud container, 4 vCPU, no GPU), Xvfb 1280×900 with openbox and a D-Bus session
bus, WebKitGTK 2.52.6 (`libwebkit2gtk-4.1-0`), GStreamer 1.24.2, Rust 1.97, Python 3.12. Every
package the doc asks for installed from apt without trouble: `libwebkit2gtk-4.1-dev build-essential
libssl-dev libayatana-appindicator3-dev librsvg2-dev`, `gstreamer1.0-plugins-base/good/bad`,
`gstreamer1.0-libav`, `gstreamer1.0-gl`.

**Build.** `cargo build --release` in `src-tauri/` → `mellowdlp-shell`, **4.19 MiB** (4,394,136
bytes; release, LTO, `opt-level = "s"`, stripped; 4.46 MiB with #69's opener plugin), 5 min from a cold cargo cache. Two fixes were
needed before it built at all, on any machine:

- `src-tauri/tauri.conf.json` had never been committed: the root `.gitignore` ignores `*.json`.
  `tauri::generate_context!()` needs it, so it is recreated from this doc (product name
  MellowDLP, version 2.14.2, `frontendDist: "ui"`, no windows in the config, `bundle.active` false,
  CSP off, no global Tauri object) and `.gitignore` now lets it through. The identifier
  (`io.github.jenox645.mellowdlp`) is a guess: replace the file with the original if it differs.
- Linux needs a PNG window icon (`failed to open icon …/icons/icon.png`): `src-tauri/icons/icon.png`
  is the 128 px image of `assets/mellow.ico`, listed before the `.ico` in `bundle.icon`.

**How it was driven.** WebKitGTK has no DevTools protocol, so the real window was used with the
real X input: `xdotool` for clicks and typing (and reading the window title), `import -window root`
for screenshots, `wmctrl -c` to close the window as a user does (the window manager's close),
`pgrep`/`ps` for the process tree. `tests/browser/test_shell_process.py` passes on Linux as it is.

**Video in the Vault player.** Both test files play in the real window (⋯ → *Preview in App*). The
package matrix was checked with a small PyGObject page in WebKit2 4.1, the same engine and the
same GStreamer: it plays both files and reports `readyState`, the error code and decoded frames
after 4 s (640×360, 25 fps).

| GStreamer packages present | H.264/AAC mp4 | VP9/Opus webm |
|---|---|---|
| base, good, bad, libav, gl | ✅ plays (Constrained Baseline and High profile) | ✅ plays |
| base, good, bad, gl (**no libav**) | ✅ plays, Baseline and High profile: `plugins-bad` on Ubuntu 24.04 has `openh264dec` and `faad` | ✅ plays |
| base, good, gl (no libav, no bad) | ❌ `MEDIA_ERR_SRC_NOT_SUPPORTED`, `canPlayType` "" | ✅ plays |

So `libav` *or* `plugins-bad` decodes H.264/AAC on Ubuntu 24.04; with neither, mp4/m4a files
don't play while webm does. Distributions that ship `plugins-bad` without OpenH264 (Fedora's
`-free`) need `libav` or OpenH264 explicitly. No sound device was there: WebKit still plays
(its audio sink falls back), so sound itself wasn't heard. One WebKit rule to know: `play()` with
sound and no click is refused (`NotAllowedError`); the Vault player starts on a click, so it plays.

**The kill path (Unix).** The backend is its own process-group leader. To have a child that
certainly runs at the moment of the close, the config's `external_downloader` was `ffmpeg` and the
file came from the slow site, so ffmpeg downloads in the backend's group while the window closes.

| | Before | After this run's fix |
|---|---|---|
| Close the window (window manager) | shell, backend, ffmpeg gone in 1.4–1.9 s; nothing left | same |
| `kill -9` the shell | backend quits (stdin EOF), instance file removed, **ffmpeg keeps running** (orphaned, still downloading) | backend, ffmpeg gone in ~2 s; nothing left |

The shell's `killpg` can't run when the shell is dead, and the backend's `os._exit` leaves its
children behind. `main._exit_with_parent` now ends with `_end_own_group()`: a backend that leads
its own group (the shell starts it so) kills that group as its last act, after removing its
instance file; one started from a terminal or a test shares its parent's group and leaves it alone.
Windows doesn't need it (the job object). Tests: `tests/test_main_window.py` (when it kills, when
not) and `tests/browser/test_shell_process.py` (a real backend as group leader and a process in
its group: stdin closed → both end).

**Other things seen on Linux.**

- **Window size:** `fit_outer_size` runs before the window is mapped, when X11 doesn't know the
  frame yet, so nothing is subtracted: the page area is 1100×780 and the window 1102×805 with
  openbox's frame (1, 1, 20, 5), a little larger than Chrome's 1100×780. Running it again once the
  window is shown would match.
- **Native `<select>`:** WebKitGTK draws selects with GTK's own light style (SORT BY in a vault
  folder, Browser Cookies in Config): a white box on the dark theme. Chrome and WebView2 follow
  the page's colours. A theme fix (`appearance: none` and our own arrow) belongs in `gui/`.
- **Second launch needs D-Bus:** `tauri-plugin-single-instance` uses the session bus on Linux.
  Every desktop session has one, so it's only a headless/CI concern; without it the second window
  still works, as a second window.

**Numbers (Linux).** Release shell, the same throwaway home, one unrecorded warm-up then 3 runs;
times from the launcher, memory 12 s after launch summed over the shell's process tree
(`/proc/<pid>/smaps_rollup`: PSS counts shared pages once).

| | Tauri (WebKitGTK) |
|---|---|
| Shell process started | 28 / 31 / 36 ms |
| `MELLOW_READY` (server listening) = window navigated | 539 / 540 / 506 ms |
| PSS, whole tree | 511 / 509 / 515 MB |
| RSS, whole tree | 686 / 684 / 690 MB |
| Processes | 4: shell 85 MB, WebKitWebProcess ~295 MB, WebKitNetworkProcess 25 MB, python 108 MB (PSS) |
| Shell binary | `mellowdlp-shell` 4.19 MiB; 4.46 MiB (4,675,512 bytes) with #69's `tauri-plugin-opener` |

Not comparable with the Windows numbers (another machine, no GPU: WebKit renders in software
under Xvfb, which inflates the web process). Today's Chrome window wasn't measured on Linux.

### Links and notifications (#69)

Linux only (same container and setup as the [Linux run](#linux-run), plus `dunst` as the
notification daemon on the session bus and `dbus-monitor` watching `org.freedesktop.Notifications`).
The default browser was a stand-in `xdg-open` first on `PATH` that logs what it is given, which is
also what `tauri-plugin-opener` calls on Linux.

**A test page first.** `MELLOW_ROOT` pointed at a stand-in backend (a `main.py` that serves one
page on 127.0.0.1 and prints the ready line), so every case could be clicked with `xdotool` in the
real window and read back from the window title:

| Click | Shell log | Default browser got |
|---|---|---|
| `<a href="https://…">` | opened … (a navigation); the window stays on the page | `https://example.com/nav` |
| `<a target="_blank" rel="noreferrer" href="https://…">`, the same without `rel`, `target="other"` | opened … (a new window) | each URL once |
| `window.open("https://…")` from a click | opened … (a new window) | the URL |
| `<a href="mailto:…">` | opened … (a navigation) | `mailto:someone@example.com` |
| `<a target="_blank" href="ftp://…">` | refused a new window to `ftp://…` | — |
| `<a target="_blank" href="/test.html#again">` (the app itself) | refused a new window to `http://127.0.0.1:…` | — |
| `<a href="file:///etc/hostname">` | nothing: WebKit itself refuses `file:` from an http page before asking the shell | — |
| `Notification.requestPermission()` + `new Notification` | permission Notifications for `http://127.0.0.1:…`: Allow | (D-Bus `Notify` "MellowDLP test") |
| `navigator.geolocation.getCurrentPosition` | permission Geolocation …: Deny | (`PERMISSION_DENIED`) |

Two findings on the way:
- **The opener plugin's own click script broke `target="_blank"`.** With `tauri_plugin_opener::init()`
  a click on an http(s) `_blank` link did nothing at all and the shell never heard of it: the
  plugin injects a click handler that sends those links to its `plugin:opener|open_url` command,
  and the page has no IPC. `Builder::new().open_js_links_on_click(false)` keeps that script out;
  the link then reaches `on_new_window` like any other.
- **A grant doesn't outlive the run.** After a restart `Notification.permission` was `default`
  again, and the app only notifies when it is `granted` (Config's toggle asks once). WebKitGTK's
  `initialize_notification_permissions` for the backend's origin made no difference: it reaches
  only web processes started after it, and the page's process already exists when the port is
  known. Asking `Notification.requestPermission()` from the shell once the backend's page has
  loaded works the same on both engines: right after each of 2 launches (each on a new port) the
  page read `granted` without a click, and a notification showed.

**The real app.** The real backend (`MELLOW_PYTHON` = a venv, throwaway home, config
`desktop_notifications: true`) in the debug shell:
- **Notifications.** The window was minimized and a 3 s H.264/AAC clip queued through the API
  (signed in from the instance file). The page's own `new Notification` arrived as D-Bus
  `Notify` "Download complete" / "clip" from `mellowdlp-shell`.
- **External links.** The signed-out screen (a stand-in backend that sends the window to `/`
  instead of `/launch`): a click on its link handed
  `https://github.com/jenox645/Mellow/releases/latest` to the default browser, and the window
  stayed. Closing the window left no backend running.
- **Windows.** Built and type-checked for `x86_64-pc-windows-msvc` (`cargo check`); the code has
  no per-platform part. Not run on Windows.

### Packaged mode

The installed app carries its own backend: the PyInstaller **one-folder** build (`dist/MellowDLP-app/`,
what today's installer installs) goes into the Tauri bundle as resources, and the shell starts its exe
by path (option (c) of the [risks](#risks)). No Python, no `externalBin`.

**Layout.** `build_setup.py --tauri` copies `dist/MellowDLP-app/` to `dist/MellowDLP-backend/` with
the exe renamed `mellowdlp-backend[.exe]` (one MellowDLP exe to start in the installed folder, and the
backend says what it is in the task manager); `tauri.bundle.conf.json` maps that folder to `backend/`:

| | Where the backend lands | Tauri's `resource_dir()` |
|---|---|---|
| Windows (NSIS, per user) | `%LOCALAPPDATA%\MellowDLP\backend\` next to `mellowdlp-shell.exe` | the exe's folder |
| Linux deb | `/usr/lib/MellowDLP/backend/` | `/usr/lib/MellowDLP` |
| Linux AppImage | `usr/lib/MellowDLP/backend/` inside the image | the same, mounted |
| macOS (from Tauri's docs, not built) | `MellowDLP.app/Contents/Resources/backend/` | `Contents/Resources` |
| `target/release/` (`tauri build` copies resources next to the binary) | `target/release/backend/` | the exe's folder |

**Which backend** (`Launch::resolve`, unit-tested): `MELLOW_BACKEND` > `MELLOW_ROOT`/`MELLOW_PYTHON`
(source) > the bundle's `backend/` > the checkout the shell was built from. Development is unchanged.

**The old updater.** In the bundle the backend's folder is writable and has no Inno uninstaller, so
`app_update.install_kind()` would have said "windows-portable" and swapped the backend's exe alone
for the FlaskWebGUI app's portable exe. With `MELLOW_SHELL=tauri` (set by the shell) a frozen backend
now answers "no self-update" and the page offers the release page, until the Tauri updater replaces
the whole bundle (`tests/test_app_update.py`).

**Linux packages.** deb: `depends` on `gstreamer1.0-plugins-base`, `-good`, `-libav`, `-gl`,
`recommends` `-plugins-bad` (the [risks](#risks)' table). AppImage: `bundleMediaFramework: true`, which
copies the build machine's GStreamer; `tauri.yml` installs base, good, bad and gl there, **not libav**
(on Ubuntu `plugins-bad` decodes H.264/AAC through OpenH264 and faad, see [Linux run](#linux-run)).
Bundling libav is the owner's call.

**Checked on Windows 11** (the installer, not the build folder): `dist/tauri/MellowDLP_2.14.2_x64-setup.exe /S`
into a scratch folder (5.4 s), then the installed shell started with a throwaway home (`USERPROFILE`,
`LOCALAPPDATA`, `APPDATA`, `TEMP`) and `PATH` = System32, Wbem and PowerShell only (no `python`,
`py`, `ffmpeg`, `node`, `deno` on it, asserted), the window driven over WebView2's DevTools port:

- process tree: `mellowdlp-shell.exe` → `mellowdlp-backend.exe` + 6 × `msedgewebview2.exe`; no python.exe;
- signed in (`/launch` → `/`), `/api/system` answered (app 2.14.2, yt-dlp 2026.10.26);
- a 12 s 640×360 H.264/AAC clip from a slow local site analyzed and downloaded: the progress panel
  moved and the title bar went `▼ 22%`, `▼ 43%`, `▼ 80%`, `⚙ processing`, `MellowDLP`; the file
  (1,206,263 bytes) in the throwaway `Downloads\MellowDLP`; the backend answered "no self-update"
  in its update check;
- the window's X (`WM_CLOSE`): the shell exited 0 after 0.09 s, no process of the run left after
  0.5 s, the instance file removed;
- `scripts/smoke_binary.py --shell dist/MellowDLP-backend/mellowdlp-backend.exe`: ready line, the
  launch link works once then 403, app and assets served, stdin closed → exit 0, instance file gone
  (CI runs the same on both systems).

Screenshots (`PrintWindow` of the real window, kept outside the repo): `10_tauri_packaged_feed.png`,
`11_tauri_packaged_analyzed.png`, `12_tauri_packaged_downloading.png`, `13_tauri_packaged_complete.png`.

**Found on the way.**

- **Install folder = data folder** (fixed since: the bundle's NSIS template installs to
  `%LOCALAPPDATA%\Programs\MellowDLP`, see TAURI_SWITCH.md). The per-user NSIS install went to `%LOCALAPPDATA%\MellowDLP`,
  which is also MellowDLP's own data folder (`datadir.py`: instance file, launch pages, API keys).
  It works: the uninstaller removes the files it installed and the folder only if empty, and the app
  only ever deletes its own `launch-*.html` there. Today's installer uses `%LOCALAPPDATA%\Programs\MellowDLP`;
  the switch decides (a custom NSIS template or hook).
- **Shortcuts.** The NSIS installer writes `Start Menu\Programs\MellowDLP.lnk` and `Desktop\MellowDLP.lnk`,
  the names today's installer uses: installed next to today's app, it takes those shortcuts over
  (seen on the test machine; put back by hand). Its uninstaller removes a shortcut only when it points
  at its own exe. Try the Tauri app on an account without today's app, or re-point the shortcuts.
- **The shell's file name** stays `mellowdlp-shell.exe`: NSIS's "is it running?" check looks for the
  main binary's name, and named `MellowDLP.exe` it would find (and offer to close) today's app.
- **The icon** is the mascot's line art (`assets/mellow.ico`): at 16 px in the title bar and taskbar
  it reads as grey noise. Today's Chrome window shows the same icon as its favicon.

**Sizes** (Windows, this machine's build):

| | Tauri app | Today (FlaskWebGUI) |
|---|---|---|
| Installer | `MellowDLP_2.14.2_x64-setup.exe` **36.4 MB** (36,372,951 bytes; NSIS, LZMA) | `MellowDLP_Setup.exe` **35.3 MB** (35,272,593 bytes; Inno Setup, LZMA2 ultra) |
| Installed | 90.3 MB: backend 89 MB (1,128 files), shell 3.3 MB, uninstaller 0.2 MB | 89 MB |
| Shell | `mellowdlp-shell.exe` 3.34 MB (3,337,216 bytes) | — (uses the installed Chrome/Edge) |
| `build_setup.py` | `--tauri`: 4 min 13 s (PyInstaller 1 min, release shell 2 min 36 s from a warm cargo cache, NSIS) | — |

**Start times** (Windows 11, the same machine as the earlier numbers): today = the one-folder build
`dist/MellowDLP-app/MellowDLP.exe` (what today's installer installs; FlaskWebGUI picks Chrome), Tauri =
the installed app. Same throwaway home per kind, stripped `PATH`, one unrecorded warm-up, then 3
runs. Measured from the launch: *window* = the app's top-level window is on screen; *app screen* =
the first `PrintWindow` capture (polled every ~40 ms) that shows the app's own loading screen (its
cyan mascot and bar: the shell's splash and a blank browser window have none), the same test for
both windows; *first data* = the page's first `/api/` answer over DevTools (Tauri only: FlaskWebGUI's
Chrome has no DevTools port without changing the app); memory = working set of the whole process
tree 12 s after the launch.

| | Tauri app (installed) | Today, clean start | Today, after a normal close |
|---|---|---|---|
| Window on screen | **0.50 / 0.40 / 0.43 s** (the splash) | 1.06 / 1.08 / 1.21 s | 3.14 / 3.08 / 3.07 s |
| App screen | **1.69 / 1.43 / 1.89 s** | 1.97 / 2.05 / 2.05 s | 3.99 / — / 4.31 s |
| First data | 1.44 / 1.33 / 1.55 s | — | — |
| Working set, whole tree | **546 / 538 / 533 MB**, 8 processes (shell 28, WebView2 ×6 ~390, backend ~119) | 795 / 799 / 804 MB, 13 processes (Chrome ×12 ~680, backend 117) | 676 / 663 / 813 MB, 11–13 processes |

"Clean start" deletes the instance file FlaskWebGUI leaves behind (it ends its server with a kill),
which otherwise costs every later start a 2 s probe (see [Numbers](#numbers)); the Tauri backend exits
cleanly, so every Tauri start is a clean one. — = the capture missed it in that run. An earlier set
with a stricter colour threshold gave Tauri 1.49 / 1.64 / 1.49 s (app screen) and 1.42 / 1.41 / 1.42 s
(first data). The packaged backend is faster than the trial's `python main.py` (first data 1.4 s vs
1.8 s): the frozen build doesn't scan site-packages.

### Premium window

The window on Windows draws its own frame; the page still gets **no IPC**:

- **Title bar** (`gui/components/titlebar.jsx`, theme slot `TitleBar`, tokens `--titlebar-*`): the window has
  no system frame (`decorations(false)`; Tauri keeps the caption style for snap and the window animations, and
  resizes from the edges natively). The page's 32 px band is the drag region through CSS `app-region: drag`
  (wry turns on WebView2's non-client regions): drag, Windows snap and double-click to maximize are the
  system's own. Its three buttons go page → `/api/window` → backend → `MELLOW_EVENT window_op` → shell. The
  bottom rule draws on when the window opens and fills with the first download's progress. Its mark,
  like the tray icon, is Mellow herself: a small badge of the app icon's mascot (`scripts/make_icons.py`;
  an official badge dropped in `assets/tray-source.png` replaces it). Every theme sets its
  band (`--titlebar-bg`); Tactical's comes out orange on its own surface with no extra code.
  `/api/system` says `window_frame: "custom"`; on Linux and macOS the system frame stays (not checked frameless).
- **Splash**: the window's background is Classic's from the first frame (no white flash before a page paints);
  the bundled page **is Classic's loading screen** (the same mascots, fonts and animation, copied in by
  `build_setup.py`), and the page skips its own when it opens from it (`/launch?splash=1`): one loading
  screen, no restart. It drags the window; its two buttons are links the shell catches (`links::splash_op`).
- **Native dialogs**: BROWSE and IMPORT FILE ask the shell over the pipe (`shell.ask("dialog")` →
  `{"cmd": "answer"}`); it shows the system's dialog owned by the window (`rfd`, what tauri-plugin-dialog wraps,
  without the script that plugin puts in every page). Tk only without a shell.
- **Global shortcut** (Config → *Download the copied link*, default Ctrl+Alt+D, empty = off) and
  **`mellowdlp://download?url=<link>`** (the installer registers the scheme; the window comes up and the Feed
  analyzes the link, never a download by itself; one http(s) link only; a link sent before the page connects
  waits for it).
- Left out on purpose: Mica/acrylic (`window-vibrancy`) — the owner rejects glassmorphism and Classic's band is
  opaque by design; a theme could opt in later. File drops keep the page's HTML5 handler (link drops anywhere;
  Tauri's own handler would give file paths but turn link drops off on Windows).

Checked on the installed build (throwaway home, real mouse and keyboard input): dragging the band moved the
window by exactly the drag (120, 80 px), the right edge resized it, double-click maximized and restored, the three
buttons did what they say, BROWSE opened the system's folder dialog **owned by the window** (and a cancel came
back empty), the close button quit with nothing running; a `mellowdlp://` link started from the system brought
the Feed up with the link analyzed; Ctrl+Alt+D downloaded the copied link; uninstalling removed the scheme.
Screenshots (outside the repo): the band on Classic, Tactical and Classic Light, maximized, the splash, the
folder dialog, the Feed after a link.

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
| Open files, folders, links | `tauri-plugin-opener` (`open_url`, `open_path`, `reveal_item_in_dir`) | In since #69 for the page's external links (Rust side, its click script off). `open_path` / `reveal_item_in_dir` could replace desktop.py's explorer/xdg-open/open calls |
| Clipboard | `tauri-plugin-clipboard-manager` | Replaces Tk's clipboard |
| Notifications | `tauri-plugin-notification` | Not needed for the page: its own web notifications work once the shell answers the permission (#69). Only for notifications the backend would raise itself |
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

Measured on Ubuntu 24.04 ([Linux run](#linux-run)): `plugins-bad` alone (OpenH264 + faad) already
plays High-profile H.264/AAC; with neither it nor `libav`, mp4 doesn't play and webm does.
`libav` stays the dependency to name, as the decoder every distribution has.

The Chrome `--app` window has none of this: Chrome brings its own decoders. On Windows WebView2
uses the same decoders as Edge (H.264/AAC/VP9/Opus/AV1 all played here); on macOS WKWebView plays
H.264/AAC everywhere and VP9/Opus webm only on recent macOS versions (Safari 14.1/15 era): check
the oldest macOS we'd support.

**SSE in WebKitGTK.** `EventSource` is long supported by WebKit; the app's stream is plain
`text/event-stream` over HTTP/1.1 to 127.0.0.1, which WebKit handles like Safari. Two things to
check on a real Linux box (the [Linux run](#linux-run) saw live progress, thumbnails and video
work in WebKitGTK 2.52 with no change): (1) the per-host connection limit (6) is shared by the SSE stream,
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
It needed one backend flag and no UI change. The two gaps found here, desktop notifications
(denied in WebView2) and external links (refused), are closed in the shell (#69, no UI change):
checked on Linux, still to be run once on Windows. What it buys later (native dialogs, tray, real
drag-and-drop paths, a signed updater, no dependence on an installed Chrome/Edge, which is today's
"no Chromium browser → default browser tab" fallback) is the real gain. The cost is on Linux
(GStreamer codecs to depend on or bundle) and in packaging (sidecar layout, signing two kinds of
binaries).

Steps for "full Tauri":

1. ✅ Keep `--shell` as the backend's contract; give the shell a packaged mode that spawns the
   PyInstaller one-folder backend (resources, spawned by path) instead of `python main.py`;
   `MELLOW_ROOT`/`MELLOW_PYTHON` stay for development. Done: [Packaged mode](#packaged-mode).
2. ✅ `build_setup.py`: build the backend one-folder, then `tauri build` with bundles on (NSIS on
   Windows to replace Inno Setup, AppImage + deb on Linux, dmg/app on macOS). Done (`--tauri`);
   still to decide: keep the `APP_ASSET_NAMES` contract or migrate installed copies with one last
   release of the old updater, and the install folder (see [Packaged mode](#packaged-mode)).
3. Linux: `deb.depends` as above; AppImage with `bundleMediaFramework` (decide on bundling
   `libav`); run the browser tests against WebKitGTK in CI (`xvfb` and a D-Bus session bus),
   including the Vault player with an H.264 and a webm file. Also on Linux: an `on_download`
   handler (a click on ⬇ BACKUP saved nothing) and size the window after it is mapped.
4. Move OS integration to the shell, one at a time, over the stdin/stdout channel (no IPC on the
   page): dialogs (`plugin-dialog`, drop Tk), open/reveal (`plugin-opener`, already in for
   links), clipboard (`plugin-clipboard-manager`), save-as for downloads (`on_download`).
   Notifications need nothing more: the page's own `new Notification` works since #69.
5. Replace `app_update.py`'s installer swap with `tauri-plugin-updater` (signed manifest on GitHub
   releases); keep yt-dlp's overlay update as is.
6. Signing: Windows (Trusted Signing via `signCommand`, the sidecar's exes included), macOS
   (Developer ID + notarization, hardened runtime for the Python parts).
7. Then the extras: tray (close to tray while downloading), `window-state`, `autostart`,
   `deep-link` (`mellowdlp://` from a browser extension).
8. Retire FlaskWebGUI and main.py's own window code once every platform ships the Tauri build;
   keep `--no-window` for headless use and the smoke test.
