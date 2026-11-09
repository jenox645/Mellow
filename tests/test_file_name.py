"""FILE NAME: one download's own file name, typed in the Feed after ANALYZE."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yt_dlp

from mellow import downloader
from mellow.constants import FILENAME_MAX, WINDOWS_MAX_PATH

OUT = Path("/home/me/Downloads/MellowDLP")


@pytest.mark.parametrize("typed, saved", [
    ("My Song", "My Song"),
    ("Song: Live / Remix?", "Song： Live ⧸ Remix？"),     # as yt-dlp makes titles safe: no folders
    ("song.MP3", "song"),                                  # the download adds the real extension
    ("version 2.0", "version 2.0"),                        # a dot that isn't an extension stays
    ("  ..hidden. ", "hidden"),                            # no hidden file the vault would leave out
    ("CON", "_CON"),                                       # a name Windows refuses
    ("50% off", "50% off"),
])
def test_a_typed_name_is_made_safe(typed, saved):
    assert downloader.custom_file_name(typed, OUT, windows=False) == saved


@pytest.mark.parametrize("typed", ["", "   ", "...", ".mp4"])
def test_nothing_usable_means_the_templates_name(typed):
    assert downloader.custom_file_name(typed, OUT, windows=False) is None


def test_a_long_name_leaves_room_for_the_rest():
    long = downloader.custom_file_name("é" * 300, OUT, windows=False)
    assert len(long.encode()) < FILENAME_MAX - 48 and long == "é" * (len(long.encode()) // 2)
    win = downloader.custom_file_name("x" * 400, Path("C:/Users/me/Downloads"), windows=True)
    assert len("C:/Users/me/Downloads") + 1 + len(win) < WINDOWS_MAX_PATH - 48


def test_the_name_replaces_the_templates_file_name_but_not_its_folders():
    opts = {"filename_template": "%(uploader)s/%(title)s [%(id)s].%(ext)s"}
    assert downloader._output_template(opts, [], "50% off") == "%(uploader)s/50%% off%(mellow_dup|)s.%(ext)s"
    # Chapters: one file each, named after it
    assert downloader._output_template({}, [{"index": 1}], "Mix") == \
        "Mix - %(section_number)02d %(section_title)s.%(ext)s"


def _outtmpl(url, opts):
    ydl_opts, _ = downloader._build_ydl_opts(url, OUT, opts, ffmpeg=None, want_audio=False,
                                             embed_thumb=False, warn=lambda *a: None)
    return ydl_opts["outtmpl"]


def test_a_download_uses_it_and_a_playlist_doesnt():
    assert Path(_outtmpl("https://example.com/v", {"file_name": "Mine"})).name == "Mine%(mellow_dup|)s.%(ext)s"
    # Every item of a playlist would get the one name
    assert "Mine" not in _outtmpl("https://example.com/playlist?list=PL1", {"file_name": "Mine"})


def test_analyze_offers_the_templates_name():
    info = {"id": "abc", "title": "Song: Live", "ext": "webm", "uploader": "Me"}
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        assert downloader.default_file_name(ydl, info) == "Song： Live"
        assert downloader.default_file_name(ydl, info, "%(uploader)s/%(title)s [%(id)s].%(ext)s") == \
            "Song： Live [abc]"


def test_the_download_request_carries_it(client, tmp_path):
    from mellow import jobs
    with patch("mellow.downloader.download_video", return_value="success") as dl:
        r = client.post("/api/download", json={"url": "https://example.com/v", "file_name": "Mine",
                                               "output_dir": str(tmp_path)})
        assert r.status_code == 200
        assert jobs.manager.wait_idle(10)
    assert dl.call_args.args[2]["file_name"] == "Mine"
