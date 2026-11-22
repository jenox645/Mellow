# Switching the shipped app to Tauri — the plan

What it takes for the Tauri app (`src-tauri/`, [TAURI_TRIAL.md](TAURI_TRIAL.md)) to replace the
FlaskWebGUI app as what a release ships, without stranding the copies already installed. A
proposal: nothing here changes `release.yml` or publishes anything yet. Decisions for the owner are
marked **Decide**; things only the owner can do are marked **Owner**.

## Where the Tauri app is

- Packaged (#99): the PyInstaller one-folder backend inside the bundle; `build_setup.py --tauri`
  makes the NSIS installer (Windows) and the AppImage + deb (Linux); checked as an installed app on
  Windows, built and smoke-tested on Linux by `tauri.yml`.
- Tray and daily sync (#100): close to the tray, tray menu, taskbar progress, start with the system,
  a daily sync at a time of day with the window closed, notifications from the tray.
- Still to come: the premium window (custom title bar, native splash and dialogs, deep links, a
  global shortcut), macOS (never built: no machine), a run in a real Linux desktop (only Xvfb so far).

## 1. Release assets: the names are an API

Installed copies find their update by asset name (`constants.APP_ASSET_NAMES`, checked against
`release.yml` by `tests/test_app_update.py`):

| Kind (`app_update.install_kind`) | Asset today | How an installed copy updates |
|---|---|---|
| `windows-installer` | `MellowDLP-{v}-windows-setup.exe` (Inno Setup) | runs it with Inno's flags: `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /LOG=…` |
| `windows-portable` | `MellowDLP-{v}-windows-portable.exe` | swaps its own exe (`<exe>.new`) |
| `appimage` | `MellowDLP-{v}-x86_64.AppImage` | swaps the AppImage file |
| `linux-binary` | `MellowDLP-{v}-linux-x86_64` | swaps the binary |

What each would do if the same name carried the Tauri build:

- **windows-installer: breaks.** NSIS ignores Inno's flags, so the update would open the
  installer's wizard instead of a silent install; it installs into another folder
  (`%LOCALAPPDATA%\MellowDLP`, not `%LOCALAPPDATA%\Programs\MellowDLP`), leaves the Inno app
  installed, and takes over its Start-menu and desktop shortcuts (same names; seen in #99's check).
- **appimage: works.** The old updater swaps the file; the Tauri AppImage starts in its place, and
  from then on the Tauri updater takes over.
- **windows-portable, linux-binary: no Tauri equivalent.** Tauri makes installers, not one-file exes.
  A portable Tauri app is a folder (shell + `backend/`, WebView2 from the system), not one exe.

**Proposal:** give the Tauri builds **new names** and move installed copies over with a **bridge
release** of today's app:

| New asset (Tauri) | For |
|---|---|
| `MellowDLP-{v}-windows-app-setup.exe` | Windows (NSIS, per user) |
| `MellowDLP-{v}-x86_64.AppImage` (same name) | Linux AppImage (the old updater's swap works) |
| `mellowdlp_{v}_amd64.deb` | Debian/Ubuntu (installed by hand, as today's `.deb`) |
| `latest.json` + one `.sig` per bundle | the Tauri updater (below) |

**Decide:** keep publishing the FlaskWebGUI portable exe and Linux binary for a while (they keep
updating themselves), or retire them with a last release that tells their users to install the app.

## 2. The bridge release (today's app, one last time)

A normal FlaskWebGUI release (version N) whose updater knows the way to the Tauri app:

1. `APP_ASSET_NAMES` gains `windows-app-setup`; `install_kind()` for an Inno install
   (`windows-installer`) now updates to it when the release has it.
2. The helper that runs after the app exits (today: `Start-Process $MELLOW_SETUP …`) does, in order:
   - the **Inno uninstaller first**, silently (`unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`):
     it removes the old program and its shortcuts; config, database, downloads and the data folder
     are in the home folder and `%LOCALAPPDATA%\MellowDLP` and stay;
   - then the **NSIS installer**, silently (`/S`), which makes the new shortcuts (doing it the other
     way round, Inno's uninstaller would delete the shortcuts NSIS just made);
   - then starts the installed `mellowdlp-shell.exe`.
3. Tested like today's updates: `scripts/update_e2e.py` (a 0.0.1 build updated to a served 9.9.9
   Tauri build with `--feed`) and `release.yml`'s `update-windows` job.

AppImage users need nothing special. deb users install the new `.deb` (it replaces `mellowdlp`).

## 3. Self-update in the Tauri app: `tauri-plugin-updater`

The bundle is one install (shell + backend), so it must update as one: the backend's own updater
is already off in the bundle (#99: `MELLOW_SHELL=tauri` → release page).

- **Owner:** make the updater's key pair (`npx tauri signer generate -w mellowdlp-updater.key`),
  keep the private key and its password as repository secrets (`TAURI_SIGNING_PRIVATE_KEY`,
  `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`). The public key goes into `tauri.bundle.conf.json`
  (`plugins.updater.pubkey`). This key signs update files only; it is not code signing.
- Build: `bundle.createUpdaterArtifacts: true` makes a `.sig` per bundle; a release step writes
  `latest.json` (version, notes = the CHANGELOG section, per-platform URL + signature) and uploads
  it with the bundles; the endpoint is `https://github.com/jenox645/Mellow/releases/latest/download/latest.json`.
- In the app: the shell checks at launch and every 6 h (today's `APP_UPDATE_POLL_MS`), tells the
  backend over the pipe (`MELLOW_EVENT update_available`); the page shows today's offer (status
  bar, toast); UPDATE goes page → backend → shell (`{"cmd": "install_update"}`), which downloads,
  checks the signature, runs the NSIS installer in passive mode and restarts (Windows), or swaps the
  AppImage (Linux). Running downloads: the same "saved and offered again" rule as today.
- yt-dlp's own update (the overlay zip in the home folder) doesn't change.

## 4. `release.yml` (proposed jobs, not changed)

Next to today's jobs, until the switch, then instead of them:

- `windows-tauri`: `python build_setup.py --tauri`, `smoke_binary.py --shell` on the staged backend,
  an installed-app check (silent install, start with a throwaway home and no Python on `PATH`, sign in,
  close, nothing left: the script behind #99/#100's checks), the bundle + `.sig` as artifacts.
- `linux-tauri` (ubuntu-22.04, for the AppImage's glibc floor): the same with the AppImage and deb
  (`tauri.yml` already does the build and smoke test).
- `update-windows-tauri`: the bridge (section 2) end to end on a runner.
- `publish`: today's `SHA256SUMS.txt` and `attest-build-provenance` for the new files too, plus
  `latest.json`. The release gate (`scripts/release_gate.py`) is unchanged.

## 5. Signing

- **Decide / Owner:** Windows code signing (e.g. Azure Trusted Signing through
  `bundle.windows.signCommand`). It must sign every exe: the shell, `mellowdlp-backend.exe` and the
  installer; antivirus heuristics dislike an unsigned exe started by a signed one.
- macOS (when built): Developer ID + notarization, every Mach-O in `backend/` signed with the
  hardened runtime.

## 6. Install folder, shortcuts, data

- **Decide:** the install folder. NSIS per user installs to `%LOCALAPPDATA%\MellowDLP`, which is
  also MellowDLP's data folder (instance file, launch pages, API keys). It works (the uninstaller only
  deletes its own files), but `%LOCALAPPDATA%\Programs\MellowDLP` (today's) keeps program and data
  apart: it needs a custom NSIS template (`bundle.windows.nsis.template`) with that default.
- **Decide:** the installed shell's name: `mellowdlp-shell.exe` today. `MellowDLP.exe` reads better
  once the Inno app is gone (the bridge removes it first, so NSIS's "is it running?" check, which goes
  by name, no longer finds the old app).
- Data stays where it is (home folder, data folder): nothing to migrate. WebView2's own data is in
  `%LOCALAPPDATA%\io.github.jenox645.mellowdlp\EBWebView` (the uninstaller's "delete app data" box).

## 7. Order

1. Merge the premium window (phase 3) and settle the decisions above.
2. One release that ships the Tauri builds **next to** today's (new names, no updater path yet):
   people who want it install it by hand; everyone else is unchanged.
3. The updater key and `latest.json` in place; the Tauri app updates itself.
4. The bridge release: Inno installs move to the Tauri app; the AppImage follows by name.
5. Retire FlaskWebGUI: `main.py`'s window code, `packaging/installer.iss`, the one-file builds (keep
   `--no-window` for headless use and the smoke test).
