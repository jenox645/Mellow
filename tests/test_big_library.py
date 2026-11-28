"""A big library stays fast (#127): what scripts/route_bench.py found slow on
20,000 files / 50,000 history rows, pinned by its number of queries or calls."""
import contextlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mellow import analytics, scheduler, vault
from mellow.config import load_config, update_config

ROOT = Path(__file__).resolve().parents[1]
EMPTY_REPORT = {"added": [], "failed": [], "filtered": [], "archived": 0}


def _write(path: Path, size: int = 8) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


# ── The vault's cards: the linked folders' sync troubles in one query ────────

def _linked_folders(tmp_path, n):
    root = tmp_path / "dl"
    folders = [str(root / f"Mix {k:02d}") for k in range(n)]
    for f in folders:
        _write(Path(f) / "a.mp3")
    update_config(lambda c: c.update(output_dir=str(root), auto_sync_enabled=True,
                                     vault_playlists={f: ["https://x/pl"] for f in folders}))
    return root, folders


def test_the_cards_read_every_folders_sync_reports_in_one_query(tmp_path, monkeypatch):
    root, folders = _linked_folders(tmp_path, 30)
    for f in folders[::3]:
        for _ in range(2):
            analytics.record_sync_report(f, "failed", EMPTY_REPORT, 1)
    calls = []
    real = analytics.recent_sync_outcomes_of
    monkeypatch.setattr(analytics, "recent_sync_outcomes_of", lambda fs: calls.append(fs) or real(fs))
    monkeypatch.setattr(analytics, "recent_sync_outcomes",
                        lambda f: pytest.fail("one query per folder"))
    cards = {c["path"]: c for c in vault.build_folder_list(str(root), load_config())}
    assert len(calls) == 1 and sorted(calls[0]) == sorted(folders)
    assert [p for p in folders if cards[p].get("sync_failures") == 2] == folders[::3]
    assert all("sync_failures" not in cards[p] for p in folders if p not in folders[::3])


def test_many_folders_outcomes_match_one_folders(tmp_path):
    a, b, c = "/music/A", "/music/B", "/music/C"
    for folder, status in [(a, "completed"), (b, "failed"), (a, "failed"), (b, "cancelled"), (a, "failed")]:
        analytics.record_sync_report(folder, status, EMPTY_REPORT, 1)
    many = analytics.recent_sync_outcomes_of([a, b, c])
    assert set(many) == {a, b}
    for folder in (a, b, c):
        assert [s for s, _ in many.get(folder, [])] == [s for s, _ in analytics.recent_sync_outcomes(folder)]
    assert [s for s, _ in many[a]] == ["failed", "failed", "completed"]       # newest first
    assert analytics.recent_sync_outcomes_of([]) == {}
    for folder in (a, b):
        assert scheduler.hold_off(folder, 86400, many[folder])[1] == scheduler.hold_off(folder, 86400)[1]


# ── The files of one folder the history knows: only that folder's rows ──────

def _record(path: Path, video_id: str) -> None:
    analytics.record_download({"url": f"https://www.youtube.com/watch?v={video_id}", "title": path.stem,
                               "status": "success", "file_path": str(path), "video_id": video_id})


def test_the_history_of_a_folder_reads_only_that_folders_rows(tmp_path, monkeypatch):
    music = tmp_path / "Music"
    _record(_write(music / "a [aaaaaaaaaaa].mp3"), "aaaaaaaaaaa")
    _record(_write(music / "50%_off [bbbbbbbbbbb].mp3"), "bbbbbbbbbbb")
    _record(_write(tmp_path / "Music2" / "c [ccccccccccc].mp3"), "ccccccccccc")   # a longer name, same start
    _record(_write(music / "sub" / "d [ddddddddddd].mp3"), "ddddddddddd")        # a subfolder's
    _record(music / "gone [eeeeeeeeeee].mp3", "eeeeeeeeeee")                     # deleted since
    for k in range(200):
        _record(tmp_path / "Elsewhere" / f"x{k}.mp3", f"x{k:010d}")
    made = []
    real_path = vault.Path

    def counting_path(*args):
        made.append(args)
        return real_path(*args)
    monkeypatch.setattr(vault, "Path", counting_path)
    assert vault._history_ids_in(music) == {"aaaaaaaaaaa": "a [aaaaaaaaaaa].mp3",
                                            "bbbbbbbbbbb": "50%_off [bbbbbbbbbbb].mp3"}
    assert len(made) <= 5      # the rows under Music only, not all 205


def test_the_history_of_a_folder_with_a_special_character_in_its_name(tmp_path):
    folder = tmp_path / "Lo'fi_100%"
    _record(_write(folder / "a [aaaaaaaaaaa].mp3"), "aaaaaaaaaaa")
    _record(_write(tmp_path / "Lo'fiX100%" / "b [bbbbbbbbbbb].mp3"), "bbbbbbbbbbb")
    assert vault._history_ids_in(folder) == {"aaaaaaaaaaa": "a [aaaaaaaaaaa].mp3"}


# ── DUPES: one listing per folder, no stat or Path per file ───────────────────

@contextlib.contextmanager
def _counting(monkeypatch, *targets):
    """Record the calls of each (owner, name) while the block runs; undone after
    it, so a failure is reported with the real ones in place."""
    calls = []
    with monkeypatch.context() as m:
        for owner, name in targets:
            real = getattr(owner, name, None) or getattr(__builtins__, name, None) or __builtins__[name]

            def wrapper(*args, _real=real, _name=name, **kwargs):
                calls.append(_name)
                return _real(*args, **kwargs)
            m.setattr(owner, name, wrapper, raising=False)
        yield calls


def test_duplicates_are_found_without_a_path_or_stat_per_file(tmp_path, monkeypatch):
    a, b, c = tmp_path / "A", tmp_path / "B", tmp_path / "C"
    _write(a / "Song [dQw4w9WgXcQ].mp3", 30)
    _write(b / "Song (copy) [dQw4w9WgXcQ].m4a", 10)
    _write(c / "Song [dQw4w9WgXcQ].f399.mp4", 50)      # a yt-dlp part: not a copy
    _write(c / "Song [dQw4w9WgXcQ].jpg", 5)            # a sidecar
    _write(c / "No id.mp3", 5)
    (c / "Folder [dQw4w9WgXcQ].mp3").mkdir()           # a folder named like one
    for k in range(50):
        _write(c / f"Other {k} [{k:011d}].mp3")
    with _counting(monkeypatch, (Path, "stat"), (Path, "is_file"), (vault, "Path")) as calls:
        groups = vault.find_duplicates([str(a), str(b), str(c), str(a), str(tmp_path / "missing")])
    assert len(calls) <= 5          # a Path per folder, nothing per file
    assert len(groups) == 1
    group = groups[0]
    assert group["video_id"] == "dQw4w9WgXcQ" and group["wasted_bytes"] == 10
    assert [(Path(cp["path"]).parent.name, cp["size"]) for cp in group["copies"]] == [("A", 30), ("B", 10)]
    assert group["copies"][0] == {"path": str(a / "Song [dQw4w9WgXcQ].mp3"), "name": "Song [dQw4w9WgXcQ].mp3",
                                  "folder": str(a), "size": 30}


def test_a_folder_card_counts_without_sorting_or_a_path_per_file(tmp_path, monkeypatch):
    for k in range(30):
        _write(tmp_path / "Mix" / f"{k}.mp3", 3)
    with _counting(monkeypatch, (Path, "stat"), (vault, "sorted")) as calls:
        stats = vault.get_folder_media_stats(str(tmp_path / "Mix"))
    assert calls == []
    assert stats == {"item_count": 30, "size_bytes": 90}


# ── The generator itself ─────────────────────────────────────────────────────

def test_the_big_library_generator_makes_what_it_says(tmp_path):
    home = tmp_path / "home"
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_big_library.py"), str(home),
                           "--files", "120", "--folders", "6", "--big-folder", "40",
                           "--history", "300", "--reports", "30"],
                          cwd=ROOT, capture_output=True, text=True, timeout=120,
                          env={**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)})
    assert done.returncode == 0, done.stderr[-2000:]
    root = home / "Downloads" / "MellowDLP"
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    assert len(folders) == 6
    media = [f for p in folders for f in p.iterdir() if vault.is_media(f)]
    assert len(media) == 120 + 120 // 50 + 1          # the files, and their copies in the next folder
    assert sum(1 for f in folders[0].iterdir() if vault.is_media(f)) >= 40
    analytics.reset_connections()
    import duckdb
    con = duckdb.connect(str(home / ".mellow_dlp.duckdb"), read_only=True)
    assert con.execute("SELECT count(*) FROM downloads").fetchone()[0] == 300
    assert con.execute("SELECT count(*) FROM sync_reports").fetchone()[0] == 30
    assert con.execute("SELECT count(*) FROM downloads WHERE file_path IS NOT NULL AND status='success'"
                       ).fetchone()[0] >= 120
    con.close()
    with pytest.raises(subprocess.CalledProcessError):     # never over an existing library
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_big_library.py"), str(home)],
                       cwd=ROOT, capture_output=True, check=True, timeout=60)


def test_dupes_lists_the_folders_without_counting_their_files(tmp_path, client, monkeypatch):
    root = tmp_path / "dl"
    _write(root / "A" / "Song [dQw4w9WgXcQ].mp3", 30)
    _write(root / "B" / "Song [dQw4w9WgXcQ].mp3", 10)
    update_config(lambda c: c.update(output_dir=str(root)))
    with _counting(monkeypatch, (vault, "get_folder_media_stats")) as calls:
        answer = client.get("/api/vault/duplicates").get_json()
    assert calls == []
    assert answer["total_wasted_bytes"] == 10 and len(answer["groups"]) == 1
    # The vault's own cards still count
    cards = {Path(c["path"]).name: c for c in client.get("/api/vault").get_json()["folders"]}
    assert (cards["A"]["item_count"], cards["B"]["size_bytes"]) == (1, 10)
