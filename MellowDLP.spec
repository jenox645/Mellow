import os as _os
import platform as _platform

_is_windows = _platform.system() == "Windows"
_is_linux   = _platform.system() == "Linux"

_ytdlp_bin = "yt-dlp.exe" if _is_windows else "yt-dlp"
_icon = _os.path.join("assets", "mellow.ico") if _is_windows else None

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[
        (_ytdlp_bin, "."),
    ] if _os.path.exists(_ytdlp_bin) else [],
    datas=[
        ("static", "static"),
        ("server.py", "."),
        ("downloader.py", "."),
        ("analytics.py", "."),
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
        "analytics",
        "tkinter",
        "tkinter.filedialog",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "pywebview", "pythonnet"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
