"""Linux file/folder dialogs: the desktop's own (XDG portal, zenity, kdialog), Tk last."""
import os
import shutil
import subprocess
import threading
from unittest.mock import patch

import pytest

from mellow import desktop

PORTAL = "portal"


@pytest.fixture
def linux(monkeypatch):
    """A Linux desktop session with nothing installed: each test adds its ways."""
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    monkeypatch.setattr(desktop, "_x11_parent", lambda: None)
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: None)
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)


def _ways(portal=None, tools=None, tk_answer="tk-path"):
    """Patch every way a dialog can be shown; return the list of ways called."""
    tools = tools or {}
    called = []

    def portal_dialog(kind, folder, extension, parent):
        called.append((PORTAL, kind, folder, extension))
        return portal

    def tool_dialog(tool, kind, folder, extension, parent):
        called.append((tool, kind, folder, extension))
        return tools[tool]

    def tk(*args):
        called.append(("tk",) + args)
        return tk_answer

    return called, [
        patch.object(desktop, "_portal_dialog", side_effect=portal_dialog),
        patch.object(desktop, "_tool_dialog", side_effect=tool_dialog),
        patch.object(desktop, "_desktop_tools", return_value=list(tools)),
        patch.object(desktop, "_tk_folder", side_effect=lambda folder: tk("folder", folder)),
        patch.object(desktop, "_tk_open_file", side_effect=lambda ext: tk("file", ext)),
    ]


def _ask(patches, fn, *args):
    for p in patches:
        p.start()
    try:
        return fn(*args)
    finally:
        for p in patches:
            p.stop()


# ── the order: portal → zenity/kdialog → Tk ─────────────────────────────────

def test_the_portal_answers_first(linux, tmp_path):
    called, patches = _ways(portal=str(tmp_path / "Music"), tools={"zenity": "never"})
    assert _ask(patches, desktop.ask_folder, str(tmp_path)) == str(tmp_path / "Music")
    assert called == [(PORTAL, "folder", str(tmp_path), "")]


def test_cancelling_the_portal_shows_no_second_dialog(linux, tmp_path):
    called, patches = _ways(portal="", tools={"zenity": "never"})
    assert _ask(patches, desktop.ask_folder, str(tmp_path)) == ""
    assert [way for way, *_ in called] == [PORTAL]


def test_no_portal_falls_back_to_zenity(linux, tmp_path):
    called, patches = _ways(portal=None, tools={"zenity": "/home/me/cookies.txt", "kdialog": "never"})
    assert _ask(patches, desktop.ask_open_file, ".txt") == "/home/me/cookies.txt"
    assert called == [(PORTAL, "file", "", ".txt"), ("zenity", "file", "", ".txt")]


def test_cancelling_zenity_is_a_cancel(linux, tmp_path):
    called, patches = _ways(portal=None, tools={"zenity": "", "kdialog": "never"})
    assert _ask(patches, desktop.ask_folder, str(tmp_path)) == ""
    assert [way for way, *_ in called] == [PORTAL, "zenity"]


def test_a_tool_that_fails_hands_over_to_the_next(linux, tmp_path):
    called, patches = _ways(portal=None, tools={"zenity": None, "kdialog": "/srv/media"})
    assert _ask(patches, desktop.ask_folder, str(tmp_path)) == "/srv/media"
    assert [way for way, *_ in called] == [PORTAL, "zenity", "kdialog"]


def test_a_file_picker_opens_where_the_field_points(linux, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File")
    called, patches = _ways(portal="")
    _ask(patches, desktop.ask_open_file, ".txt", str(cookies))
    assert called == [(PORTAL, "file", str(tmp_path), ".txt")]


def test_tk_is_the_last_resort(linux, tmp_path):
    called, patches = _ways(portal=None, tools={})
    assert _ask(patches, desktop.ask_folder, str(tmp_path)) == "tk-path"
    assert called[-1] == ("tk", "folder", str(tmp_path))
    called, patches = _ways(portal=None, tools={"zenity": None})
    assert _ask(patches, desktop.ask_open_file, ".txt") == "tk-path"
    assert called[-1] == ("tk", "file", ".txt")


def test_windows_and_macos_keep_tk(monkeypatch, tmp_path):
    for system in ("win32", "darwin"):
        monkeypatch.setattr(desktop.sys, "platform", system)
        called, patches = _ways(portal="never", tools={"zenity": "never"})
        assert _ask(patches, desktop.ask_folder, str(tmp_path)) == "tk-path"
        assert called == [("tk", "folder", str(tmp_path))]


def test_a_folder_that_doesnt_exist_yet_opens_on_its_parent(linux, tmp_path):
    called, patches = _ways(portal="")
    _ask(patches, desktop.ask_folder, str(tmp_path / "MellowDLP" / "not yet"))
    assert called[0][2] == str(tmp_path)
    assert desktop.nearest_folder(str(tmp_path / "a" / "b")) == str(tmp_path)
    assert desktop.nearest_folder(str(tmp_path)) == str(tmp_path)


def test_the_desktops_own_tool_comes_first(monkeypatch):
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: "/usr/bin/" + tool)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert desktop._desktop_tools() == ["kdialog", "zenity"]
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    assert desktop._desktop_tools() == ["zenity", "kdialog"]
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: "/usr/bin/kdialog" if tool == "kdialog" else None)
    assert desktop._desktop_tools() == ["kdialog"]


def test_one_dialog_at_a_time(linux, tmp_path):
    """A second BROWSE waits for the first dialog, like Tk's lock made it."""
    release = threading.Event()
    calls = []

    def slow_portal(kind, folder, extension, parent):
        calls.append(kind)
        release.wait(5)
        return ""

    with patch.object(desktop, "_portal_dialog", side_effect=slow_portal), \
            patch.object(desktop, "_desktop_tools", return_value=[]):
        first = threading.Thread(target=desktop.ask_folder, args=(str(tmp_path),))
        first.start()
        while not calls:
            pass
        second = threading.Thread(target=desktop.ask_open_file)
        second.start()
        second.join(0.3)
        assert calls == ["folder"]
        release.set()
        first.join(5)
        second.join(5)
    assert calls == ["folder", "file"]


def test_dialogs_available_without_tk(monkeypatch):
    monkeypatch.setattr(desktop, "tkinter_available", False)
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    monkeypatch.setattr(desktop, "_jeepney_available", lambda: False)
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: None)
    assert not desktop.dialogs_available()
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: "/usr/bin/zenity" if tool == "zenity" else None)
    assert desktop.dialogs_available()
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: None)
    monkeypatch.setattr(desktop, "_jeepney_available", lambda: True)
    assert desktop.dialogs_available()
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    assert not desktop.dialogs_available()


# ── zenity / kdialog ────────────────────────────────────────────────────────

def test_zenity_command_lines():
    assert desktop.tool_argv("zenity", "folder", "/home/me/Music", "", None) == [
        "zenity", "--file-selection", "--title=Choose a folder", "--modal", "--directory",
        "--filename=/home/me/Music/"]
    assert desktop.tool_argv("zenity", "file", "", ".txt", 0x3a00007) == [
        "zenity", "--file-selection", "--title=Choose a file", "--modal",
        "--file-filter=Text files | *.txt", "--file-filter=All files | *", f"--attach={0x3a00007}"]


def test_kdialog_command_lines():
    assert desktop.tool_argv("kdialog", "folder", "/home/me/Music", "", 77) == [
        "kdialog", "--getexistingdirectory", "/home/me/Music", "--title", "Choose a folder", "--attach", "77"]
    argv = desktop.tool_argv("kdialog", "file", "", ".txt", None)
    assert argv[:3] == ["kdialog", "--getopenfilename", os.path.expanduser("~")]
    assert argv[3] == "*.txt|Text files\n*|All files"


@pytest.mark.parametrize("code, out, expected", [
    (0, "/home/me/Bässe & Höhen\n".encode(), "/home/me/Bässe & Höhen"),
    (1, b"", ""),          # Cancel
    (255, b"", None),      # couldn't open: the next way
    (5, b"", None),
])
def test_what_a_tool_answers(code, out, expected):
    done = subprocess.CompletedProcess([], code, out, b"Gtk-WARNING cannot open display")
    with patch.object(desktop.subprocess, "run", return_value=done):
        assert desktop._tool_dialog("zenity", "folder", "/tmp", "", None) == expected


def test_tools_write_paths_in_utf8_and_keep_the_language():
    """Under C/POSIX zenity printed "Musique d'?t?" (seen in Xvfb)."""
    assert desktop.tool_env({})["LC_CTYPE"] == "C.UTF-8"
    env = desktop.tool_env({"LANG": "C", "LC_MESSAGES": "fr_FR.UTF-8"})
    assert env["LC_CTYPE"] == "C.UTF-8" and env["LC_MESSAGES"] == "fr_FR.UTF-8" and env["LANG"] == "C"
    assert desktop.tool_env({"LC_ALL": "POSIX"})["LC_ALL"] == "C.UTF-8"
    assert desktop.tool_env({"LANG": "fr_FR.UTF-8"}) == {"LANG": "fr_FR.UTF-8"}
    assert desktop.tool_env({"LC_ALL": "de_DE.utf8"}) == {"LC_ALL": "de_DE.utf8"}


def test_a_tool_left_open_too_long_is_a_cancel():
    with patch.object(desktop.subprocess, "run", side_effect=subprocess.TimeoutExpired("zenity", 1)):
        assert desktop._tool_dialog("zenity", "folder", "/tmp", "", None) == ""
    with patch.object(desktop.subprocess, "run", side_effect=FileNotFoundError("zenity")):
        assert desktop._tool_dialog("zenity", "folder", "/tmp", "", None) is None


# ── the window the dialog sits on (X11 only) ────────────────────────────────

def _x11(monkeypatch, tools, outputs):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(desktop.shutil, "which", lambda tool: tool if tool in tools else None)
    monkeypatch.setattr(desktop, "_run_text", lambda argv: outputs.get(tuple(argv), ""))


def test_the_dialog_sits_on_mellows_window(monkeypatch):
    _x11(monkeypatch, {"xdotool"}, {("xdotool", "getactivewindow"): "60817415\n",
                                    ("xdotool", "getwindowname", "60817415"): "▼ 42% — MellowDLP\n"})
    assert desktop._x11_parent() == 60817415
    _x11(monkeypatch, {"xprop"}, {
        ("xprop", "-root", "_NET_ACTIVE_WINDOW"): "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3a00007\n",
        ("xprop", "-id", "0x3a00007", "_NET_WM_NAME"): '_NET_WM_NAME(UTF8_STRING) = "MellowDLP"\n'})
    assert desktop._x11_parent() == 0x3a00007


def test_never_another_programs_window(monkeypatch):
    _x11(monkeypatch, {"xdotool"}, {("xdotool", "getactivewindow"): "123\n",
                                    ("xdotool", "getwindowname", "123"): "Terminal\n"})
    assert desktop._x11_parent() is None


def test_wayland_has_no_parent(monkeypatch):
    _x11(monkeypatch, {"xdotool"}, {("xdotool", "getactivewindow"): "123\n",
                                    ("xdotool", "getwindowname", "123"): "MellowDLP\n"})
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert desktop._x11_parent() is None


# ── the portal: what it's asked, what it answers ────────────────────────────

def test_portal_options():
    opts = desktop.portal_options("folder", "/home/me/Mösic", "", "mellow_1")
    assert opts["directory"] == ("b", True)
    assert opts["current_folder"] == ("ay", "/home/me/Mösic".encode() + b"\0")
    assert opts["handle_token"] == ("s", "mellow_1")
    assert "filters" not in opts
    opts = desktop.portal_options("file", "", ".txt", "mellow_2")
    assert "directory" not in opts and "current_folder" not in opts
    assert opts["filters"] == ("a(sa(us))", [("Text files", [(0, "*.txt")]), ("All files", [(0, "*")])])


def test_portal_uris_become_paths():
    assert desktop.portal_path("file:///home/me/M%C3%B6sic/A%20B") == "/home/me/Mösic/A B"
    assert desktop.portal_path("https://example.com/x") == ""


def test_no_session_bus_means_the_next_way(monkeypatch):
    jeepney = pytest.importorskip("jeepney")  # noqa: F841
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/nonexistent/bus")
    assert desktop._portal_dialog("folder", "/tmp", "", None) is None


# A real D-Bus round trip: a private bus with a stand-in portal on it

def _fake_portal(address, version, answer, seen, stop):
    from jeepney import (
        DBusAddress,
        HeaderFields,
        MessageType,
        message_bus,
        new_method_return,
        new_signal,
    )
    from jeepney.io.blocking import Proxy, open_dbus_connection

    conn = open_dbus_connection(bus=address)
    Proxy(message_bus, conn).RequestName(desktop._PORTAL_BUS, 0)
    seen["ready"].set()
    with conn:
        while not stop.is_set():
            try:
                msg = conn.receive(timeout=0.1)
            except TimeoutError:
                continue
            if msg.header.message_type != MessageType.method_call:
                continue
            member = msg.header.fields[HeaderFields.member]
            sender = msg.header.fields[HeaderFields.sender]
            if member == "Get":
                conn.send(new_method_return(msg, "v", (("u", version),)))
            elif member == "OpenFile":
                parent, title, options = msg.body
                seen["open"] = (parent, title, options)
                handle = (f"/org/freedesktop/portal/desktop/request/"
                          f"{sender[1:].replace('.', '_')}/{options['handle_token'][1]}")
                conn.send(new_method_return(msg, "o", (handle,)))
                if answer is not None:
                    response = new_signal(DBusAddress(handle, interface=desktop._REQUEST), "Response",
                                          "ua{sv}", answer)
                    response.header.fields[HeaderFields.destination] = sender
                    conn.send(response)
            elif member == "Close":
                seen["closed"] = msg.header.fields[HeaderFields.path]


@pytest.fixture
def portal_bus(monkeypatch, tmp_path):
    """Start a private session bus; returns a function that puts a portal on it."""
    pytest.importorskip("jeepney")
    if not shutil.which("dbus-daemon"):
        pytest.skip("dbus-daemon not installed")
    config = tmp_path / "bus.conf"
    config.write_text(f"""<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>session</type><listen>unix:path={tmp_path}/bus</listen>
<policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/>
<allow own="*"/></policy></busconfig>""")
    daemon = subprocess.Popen(["dbus-daemon", "--nofork", "--print-address", f"--config-file={config}"],
                              stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    stop = threading.Event()
    threads = []

    def start(version=4, answer=(0, {"uris": ("as", ["file:///home/me/M%C3%BCsic"])})):
        seen = {"ready": threading.Event()}
        t = threading.Thread(target=_fake_portal, args=(address, version, answer, seen, stop), daemon=True)
        t.start()
        threads.append(t)
        assert seen["ready"].wait(5)
        return seen

    yield start
    stop.set()
    for t in threads:
        t.join(5)
    daemon.terminate()
    daemon.wait(5)


def test_portal_folder_round_trip(portal_bus, tmp_path):
    seen = portal_bus()
    assert desktop._portal_dialog("folder", str(tmp_path), "", 0x3a00007) == "/home/me/Müsic"
    parent, title, options = seen["open"]
    assert parent == "x11:3a00007" and title == "Choose a folder"
    assert options["directory"] == ("b", True)
    assert options["current_folder"] == ("ay", os.fsencode(str(tmp_path)) + b"\0")


def test_portal_file_round_trip(portal_bus):
    seen = portal_bus(answer=(0, {"uris": ("as", ["file:///home/me/cookies.txt"])}))
    assert desktop._portal_dialog("file", "", ".txt", None) == "/home/me/cookies.txt"
    parent, _, options = seen["open"]
    assert parent == "" and options["filters"][1][0] == ("Text files", [(0, "*.txt")])


def test_portal_cancel(portal_bus):
    portal_bus(answer=(1, {}))
    assert desktop._portal_dialog("folder", "/tmp", "", None) == ""


def test_an_old_portal_cant_pick_folders(portal_bus):
    seen = portal_bus(version=2)
    assert desktop._portal_dialog("folder", "/tmp", "", None) is None
    assert "open" not in seen


def test_a_portal_dialog_left_open_is_closed(portal_bus, monkeypatch):
    seen = portal_bus(answer=None)
    monkeypatch.setattr(desktop, "DIALOG_TIMEOUT_SECS", 0.3)
    assert desktop._portal_dialog("folder", "/tmp", "", None) == ""
    for _ in range(50):
        if "closed" in seen:
            break
        threading.Event().wait(0.05)
    assert seen["closed"].startswith("/org/freedesktop/portal/desktop/request/")


def test_no_portal_on_the_bus(portal_bus):
    """A bus without xdg-desktop-portal (a bare server): the next way is tried."""
    assert desktop._portal_dialog("folder", "/tmp", "", None) is None


# ── the endpoints ───────────────────────────────────────────────────────────

def test_browse_folder_opens_in_the_download_folder(client, tmp_path):
    from mellow import config
    config.update_config(lambda c: c.update(output_dir=str(tmp_path / "dl")))
    with patch.object(desktop, "dialogs_available", return_value=True), \
            patch.object(desktop, "ask_folder", return_value="/picked") as ask:
        r = client.post("/api/browse-folder", json={})
        assert r.get_json() == {"path": "/picked"}
        assert ask.call_args.args[0] == str(config.download_root(config.load_config()))
        client.post("/api/browse-folder", json={"initial": "/home/me/Music"})
        assert ask.call_args.args[0] == "/home/me/Music"
    with patch.object(desktop, "dialogs_available", return_value=True), \
            patch.object(desktop, "ask_open_file", return_value="/c.txt") as ask:
        assert client.post("/api/browse-file", json={"filter": ".txt", "initial": "/home/me/c.txt"}).get_json() == {
            "path": "/c.txt"}
        assert ask.call_args.args == (".txt", "/home/me/c.txt")


def test_browse_without_any_dialog_says_so(client):
    with patch.object(desktop, "dialogs_available", return_value=False):
        for route in ("/api/browse-folder", "/api/browse-file"):
            body = client.post(route, json={}).get_json()
            assert body["path"] == "" and "unavailable" in body["error"]
