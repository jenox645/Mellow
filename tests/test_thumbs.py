"""The vault's thumbnails, served at once (#126): small cached copies, ffmpeg only in a background
pool, the window's HTTP cache. mellow/thumbs.py and /api/vault/thumb."""
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mellow import thumbs, vault
from mellow.constants import THUMB_CACHE_SECS, THUMB_SMALL_MIN_BYTES

BIG = b"\xff\xd8\xff\xe0" + b"a download's 1280 px sidecar" * 4000          # > THUMB_SMALL_MIN_BYTES
SMALL = b"\xff\xd8\xff\xe0" + b"its 480 px copy" * 100
FRAME = b"\xff\xd8\xff\xe0" + b"a frame" * 100
assert len(BIG) > THUMB_SMALL_MIN_BYTES > len(SMALL)


@pytest.fixture(autouse=True)
def _quiet_pool():
    vault._thumb_failed.clear()
    thumbs.pool.clear()
    yield
    thumbs.pool.clear()
    assert thumbs.pool.idle(10)
    vault._thumb_failed.clear()


@pytest.fixture
def ffmpeg():
    """ffmpeg "there", answering like vault's calls expect: a frame written to the file it's told,
    a picture piped back small."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[-1] == "pipe:1":
            return subprocess.CompletedProcess(cmd, 0, stdout=SMALL, stderr=b"")
        Path(cmd[-1]).write_bytes(FRAME)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.thumbs.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run", side_effect=run):
        yield calls


def _sidecar(folder: Path, name: str, data: bytes = BIG) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / f"{name}.mp4"
    video.write_bytes(b"\0" * 64)
    side = folder / f"{name}.jpg"
    side.write_bytes(data)
    return video, side


def test_a_big_sidecar_is_sent_now_and_its_small_copy_from_then_on(tmp_path, ffmpeg):
    video, side = _sidecar(tmp_path / "v", "clip")
    first = thumbs.serve(str(video))
    assert (first.data, first.final) == (BIG, False)             # at once: no waiting for ffmpeg
    assert thumbs.pool.idle(5)
    second = thumbs.serve(str(video))
    assert (second.data, second.mime, second.final) == (SMALL, "image/jpeg", True)
    assert second.etag != first.etag
    assert thumbs.serve(str(side)) == second                     # asked for by the sidecar's own path too
    assert len([c for c in ffmpeg if c[-1] == "pipe:1"]) == 1    # made once


def test_a_changed_sidecar_is_a_new_picture_not_the_old_small_copy(tmp_path, ffmpeg):
    video, side = _sidecar(tmp_path / "v", "clip")
    thumbs.serve(str(video))
    assert thumbs.pool.idle(5)
    old = thumbs.serve(str(video))
    assert old.data == SMALL
    side.write_bytes(BIG + b"again")
    os.utime(side, ns=(time.time_ns(), time.time_ns() + 10**9))
    new = thumbs.serve(str(video))
    assert (new.data, new.final) == (BIG + b"again", False) and new.etag != old.etag


def test_a_small_sidecar_is_sent_as_it_is(tmp_path, ffmpeg):
    video, _ = _sidecar(tmp_path / "v", "clip", SMALL)
    got = thumbs.serve(str(video))
    assert (got.data, got.final) == (SMALL, True)
    assert thumbs.pool.idle(5) and ffmpeg == []


def test_without_ffmpeg_a_big_sidecar_is_sent_as_it_is_for_good(tmp_path):
    video, _ = _sidecar(tmp_path / "v", "clip")
    with patch("mellow.thumbs.find_ffmpeg", return_value=None), patch("mellow.vault.find_ffmpeg", return_value=None):
        got = thumbs.serve(str(video))
    assert (got.data, got.final) == (BIG, True)


def test_a_videos_frame_is_made_in_the_background_never_in_the_request(tmp_path, ffmpeg):
    folder = tmp_path / "v"
    folder.mkdir()
    clip = folder / "clip.mkv"
    clip.write_bytes(b"\x1a\x45\xdf\xa3" * 10)
    assert thumbs.serve(str(clip)) == thumbs.PENDING
    assert thumbs.pool.idle(5)
    got = thumbs.serve(str(clip))
    assert (got.data, got.final) == (FRAME, True)                # the frame, now a sidecar
    assert (folder / "clip.jpg").read_bytes() == FRAME


def test_a_file_with_no_picture_is_tried_once(tmp_path):
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"\x1a\x45\xdf\xa3" * 10)
    failing = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"no")
    with patch("mellow.vault.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.thumbs.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault.subprocess.run", return_value=failing) as run:
        assert thumbs.serve(str(clip)) == thumbs.PENDING
        assert thumbs.pool.idle(5)
        assert thumbs.serve(str(clip)) is None
        assert thumbs.serve(str(clip)) is None
    assert run.call_count == 2                                   # the frame 30 s in, then from the start


def test_the_pool_does_the_newest_first_and_what_cards_wait_for_before_smaller_copies():
    pool = thumbs.Pool(workers=1)
    gate, done = threading.Event(), []
    pool.submit(("gate",), gate.wait)
    time.sleep(0.05)                                             # the one worker is busy
    for key, needed in (("small a", False), ("frame 1", True), ("frame 2", True), ("small b", False),
                        ("frame 3", True)):
        pool.submit((key,), lambda k=key: done.append(k), needed=needed)
    pool.submit(("frame 1",), lambda: done.append("frame 1 again"))   # on screen again: to the front
    pool.submit(("gate",), lambda: done.append("gate twice"))         # running: not added again
    gate.set()
    assert pool.idle(5)
    assert done == ["frame 1", "frame 3", "frame 2", "small b", "small a"]


def test_the_pool_forgets_the_oldest_jobs_past_its_limit():
    pool = thumbs.Pool(workers=1, limit=3)
    gate, done = threading.Event(), []
    pool.submit(("gate",), gate.wait)
    time.sleep(0.05)
    for i in range(6):
        pool.submit((i,), lambda i=i: done.append(i))
    gate.set()
    assert pool.idle(5)
    assert done == [5, 4, 3]                                     # 0-2 were scrolled past


def test_the_route_sends_a_placeholder_while_a_picture_is_made(client, tmp_path):
    clip = tmp_path / "clip.mkv"
    clip.write_bytes(b"\x1a\x45\xdf\xa3" * 10)
    started, release = threading.Event(), threading.Event()

    def slow(media, out):
        started.set()
        release.wait(10)
        return False
    with patch("mellow.thumbs.find_ffmpeg", return_value="/usr/bin/ffmpeg"), \
            patch("mellow.vault._generate_thumb", side_effect=slow):
        t = time.perf_counter()
        r = client.get(f"/api/vault/thumb?path={clip}")
        assert time.perf_counter() - t < 1
        assert (r.status_code, r.mimetype, r.headers["Cache-Control"]) == (202, "image/gif", "no-store")
        assert r.data.startswith(b"GIF89a")
        assert started.wait(5)
        # The server answers everything else meanwhile, the same picture included
        t = time.perf_counter()
        assert client.get("/api/queue/status").status_code == 200
        assert client.get(f"/api/vault/thumb?path={clip}").status_code == 202
        assert time.perf_counter() - t < 1
        release.set()
        assert thumbs.pool.idle(5)
    assert client.get(f"/api/vault/thumb?path={clip}").status_code == 404     # it had none


def test_a_kept_picture_is_checked_with_its_etag(client, tmp_path, ffmpeg):
    video, _ = _sidecar(tmp_path / "v", "clip", SMALL)
    r = client.get(f"/api/vault/thumb?path={video}")
    assert r.status_code == 200 and r.data == SMALL
    assert r.headers["Cache-Control"] == f"private, max-age={THUMB_CACHE_SECS}"
    again = client.get(f"/api/vault/thumb?path={video}", headers={"If-None-Match": r.headers["ETag"]})
    assert (again.status_code, again.data) == (304, b"")


def test_a_picture_whose_small_copy_is_being_made_is_checked_every_time(client, tmp_path, ffmpeg):
    video, _ = _sidecar(tmp_path / "v", "clip")
    r = client.get(f"/api/vault/thumb?path={video}")
    assert r.data == BIG and r.headers["Cache-Control"] == "private, no-cache"
    assert thumbs.pool.idle(5)
    again = client.get(f"/api/vault/thumb?path={video}", headers={"If-None-Match": r.headers["ETag"]})
    assert (again.status_code, again.data) == (200, SMALL)


def test_thumbnail_urls_carry_the_files_version(tmp_path):
    video, side = _sidecar(tmp_path / "v", "clip")
    url = vault.thumb_url(side)
    assert url.endswith(f"&v={side.stat().st_mtime_ns}")
    side.write_bytes(BIG + b"!")
    os.utime(side, ns=(time.time_ns(), time.time_ns() + 10**9))
    assert vault.thumb_url(side) != url
    assert vault.resolve_file_thumbs([str(video)], lambda: None) == {str(video): vault.thumb_url(side)}

