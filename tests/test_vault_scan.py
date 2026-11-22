"""The vault's folder reads: what a folder card counts, what an open folder
lists and which thumbnails a card shows (one directory read per folder)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import pytest

from mellow import vault
from mellow.constants import THUMB_PREVIEW_LIMIT


def _write(path: Path, size: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def _symlink(link: Path, target: Path, is_dir: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError):
        pytest.skip("can't make symlinks here (Windows without developer mode)")


def test_a_card_counts_media_in_subfolders_but_not_parts_hidden_files_or_sidecars(tmp_path):
    root = tmp_path / "Mix"
    _write(root / "a.mp4", 10)
    _write(root / "a.jpg", 99)                      # sidecar
    _write(root / "a.en.srt", 99)                   # subtitles
    _write(root / ".hidden.mp4", 99)
    _write(root / "Title.f399.mp4", 99)             # yt-dlp part
    _write(root / "upper.MP3", 3)
    _write(root / "sub" / "b.mp3", 20)
    _write(root / "sub" / "deeper" / "c.webm", 5)
    (root / "folder.mp4").mkdir()                   # a folder with a media name
    assert vault.get_folder_media_stats(str(root)) == {"item_count": 4, "size_bytes": 38}


def test_a_linked_file_counts_a_linked_folder_is_not_followed(tmp_path):
    root, outside = tmp_path / "Mix", tmp_path / "elsewhere"
    _write(root / "a.mp4", 10)
    _write(outside / "big.mp4", 1000)
    _write(outside / "one.mp4", 7)
    _symlink(root / "linked.mp4", outside / "one.mp4")
    _symlink(root / "linked_dir", outside, is_dir=True)
    _symlink(root / "broken.mp4", tmp_path / "gone.mp4")
    assert vault.get_folder_media_stats(str(root)) == {"item_count": 2, "size_bytes": 17}


def test_an_unreadable_subfolder_is_left_out_not_the_whole_count(tmp_path, monkeypatch):
    root = tmp_path / "Mix"
    _write(root / "a.mp4", 10)
    _write(root / "locked" / "b.mp4", 20)
    _write(root / "open" / "c.mp4", 5)
    real = os.scandir

    def scandir(path):
        if Path(path).name == "locked":
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(vault.os, "scandir", scandir)
    assert vault.get_folder_media_stats(str(root)) == {"item_count": 2, "size_bytes": 15}


def test_a_missing_folder_counts_nothing(tmp_path):
    assert vault.get_folder_media_stats(str(tmp_path / "nope")) == {"item_count": 0, "size_bytes": 0}
    assert vault.list_folder_files(str(tmp_path / "nope")) == []
    assert vault.get_folder_previews(str(tmp_path / "nope")) == []


def test_an_open_folder_lists_its_own_media_files_in_name_order(tmp_path):
    root = tmp_path / "Mix"
    for name in ("b.mp3", "a.mp4", "C.webm", "a.jpg", ".x.mp4", "T.f251.webm"):
        _write(root / name, 4)
    _write(root / "sub" / "deep.mp4")
    (root / "folder.mp4").mkdir()
    # As typed, with a doubled separator: paths come back the way the rest of
    # the app writes them (history, config)
    files = vault.list_folder_files(str(root.parent) + os.sep + os.sep + root.name + os.sep)
    expected = sorted(["b.mp3", "a.mp4", "C.webm"], key=os.path.normcase)
    assert [f["name"] for f in files] == expected
    first = files[0]
    st = (root / first["name"]).stat()
    assert first == {"name": first["name"], "path": str(root / first["name"]), "size_bytes": 4,
                     "modified": st.st_mtime, "created": st.st_ctime,
                     "ext": Path(first["name"]).suffix.lower().lstrip(".")}


def test_a_card_shows_the_first_media_files_that_have_a_thumbnail(tmp_path):
    root = tmp_path / "Mix"
    names = [f"{i:02d} song" for i in range(THUMB_PREVIEW_LIMIT + 2)]
    for n in names:
        _write(root / f"{n}.mp3")
        _write(root / f"{n}.jpg")
    _write(root / "00 a no thumb.mp3")
    _write(root / "00 song.f251.webm")                        # a part with the same stem
    _write(root / "00 a folder.mp3")
    (root / "00 a folder.jpg").mkdir()                       # not a thumbnail
    previews = vault.get_folder_previews(str(root))
    assert previews == [f"/api/vault/thumb?path={quote(str(root / (n + '.jpg')))}"
                        for n in names[:THUMB_PREVIEW_LIMIT]]


@pytest.mark.parametrize("name", [
    "a.mp4", "A.MP4", "Title.f399.mp4", "Title.f251.webm", "Title.f140.m4a", "Title.fhls-720p.mp4",
    "Ferrari.f40.mp3", "Cars.f1.flac", ".hidden.mp4", "noext", "a.jpg", "a.", "x.f1.y.mp4",
])
def test_the_fast_name_check_agrees_with_is_media(name):
    # The vault's folder reads use the name check; everything else is_media()
    assert vault._is_media_name(name) == vault.is_media(Path(name))


# ── Folder stats (the open folder's STATS panel, /api/vault/folder-stats) ─────
# Pinned since #59: one os.scandir per folder (Windows lists size and mtime
# with the names), so it walks the folder on every call and keeps no cache.

def _stats_folder(tmp_path: Path) -> Path:
    root = tmp_path / "Mix"
    files = {
        "a.mp4": (10, 1_000), "upper.MP3": (3, 4_000),
        "sub/b.mp3": (20, 2_000), "sub/deeper/c.webm": (5, 3_000),
    }
    for rel, (size, mtime) in files.items():
        os.utime(_write(root / rel, size), (mtime, mtime))
    _write(root / "a.jpg", 99)                      # sidecar: a file, not media
    _write(root / "a.en.srt", 99)                   # subtitles: a file, not media
    _write(root / "Title.f399.mp4", 99)             # yt-dlp part: a file, not media
    _write(root / "Ferrari.f40.mp3", 7)             # a title, not a part (only mp4/webm/m4a parts)
    os.utime(root / "Ferrari.f40.mp3", (500, 500))
    _write(root / ".hidden.mp4", 99)                # hidden: not counted at all
    (root / "folder.mp4").mkdir()                   # a folder with a media name
    return root


def test_folder_stats_counts_sizes_formats_and_extremes(tmp_path):
    root = _stats_folder(tmp_path)
    assert vault.get_folder_stats(str(root), ["https://a", "https://b"]) == {
        "path": str(root),
        "file_count": 8,            # every non-hidden file, sidecars and parts too
        "media_count": 5,
        "video_count": 2,           # a.mp4, c.webm
        "audio_count": 3,           # upper.MP3, b.mp3, Ferrari.f40.mp3
        "total_size_bytes": 45,
        "avg_size_bytes": 9,        # int(45 / 5)
        "formats": {"mp4": 1, "mp3": 3, "webm": 1},  # lower-cased extensions
        "largest_file": {"name": "b.mp3", "size": 20},
        "smallest_file": {"name": "upper.MP3", "size": 3},
        "newest_file": {"name": "upper.MP3", "ts": 4_000},
        "oldest_file": {"name": "Ferrari.f40.mp3", "ts": 500},
        "linked_playlists": 2,
    }


def test_folder_stats_average_is_truncated_to_an_int(tmp_path):
    root = tmp_path / "Odd"
    for i, size in enumerate((10, 10, 10, 10, 8)):          # 48 / 5 = 9.6
        _write(root / f"{i}.mp3", size)
    avg = vault.get_folder_stats(str(root), [])["avg_size_bytes"]
    assert avg == 9 and type(avg) is int


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_folder_stats_does_not_follow_a_symlinked_folder(tmp_path):
    root = _stats_folder(tmp_path)
    elsewhere = tmp_path / "Elsewhere"
    _write(elsewhere / "far.mp4", 50)
    try:
        (root / "link").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not allowed here")
    stats = vault.get_folder_stats(str(root), [])
    assert (stats["file_count"], stats["media_count"]) == (8, 5)


def test_folder_stats_leaves_out_only_an_unreadable_subfolder(tmp_path, monkeypatch):
    root = _stats_folder(tmp_path)
    real_scandir = os.scandir
    locked = str(root / "sub")

    def scandir(path="."):
        if os.fspath(path) == locked:
            raise PermissionError(13, "Permission denied", locked)
        return real_scandir(path)

    monkeypatch.setattr(vault.os, "scandir", scandir)
    stats = vault.get_folder_stats(str(root), [])
    # sub/b.mp3 and sub/deeper/c.webm are behind the locked folder
    assert (stats["file_count"], stats["media_count"], stats["total_size_bytes"]) == (6, 3, 20)


def test_folder_stats_sees_a_file_added_or_removed_on_the_next_call(tmp_path):
    root = _stats_folder(tmp_path)
    assert vault.get_folder_stats(str(root), [])["media_count"] == 5
    _write(root / "sub" / "new.m4a", 100)
    after_add = vault.get_folder_stats(str(root), [])
    assert (after_add["media_count"], after_add["largest_file"]) == (6, {"name": "new.m4a", "size": 100})
    (root / "sub" / "new.m4a").unlink()
    (root / "a.mp4").unlink()
    after_delete = vault.get_folder_stats(str(root), [])
    assert (after_delete["media_count"], after_delete["video_count"]) == (4, 1)


def test_folder_stats_of_an_empty_or_missing_folder(tmp_path):
    (tmp_path / "Empty").mkdir()
    for path in (tmp_path / "Empty", tmp_path / "Gone"):
        stats = vault.get_folder_stats(str(path), [])
        assert (stats["file_count"], stats["media_count"], stats["total_size_bytes"],
                stats["avg_size_bytes"], stats["formats"]) == (0, 0, 0, 0, {})
        assert stats["largest_file"] is stats["smallest_file"] is None
        assert stats["newest_file"] is stats["oldest_file"] is None


def test_folder_stats_route_passes_the_folders_linked_playlists(client, tmp_path):
    from mellow.config import update_config
    root = _stats_folder(tmp_path)
    update_config(lambda c: c.update(vault_playlists={str(root): ["https://a"]}))
    r = client.get("/api/vault/folder-stats", query_string={"path": str(root)})
    assert r.status_code == 200
    assert (r.get_json()["media_count"], r.get_json()["linked_playlists"]) == (5, 1)
    missing = client.get("/api/vault/folder-stats", query_string={"path": str(tmp_path / "Gone")})
    assert missing.status_code == 400
