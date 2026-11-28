# Compatibility

What MellowDLP has been checked on, how, and what still needs a real machine (#128). ✅ checked (the
test or PR that pins it) · ⚠️ works with a caveat · ❌ broken (issue) · — not checked yet.

## Files in a vault folder

| Case | Listing, card count | Picture | Player (stream) | Delete | How |
|---|---|---|---|---|---|
| Emoji, `#`, `%`, `+`, `;`, `,`, quotes, non-Latin (`Ünïcödé — дорога 日本`) | ✅ | ✅ sidecar served | ✅ | ✅ | `tests/test_odd_files.py` |
| Folder named `Musique d'été 日本 #1 100%` | ✅ | ✅ | ✅ | ✅ | `tests/test_odd_files.py` |
| Very long name (200 characters) | ✅ | — | ✅ | ✅ | `tests/test_odd_files.py` |
| A newline in the name (Linux, macOS) | ✅ | — | ✅ (was a 500) | ✅ | `tests/test_odd_files.py` |
| Zero-byte and broken files | ✅ counted, smallest = 0 B | ✅ the ▶ / ♫ placeholder | ✅ | ✅ | `tests/test_odd_files.py` |
| Hidden files (`.name.mp3`), yt-dlp parts (`.f399.mp4`) | ✅ left out | — | — | — | `tests/test_vault_scan.py` |
| Read-only file (Windows' read-only attribute) | ✅ | ✅ | ✅ | ✅ (was refused: WinError 5) | `tests/test_odd_files.py` (Windows' refusal simulated) |
| A file in use by another program (Windows) | ✅ | ✅ | ✅ | ⚠️ refused, says why | `tests/test_odd_files.py` |
| 20,000 files in 300 folders, 2,000 in one | ✅ | ✅ only what's on screen (#136) | ✅ | ✅ | `scripts/make_big_library.py`, #138 / #139 |

## Systems

| System | Status | How |
|---|---|---|
| Linux (Ubuntu 24.04, cloud) | ✅ app, dialogs (XDG portal, zenity), thumbnails | #121, #122, CI |
| Fedora 40+ (the Tauri rpm) | ⚠️ installs and starts in a container; GNOME naming and icon in #135 | `tauri.yml` dnf check, #135 |
| Windows 10 / 11 | ✅ CI tests and builds; — HiDPI, real paths | CI (`windows-latest`) |
| Debian, Arch, a KDE desktop, Wayland, HiDPI 125–200 % | — | owner: see below |
| A network drive / NAS folder, an unplugged external drive | — | owner: see below |

## To try on a real machine

1. **Windows paths**: put a folder at `C:\Users\<you>\Musique\日本 été #1` (Explorer accepts it), set it as SAVE TO,
   download one video, open it from the Vault, delete it. Then mark a file read-only (Properties → Read-only) and
   delete it from the Vault: it should go.
2. **An unplugged drive**: link a vault folder on a USB drive, close MellowDLP, unplug the drive, start it: the
   Vault should open, the folder card show 0 items, and nothing else stop working. Plug it back, REFRESH.
3. **A NAS folder** (`\\nas\music` or an SMB mount): add it with + WATCH, open it, play a file, sync into it.
4. **HiDPI**: Windows display scaling at 125 %, 150 % and 200 %: the window, the status bar and the dialogs
   should be sharp and nothing cut off.
