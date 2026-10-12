# Contributing to MellowDLP

Thanks for looking! Bug reports and ideas are welcome as [issues](https://github.com/jenox645/Mellow/issues/new/choose);
for a change, open a pull request (its template lists the checks to run).

- [Build from source](#build-from-source)
- [Development](#development)
- [Screenshots](#screenshots)
- [Releasing](#releasing)

## Build from source

Needs Python 3.12+ and Node.js 20+.

**Windows**: run `SETUP.bat` and pick:

1. Full installer: `dist\MellowDLP_Setup.exe`
2. App only: `dist\MellowDLP.exe` and a Desktop shortcut (it updates itself like the portable exe)
3. Frontend only: rebuilds `static\` in seconds, for UI work
4. Run tests

**Linux**:
```bash
git clone https://github.com/jenox645/Mellow
cd Mellow
bash setup.sh
./dist/MellowDLP
```

Or as a `.deb` (after `setup.sh`): `python3 packaging/build_linux_deb.py && sudo dpkg -i dist/mellowdlp_*.deb`. A `.deb` install is updated by installing the next `.deb`.

Both run `python build_setup.py`, which creates `.venv`, installs the pinned dependencies (`requirements.txt`, `requirements-build.txt`, `package-lock.json`), bundles the frontend with esbuild and packages the app with PyInstaller (plus Inno Setup for the Windows installer).

**Run without packaging** (`static/` is build output, so build the frontend once first):
```bash
python build_setup.py --frontend-only
python main.py               # in a window
python main.py --no-window   # just the server; open the printed URL in any browser
```
On Linux, `python3-tk` gives you the native BROWSE dialogs, and `xclip` the "copied a link?" suggestion.

---

## Development

| Layer | Tech |
|---|---|
| Backend | Python 3.12+, Flask, yt-dlp (Python API), DuckDB |
| Frontend | React 18 (UMD) in ES modules, bundled by esbuild; fonts bundled, no CDN |
| Window | [FlaskWebGUI](https://github.com/ClimenteA/flaskwebgui): a Chromium-based browser in app mode |
| Packaging | PyInstaller (`packaging/MellowDLP.spec`: one file and one folder), Inno Setup (`packaging/installer.iss`), appimagetool |

`main.py` starts the app, the backend is in `mellow/` (`server.py` is the routes only), the frontend source in `gui/`. [CLAUDE.md](../CLAUDE.md) is the detailed developer guide: architecture, events, and the rules the code keeps.

**Tests and lint**
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -m "not e2e and not slow and not browser"
ruff check .
npm ci
npm test            # frontend unit tests (node:test)
npm run lint        # ESLint
```

Tests never touch your real config, database or queue: every test runs in a temp folder.

- `python -m pytest tests/browser -m browser` clicks through the main flows (download, playlist, search, cancel, vault) in Chromium, downloading from a local test site. Needs the frontend built, ffmpeg, and `python -m playwright install chromium`.
- The `e2e` and `slow` markers download from real sites; run them by hand.
- `python scripts/canary.py` checks extraction against live sites; CI runs it weekly on the yt-dlp pre-release.

CI runs the Python, JavaScript and browser tests on every pull request; pull requests that touch packaging also build the Windows and Linux apps, smoke-test them, install GET FFMPEG for real, and update an old copy to the new build.

---

## Screenshots

The README's pictures come from `scripts/screenshots.py`: it runs the app on made-up demo data
(invented titles and generated cover art; nothing is downloaded), plays a playlist download through
to Mellow's celebration, and saves `assets/screenshots/*.png`, `celebration.gif` and `social-preview.png`
(upload that one under the repository's Settings → Social preview).

```bash
python build_setup.py --frontend-only
python scripts/screenshots.py      # needs Pillow, ffmpeg and Playwright's Chromium
```

---

## Releasing

1. Raise `APP_VERSION` in `mellow/version.py` (and the fallback `AppVersion` in `packaging/installer.iss`).
2. Add a `## X.Y.Z` section at the top of [CHANGELOG.md](../CHANGELOG.md), as `- **Title**: what it does` lines. CI fails without it; the app shows it after updating, and the GitHub release starts with it.
3. Merge the pull request. GitHub Actions builds the Windows installer, portable exe, Linux binary and AppImage, tests them, and publishes `vX.Y.Z` with `SHA256SUMS.txt`. Installed copies offer the update within hours.

Pushing a tag `vX.Y.Z` that matches `APP_VERSION` does the same by hand; a `-suffix` tag makes a pre-release.
