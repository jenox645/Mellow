"""Desktop integration: file manager, default apps, clipboard, native dialogs."""
from __future__ import annotations

import os
import platform
import subprocess
import threading
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

from .constants import DIALOG_TIMEOUT_SECS

# Tk isn't thread-safe: every Tk use (clipboard, dialogs) goes through this lock
_tk_lock = threading.Lock()


def show_in_folder(path: str) -> None:
    """Open the file manager at `path` (a file is selected where supported)."""
    p = Path(path)
    system = platform.system()
    if system == "Windows":
        if p.is_file():
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(str(p))}"])
        else:
            subprocess.Popen(["explorer", os.path.normpath(str(p if p.is_dir() else p.parent))])
    elif system == "Darwin":
        if p.is_file():
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["open", str(p if p.is_dir() else p.parent)])
    else:
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])


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
