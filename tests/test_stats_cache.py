"""/api/stats is asked every 3 s while downloading: analytics.get_stats keeps its
answer until the data changes (or STATS_CACHE_SECS pass)."""
from __future__ import annotations

import pytest

from mellow import analytics


@pytest.fixture
def computed(monkeypatch):
    """How many times get_stats really ran its queries."""
    runs: list[int | None] = []
    real = analytics._compute_stats

    def spy(days):
        runs.append(days)
        return real(days)
    monkeypatch.setattr(analytics, "_compute_stats", spy)
    return runs


def _download(title: str = "A song") -> None:
    """A history row, the way the downloader records one."""
    analytics.record_download({"url": "https://example.com/v/" + title, "title": title,
                               "platform": "youtube", "format": "mp3", "file_size_bytes": 1000})


def test_asking_twice_runs_the_queries_once(computed):
    _download()
    first = analytics.get_stats("30d")
    second = analytics.get_stats("30d")
    assert computed == [30]
    assert first == second and first["total_downloads"] == 1


def test_a_recorded_download_shows_at_once(computed):
    assert analytics.get_stats("30d")["total_downloads"] == 0
    _download()
    assert analytics.get_stats("30d")["total_downloads"] == 1
    assert computed == [30, 30]


@pytest.mark.parametrize("write", [
    lambda: analytics.delete_history(delete_all=True),
    lambda: analytics.delete_history_by_path("/music/a.mp3"),
    lambda: analytics.move_paths(lambda p: None),
    lambda: analytics.upsert_library_entry({"id": "e1", "name": "Lofi", "url": "https://x/pl",
                                            "folder": "", "folder_name": "Lofi"}),
    lambda: analytics.delete_library_entry("e1"),
    lambda: analytics.update_library_last_synced("e1"),
    lambda: analytics.record_sync_log("e1", 1, 0, 0),
    analytics.init_db,
])
def test_every_writer_makes_the_next_call_recompute(computed, write):
    analytics.get_stats("30d")
    write()
    analytics.get_stats("30d")
    assert computed == [30, 30]


def test_a_restored_database_is_read_again(computed):
    analytics.get_stats("all")
    with analytics.exclusive_file_access():
        pass   # backup.restore_backup swaps the file in here
    analytics.get_stats("all")
    assert computed == [None, None]


def test_library_and_sync_log_changes_show(computed):
    assert analytics.get_stats("all")["library_playlists"] == 0
    analytics.upsert_library_entry({"id": "e1", "name": "Lofi", "url": "https://x/pl",
                                    "folder": "", "folder_name": "Lofi"})
    analytics.record_sync_log("e1", 3, 1, 0)
    stats = analytics.get_stats("all")
    assert stats["library_playlists"] == 1
    assert [r["name"] for r in stats["sync_runs"]] == ["Lofi"]


def test_each_range_is_computed_on_its_own(computed):
    analytics.get_stats("7d")
    analytics.get_stats("30d")
    analytics.get_stats("all")
    analytics.get_stats("7d")
    analytics.get_stats("bogus")   # anything else is "all", and shares its answer
    assert computed == [7, 30, None]


def test_it_recomputes_after_stats_cache_secs(computed, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(analytics.time, "monotonic", lambda: now[0])
    analytics.get_stats("30d")
    now[0] += analytics.STATS_CACHE_SECS - 1
    analytics.get_stats("30d")
    assert computed == [30]
    now[0] += 2
    analytics.get_stats("30d")
    assert computed == [30, 30]


def test_a_caller_cant_change_the_kept_answer(computed):
    _download()
    stats = analytics.get_stats("30d")
    stats["library_playlists"] = 99            # what /api/stats does with vault_playlists
    stats["by_platform"].append({"platform": "x", "count": 1})
    again = analytics.get_stats("30d")
    assert again["library_playlists"] == 0
    assert again["by_platform"] == [{"platform": "youtube", "count": 1}]
    assert computed == [30]


def test_a_write_during_the_queries_isnt_hidden(computed, monkeypatch):
    """An answer computed while a download was being recorded may miss it: it isn't kept."""
    real = analytics._compute_stats

    def racing(days):
        stats = real(days)
        _download("Recorded meanwhile")
        return stats
    monkeypatch.setattr(analytics, "_compute_stats", racing)
    assert analytics.get_stats("30d")["total_downloads"] == 0
    monkeypatch.setattr(analytics, "_compute_stats", real)
    assert analytics.get_stats("30d")["total_downloads"] == 1


def test_the_route_still_adds_vault_playlists(client):
    from mellow import config
    _download()
    config.update_config(lambda c: c.update(vault_playlists={"/m/a": ["https://x/1"], "/m/b": ["https://x/2"]}))
    assert client.get("/api/stats?range=30d").get_json()["library_playlists"] == 2
    config.update_config(lambda c: c.update(vault_playlists={}))
    body = client.get("/api/stats?range=30d").get_json()
    assert body["library_playlists"] == 0 and body["total_downloads"] == 1
