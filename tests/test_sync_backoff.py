"""Auto-sync after failures and cancels: from the folder's own sync reports,
which survive restarts (scheduler.hold_off)."""
import pytest

from mellow import analytics, scheduler, vault
from mellow.config import load_config, update_config
from mellow.constants import SYNC_RETRY_BACKOFF_MAX_SECS, SYNC_RETRY_BACKOFF_SECS

FOLDER = "/music/Chill"
H = 3600


@pytest.fixture(autouse=True)
def linked(tmp_path):
    update_config(lambda c: c.update(auto_sync_enabled=True, auto_sync_default_interval="daily",
                                     vault_playlists={FOLDER: ["https://x/pl"]},
                                     vault_sync_times={FOLDER: "2020-01-01T00:00:00"}))
    scheduler._last_attempt.clear()        # as after a restart


def _outcomes(*statuses_ages):
    """Sync reports for FOLDER, oldest first: (status, seconds ago)."""
    for status, ago in statuses_ages:
        analytics.record_sync_report(FOLDER, status, {"added": [], "failed": [], "filtered": [], "archived": 0}, 1)
        with analytics.get_conn() as con:
            con.execute("UPDATE sync_reports SET finished_at = CAST(now() AS TIMESTAMP) - to_seconds(?::BIGINT) "
                        "WHERE id = (SELECT max(id) FROM sync_reports)", [ago])


def _queued():
    return scheduler.tick(lambda path: True, lambda path: False)


def test_a_failing_folder_waits_longer_after_each_failure():
    _outcomes(("failed", 3 * H), ("failed", 2 * H), ("failed", H))   # 3 in a row: 4 h after the last
    wait, failures = scheduler.hold_off(FOLDER, 86400)
    assert failures == 3 and 2.9 * H < wait <= 3 * H
    assert _queued() == []


def test_the_wait_is_over_once_the_backoff_has_passed():
    _outcomes(("failed", 30 * H), ("failed", 5 * H))     # 2 in a row: 2 h after the last, 5 h ago
    assert _queued() == [FOLDER]


def test_a_restart_doesn_t_retry_every_failing_folder_at_once():
    """The wait was in memory: right after a restart every failing folder was
    retried at the first tick."""
    _outcomes(("failed", 10 * 60))
    assert _queued() == []


def test_a_cancelled_sync_waits_for_its_next_turn():
    _outcomes(("cancelled", 2 * H))
    assert _queued() == []                  # daily: not again 1 h later as before
    scheduler._last_attempt.clear()
    with analytics.get_conn() as con:
        con.execute("UPDATE sync_reports SET finished_at = CAST(now() AS TIMESTAMP) - to_seconds(25 * 3600)")
    assert _queued() == [FOLDER]


def test_a_success_ends_the_backoff():
    _outcomes(("failed", 3 * H), ("failed", 2 * H), ("complete", H))
    assert scheduler.hold_off(FOLDER, 86400) == (0.0, 0)


def test_the_wait_never_exceeds_a_day():
    _outcomes(*[("failed", 100 * H - i) for i in range(10)])
    wait, failures = scheduler.hold_off(FOLDER, 7 * 86400)
    assert failures == 10
    assert wait <= SYNC_RETRY_BACKOFF_MAX_SECS
    assert SYNC_RETRY_BACKOFF_SECS * 2 ** 9 > SYNC_RETRY_BACKOFF_MAX_SECS   # the cap is what limits it


def test_the_folder_card_says_syncs_keep_failing(tmp_path):
    folder = tmp_path / "dl" / "Chill"
    folder.mkdir(parents=True)
    path = str(folder)
    update_config(lambda c: c.update(output_dir=str(tmp_path / "dl"), vault_playlists={path: ["https://x/pl"]}))
    for _ in range(2):
        analytics.record_sync_report(path, "failed", {"added": [], "failed": [], "filtered": [], "archived": 0}, 1)
    card = next(f for f in vault.build_folder_list(str(tmp_path / "dl"), load_config()) if f["path"] == path)
    assert card["sync_failures"] == 2
    assert 0 < card["sync_retry_in"] <= 2 * H
