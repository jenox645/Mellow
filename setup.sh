#!/usr/bin/env bash
# MellowDLP — Linux build script
# Usage: bash setup.sh [--desktop-shortcut]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  MellowDLP Linux Builder"
echo "  -----------------------"
echo ""

# ── Dependency checks ─────────────────────────────────────────────────────────
check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "ERROR: '$1' not found. $2"
        exit 1
    fi
}

check_cmd python3 "Install with: sudo apt install python3"
check_cmd pip3    "Install with: sudo apt install python3-pip"
check_cmd node    "Install from https://nodejs.org/ or: sudo apt install nodejs npm"
check_cmd npm     "Install from https://nodejs.org/ or: sudo apt install npm"

if ! command -v ffmpeg &>/dev/null; then
    echo "WARNING: ffmpeg not found — install with: sudo apt install ffmpeg"
fi

# ── Python dependencies ───────────────────────────────────────────────────────
echo "  Installing Python dependencies..."
pip3 install -r requirements.txt --quiet 2>/dev/null \
  || pip3 install -r requirements.txt --quiet --break-system-packages \
  || { echo "ERROR: pip install failed"; exit 1; }
echo "  Python deps — OK"

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
echo "  Running build_setup.py..."
python3 build_setup.py "$@"

echo ""
echo "  Build complete!"
echo "  Binary:   dist/MellowDLP"
echo "  AppImage: dist/MellowDLP-*-x86_64.AppImage (if appimagetool was available)"
echo ""
echo "  Run with: ./dist/MellowDLP"
