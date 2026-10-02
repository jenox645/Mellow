from __future__ import annotations

import base64
import json
import os
import platform
import py_compile
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STATIC = HERE / "static"
ASSETS = HERE / "assets"
GUI = HERE / "gui"

# The step banners use "·", "→" and "—". When output is piped (CI, an IDE
# run panel) Windows picks cp1252 and the first arrow crashes the build.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DESKTOP_SHORTCUT = "--desktop-shortcut" in sys.argv
# Fast dev loop: rebuild static/ (mascots, bundle, html) and skip pip,
# PyInstaller and the installer entirely.
FRONTEND_ONLY = "--frontend-only" in sys.argv
# Install deps into .venv and run the test suite instead of building.
RUN_TESTS = "--run-tests" in sys.argv
SYSTEM = platform.system()   # 'Windows' | 'Linux' | 'Darwin'
IS_WINDOWS = SYSTEM == "Windows"
IS_LINUX   = SYSTEM == "Linux"

from mellow.version import APP_VERSION as VERSION  # noqa: E402 — single version source

# Syntax-checked before packaging: the entry points plus the whole backend
PYTHON_FILES = ["main.py", "build_setup.py", *sorted(
    str(p.relative_to(HERE)) for p in (HERE / "mellow").glob("*.py"))]

# (file_stem_without_ext, js_var_name, use_svg)
# SVG files are embedded inline so CSS currentColor tinting works.
# PNG entries use _vector.png (transparent background).
MASCOT_ENTRIES = [
    ("dj_mellow_vector",          "MASCOT_DJ",             False),
    ("vibing_mellow_vector",      "MASCOT_VIBING",         False),
    ("chilling_mellow_vector",    "MASCOT_CHILLING",       True),
    ("frustrated_mellow_vector",  "MASCOT_FRUSTRATED",     True),
    ("tired_mellow_vector",       "MASCOT_TIRED",          True),
    ("comfy_mellow_vector",       "MASCOT_COMFY",          True),
    ("success_mellow_vector",     "MASCOT_SUCCESS",        True),
    ("troubleshooting_mellow_vector", "MASCOT_TROUBLESHOOTING", True),
    ("victory_mellow_vector",     "MASCOT_VICTORY",        True),
]

# Keep legacy name for backward compat with old code paths
MASCOT_NAMES = [(e[0], e[1]) for e in MASCOT_ENTRIES]


def step(msg: str) -> None:
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def fail(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    display = " ".join(str(c) for c in cmd)
    print(f"  $ {display}")
    if platform.system() == "Windows":
        # .cmd shims (npm, esbuild, pyinstaller) need shell=True on Windows;
        # list2cmdline quotes paths with spaces correctly.
        result = subprocess.run(subprocess.list2cmdline(cmd), shell=True, **kwargs)
    else:
        result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        fail(f"Command failed: {display}")
    return result


# ── Step 1: Python version check ──────────────────────────────────────────────
step("1/12 · Checking Python version")
major, minor = sys.version_info[:2]
if major < 3 or (major == 3 and minor < 9):
    fail(f"Python 3.9+ required, got {major}.{minor}")
print(f"  Python {sys.version.split()[0]} — OK")


# ── Step 1b: Re-exec inside the project venv ──────────────────────────────────
# Builds install/uninstall packages; doing that in the system Python pollutes
# (and step 2 even removes packages from) the global site-packages. Everything
# below therefore runs inside .venv/, created on first use.
VENV_DIR = HERE / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")

if not FRONTEND_ONLY and os.environ.get("MELLOW_BUILD_VENV") != "1":
    if Path(sys.prefix).resolve() != VENV_DIR.resolve():
        step("1b/12 · Preparing build virtualenv (.venv)")
        if not VENV_PYTHON.exists():
            print("  Creating .venv (first build only)...")
            r = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
            if r.returncode != 0 or not VENV_PYTHON.exists():
                fail("Could not create .venv — check that the 'venv' module is available")
        print(f"  Re-launching inside {VENV_PYTHON}")
        r = subprocess.run(
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
            env={**os.environ, "MELLOW_BUILD_VENV": "1"},
        )
        sys.exit(r.returncode)


# ── Test mode: install deps + pytest, run the suite, exit ─────────────────────
if RUN_TESTS:
    step("Running test suite")
    run([
        sys.executable, "-m", "pip", "install", "--upgrade", "--quiet",
        "-r", str(HERE / "requirements.txt"), "-r", str(HERE / "requirements-dev.txt"),
    ])
    result = subprocess.run([
        sys.executable, "-m", "pytest", "tests/", "-q",
        "-m", "not e2e and not slow",
    ], cwd=str(HERE))
    sys.exit(result.returncode)


# ── Step 2: Remove conflicting packages ───────────────────────────────────────
step("2/12 · Removing conflicting packages")
if FRONTEND_ONLY:
    print("  (frontend-only: skipped)")
else:
    for pkg in ["pywebview", "pythonnet", "proxy-tools", "bottle"]:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", pkg],
            capture_output=True,
        )
        print(f"  Removed (or not present): {pkg}")


# ── Step 3: Install required packages ─────────────────────────────────────────
step("3/12 · Installing dependencies")
if FRONTEND_ONLY:
    print("  (frontend-only: skipped)")
else:
    run([
        sys.executable, "-m", "pip", "install", "--upgrade",
        "-r", str(HERE / "requirements.txt"), "-r", str(HERE / "requirements-build.txt"),
    ])


# ── Step 4: Check Node.js ──────────────────────────────────────────────────────
step("4/12 · Checking Node.js")
node = shutil.which("node")
if not node:
    fail(
        "Node.js not found. Install from https://nodejs.org/ and restart your terminal.\n"
        "  Quick install: winget install OpenJS.NodeJS.LTS"
    )
result = subprocess.run([node, "--version"], capture_output=True, text=True)
print(f"  Node {result.stdout.strip()} — OK")


npm = shutil.which("npm")
if not npm:
    fail("npm not found — it comes with Node.js; reinstall Node.js from https://nodejs.org/")

# esbuild, ESLint and the React builds are pinned in package-lock.json.
# `npm ci` installs exactly those; it only runs when the lockfile changed.
NODE_MODULES = HERE / "node_modules"
_lock = HERE / "package-lock.json"
_installed = NODE_MODULES / ".package-lock.json"
if not _installed.exists() or _installed.stat().st_mtime < _lock.stat().st_mtime:
    run([npm, "ci", "--no-audit", "--no-fund"], cwd=str(HERE))
else:
    print("  node_modules matches package-lock.json — OK")
esbuild = str(NODE_MODULES / ".bin" / ("esbuild.cmd" if IS_WINDOWS else "esbuild"))
if not Path(esbuild).exists():
    fail(f"{esbuild} is missing — delete node_modules and run the build again")
_eb_cmd = subprocess.list2cmdline([esbuild, "--version"]) if IS_WINDOWS else [esbuild, "--version"]
result2 = subprocess.run(_eb_cmd, shell=IS_WINDOWS, capture_output=True, text=True)
print(f"  esbuild {result2.stdout.strip()} — OK")


# ── Step 5: Encode mascot images → static/mascots.js ─────────────────────────
step("5/12 · Encoding mascot images (vector editions)")
STATIC.mkdir(exist_ok=True)


def _patch_svg_for_css(svg_text: str) -> str:
    """Replace fill: #fff (white) → fill: currentColor inside embedded <style> blocks
    and on inline fill= attributes, so CSS color property controls the art color."""
    def _patch_style(m: re.Match) -> str:
        block = m.group(1)
        block = re.sub(r'fill\s*:\s*#(?:fff|ffffff|FFF|FFFFFF)\b', 'fill: currentColor', block)
        return f"<style>{block}</style>"

    svg_text = re.sub(r"<style>(.*?)</style>", _patch_style, svg_text, flags=re.DOTALL)
    svg_text = re.sub(r'fill="#(?:fff|ffffff|FFF|FFFFFF)"', 'fill="currentColor"', svg_text)
    return svg_text


lines = ["// Auto-generated by build_setup.py — do not edit\n"]
for file_stem, var_name, use_svg in MASCOT_ENTRIES:
    svg_src = ASSETS / f"{file_stem}.svg"
    png_src = ASSETS / f"{file_stem}.png"

    if use_svg and svg_src.exists():
        raw = svg_src.read_text(encoding="utf-8")
        patched = _patch_svg_for_css(raw)
        # Export as JSON string so special chars are properly escaped
        lines.append(f"var {var_name} = {json.dumps(patched)};\n")
        print(f"  {svg_src.name} → {var_name} (SVG inline, {len(patched):,} chars) — OK")
    elif png_src.exists():
        data = base64.b64encode(png_src.read_bytes()).decode("ascii")
        lines.append(f'var {var_name} = "data:image/png;base64,{data}";\n')
        print(f"  {png_src.name} → {var_name} ({len(data):,} chars base64) — OK")
    else:
        fail(f"Missing mascot asset for {var_name}: tried {svg_src} and {png_src}")

(STATIC / "mascots.js").write_text("".join(lines), encoding="utf-8")
print("  static/mascots.js written — OK")


# ── Step 6: Process images with Pillow ────────────────────────────────────────
step("6/12 · Processing images")

ico_path = ASSETS / "mellow.ico"
if not ico_path.exists():
    fail(f"Missing {ico_path} — this file must exist with 16/32/48/256px frames")
print(f"  mellow.ico ({ico_path.stat().st_size} bytes) — OK")

# Copy favicon to static/
shutil.copy2(ico_path, STATIC / "favicon.ico")
print("  favicon.ico copied to static/ — OK")

if FRONTEND_ONLY:
    # Wizard/installer images aren't needed (and Pillow may not be installed)
    print("  (frontend-only: skipping installer image generation)")
elif IS_WINDOWS:
    from PIL import Image  # noqa: E402
    # Wizard BMPs are only needed by Inno Setup on Windows
    wizard_large = ASSETS / "wizard_large.bmp"
    if wizard_large.exists():
        print(f"  wizard_large.bmp already present ({wizard_large.stat().st_size:,} bytes) — using as-is")
    else:
        banner_src = ASSETS / "wizard_banner.png"
        if not banner_src.exists():
            fail(f"Missing {banner_src} and no wizard_large.bmp — cannot generate wizard images")
        img = Image.open(banner_src).convert("RGB")
        img = img.resize((164, 314), Image.LANCZOS)
        img.save(wizard_large)
        assert wizard_large.exists(), "wizard_large.bmp was not created"
        print("  wizard_large.bmp (164x314) generated from wizard_banner.png — OK")

    wizard_small = ASSETS / "wizard_small.bmp"
    if wizard_small.exists():
        print(f"  wizard_small.bmp already present ({wizard_small.stat().st_size:,} bytes) — using as-is")
    else:
        mellow_src = ASSETS / "mellow_source.png"
        small_src = mellow_src if mellow_src.exists() else (ASSETS / "wizard_banner.png")
        if not small_src.exists():
            fail("Missing wizard_small.bmp and no source image found to generate it")
        src = Image.open(small_src).convert("RGBA")
        src.thumbnail((55, 58), Image.LANCZOS)
        out_img = Image.new("RGB", (55, 58), (26, 22, 20))
        out_img.paste(src, ((55 - src.width) // 2, (58 - src.height) // 2), src)
        out_img.save(wizard_small)
        assert wizard_small.exists(), "wizard_small.bmp was not created"
        print(f"  wizard_small.bmp (55x58) generated from {small_src.name} — OK")

elif IS_LINUX:
    from PIL import Image  # noqa: E402

    # Derive a 256×256 PNG from mellow.ico for .desktop / AppImage / .deb
    icon_png = ASSETS / "mellow_256.png"
    if not icon_png.exists():
        ico_img = Image.open(ico_path)
        # Pick the largest frame
        best = max(ico_img.ico.sizes(), key=lambda s: s[0] * s[1], default=(256, 256))
        ico_img.size = best
        frame = ico_img.convert("RGBA")
        frame = frame.resize((256, 256), Image.LANCZOS)
        frame.save(icon_png)
        print("  mellow_256.png (256×256) derived from mellow.ico — OK")
    else:
        print("  mellow_256.png already present — OK")


# ── Step 7: Copy the React UMD builds ─────────────────────────────────────────
step("7/12 · Copying React UMD builds from node_modules")
for pkg, src_name, dest_name in [
    ("react", "react.production.min.js", "react.min.js"),
    ("react-dom", "react-dom.production.min.js", "react-dom.min.js"),
]:
    src = NODE_MODULES / pkg / "umd" / src_name
    if not src.exists():
        fail(f"Missing {src} — run `npm ci`")
    shutil.copy2(src, STATIC / dest_name)
    print(f"  {dest_name} ({src.stat().st_size:,} bytes, {pkg} "
          f"{json.loads((NODE_MODULES / pkg / 'package.json').read_text())['version']}) — OK")


# ── Step 8: Copy index.html ────────────────────────────────────────────────────
step("8/12 · Copying index.html to static/")
src_html = GUI / "index.html"
if not src_html.exists():
    fail(f"Missing {src_html}")
shutil.copy2(src_html, STATIC / "index.html")
# Bundled web fonts: the app never fetches them from Google
shutil.copytree(GUI / "fonts", STATIC / "fonts", dirs_exist_ok=True)
print("  static/index.html, static/fonts/ — OK")


# ── Step 9: Bundle app.jsx with esbuild ───────────────────────────────────────
step("9/12 · Bundling app.jsx with esbuild")
app_jsx = GUI / "app.jsx"
if not app_jsx.exists():
    fail(f"Missing {app_jsx}")

bundle_out = STATIC / "app.bundle.js"
# --bundle resolves the gui/lib + gui/components + gui/pages module imports
# into the single static/app.bundle.js (React stays a UMD global).
run([
    esbuild,
    str(app_jsx),
    f"--outfile={bundle_out}",
    "--bundle",
    "--loader:.jsx=jsx",
    "--target=es2020",
    "--platform=browser",
    "--format=iife",
    "--global-name=MellowApp",
    "--jsx=transform",
    "--jsx-factory=React.createElement",
    "--jsx-fragment=React.Fragment",
])
print(f"  app.bundle.js ({bundle_out.stat().st_size:,} bytes) — OK")


# ── Step 10: py_compile all Python files ──────────────────────────────────────
step("10/12 · Syntax-checking Python files")
for fname in PYTHON_FILES:
    fpath = HERE / fname
    if not fpath.exists():
        fail(f"Missing Python file: {fpath}")
    try:
        py_compile.compile(str(fpath), doraise=True)
        print(f"  {fname} — OK")
    except py_compile.PyCompileError as exc:
        fail(f"Syntax error in {fname}: {exc}")
print("  All Python files syntax-valid")


# ── Step 11: PyInstaller ───────────────────────────────────────────────────────
step("11/12 · Running PyInstaller")
if FRONTEND_ONLY:
    print("  (frontend-only: skipped)")
    step("12/12 · Skipping packaging (frontend-only)")
    print("  static/ refreshed — restart the app (or reload the browser tab)")
    step("Frontend build complete")
    bundle = STATIC / "app.bundle.js"
    print(f"\n    static/app.bundle.js  ({bundle.stat().st_size:,} bytes)\n")
    sys.exit(0)

spec_file = HERE / "MellowDLP.spec"
if not spec_file.exists():
    fail(f"Missing {spec_file}")

# --clean wipes PyInstaller's cache: keep it for installer builds (correctness),
# skip it for "App only" dev builds (saves a minute or two per iteration)
_pyi_args = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
if not DESKTOP_SHORTCUT:
    _pyi_args.append("--clean")
run([*_pyi_args, str(spec_file)])

exe_name = "MellowDLP.exe" if IS_WINDOWS else "MellowDLP"
built_exe = HERE / "dist" / exe_name
if not built_exe.exists():
    fail(f"PyInstaller finished but binary not found at {built_exe}")
print(f"  dist/{exe_name} ({built_exe.stat().st_size:,} bytes) — OK")


# ── Step 12: Installer / AppImage / Desktop shortcut ─────────────────────────
if IS_LINUX:
    step("12/12 · Building AppImage")

    appdir = HERE / "dist" / "MellowDLP.AppDir"
    appdir_bin = appdir / "usr" / "bin"
    appdir_icons = appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    for d in [appdir_bin, appdir_icons]:
        d.mkdir(parents=True, exist_ok=True)

    shutil.copy2(built_exe, appdir_bin / "MellowDLP")
    (appdir_bin / "MellowDLP").chmod(0o755)

    icon_png = ASSETS / "mellow_256.png"
    if icon_png.exists():
        shutil.copy2(icon_png, appdir / "mellowdlp.png")
        shutil.copy2(icon_png, appdir_icons / "mellowdlp.png")

    desktop_content = (
        "[Desktop Entry]\n"
        "Name=MellowDLP\n"
        "Comment=Data Lake Commander\n"
        "Exec=MellowDLP\n"
        "Icon=mellowdlp\n"
        "Terminal=false\n"
        "Type=Application\n"
        "Categories=AudioVideo;Network;\n"
    )
    (appdir / "mellowdlp.desktop").write_text(desktop_content)

    apprun = appdir / "AppRun"
    apprun.write_text(
        '#!/bin/bash\n'
        'HERE="$(dirname "$(readlink -f "${0}")")"\n'
        'exec "${HERE}/usr/bin/MellowDLP" "$@"\n'
    )
    apprun.chmod(0o755)

    appimagetool = HERE / "appimagetool"
    if not appimagetool.exists():
        print("  Downloading appimagetool…")
        try:
            urllib.request.urlretrieve(
                "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage",
                appimagetool,
            )
            appimagetool.chmod(0o755)
            print("  appimagetool downloaded — OK")
        except Exception as exc:
            print(f"  WARNING: could not download appimagetool: {exc} — AppImage skipped")
            appimagetool = None

    if appimagetool and appimagetool.exists():
        appimage_out = HERE / "dist" / f"MellowDLP-{VERSION}-x86_64.AppImage"
        # APPIMAGE_EXTRACT_AND_RUN=1 lets appimagetool run without FUSE (needed in CI)
        run([str(appimagetool), str(appdir), str(appimage_out)],
            env={**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1"})
        if appimage_out.exists():
            print(f"  {appimage_out.name} ({appimage_out.stat().st_size:,} bytes) — OK")
    else:
        print("  AppImage skipped (appimagetool unavailable)")

elif IS_WINDOWS and DESKTOP_SHORTCUT:
    step("12/12 · Creating Desktop shortcut")
    desktop = Path.home() / "Desktop"
    shortcut = desktop / "MellowDLP.lnk"
    ps = (
        f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{shortcut}");'
        f'$s.TargetPath="{built_exe}";'
        f'$s.WorkingDirectory="{built_exe.parent}";'
        f'$s.IconLocation="{built_exe}";'
        f'$s.Save()'
    )
    run(["powershell", "-NoProfile", "-Command", ps])
    print(f"  Desktop shortcut → {shortcut} — OK")

elif IS_WINDOWS:
    step("12/12 · Building installer with Inno Setup")

    def _find_iscc() -> Path | None:
        """Locate ISCC.exe: PATH, then the uninstall registry key, then defaults."""
        on_path = shutil.which("ISCC") or shutil.which("iscc")
        if on_path:
            return Path(on_path)
        candidates: list[Path] = []
        try:
            import winreg
            for hive, key in [
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
                (winreg.HKEY_CURRENT_USER,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
            ]:
                try:
                    with winreg.OpenKey(hive, key) as k:
                        loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                        if loc:
                            candidates.append(Path(loc) / "ISCC.exe")
                except OSError:
                    pass
        except ImportError:
            pass
        candidates += [
            Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        ]
        return next((c for c in candidates if c.exists()), None)

    iscc = _find_iscc()
    if iscc:
        print(f"  Inno Setup found: {iscc}")
        iss_file = HERE / "installer.iss"
        run([str(iscc), f"/DAppVersion={VERSION}", str(iss_file)])
        setup_exe = HERE / "dist" / "MellowDLP_Setup.exe"
        if setup_exe.exists():
            print(f"  dist/MellowDLP_Setup.exe ({setup_exe.stat().st_size:,} bytes) — OK")
        else:
            print("  Inno Setup ran but Setup exe not found at expected path")
    else:
        print("  Inno Setup not found — skipping installer")
        print("  Install from https://jrsoftware.org/isinfo.php")

else:
    step("12/12 · Skipping platform-specific installer")
    print("  Binary ready at dist/MellowDLP")


# ── Summary ────────────────────────────────────────────────────────────────────
step("Build complete")
print("\n  Output files:")
candidates = [HERE / "static" / "app.bundle.js"]
if IS_WINDOWS:
    candidates += [HERE / "dist" / "MellowDLP.exe", HERE / "dist" / "MellowDLP_Setup.exe"]
elif IS_LINUX:
    candidates += [HERE / "dist" / "MellowDLP"]
    candidates += list((HERE / "dist").glob("MellowDLP-*.AppImage"))
else:
    candidates += [HERE / "dist" / "MellowDLP"]
for path in candidates:
    if path.exists():
        print(f"    {path.relative_to(HERE)}  ({path.stat().st_size:,} bytes)")
    else:
        print(f"    {path.relative_to(HERE)}  (not built)")
print()
