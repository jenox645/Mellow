"""A tester's first round: readable small text, a GitHub link, sync options
that stick, and PLAY ALL for big folders."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mellow import config, vault
from mellow.constants import APP_REPO_PAGE

ROOT = Path(__file__).resolve().parents[1]


# ── Contrast ──────────────────────────────────────────────────────────────────

def _luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _tokens() -> dict[str, str]:
    css = (ROOT / "gui" / "index.html").read_text(encoding="utf-8")
    return dict(re.findall(r"--(bg\d?|t\d):(#[0-9A-Fa-f]{6})", css))


@pytest.mark.parametrize("text", ["t1", "t2", "t3", "t4"])
def test_every_text_color_is_readable_on_every_background(text):
    """The small grey-blue text (t3, t4) was 2.4-2.9:1 and 1.4-1.7:1: WCAG
    asks 4.5:1 for small text."""
    tokens = _tokens()
    backgrounds = [tokens[k] for k in ("bg", "bg1", "bg2", "bg3")]
    worst = min(_contrast(tokens[text], bg) for bg in backgrounds)
    assert worst >= 4.5, f"--{text} {tokens[text]} is {worst:.2f}:1 on one background"


def test_the_text_colors_still_step_down():
    tokens = _tokens()
    on = tokens["bg2"]
    assert _contrast(tokens["t1"], on) > _contrast(tokens["t2"], on) > _contrast(tokens["t3"], on) \
        > _contrast(tokens["t4"], on)


# ── GitHub link ───────────────────────────────────────────────────────────────

def _opened(client, body):
    with patch("mellow.desktop.open_url") as open_url:
        r = client.post("/api/open-release", json=body)
        for _ in range(50):
            if open_url.called:
                break
            time.sleep(0.02)
    return r, open_url


def test_the_github_button_opens_the_project_page(client):
    r, open_url = _opened(client, {"page": "repo"})
    assert r.status_code == 200
    open_url.assert_called_once_with(APP_REPO_PAGE)


def test_only_known_pages_open(client):
    r, open_url = _opened(client, {"page": "https://evil.example"})
    assert r.status_code == 400
    assert not open_url.called


# ── Sync options are the folder's ─────────────────────────────────────────────

@pytest.fixture
def linked(tmp_path):
    folder = str(tmp_path / "Radio")
    config.update_config(lambda c: c.update(vault_playlists={folder: ["https://example.com/pl"]}))
    return folder


def test_sync_options_save_without_syncing(client, linked):
    with patch("mellow.downloader.download_video") as dl:
        r = client.post("/api/vault/sync-format", json={"path": linked, "sync_audio": True,
                                                        "audio_format": "wav", "embed_thumbnail": False})
        assert r.status_code == 200
    assert not dl.called
    saved = config.load_config()["vault_sync_formats"][linked]
    assert saved == {"sync_audio": True, "audio_format": "wav", "embed_thumbnail": False}
    # What the folder's SYNC NOW, SYNC ALL and auto-sync then use
    opts = vault.build_sync_opts({}, None, config.load_config(), linked)
    assert (opts["sync_audio"], opts["audio_format"], opts["embed_thumbnail"]) == (True, "wav", False)


def test_saving_merges_with_what_the_folder_had(client, linked):
    client.post("/api/vault/sync-format", json={"path": linked, "sync_audio": True, "audio_format": "wav"})
    client.post("/api/vault/sync-format", json={"path": linked, "sync_audio": False, "quality": "720p",
                                               "container": "mkv"})
    assert config.load_config()["vault_sync_formats"][linked] == {
        "sync_audio": False, "audio_format": "wav", "quality": "720p", "container": "mkv"}


@pytest.mark.parametrize("body, error", [
    ({"audio_format": "exe"}, "audio_format must be one of"),
    ({"container": "avi"}, "container must be one of"),
    ({"quality": "8k"}, "quality must be one of"),
    ({"embed_thumbnail": "yes"}, "embed_thumbnail must be true or false"),
    ({"sync_audio": 1}, "sync_audio must be true or false"),
    ({"filename_template": "x"}, "No sync options given"),
])
def test_only_valid_sync_options_are_saved(client, linked, body, error):
    r = client.post("/api/vault/sync-format", json={"path": linked, **body})
    assert r.status_code == 400 and error in r.get_json()["error"]
    assert linked not in (config.load_config().get("vault_sync_formats") or {})


def test_only_a_linked_folder_gets_sync_options(client, tmp_path):
    r = client.post("/api/vault/sync-format", json={"path": str(tmp_path), "sync_audio": True})
    assert r.status_code == 400
    assert not config.load_config().get("vault_sync_formats")


# ── PLAY ALL of a big folder ──────────────────────────────────────────────────

def _launch(paths, monkeypatch):
    started = []
    done = threading.Event()

    def popen(args, *a, **kw):
        started.append(list(args))
        done.set()

    monkeypatch.setattr(vault, "_VLC_PATHS", [])
    monkeypatch.setattr(vault.shutil, "which", lambda name: "/usr/bin/vlc" if name == "vlc" else None)
    monkeypatch.setattr(vault.subprocess, "Popen", popen)
    assert vault.launch_playlist(paths, lambda p: None) == "vlc_direct"
    assert done.wait(5)
    return started[0]


def _files(tmp_path, n, name_len=60):
    out = []
    for i in range(n):
        p = tmp_path / (f"{i:04d} " + "x" * name_len + ".mp3")
        p.write_bytes(b"x")
        out.append(str(p))
    return out


def test_a_few_files_go_to_the_player_as_they_are(tmp_path, monkeypatch):
    paths = _files(tmp_path, 3)
    assert _launch(paths, monkeypatch) == ["/usr/bin/vlc", "--playlist-enqueue", *paths]


def test_a_whole_big_folder_goes_to_the_player_as_one_playlist(tmp_path, monkeypatch):
    """Windows refuses a command line over 32767 characters: 400 files with long
    names didn't start the player at all."""
    paths = _files(tmp_path, 400, name_len=120)
    args = _launch(paths, monkeypatch)
    assert args[:2] == ["/usr/bin/vlc", "--playlist-enqueue"] and len(args) == 3
    playlist = Path(args[2])
    assert playlist.suffix == ".m3u8"
    lines = playlist.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0] == "#EXTM3U" and lines[1:] == [p.replace("\\", "/") for p in paths]
