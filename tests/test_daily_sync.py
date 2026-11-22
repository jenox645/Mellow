"""The daily auto-sync is a time of day (scheduler.py): due once that day's
auto_sync_time has passed and the folder hasn't synced since, with catch-up
after the computer was off; 6h and weekly stay intervals."""
from datetime import datetime

import pytest

from mellow import scheduler
from mellow.constants import SCHEDULER_TICK_SECS, SYNC_DAILY_MIN_GAP_SECS

FOLDER = "/music/Chill"


def at(text: str) -> float:
    """Local time 'YYYY-MM-DD HH:MM' as epoch seconds."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()


def stamp(text: str) -> str:
    """The way _on_finished records a sync (local, ISO)."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M:%S")


def cfg(last: str | None = None, interval: str = "daily", time: str = "03:00", **extra) -> dict:
    c = {"auto_sync_enabled": True, "auto_sync_default_interval": interval, "auto_sync_time": time,
         "vault_playlists": {FOLDER: ["https://x/pl"]}, "vault_sync_schedule": {},
         "vault_sync_times": {FOLDER: stamp(last)} if last else {}}
    c.update(extra)
    return c


def test_the_daily_mark_is_todays_time_once_it_has_passed_else_yesterdays():
    assert scheduler.daily_mark("03:00", at("2026-11-22 09:00")) == at("2026-11-22 03:00")
    assert scheduler.daily_mark("03:00", at("2026-11-22 02:59")) == at("2026-11-21 03:00")
    assert scheduler.daily_mark("03:00", at("2026-11-22 03:00")) == at("2026-11-22 03:00")


def test_a_folder_synced_yesterday_evening_waits_for_todays_time():
    c = cfg(last="2026-11-21 20:00")
    assert scheduler.due_folders(c, at("2026-11-22 02:58")) == []
    assert scheduler.due_folders(c, at("2026-11-22 03:00")) == [FOLDER]


def test_a_computer_that_was_off_at_that_time_catches_up_when_it_runs():
    c = cfg(last="2026-11-19 03:05")                        # three days ago
    assert scheduler.due_folders(c, at("2026-11-22 14:30")) == [FOLDER]
    assert scheduler.due_folders(cfg(), at("2026-11-22 14:30")) == [FOLDER]     # never synced


def test_synced_after_todays_time_waits_for_tomorrows():
    c = cfg(last="2026-11-22 03:04")
    assert scheduler.due_folders(c, at("2026-11-22 23:59")) == []
    assert scheduler.due_folders(c, at("2026-11-23 03:00")) == [FOLDER]


def test_synced_by_hand_just_before_its_time_skips_that_days_run():
    c = cfg(last="2026-11-22 02:50")
    assert scheduler.due_folders(c, at("2026-11-22 03:01")) == []
    assert scheduler.due_folders(c, at("2026-11-23 03:01")) == [FOLDER]
    # Long enough before it: that day's run happens
    early = at("2026-11-22 03:00") - SYNC_DAILY_MIN_GAP_SECS - 60
    c = cfg(last=datetime.fromtimestamp(early).strftime("%Y-%m-%d %H:%M"))
    assert scheduler.due_folders(c, at("2026-11-22 03:01")) == [FOLDER]


def test_six_hours_and_weekly_stay_intervals():
    c = cfg(last="2026-11-22 02:00", interval="6h")
    assert scheduler.due_folders(c, at("2026-11-22 07:59")) == []
    assert scheduler.due_folders(c, at("2026-11-22 08:00")) == [FOLDER]
    c = cfg(last="2026-11-16 02:00", interval="weekly")
    assert scheduler.due_folders(c, at("2026-11-23 01:59")) == []
    assert scheduler.due_folders(c, at("2026-11-23 02:00")) == [FOLDER]


@pytest.mark.parametrize("value", ["", "25:00", "noon", None, "3"])
def test_an_unreadable_time_is_the_default(value):
    assert scheduler.daily_time({"auto_sync_time": value}) == "03:00"
    assert scheduler.daily_time({"auto_sync_time": "7:5"}) == "07:05"


def test_the_loop_wakes_on_the_minute_of_the_daily_time():
    c = cfg(time="03:00")
    assert scheduler.next_wait(c, at("2026-11-22 02:58")) == pytest.approx(121)   # 2 min + 1 s
    assert scheduler.next_wait(c, at("2026-11-22 10:00")) == SCHEDULER_TICK_SECS
    assert scheduler.next_wait(cfg(auto_sync_enabled=False), at("2026-11-22 02:58")) == SCHEDULER_TICK_SECS
