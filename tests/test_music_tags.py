"""Music tags: album, track number and artist for audio downloads and re-tags."""
import shutil
import subprocess

import pytest

from mellow import music_tags


@pytest.mark.parametrize("channel,artist", [
    ("Rick Astley - Topic", "Rick Astley"),
    ("RickAstleyVEVO", "Rick Astley"),
    ("Taylor Swift VEVO", "Taylor Swift"),
    ("acdcVEVO", "acdc"),
    ("Lofi Girl", "Lofi Girl"),
    ("VEVO", "VEVO"),                 # nothing left to call the artist: unchanged
    ("Daft Punk - Topical", "Daft Punk - Topical"),
    ("", ""), (None, None),
])
def test_clean_artist(channel, artist):
    assert music_tags.clean_artist(channel) == artist


def test_a_playlist_item_becomes_a_track_of_the_playlist_album():
    info = {"title": "Song", "uploader": "Rick Astley - Topic", "playlist_title": "Chill Mix", "playlist_index": 7}
    assert music_tags.tags_for(info) == {
        "album": "Chill Mix", "track": "7", "album_artist": "Various Artists", "artist": "Rick Astley"}


def test_a_real_album_keeps_its_own_album_and_numbers():
    info = {"album": "Whenever You Need Somebody", "track_number": 1, "artist": "Rick Astley",
            "playlist_title": "Chill Mix", "playlist_index": 7, "uploader": "Rick Astley - Topic"}
    assert music_tags.tags_for(info) == {}


def test_a_single_video_gets_no_album():
    assert music_tags.tags_for({"title": "Song", "uploader": "Lofi Girl"}) == {}
    assert music_tags.tags_for({"title": "Song", "uploader": "RickAstleyVEVO"}) == {"artist": "Rick Astley"}


def test_the_postprocessor_hands_the_tags_to_the_metadata_step():
    info = {"playlist": "Chill Mix", "playlist_index": 2, "uploader": "Somebody"}
    _, out = music_tags.MusicTagsPP(None).run(info)
    assert out["meta_album"] == "Chill Mix" and out["meta_track"] == "2"
    assert "meta_artist" not in out


# ── Re-tag ───────────────────────────────────────────────────────────────────

def _audio(path, **tags):
    """A one-second file with these tags, made by ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("needs ffmpeg")
    meta = [arg for k, v in tags.items() for arg in ("-metadata", f"{k}={v}")]
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", *meta, str(path)],
                   check=True)
    return path


def _read(path):
    import mutagen
    audio = mutagen.File(str(path), easy=True)
    return {k: v[0] for k, v in (audio.tags or {}).items()}


@pytest.mark.parametrize("ext", [".mp3", ".m4a", ".opus", ".flac"])
def test_retag_writes_album_track_and_cleans_the_artist(tmp_path, ext):
    f = _audio(tmp_path / f"song{ext}", title="Song", artist="RickAstleyVEVO")
    assert music_tags.retag_file(f, "Chill Mix", 3)
    tags = _read(f)
    assert tags["album"] == "Chill Mix" and tags["tracknumber"].split("/")[0] == "3"
    assert tags["albumartist"] == "Various Artists" and tags["artist"] == "Rick Astley"
    assert tags["title"] == "Song"
    assert not music_tags.retag_file(f, "Chill Mix", 3)        # again: nothing to change


def test_retag_keeps_a_real_album(tmp_path):
    f = _audio(tmp_path / "song.mp3", album="Whenever You Need Somebody", track="1", artist="Rick Astley")
    assert not music_tags.retag_file(f, "Chill Mix", 9)
    assert _read(f)["album"] == "Whenever You Need Somebody" and _read(f)["tracknumber"] == "1"


def test_retag_folder_counts_and_leaves_videos_alone(tmp_path):
    _audio(tmp_path / "a.mp3", title="A")
    _audio(tmp_path / "b.mp3", title="B")
    _audio(tmp_path / "c.wav", title="C")
    (tmp_path / "clip.mp4").write_bytes(b"not really a video")
    (tmp_path / "notes.txt").write_text("hi")
    result = music_tags.retag_folder(tmp_path, "Chill Mix", {"a.mp3": 2, "b.mp3": 1})
    assert result == {"tagged": 2, "unchanged": 0, "skipped": 2, "failed": 0}
    assert _read(tmp_path / "a.mp3")["tracknumber"] == "2" and _read(tmp_path / "b.mp3")["tracknumber"] == "1"
    # The playlist order changed: the numbers follow it
    result = music_tags.retag_folder(tmp_path, "Chill Mix", {"a.mp3": 1, "b.mp3": 2})
    assert result["tagged"] == 2 and _read(tmp_path / "a.mp3")["tracknumber"] == "1"


# ── Re-tag a vault folder: matching files to the playlist ───────────────────

def _playlist(*ids, title="Chill Mix"):
    return [{"title": title, "entries": [{"id": i, "url": f"https://www.youtube.com/watch?v={i}"} for i in ids]}]


def _record(path, vid, url=None):
    from mellow import analytics
    analytics.record_download({"url": url or f"https://www.youtube.com/watch?v={vid}", "title": path.stem,
                               "file_path": str(path), "format": "audio", "status": "success",
                               "video_id": vid})


def test_retag_numbers_follow_the_playlists_current_order(tmp_path):
    from unittest.mock import patch

    from mellow import vault
    a = _audio(tmp_path / "Song A.mp3")
    b = _audio(tmp_path / "Song B.mp3")
    c = _audio(tmp_path / "Song C [cccccccccc3].mp3")      # no history: its [id] matches
    _record(a, "aaaaaaaaaa1")
    _record(b, "bbbbbbbbbb2")
    with patch.object(vault, "_read_playlists", return_value=(_playlist("aaaaaaaaaa1", "bbbbbbbbbb2", "cccccccccc3"), [])):
        result = vault.retag(str(tmp_path), ["https://youtube.com/playlist?list=PL1"])
    assert result["numbered"] == 3 and result["tagged"] == 3 and result["album"] == "Chill Mix"
    assert [_read(f)["tracknumber"] for f in (a, b, c)] == ["1", "2", "3"]
    # Reordered on YouTube: RE-TAG renumbers
    with patch.object(vault, "_read_playlists", return_value=(_playlist("cccccccccc3", "aaaaaaaaaa1", "bbbbbbbbbb2"), [])):
        vault.retag(str(tmp_path), ["https://youtube.com/playlist?list=PL1"])
    assert [_read(f)["tracknumber"] for f in (a, b, c)] == ["2", "3", "1"]


def test_retag_writes_nothing_when_the_playlist_cant_be_read(tmp_path):
    from unittest.mock import patch

    from mellow import vault
    a = _audio(tmp_path / "Song A.mp3")
    with patch.object(vault, "_read_playlists", return_value=([], ["https://youtube.com/playlist?list=PL1"])):
        result = vault.retag(str(tmp_path), ["https://youtube.com/playlist?list=PL1"])
    assert "error" in result and "album" not in _read(a)


def test_retag_without_a_playlist_uses_the_folder_name_and_no_numbers(tmp_path):
    from mellow import vault
    folder = tmp_path / "Road Trip"
    folder.mkdir()
    a = _audio(folder / "Song A.mp3", artist="Lofi Girl - Topic")
    result = vault.retag(str(folder), [])
    assert result["album"] == "Road Trip" and result["numbered"] == 0
    tags = _read(a)
    assert tags["album"] == "Road Trip" and "tracknumber" not in tags and tags["artist"] == "Lofi Girl"


def test_a_page_url_shared_by_several_files_matches_none_of_them(tmp_path):
    from unittest.mock import patch

    from mellow import vault
    a = _audio(tmp_path / "One.mp3")
    b = _audio(tmp_path / "Two.mp3")
    page = "https://example.com/mix"
    _record(a, None, url=page)
    _record(b, None, url=page)
    entries = [{"title": "Mix", "entries": [{"id": "x-1", "webpage_url": page}, {"id": "x-2", "webpage_url": page}]}]
    with patch.object(vault, "_read_playlists", return_value=(entries, [])):
        result = vault.retag(str(tmp_path), [page])
    assert result["numbered"] == 0 and result["tagged"] == 2     # album yes, a made-up order no
