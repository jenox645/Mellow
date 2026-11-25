"""Desktop integration: file manager, default apps, clipboard, native dialogs."""
from __future__ import annotations

import logging
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

try:
    import tkinter
    import tkinter.filedialog
    tkinter_available = True
except ModuleNotFoundError:
    tkinter = None  # type: ignore[assignment]
    tkinter_available = False

from .constants import (
    DIALOG_TIMEOUT_SECS,
    EXPLORER_FIND_SECS,
    EXPLORER_POLL_SECS,
    PORTAL_REPLY_SECS,
    WINDOW_PROBE_SECS,
)

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


def dialogs_available() -> bool:
    """A file or folder dialog can be shown: Tk's, or on Linux the desktop's
    own (the portal, zenity, kdialog)."""
    if tkinter_available:
        return True
    if not _on_linux():
        return False
    return _jeepney_available() or any(shutil.which(tool) for tool in ("zenity", "kdialog"))


def ask_open_file(extension: str = "", initial: str = "") -> str:
    """Native "open file" dialog; "" when cancelled. Linux opens it in
    `initial`'s folder (the file a field already names)."""
    if _on_linux():
        return _linux_dialog("file", initial, extension)
    return _tk_open_file(extension)


def ask_folder(initial: str) -> str:
    """Native folder picker; "" when cancelled."""
    if _on_linux():
        return _linux_dialog("folder", initial, "")
    return _tk_folder(initial)


def _tk_open_file(extension: str) -> str:
    if not tkinter_available:
        return ""
    filetypes = ([("Text files", f"*{extension}"), ("All files", "*.*")] if extension
                 else [("All files", "*.*")])
    return _tk_dialog(tkinter.filedialog.askopenfilename, filetypes=filetypes)


def _tk_folder(initial: str) -> str:
    if not tkinter_available:
        return ""
    return _tk_dialog(tkinter.filedialog.askdirectory, initialdir=initial, mustexist=False)


# ── Linux: the desktop's own dialog ─────────────────────────────────────────
# Tk draws its own small dialog, nothing like GNOME's or KDE's. In this order:
# the XDG desktop portal (the real GNOME/KDE chooser, sandbox-safe), zenity or
# kdialog (the one that fits the desktop first), and Tk last. Each way answers
# a path, "" (the person cancelled: no second dialog), or None (it couldn't
# show one: the next way is tried).

APP_WINDOW_TITLE = "MellowDLP"   # gui/app.jsx: the window's title ends with it
DIALOG_TITLES = {"folder": "Choose a folder", "file": "Choose a file"}

# One dialog at a time, like Tk's lock: a second BROWSE waits for the first
_dialog_lock = threading.Lock()

_PORTAL_BUS = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_FILE_CHOOSER = "org.freedesktop.portal.FileChooser"
_REQUEST = "org.freedesktop.portal.Request"
_PORTAL_FOLDERS_SINCE = 3     # FileChooser's `directory` option came in version 3
_PORTAL_CANCELLED = 1


def _on_linux() -> bool:
    return sys.platform.startswith("linux")


def _jeepney_available() -> bool:
    try:
        import jeepney  # noqa: F401
    except ImportError:
        return False
    return True


def _linux_dialog(kind: str, initial: str, extension: str) -> str:
    """The chosen path, "" when cancelled or no dialog could be shown."""
    if not _dialog_lock.acquire(timeout=DIALOG_TIMEOUT_SECS):
        return ""
    try:
        folder = nearest_folder(initial) if initial else ""
        parent = _x11_parent()
        ways = [("portal", lambda: _portal_dialog(kind, folder, extension, parent))]
        ways += [(tool, lambda tool=tool: _tool_dialog(tool, kind, folder, extension, parent))
                 for tool in _desktop_tools()]
        for name, way in ways:
            answer = way()
            if answer is not None:
                log.debug(f"{kind} dialog: {name}")
                return answer
        log.info(f"no desktop {kind} dialog (portal, zenity, kdialog): Tk's")
        return _tk_folder(folder or initial) if kind == "folder" else _tk_open_file(extension)
    finally:
        _dialog_lock.release()


def nearest_folder(path: str) -> str:
    """`path` when it's a folder, else the closest folder above it (a download
    folder that doesn't exist yet opens on its parent), else home."""
    p = Path(path).expanduser()
    for candidate in (p, *p.parents):
        try:
            if candidate.is_dir():
                return str(candidate)
        except OSError:
            continue
    return str(Path.home())


def _desktop_tools() -> list[str]:
    """zenity and kdialog where installed, the desktop's own first."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    order = ["kdialog", "zenity"] if "KDE" in desktop else ["zenity", "kdialog"]
    return [tool for tool in order if shutil.which(tool)]


def _x11_parent() -> int | None:
    """MellowDLP's window on X11 (the one BROWSE was just clicked in, so the
    active one), for the dialog to sit on. Wayland gives other programs no
    window ids: there the dialog opens unparented, in front."""
    if (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY")):
        return None
    try:
        if shutil.which("xdotool"):
            wid = _run_text(["xdotool", "getactivewindow"]).strip()
            name = _run_text(["xdotool", "getwindowname", wid]).strip() if wid.isdigit() else ""
            if wid.isdigit() and name.endswith(APP_WINDOW_TITLE):
                return int(wid)
        if shutil.which("xprop"):
            found = re.search(r"window id # (0x[0-9a-fA-F]+)",
                              _run_text(["xprop", "-root", "_NET_ACTIVE_WINDOW"]))
            if found:
                name = _run_text(["xprop", "-id", found.group(1), "_NET_WM_NAME"])
                if re.search(re.escape(APP_WINDOW_TITLE) + r'"\s*$', name):
                    return int(found.group(1), 16)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug(f"finding MellowDLP's window failed: {exc}")
    return None


def _run_text(argv: list[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True, timeout=WINDOW_PROBE_SECS,
                          check=False).stdout


# ── the XDG desktop portal (org.freedesktop.portal.FileChooser) ────────────

def portal_options(kind: str, folder: str, extension: str, token: str) -> dict:
    """OpenFile's options (D-Bus `a{sv}`: name → (signature, value))."""
    options: dict = {"handle_token": ("s", token), "modal": ("b", True)}
    if kind == "folder":
        options["directory"] = ("b", True)
    if folder:
        options["current_folder"] = ("ay", os.fsencode(folder) + b"\0")
    if extension:
        options["filters"] = ("a(sa(us))", [("Text files", [(0, f"*{extension}")]),
                                            ("All files", [(0, "*")])])
    return options


def portal_path(uri: str) -> str:
    """A local path from the portal's file:// URI ("" for anything else)."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return ""
    return os.fsdecode(unquote(parsed.path).encode("utf-8", "surrogateescape"))


def _portal_dialog(kind: str, folder: str, extension: str, parent: int | None) -> str | None:
    try:
        from jeepney.io.blocking import open_dbus_connection
    except ImportError:
        return None
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception as exc:   # no session bus (a bare server, a container)
        log.debug(f"no D-Bus session bus: {exc}")
        return None
    try:
        return _portal_ask(conn, kind, folder, extension, parent)
    except Exception as exc:   # no portal, no FileChooser backend, a broken answer
        log.info(f"desktop portal file chooser unavailable: {exc}")
        return None
    finally:
        conn.close()


def _portal_ask(conn: Any, kind: str, folder: str, extension: str, parent: int | None) -> str | None:
    from jeepney import (
        DBusAddress,
        HeaderFields,
        MatchRule,
        Properties,
        message_bus,
        new_method_call,
    )
    from jeepney.io.blocking import Proxy
    from jeepney.wrappers import unwrap_msg

    chooser = DBusAddress(_PORTAL_PATH, bus_name=_PORTAL_BUS, interface=_FILE_CHOOSER)
    if kind == "folder":
        # An older portal would ignore `directory` and let only a file be picked
        (_, version), = unwrap_msg(conn.send_and_get_reply(
            Properties(chooser).get("version"), timeout=PORTAL_REPLY_SECS))
        if version < _PORTAL_FOLDERS_SINCE:
            log.info(f"desktop portal FileChooser {version} can't pick folders")
            return None

    # The answer comes as a Response signal on a Request object: listen before asking
    token = "mellow_" + secrets.token_hex(8)
    rule = MatchRule(type="signal", interface=_REQUEST, member="Response")
    Proxy(message_bus, conn, timeout=PORTAL_REPLY_SECS).AddMatch(rule)
    with conn.filter(rule, bufsize=16) as responses:
        ask = new_method_call(chooser, "OpenFile", "ssa{sv}", (
            f"x11:{parent:x}" if parent else "", DIALOG_TITLES[kind],
            portal_options(kind, folder, extension, token)))
        (handle,) = unwrap_msg(conn.send_and_get_reply(ask, timeout=PORTAL_REPLY_SECS))
        deadline = time.monotonic() + DIALOG_TIMEOUT_SECS
        while True:
            try:
                answer = conn.recv_until_filtered(responses, timeout=max(0.0, deadline - time.monotonic()))
            except TimeoutError:
                # Left open too long: close it, as Tk's dialog gives up then too
                conn.send(new_method_call(DBusAddress(handle, bus_name=_PORTAL_BUS, interface=_REQUEST),
                                          "Close"))
                return ""
            if answer.header.fields.get(HeaderFields.path) == handle:
                break
    code, results = answer.body
    if code != 0:   # 1: cancelled; 2: ended otherwise (GTK's portal answers 2 to Esc)
        if code != _PORTAL_CANCELLED:
            log.info(f"desktop portal {kind} dialog ended without a choice (response {code})")
        return ""
    uris = results.get("uris", ("as", []))[1]
    return portal_path(uris[0]) if uris else ""


# ── zenity / kdialog ────────────────────────────────────────────────────────

def tool_argv(tool: str, kind: str, folder: str, extension: str, parent: int | None) -> list[str]:
    """The command line that asks `tool` (zenity or kdialog) for a file or folder."""
    title = DIALOG_TITLES[kind]
    if tool == "zenity":
        argv = ["zenity", "--file-selection", f"--title={title}", "--modal"]
        if kind == "folder":
            argv.append("--directory")
        if folder:
            argv.append("--filename=" + folder.rstrip(os.sep) + os.sep)   # opens inside it
        if extension:
            argv += [f"--file-filter=Text files | *{extension}", "--file-filter=All files | *"]
    else:
        start = folder or str(Path.home())
        if kind == "folder":
            argv = ["kdialog", "--getexistingdirectory", start]
        else:
            argv = ["kdialog", "--getopenfilename", start]
            if extension:
                argv.append(f"*{extension}|Text files\n*|All files")
        argv += ["--title", title]
    if parent:
        argv += [f"--attach={parent}"] if tool == "zenity" else ["--attach", str(parent)]
    return argv


def tool_env(environ: dict | None = None) -> dict:
    """The tool's environment, with a UTF-8 character set: zenity writes the
    path in the locale's, and under C/POSIX "Musique d'été" came back as
    "Musique d'?t?". The language (LC_MESSAGES, LANG) stays the person's."""
    env = dict(os.environ if environ is None else environ)
    if env.get("LC_ALL"):
        if not _is_utf8(env["LC_ALL"]):
            env["LC_ALL"] = "C.UTF-8"
    elif not _is_utf8(env.get("LC_CTYPE") or env.get("LANG") or ""):
        env["LC_CTYPE"] = "C.UTF-8"
    return env


def _is_utf8(locale_name: str) -> bool:
    return bool(re.search(r"utf-?8", locale_name, re.IGNORECASE))


def _tool_dialog(tool: str, kind: str, folder: str, extension: str, parent: int | None) -> str | None:
    try:
        done = subprocess.run(tool_argv(tool, kind, folder, extension, parent), env=tool_env(),
                              capture_output=True, timeout=DIALOG_TIMEOUT_SECS, check=False)
    except subprocess.TimeoutExpired:   # run() has closed it
        return ""
    except OSError as exc:
        log.info(f"{tool} didn't start: {exc}")
        return None
    if done.returncode == 0:
        return os.fsdecode(done.stdout.rstrip(b"\n"))
    if done.returncode == 1:            # Cancel, Esc, the window closed
        return ""
    log.info(f"{tool} couldn't show a dialog (exit {done.returncode}): "
             f"{done.stderr.decode(errors='replace').strip()[-200:]}")
    return None
