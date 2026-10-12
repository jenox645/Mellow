"""Desktop integration: file manager, default apps, clipboard, native dialogs."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

try:
    import tkinter
    import tkinter.filedialog
    tkinter_available = True
except ModuleNotFoundError:
    tkinter = None  # type: ignore[assignment]
    tkinter_available = False

from .constants import DIALOG_TIMEOUT_SECS, EXPLORER_FIND_SECS, EXPLORER_POLL_SECS

log = logging.getLogger(__name__)

# Win32 values for bringing a window forward
_SW_RESTORE = 9
_INPUT_MOUSE = 0

# Tk isn't thread-safe: every Tk use (clipboard, dialogs) goes through this lock
_tk_lock = threading.Lock()


def explorer_command(target: str, select: bool) -> str:
    """The command line that shows `target` (a Windows path) in Explorer.

    A string, not an argument list: Python quotes a whole argument that holds
    a space, and Explorer doesn't understand "/select,C:\\My Music\\a.mp3"
    in quotes; it opened Documents instead. Only the path is quoted (a
    Windows path can't contain a double quote).
    """
    return f'explorer /select,"{target}"' if select else f'explorer "{target}"'


def show_in_folder(path: str, bring_forward: bool = True) -> None:
    """Open the file manager at `path` (a file is selected where supported).

    bring_forward: put the window in front (a click in MellowDLP asked for
    it), rather than where Windows leaves a background process's window.
    """
    p = Path(path)
    if not p.exists():
        p = p.parent
    system = platform.system()
    if system == "Windows":
        before = _explorer_windows() if bring_forward else []
        subprocess.Popen(explorer_command(os.path.normpath(os.path.abspath(str(p))), p.is_file()))
        if bring_forward:
            # Opened by a background process (this server), the window would
            # stay behind MellowDLP's: find it and bring it to the front
            _bring_forward(before, (p.parent if p.is_file() else p).name)
    elif system == "Darwin":
        if p.is_file():
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])


# ── Windows: bring the Explorer window to the front ─────────────────────────

def _explorer_windows() -> list[tuple[int, str]]:
    """(handle, title) of every open Explorer window."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "CabinetWClass" and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            found.append((int(hwnd), title.value))
        return True

    try:
        user32.EnumWindows(visit, 0)
    except Exception as exc:
        log.debug(f"listing Explorer windows failed: {exc}")
    return found


def pick_window(before: list[tuple[int, str]], now: list[tuple[int, str]], folder: str) -> int | None:
    """The Explorer window that just showed `folder`: a new one, else one
    whose title is the folder's name (Windows 11 may open a tab in an
    existing window instead)."""
    old = {hwnd for hwnd, _ in before}
    new = [hwnd for hwnd, _ in now if hwnd not in old]
    if new:
        return new[-1]
    wanted = folder.casefold()
    return next((hwnd for hwnd, title in now
                 if title.casefold() == wanted or title.casefold().startswith(wanted + " - ")), None)


def _send_empty_input() -> None:
    """SendInput with one mouse event that neither moves nor clicks."""
    import ctypes
    from ctypes import wintypes

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class InputUnion(ctypes.Union):
        _fields_ = [("mi", MouseInput)]    # the largest member: the union has INPUT's size

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", InputUnion)]

    event = Input(type=_INPUT_MOUSE)
    ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input))


def _bring_forward(before: list[tuple[int, str]], folder: str) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + EXPLORER_FIND_SECS
    while time.monotonic() < deadline:
        hwnd = pick_window(before, _explorer_windows(), folder)
        if hwnd:
            try:
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, _SW_RESTORE)
                # Windows lets a process take the foreground right after an
                # input event of its own: an empty mouse event (PowerToys does
                # the same), no key a window could react to
                _send_empty_input()
                user32.SetForegroundWindow(hwnd)
            except Exception as exc:
                log.debug(f"couldn't bring Explorer forward: {exc}")
            return
        time.sleep(EXPLORER_POLL_SECS)
    log.debug(f"no Explorer window for {folder!r} showed up")


def open_file(path: str) -> None:
    """Open a file with its default application."""
    system = platform.system()
    if system == "Windows":
        getattr(os, "startfile")(path)
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_url(url: str) -> None:
    """Open a web page in the default browser."""
    webbrowser.open(url)


def clipboard_text() -> str:
    system = platform.system()
    try:
        if system == "Windows" and tkinter_available:
            # Tk's clipboard: no shell window, no PowerShell spawned
            with _tk_lock:
                root = tkinter.Tk()
                root.withdraw()
                try:
                    text = root.clipboard_get()
                except tkinter.TclError:
                    text = ""
                finally:
                    root.destroy()
            return text.strip()
        if system == "Darwin":
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return result.stdout.strip()
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _tk_dialog(dialog_fn: Any, **kwargs: Any) -> str:
    result: list[str] = []

    def _run() -> None:
        with _tk_lock:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)  # stay above app window
            root.lift()
            root.focus_force()
            try:
                val = dialog_fn(**kwargs)
                result.append(str(val) if val else "")
            finally:
                root.destroy()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=DIALOG_TIMEOUT_SECS)
    return result[0] if result else ""


def ask_open_file(extension: str = "") -> str:
    """Native "open file" dialog; "" when cancelled."""
    filetypes = ([("Text files", f"*{extension}"), ("All files", "*.*")] if extension
                 else [("All files", "*.*")])
    return _tk_dialog(tkinter.filedialog.askopenfilename, filetypes=filetypes)


def ask_folder(initial: str) -> str:
    """Native folder picker; "" when cancelled."""
    return _tk_dialog(tkinter.filedialog.askdirectory, initialdir=initial, mustexist=False)
