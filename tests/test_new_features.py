"""Tests for the scheduler, backup, wrapped stats, and storage budget."""
import io
import json
import time
import zipfile
from unittest.mock import patch

import scheduler
import vault

# ── Scheduler ──────────────────────────────────────────────────────────────────

def _cfg(**overrides):
    base = {
        "auto_sync_enabled": True,
        "auto_sync_default_interval": "daily",
        "vault_playlists": {"/folder/a": ["https://pl"]},
        "vault_sync_schedule": {},
        "vault_sync_times": {},
    }
    base.update(overrides)
    return base


def test_due_when_never_synced():
    assert scheduler.due_folders(_cfg()) == ["/folder/a"]


def test_not_due_when_recently_synced():
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    assert scheduler.due_folders(_cfg(vault_sync_times={"/folder/a": stamp})) == []


def test_due_when_stale():
    cfg = _cfg(vault_sync_times={"/folder/a": "2020-01-01T00:00:00"})
    assert scheduler.due_folders(cfg) == ["/folder/a"]


def test_master_switch_off():
    assert scheduler.due_folders(_cfg(auto_sync_enabled=False)) == []


def test_per_folder_off_overrides_default():
    cfg = _cfg(vault_sync_schedule={"/folder/a": "off"})
    assert scheduler.due_folders(cfg) == []


def test_folder_without_playlists_skipped():
    assert scheduler.due_folders(_cfg(vault_playlists={"/folder/a": []})) == []


def test_interval_override_respected():
    seven_hours_ago = time.time() - 7 * 3600
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(seven_hours_ago))
    cfg = _cfg(vault_sync_times={"/folder/a": stamp},
               vault_sync_schedule={"/folder/a": "6h"})
    assert scheduler.due_folders(cfg) == ["/folder/a"]
    cfg["vault_sync_schedule"]["/folder/a"] = "weekly"
    assert scheduler.due_folders(cfg) == []


# ── Backup ─────────────────────────────────────────────────────────────────────

def test_backup_roundtrip(tmp_path):
    import analytics
    import backup
    cfg_path = tmp_path / "config.json"
    db_path = tmp_path / "data.duckdb"
    cfg_path.write_text(json.dumps({"output_dir": "X"}), encoding="utf-8")
    with patch("config.CONFIG_PATH", cfg_path), patch("analytics.DB_PATH", db_path), \
            patch("backup.CONFIG_PATH", cfg_path):
        analytics.init_db()
        analytics.reset_connections()
        data = backup.create_backup()
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert backup.CONFIG_MEMBER in names
        assert backup.DB_MEMBER in names
        # Mutate, then restore — original content must come back
        cfg_path.write_text("{}", encoding="utf-8")
        result = backup.restore_backup(data)
        assert result["ok"]
        assert json.loads(cfg_path.read_text(encoding="utf-8")) == {"output_dir": "X"}
        # Pre-restore safety copy exists
        assert cfg_path.with_suffix(".json.pre-restore").exists()
        analytics.reset_connections()


def test_restore_rejects_garbage():
    import backup
    assert backup.restore_backup(b"not a zip")["ok"] is False


def test_restore_rejects_foreign_members(tmp_path):
    import backup
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "nope")
    assert backup.restore_backup(buf.getvalue())["ok"] is False


# ── Wrapped ────────────────────────────────────────────────────────────────────

def test_wrapped_aggregates(tmp_path):
    import analytics
    with patch("analytics.DB_PATH", tmp_path / "w.duckdb"):
        analytics.init_db()
        analytics.record_download({
            "url": "https://youtu.be/x", "title": "T", "uploader": "Chan",
            "platform": "YouTube", "duration_seconds": 3600,
            "file_size_bytes": 1000, "status": "success",
        })
        data = analytics.get_wrapped(time.localtime().tm_year)
        assert data["total_downloads"] == 1
        assert data["total_duration_seconds"] == 3600
        assert data["top_uploaders"][0]["uploader"] == "Chan"
        assert len(data["monthly"]) == 12
        assert sum(data["monthly"]) == 1
        analytics.reset_connections()


# ── Storage budget ─────────────────────────────────────────────────────────────

def test_cleanup_candidates_oldest_first(tmp_path):
    old = tmp_path / "old.mp4"
    new = tmp_path / "new.mp4"
    old.write_bytes(b"x" * 600)
    new.write_bytes(b"x" * 600)
    long_ago = time.time() - 86400 * 30
    import os
    os.utime(old, (long_ago, long_ago))

    result = vault.get_cleanup_candidates(str(tmp_path), budget_bytes=1000)
    assert result["total_bytes"] == 1200
    assert result["over_bytes"] == 200
    # Oldest file is suggested first, and only enough to cover the overage
    assert [c["name"] for c in result["candidates"]] == ["old.mp4"]


def test_cleanup_candidates_under_budget(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x" * 100)
    result = vault.get_cleanup_candidates(str(tmp_path), budget_bytes=1000)
    assert result["over_bytes"] == 0
    assert result["candidates"] == []
