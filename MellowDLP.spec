block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
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
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon="assets\\mellow.ico",
)
