#!/usr/bin/env python3
"""MellowDLP build script — produces MellowDLP.exe AND MellowDLP_Setup.exe installer"""
import sys, os, subprocess, urllib.request, shutil
from pathlib import Path

HERE = Path(__file__).parent

def run(cmd): return subprocess.run(cmd, shell=True, cwd=HERE)
def fail(msg):
    print(f"\n  ERROR: {msg}\n")
    input("  Press Enter to exit...")
    sys.exit(1)

print("\n" + "="*56)
print("  MellowDLP v2 -- Build")
print("="*56)

if not (HERE / "main.py").exists():
    fail("main.py not found. Run SETUP.bat from inside the MellowDLP folder.")

print(f"\n[1/7] Python {sys.version.split()[0]}")
if sys.version_info < (3, 9): fail("Python 3.9+ required.")
print("  OK")

print("\n[2/7] Removing incompatible packages...")
for pkg in ["pywebview", "pythonnet", "proxy-tools", "bottle"]:
    subprocess.run([sys.executable,"-m","pip","uninstall","-y",pkg], capture_output=True)
subprocess.run([sys.executable,"-m","pip","cache","purge"], capture_output=True)
print("  OK")

print("\n[3/7] Installing: yt-dlp flask flaskwebgui pyinstaller ...")
r = subprocess.run([sys.executable,"-m","pip","install","--upgrade","yt-dlp","flask","flaskwebgui","pyinstaller"], cwd=HERE)
if r.returncode != 0: fail("pip install failed. Check internet connection.")
print("  OK")

print("\n[4/7] Node.js check...")
r = subprocess.run("node --version", shell=True, capture_output=True, text=True)
if r.returncode != 0: fail("Node.js not found.\nInstall LTS from https://nodejs.org and restart this script.")
print(f"  node {r.stdout.strip()} -- OK")

print("\n[5/7] Downloading React runtime...")
static = HERE / "static"
static.mkdir(exist_ok=True)
for url, dest in [
    ("https://unpkg.com/react@18/umd/react.production.min.js",        static/"react.min.js"),
    ("https://unpkg.com/react-dom@18/umd/react-dom.production.min.js", static/"react-dom.min.js"),
]:
    if dest.exists(): print(f"  cached: {dest.name}"); continue
    print(f"  downloading {dest.name}...")
    try: urllib.request.urlretrieve(url, dest)
    except Exception as e: fail(f"Download failed: {e}")
shutil.copy(HERE / "gui" / "index.html", static / "index.html")
print("  OK")

print("\n[6/7] Compiling React UI...")
if not (HERE / "gui" / "app.jsx").exists(): fail("gui/app.jsx missing.")
r = run('npx --yes esbuild gui/app.jsx --bundle --outfile=static/app.bundle.js --platform=browser --define:process.env.NODE_ENV=\'"production"\' --external:react --external:react-dom --minify')
if r.returncode != 0: fail("esbuild failed. Try: npm install -g esbuild")
print("  OK")

print("\n" + "="*56)
print("  PyInstaller (1-3 minutes)...")
print("="*56 + "\n")
r = subprocess.run([sys.executable,"-m","PyInstaller","MellowDLP.spec","--clean","--noconfirm"], cwd=HERE)
if r.returncode != 0: fail("PyInstaller failed. Disable antivirus temporarily and retry.")

exe = HERE / "dist" / "MellowDLP.exe"
if not exe.exists(): fail("MellowDLP.exe not found after PyInstaller.")
print(f"\n  MellowDLP.exe built: {exe.stat().st_size//1024//1024} MB")

# Step 7: Inno Setup
print("\n[7/7] Building installer with Inno Setup...")
iscc_paths = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    shutil.which("ISCC") or "",
]
iscc = next((p for p in iscc_paths if p and Path(p).exists()), None)

if not iscc:
    print("\n  Inno Setup not found -- skipping installer creation.")
    print("  To create the installer:")
    print("  1. Install Inno Setup 6 from: https://jrsoftware.org/isdl.php")
    print("  2. Run SETUP.bat again")
    print()
else:
    r = subprocess.run([iscc, str(HERE / "installer.iss")], cwd=HERE)
    if r.returncode != 0:
        print("  Inno Setup failed. The .exe still works though.")
    else:
        setup_exe = HERE / "dist" / "MellowDLP_Setup.exe"
        print(f"\n  Installer built: {setup_exe}")

print()
print("="*56)
print("  BUILD COMPLETE")
print("="*56)
print()

setup = HERE / "dist" / "MellowDLP_Setup.exe"
portable = HERE / "dist" / "MellowDLP.exe"
if setup.exists():
    print(f"  INSTALLER:  dist\\MellowDLP_Setup.exe  ({setup.stat().st_size//1024//1024} MB)")
    print(f"  PORTABLE:   dist\\MellowDLP.exe  ({portable.stat().st_size//1024//1024} MB)")
    ans = input("\n  Copy MellowDLP_Setup.exe to Desktop? (y/n): ").strip().lower()
    if ans == 'y':
        dst = Path.home() / "Desktop" / "MellowDLP_Setup.exe"
        shutil.copy(setup, dst); print(f"  Copied to {dst}")
else:
    print(f"  PORTABLE:   dist\\MellowDLP.exe  ({portable.stat().st_size//1024//1024} MB)")
    ans = input("\n  Copy MellowDLP.exe to Desktop? (y/n): ").strip().lower()
    if ans == 'y':
        dst = Path.home() / "Desktop" / "MellowDLP.exe"
        shutil.copy(portable, dst); print(f"  Copied to {dst}")

input("\n  Press Enter to exit...")
