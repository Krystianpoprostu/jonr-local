"""Pure tests for the fork's cleaning-session tracker (clean_log.py)."""
from __future__ import annotations

import clean_log
from clean_log import PAUSED_ON_DOCK_END, CleanSessionTracker, parse_targets

NAMES = {3: "A", 4: "B", 5: "C"}
AREAS = {3: 10.0, 4: 5.0, 5: 2.0}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _tracker():
    clock = Clock()
    return CleanSessionTracker(lambda: NAMES, lambda: AREAS, now=clock), clock


def feed(tr, clock, task, status, targets="[]", area=0, dt=10, **kw):
    clock.t += dt
    return tr.feed(task=task, status=status, targets_raw=targets, area=area,
                   minutes=kw.get("minutes"), fault=kw.get("fault", 0),
                   station_error=kw.get("station_error", 0), battery=kw.get("battery", 90))


def test_parse_targets_shapes():
    assert parse_targets("[3, 4]") == [3, 4]
    assert parse_targets([5]) == [5]
    assert parse_targets("") == [] and parse_targets(None) == [] and parse_targets("x") == []


def test_room_task_ends_on_idle_with_coverage_and_returns():
    tr, c = _tracker()
    assert feed(tr, c, 1, 13) is None                      # idle on dock: nothing
    feed(tr, c, 8, 7, "[3,4]", 1)
    feed(tr, c, 8, 12, "[3,4]", 6)                         # GoWash -> one dock return
    feed(tr, c, 8, 7, "[3,4]", 9)
    rec = feed(tr, c, 1, 13, "[]", 9)
    assert rec["kind"] == "rooms" and rec["room_ids"] == [3, 4] and rec["rooms"] == ["A", "B"]
    assert rec["expected_area_m2"] == 15.0 and rec["area_m2"] == 9 and rec["coverage_pct"] == 60
    assert rec["dock_returns"] == 1 and rec["ended_on_dock"] and rec["unknown_room_ids"] == []


def test_whole_home_targets_every_saved_room():
    tr, c = _tracker()
    feed(tr, c, 2, 7, "[]", 5)
    rec = feed(tr, c, 1, 9, "[]", 17)
    assert rec["kind"] == "whole_home" and rec["room_ids"] == [3, 4, 5]
    assert rec["expected_area_m2"] == 17.0 and rec["coverage_pct"] == 100


def test_mop_wash_dock_stop_does_not_split_the_session():
    tr, c = _tracker()
    feed(tr, c, 2, 7, "[]", 4)
    assert feed(tr, c, 3, 13, "[]", 4, dt=120) is None     # ~2 min paused on dock (wash)
    assert feed(tr, c, 4, 7, "[]", 8) is None              # resumes
    rec = feed(tr, c, 1, 13, "[]", 12)
    assert rec["area_m2"] == 12 and rec["task_codes"] == [2, 3, 4]


def test_return_to_dock_leaves_task_paused_and_closes_after_timeout_once():
    tr, c = _tracker()
    feed(tr, c, 8, 7, "[3]", 2)
    feed(tr, c, 8, 10, "[3]", 2)                           # Go Charging
    assert feed(tr, c, 9, 13, "[3]", 2) is None            # parked, Area Pause
    rec = feed(tr, c, 9, 13, "[3]", 2, dt=PAUSED_ON_DOCK_END)
    assert rec is not None and rec["room_ids"] == [3] and rec["ended_on_dock"]
    for _ in range(5):                                     # still parked: no new session
        assert feed(tr, c, 9, 13, "[3]", 2, dt=PAUSED_ON_DOCK_END) is None
    assert tr.active is None


def test_paused_task_found_at_startup_opens_nothing():
    tr, c = _tracker()
    for _ in range(3):
        assert feed(tr, c, 9, 13, "[6]", 0, dt=PAUSED_ON_DOCK_END) is None
    assert tr.active is None


def test_new_task_replacing_open_one_closes_it():
    tr, c = _tracker()
    feed(tr, c, 8, 7, "[3]", 3)
    rec = feed(tr, c, 11, 7, "[1,2,3,2,3,4,1,4]", 0)       # zone task, Idle missed
    assert rec["kind"] == "rooms" and rec["room_ids"] == [3]
    assert tr.active["kind"] == "zones"
    rec2 = feed(tr, c, 1, 13)
    assert rec2["kind"] == "zones" and rec2["room_ids"] == [] and rec2["coverage_pct"] is None


def test_unknown_room_and_errors_are_reported():
    tr, c = _tracker()
    feed(tr, c, 8, 7, "[3,9]", 1, fault=2008)
    rec = feed(tr, c, 1, 13, "[]", 1, station_error=4502)
    assert rec["unknown_room_ids"] == [9] and rec["rooms"] == ["A", "#9"]
    assert rec["errors"] == [2008, 4502]


def test_missing_task_reading_changes_nothing():
    tr, c = _tracker()
    feed(tr, c, 8, 7, "[3]", 1)
    assert feed(tr, c, None, None) is None
    assert tr.active is not None and clean_log.HISTORY_LEN == 30
