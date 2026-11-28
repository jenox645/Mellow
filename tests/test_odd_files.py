"""A vault folder people really have (#128): odd file names (emoji, #, %, quotes,
non-Latin, very long, a newline), zero-byte and broken files, read-only files.
Every vault route answers, lists every file and only media, and nothing breaks."""
import os
import stat
import sys
from pathlib import Path

import pytest

from mellow import vault
from mellow.config import update_config

ODD_NAMES = [
    "🎵 emoji song [dQw4w9WgXcQ].mp3",
    "hash #1 & 50% off.m4a",
    "a" * 200 + ".mp4",
    "Ünïcödé — дорога 日本.flac",
    "semi;colon,comma'quote\".webm" if sys.platform != "win32" else "semi;colon,comma'quote.webm",
    "trailing dot..mkv",
    "percent%20encoded.mp3",
    "plus+sign.opus",
]
NEWLINE_NAME = "line\nbreak.mp3"        # Linux and macOS allow it


@pytest.fixture
def odd_folder(tmp_path):
    root = tmp_path / "dl"
    folder = root / "Musique d'été 日本 #1 100%"
    folder.mkdir(parents=True)
    for name in ODD_NAMES:
        (folder / name).write_bytes(b"not really media " * 4)
    (folder / "zero.mp3").write_bytes(b"")
    (folder / "broken.mp4").write_bytes(b"\x00\x01")
    (folder / ".hidden.mp3").write_bytes(b"x")
    (folder / "🎵 emoji song [dQw4w9WgXcQ].jpg").write_bytes(b"\xff\xd8\xff\xd9")
    if sys.platform != "win32":
        (folder / NEWLINE_NAME).write_bytes(b"x" * 10)
    update_config(lambda c: c.update(output_dir=str(root)))
    return folder


def _media_names(folder):
    names = {*ODD_NAMES, "zero.mp3", "broken.mp4"}
    return names | ({NEWLINE_NAME} if sys.platform != "win32" else set())


def test_every_vault_route_answers_for_a_folder_of_odd_files(client, odd_folder):
    path = str(odd_folder)
    card = next(f for f in client.get("/api/vault").get_json()["folders"] if f["path"] == path)
    assert card["item_count"] == len(_media_names(odd_folder))
    files = client.get("/api/vault/folder", query_string={"path": path}).get_json()["files"]
    assert {f["name"] for f in files} == _media_names(odd_folder)
    for route, kwargs in [
        ("/api/vault/folder-previews", {"query_string": {"path": path}}),
        ("/api/vault/folder-stats", {"query_string": {"path": path}}),
        ("/api/vault/duplicates", {}),
        ("/api/vault/playlists", {"query_string": {"path": path}}),
    ]:
        assert client.get(route, **kwargs).status_code == 200, route
    assert client.post("/api/vault/file-thumbs", json={"paths": [f["path"] for f in files]}).status_code == 200
    assert client.post("/api/vault/archive-generate", json={"path": path}).status_code == 200
    stats = client.get("/api/vault/folder-stats", query_string={"path": path}).get_json()
    assert stats["media_count"] == len(files) and stats["smallest_file"]["size"] == 0


@pytest.mark.parametrize("name", [*ODD_NAMES, "zero.mp3", "broken.mp4"])
def test_each_odd_file_streams_to_the_player(client, odd_folder, name):
    data = (odd_folder / name).read_bytes()
    resp = client.get("/api/vault/stream", query_string={"path": str(odd_folder / name)},
                      headers={"Range": "bytes=0-3"} if data else {})
    assert resp.status_code == (206 if data else 200)
    assert resp.get_data() == data[:4]


@pytest.mark.skipif(sys.platform == "win32", reason="Windows file names can't hold a newline")
def test_a_file_name_with_a_newline_streams_too(client, odd_folder):
    resp = client.get("/api/vault/stream", query_string={"path": str(odd_folder / NEWLINE_NAME)},
                      headers={"Range": "bytes=0-1"})
    assert resp.status_code == 206 and resp.get_data() == b"xx"
    disposition = resp.headers["Content-Disposition"]
    assert "\n" not in disposition and "line break.mp3" in disposition


# ── Read-only files: Windows refuses to delete them ──────────────────────────

@pytest.fixture
def windows_like_unlink(monkeypatch):
    """Path.unlink as Windows does it: a file without write permission (the
    read-only attribute) can't be deleted (WinError 5)."""
    real = Path.unlink

    def unlink(self, missing_ok=False):
        try:
            mode = os.stat(self).st_mode
        except FileNotFoundError:
            return real(self, missing_ok=missing_ok)
        if not mode & stat.S_IWRITE:
            raise PermissionError(13, "Access is denied", str(self))
        return real(self, missing_ok=missing_ok)
    monkeypatch.setattr(Path, "unlink", unlink)


def test_a_read_only_file_and_its_sidecar_are_deleted(client, odd_folder, windows_like_unlink):
    song = odd_folder / "hash #1 & 50% off.m4a"
    thumb = song.with_suffix(".jpg")
    thumb.write_bytes(b"\xff\xd8\xff\xd9")
    for f in (song, thumb):
        f.chmod(stat.S_IREAD)
    resp = client.delete("/api/vault/file", json={"path": str(song)})
    assert resp.status_code == 200, resp.get_json()
    assert not song.exists() and not thumb.exists()


def test_a_file_refused_for_another_reason_still_says_so(client, odd_folder, monkeypatch):
    song = odd_folder / "plus+sign.opus"

    def locked(self, missing_ok=False):
        raise PermissionError(32, "The process cannot access the file: it is being used", str(self))
    monkeypatch.setattr(Path, "unlink", locked)
    resp = client.delete("/api/vault/file", json={"path": str(song)})
    assert resp.status_code == 500 and "being used" in resp.get_json()["error"]
    monkeypatch.undo()
    assert song.exists() and os.stat(song).st_mode & stat.S_IWRITE     # left as it was


def test_unlink_leaves_a_missing_sidecar_alone(tmp_path, windows_like_unlink):
    vault._unlink(tmp_path / "none.jpg", missing_ok=True)
    with pytest.raises(FileNotFoundError):
        vault._unlink(tmp_path / "none.jpg")
