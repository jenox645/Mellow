"""PLAY ALL / RANDOMIZE / SELECT → play (`/api/vault/play-files`): a player that
can't start is reported, not covered by a "Playing" toast."""
from __future__ import annotations

import pytest

from mellow import vault


@pytest.fixture
def players(monkeypatch):
    """No real player is looked up or started: VLC is found on PATH, nothing else."""
    started: list[list[str]] = []
    monkeypatch.setattr(vault, "_VLC_PATHS", [])
    monkeypatch.setattr(vault, "_MPV_PATHS", [])
    monkeypatch.setattr(vault, "_MPC_PATHS", [])
    monkeypatch.setattr(vault.shutil, "which", lambda name: "/usr/bin/vlc" if name == "vlc" else None)
    monkeypatch.setattr(vault.subprocess, "Popen", lambda args, *a, **kw: started.append(list(args)))
    return started


@pytest.fixture
def songs(tmp_path):
    out = []
    for name in ("one.mp3", "two.mp3"):
        p = tmp_path / name
        p.write_bytes(b"x")
        out.append(str(p))
    return out


def test_playing_starts_the_player_once(client, players, songs):
    r = client.post("/api/vault/play-files", json={"paths": songs})
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "method": "vlc_direct"}
    assert players == [["/usr/bin/vlc", "--playlist-enqueue", *songs]]


def test_a_player_that_wont_start_is_an_error_naming_it(client, players, songs, monkeypatch, caplog):
    def popen(args, *a, **kw):
        raise FileNotFoundError(2, "No such file or directory", args[0])
    monkeypatch.setattr(vault.subprocess, "Popen", popen)
    r = client.post("/api/vault/play-files", json={"paths": songs})
    assert r.status_code == 500
    error = r.get_json()["error"]
    assert error.startswith("Couldn't start VLC: ")
    assert "No such file or directory" in error
    assert "Couldn't start VLC" in caplog.text


@pytest.mark.parametrize("player, paths_var, method", [
    ("mpv", "_MPV_PATHS", "mpv_direct"),
    ("MPC", "_MPC_PATHS", "mpc_direct"),
])
def test_every_player_is_named_when_it_wont_start(players, songs, monkeypatch, tmp_path, player, paths_var, method):
    monkeypatch.setattr(vault.shutil, "which", lambda name: None)
    exe = tmp_path / "player.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(vault, paths_var, [str(exe)])
    assert vault.launch_playlist(songs, lambda p: None) == method

    def popen(args, *a, **kw):
        raise PermissionError(13, "Permission denied", args[0])
    monkeypatch.setattr(vault.subprocess, "Popen", popen)
    with pytest.raises(vault.PlayerStartError, match=f"^Couldn't start {player}: .*Permission denied"):
        vault.launch_playlist(songs, lambda p: None)


def test_files_that_are_all_gone_are_a_400(client, players, tmp_path):
    r = client.post("/api/vault/play-files", json={"paths": [str(tmp_path / "gone.mp3")]})
    assert r.status_code == 400
    assert r.get_json() == {"error": "None of these files exist any more"}
    assert players == []
