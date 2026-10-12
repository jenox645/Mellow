"""Showing a file in Windows Explorer: the right folder, in front of MellowDLP."""
import subprocess
from unittest.mock import MagicMock, patch

from mellow import desktop

SONG = r"C:\Users\jenis\HW 3 Jenisvar NADESU\test\ヨルシカ - 千鳥 (OFFICIAL).mp3"


def test_the_path_alone_is_quoted():
    assert desktop.explorer_command(SONG, select=True) == f'explorer /select,"{SONG}"'
    assert desktop.explorer_command(r"C:\My Music", select=False) == r'explorer "C:\My Music"'
    # What an argument list became: the whole switch in quotes, which Explorer
    # doesn't understand (it opened Documents)
    assert subprocess.list2cmdline(["explorer", "/select," + SONG]).startswith('explorer "/select,')


def test_pick_the_window_that_just_opened():
    before = [(1, "Downloads"), (2, "Documents")]
    assert desktop.pick_window(before, before + [(7, "test")], "test") == 7
    # Windows 11 opened a tab in an existing window: that window, by its title
    assert desktop.pick_window(before, [(1, "Downloads"), (2, "test")], "test") == 2
    assert desktop.pick_window(before, [(1, "Downloads"), (2, "Test - File Explorer")], "test") == 2
    assert desktop.pick_window(before, before, "test") is None


def test_windows_opens_the_song_and_brings_explorer_forward(tmp_path):
    folder = tmp_path / "HW 3 Jenisvar NADESU" / "test"
    folder.mkdir(parents=True)
    song = folder / "ヨルシカ - 千鳥.mp3"
    song.write_bytes(b"\0")
    user32 = MagicMock()
    user32.IsIconic.return_value = 0
    windows = iter([[(1, "Downloads")], [(1, "Downloads")], [(1, "Downloads"), (9, "test")]])
    with patch.object(desktop.platform, "system", return_value="Windows"), \
            patch.object(desktop.subprocess, "Popen") as popen, \
            patch.object(desktop, "_explorer_windows", side_effect=lambda: next(windows)), \
            patch.object(desktop, "_send_empty_input") as empty_input, \
            patch("ctypes.windll", MagicMock(user32=user32), create=True), \
            patch.object(desktop, "EXPLORER_POLL_SECS", 0):
        desktop.show_in_folder(str(song))
    (cmd,), _ = popen.call_args
    assert cmd.startswith('explorer /select,"') and cmd.endswith('ヨルシカ - 千鳥.mp3"')
    empty_input.assert_called_once()
    user32.SetForegroundWindow.assert_called_once_with(9)


def test_a_missing_file_opens_its_folder(tmp_path):
    with patch.object(desktop.platform, "system", return_value="Linux"), \
            patch.object(desktop.subprocess, "Popen") as popen:
        desktop.show_in_folder(str(tmp_path / "gone.mp3"))
    assert popen.call_args.args[0] == ["xdg-open", str(tmp_path)]


def test_the_queue_finishing_opens_the_folder_without_taking_the_front(tmp_path):
    with patch.object(desktop.platform, "system", return_value="Windows"), \
            patch.object(desktop.subprocess, "Popen") as popen, \
            patch.object(desktop, "_explorer_windows") as listing, \
            patch.object(desktop, "_bring_forward") as forward:
        desktop.show_in_folder(str(tmp_path), bring_forward=False)
    assert popen.call_args.args[0] == f'explorer "{tmp_path}"'
    listing.assert_not_called()
    forward.assert_not_called()
