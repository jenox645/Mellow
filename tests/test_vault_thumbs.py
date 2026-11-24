"""Vault thumbnails without a sidecar (#109): the cover inside an audio file read with mutagen (no ffmpeg
needed), ffmpeg as the fallback, the per-user cache for folders the app can't write to, and the formats
the vault lists."""
import base64
import os
import shutil
import struct
import subprocess
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import pytest

from mellow import covers, datadir, thumb_cache, vault
from mellow.constants import MEDIA_EXTS, THUMB_PREVIEW_LIMIT, VIDEO_EXTS

JPEG = b"\xff\xd8\xff\xe0" + b"front cover" * 10
BACK = b"\xff\xd8\xff\xe0" + b"back cover" * 10
PNG = b"\x89PNG\r\n\x1a\n" + b"png cover" * 10

# Encoders for a one-second file of each format (ffmpeg's lavfi sine)
ENCODE = {
    ".flac": ["-c:a", "flac"], ".mp3": ["-c:a", "libmp3lame"], ".m4a": ["-c:a", "aac"],
    ".m4b": ["-c:a", "aac", "-f", "ipod"], ".opus": ["-c:a", "libopus"], ".ogg": ["-c:a", "libvorbis"],
    ".aiff": ["-c:a", "pcm_s16be"], ".wma": ["-c:a", "wmav2"], ".wav": ["-c:a", "pcm_s16le"],
}


@pytest.fixture
def music(tmp_path):
    """A folder of this test's own (tmp_path also holds the app's isolated config, DB and cache)."""
    folder = tmp_path / "music"
    folder.mkdir()
    return folder


@pytest.fixture(autouse=True)
def _fresh():
    vault._thumb_failed.clear()
    yield
    vault._thumb_failed.clear()


def _audio(path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("needs ffmpeg to make the audio files")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", *ENCODE[path.suffix],
                    str(path)], check=True)
    return path


def _picture(data: bytes, kind: int = covers.FRONT_COVER, mime: str = "image/jpeg"):
    from mutagen.flac import Picture
    pic = Picture()
    pic.type, pic.mime, pic.data = kind, mime, data
    return pic


def _with_cover(path: Path, data: bytes = JPEG) -> Path:
    """Put `data` into the file as its cover, the way each format keeps one."""
    import mutagen
    ext = path.suffix
    if ext == ".flac":
        from mutagen.flac import FLAC
        f = FLAC(path)
        f.add_picture(_picture(BACK, kind=4))            # a back cover first: the front one must win
        f.add_picture(_picture(data))
        f.save()
    elif ext in (".mp3", ".aiff", ".wav"):
        from mutagen.id3 import APIC
        f = mutagen.File(path)
        if f.tags is None:
            f.add_tags()
        f.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="cover", data=data))
        f.save()
    elif ext in (".m4a", ".m4b"):
        from mutagen.mp4 import MP4, MP4Cover
        f = MP4(path)
        f["covr"] = [MP4Cover(data, imageformat=MP4Cover.FORMAT_JPEG)]
        f.save()
    elif ext in (".opus", ".ogg"):
        f = mutagen.File(path)
        f["metadata_block_picture"] = [base64.b64encode(_picture(data).write()).decode()]
        f.save()
    elif ext == ".wma":
        from mutagen.asf import ASF, ASFByteArrayAttribute
        f = ASF(path)
        mime, desc = "image/jpeg".encode("utf-16-le") + b"\0\0", b"\0\0"
        f["WM/Picture"] = [ASFByteArrayAttribute(bytes([3]) + struct.pack("<I", len(data)) + mime + desc + data)]
        f.save()
    return path


@pytest.mark.parametrize("ext", [".flac", ".mp3", ".m4a", ".m4b", ".opus", ".ogg", ".aiff", ".wav", ".wma"])
def test_an_audio_files_own_cover_is_its_thumbnail_without_ffmpeg(music, ext):
    song = _with_cover(_audio(music / ("song" + ext)))
    with patch("mellow.vault.find_ffmpeg", return_value=None), \
            patch("mellow.vault.subprocess.run") as run:
        assert vault.get_thumb_bytes(str(song)) == (JPEG, "image/jpeg")
    run.assert_not_called()
    # Nothing is added to the music folder: the picture is in the file, the thumbnail in the cache
    assert sorted(p.name for p in music.iterdir()) == [song.name]
    assert len(list(thumb_cache.folder().iterdir())) == 1


def test_a_png_cover_and_the_old_coverart_comment(music):
    flac = _audio(music / "a.flac")
    from mutagen.flac import FLAC
    f = FLAC(flac)
    f.add_picture(_picture(PNG, mime="image/jpeg"))     # a tag's MIME is often wrong: the bytes decide
    f.save()
    assert vault.get_thumb_bytes(str(flac)) == (PNG, "image/png")
    ogg = _audio(music / "b.ogg")
    from mutagen.oggvorbis import OggVorbis
    f = OggVorbis(ogg)
    f["coverart"] = [base64.b64encode(JPEG).decode()]
    f.save()
    assert vault.get_thumb_bytes(str(ogg)) == (JPEG, "image/jpeg")


def test_no_cover_means_no_ffmpeg_and_no_retry(music):
    song = _audio(music / "plain.flac")
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run") as run, \
            patch("mellow.covers.embedded_cover", wraps=covers.embedded_cover) as read:
        assert vault.get_thumb_bytes(str(song)) is None
        assert vault.get_thumb_bytes(str(song)) is None
    run.assert_not_called()          # mutagen read the tags: there is no cover for ffmpeg to find
    assert read.call_count == 1
    assert not vault.has_thumb(song)


def _fake_ffmpeg(out_bytes=JPEG):
    """subprocess.run as ffmpeg: writes a jpg at the command's last argument, or to stdout for a pipe."""
    def run(cmd, **kw):
        if cmd[-1] == "pipe:1":
            return subprocess.CompletedProcess(cmd, 0, stdout=out_bytes, stderr=b"")
        Path(cmd[-1]).write_bytes(out_bytes)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
    return run


def test_a_file_mutagen_cant_read_falls_back_to_ffmpeg(music):
    mka = music / "live.mka"
    mka.write_bytes(b"\x1a\x45\xdf\xa3 not much of a matroska file")
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run", side_effect=_fake_ffmpeg()) as run:
        assert vault.get_thumb_bytes(str(mka)) == (JPEG, "image/jpeg")
    assert "0:v:0" in run.call_args[0][0]               # the cover: the file's first picture stream
    assert sorted(p.name for p in music.iterdir()) == ["live.mka"]


def test_a_big_cover_is_scaled_down_when_ffmpeg_is_there(music):
    big = JPEG + b"x" * 300_000
    song = _with_cover(_audio(music / "big.mp3"), big)
    with patch("mellow.vault.find_ffmpeg", return_value=None):
        assert vault.get_thumb_bytes(str(song)) == (big, "image/jpeg")       # as it is
    for f in thumb_cache.folder().iterdir():
        f.unlink()
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run", side_effect=_fake_ffmpeg(JPEG)) as run:
        assert vault.get_thumb_bytes(str(song)) == (JPEG, "image/jpeg")
    assert run.call_args[1]["input"] == big


def test_a_video_frame_is_a_sidecar_or_cached_when_the_folder_is_read_only(music, monkeypatch):
    clip = music / "clip.ts"
    clip.write_bytes(b"G" * 376)
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run", side_effect=_fake_ffmpeg()):
        assert vault.get_thumb_bytes(str(clip)) == (JPEG, "image/jpeg")
    assert (music / "clip.jpg").read_bytes() == JPEG     # next to it, as a download's would be

    ro = music / "ro"
    ro.mkdir()
    other = ro / "other.wmv"
    other.write_bytes(b"0&\xb2u" * 10)
    real_write = Path.write_bytes

    def refuse(self, data):
        if self.parent == ro:
            raise PermissionError(13, "Read-only file system", str(self))
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", refuse)
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run", side_effect=_fake_ffmpeg()) as run:
        assert vault.get_thumb_bytes(str(other)) == (JPEG, "image/jpeg")
        assert vault.get_thumb_bytes(str(other)) == (JPEG, "image/jpeg")
    assert run.call_count == 1                   # the second came from the cache
    assert list(ro.iterdir()) == [other]
    assert vault.has_thumb(other)


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs a folder this account can't write to (root writes anywhere)")
def test_a_really_read_only_folder_gets_its_covers_from_the_cache(music):
    folder = music / "mounted"
    song = _with_cover(_audio(folder / "song.flac"))
    folder.chmod(0o555)
    try:
        with patch("mellow.vault.find_ffmpeg", return_value=None):
            assert vault.get_thumb_bytes(str(song)) == (JPEG, "image/jpeg")
        assert len(list(thumb_cache.folder().iterdir())) == 1
    finally:
        folder.chmod(0o755)


def test_a_changed_file_gets_a_new_thumbnail(music):
    song = _with_cover(_audio(music / "s.mp3"))
    assert vault.get_thumb_bytes(str(song))[0] == JPEG
    _with_cover(song, BACK)
    os.utime(song, (1, 1))                       # another mtime: another cache entry
    assert vault.get_thumb_bytes(str(song))[0] == BACK


def test_the_cache_drops_its_oldest_thumbnails_past_its_size():
    folder = thumb_cache.folder()
    folder.mkdir(parents=True)
    for i in range(10):
        f = folder / f"{i:02d}.jpg"
        f.write_bytes(b"x" * 100)
        os.utime(f, (1000 + i, 1000 + i))
    assert thumb_cache.prune(max_bytes=600) == 6            # down to 80 % (480 bytes): 400 left
    assert sorted(p.name for p in folder.iterdir()) == [f"{i:02d}.jpg" for i in range(6, 10)]
    assert thumb_cache.prune(max_bytes=600) == 0


def test_a_folder_card_shows_the_covers_inside_its_files(music):
    root = music / "Flacs"
    names = [f"{i:02d} song.flac" for i in range(THUMB_PREVIEW_LIMIT + 1)]
    _audio(root / "00 a no cover.flac")
    for n in names:
        _with_cover(_audio(root / n))
    with patch("mellow.vault.find_ffmpeg", return_value=None):
        previews = vault.get_folder_previews(str(root))
    assert previews == [f"/api/vault/thumb?path={quote(str(root / n))}" for n in names[:THUMB_PREVIEW_LIMIT]]


def test_the_vault_lists_every_format_ffmpeg_reads(music):
    new = [".mka", ".m4b", ".aiff", ".aif", ".wma", ".ts", ".m2ts", ".3gp", ".flv", ".wmv"]
    assert set(new) <= MEDIA_EXTS
    assert {".ts", ".m2ts", ".3gp", ".flv", ".wmv"} <= VIDEO_EXTS
    for ext in new:
        (music / ("file" + ext)).write_bytes(b"\0" * 8)
    assert sorted(f["ext"] for f in vault.list_folder_files(str(music))) == sorted(e[1:] for e in new)


def test_a_wm_picture_is_read_from_its_layout():
    mime = "image/png".encode("utf-16-le") + b"\0\0"
    raw = bytes([3]) + struct.pack("<I", len(PNG)) + mime + "front".encode("utf-16-le") + b"\0\0" + PNG
    assert covers._asf_picture(raw) == (3, PNG)
    assert covers._asf_picture(raw[:-1]) is None            # cut short
    assert covers._asf_picture(b"\x03") is None


@pytest.mark.parametrize("data,mime", [(JPEG, "image/jpeg"), (PNG, "image/png"), (b"GIF89a..", "image/gif"),
                                       (b"RIFF\0\0\0\0WEBPVP8 ", "image/webp"), (b"BM....", None), (b"", None)])
def test_a_pictures_bytes_say_what_it_is(data, mime):
    assert covers.sniff_mime(data) == mime


def test_the_cache_folder_follows_each_systems_convention(monkeypatch):
    # conftest replaces datadir.cache_dir for every test: load the module's own, as a separate copy
    import importlib.util
    spec = importlib.util.spec_from_file_location("datadir_copy", datadir.__file__)
    own = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(own)
    if os.name == "nt":
        assert own.cache_dir({"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}) == \
            Path(r"C:\Users\me\AppData\Local\MellowDLP\Cache")
        return
    monkeypatch.setattr(own.sys, "platform", "linux")
    assert own.cache_dir({"HOME": "/home/me", "XDG_CACHE_HOME": "/xdg/cache"}) == Path("/xdg/cache/mellowdlp")
    assert own.cache_dir({"HOME": "/home/me"}) == Path("/home/me/.cache/mellowdlp")
    monkeypatch.setattr(own.sys, "platform", "darwin")
    assert own.cache_dir({"HOME": "/Users/me"}) == Path("/Users/me/Library/Caches/MellowDLP")
