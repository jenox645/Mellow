import importlib.util as _iu
import os as _os
import platform as _platform

from PyInstaller.utils.hooks import copy_metadata

_is_windows = _platform.system() == "Windows"
_is_linux   = _platform.system() == "Linux"
_has_tkinter = _iu.find_spec("tkinter") is not None

_icon = _os.path.join("assets", "mellow.ico") if _is_windows else None

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    # The mellow package is found by following main.py's imports. yt-dlp's
    # metadata tells ytdlp_update which version is bundled (a newer download
    # in ~/.mellow_dlp_ytdlp.zip runs instead).
    datas=[
        ("static", "static"),
        ("CHANGELOG.md", "."),        # What's new (mellow/changelog.py)
        *copy_metadata("yt-dlp"),
    ],
    hiddenimports=[
        "yt_dlp",
        "yt_dlp.utils",
        "yt_dlp.extractor",
        "flask",
        "werkzeug",
        "flaskwebgui",
        "jinja2",
        "markupsafe",
        "click",
        "itsdangerous",
        "duckdb",
        "mutagen",
    ] + (["tkinter", "tkinter.filedialog"] if _has_tkinter else []),
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "pywebview", "pythonnet"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Two builds of the same app:
# - one file (dist/MellowDLP[.exe]): the portable exe and the Linux binary.
#   It unpacks itself to a temp folder at every start, which an antivirus
#   then scans again: seconds on a laptop.
# - one folder (dist/MellowDLP-app/): what the Windows installer installs and
#   the AppImage carries. Nothing to unpack, so it starts at once.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MellowDLP",
    debug=False,
    bootloader_ignore_signals=True,
    strip=_is_linux,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon=_icon,
)

exe_dir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MellowDLP",
    debug=False,
    bootloader_ignore_signals=True,
    strip=_is_linux,
    upx=False,
    console=False,
    icon=_icon,
)

app_dir = COLLECT(
    exe_dir,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=_is_linux,
    upx=False,
    name="MellowDLP-app",
)
