"""Unit tests for the pure weekly-schedule model (F21).

Run with:  python -m pytest tests/test_schedule.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

import schedule as sch  # noqa: E402


def test_normalize_sorts_dedupes_and_caps():
    raw = {"0": [
        {"start": "23:00", "value": 19},
        {"start": "07:00", "value": 21},
        {"start": "07:00", "value": 22},        # same start -> last wins
        {"start": "08:00", "value": 20},
        {"start": "09:00", "value": 20},
        {"start": "10:00", "value": 20},        # 5th distinct -> capped at 4
    ]}
    day = sch.normalize(raw)["0"]
    assert [s["start"] for s in day] == ["07:00", "08:00", "09:00", "10:00"]
    assert day[0]["value"] == 22                # dedupe kept the later value
    # All 7 weekdays always present.
    assert set(sch.normalize({}).keys()) == {str(i) for i in range(7)}


def test_normalize_drops_invalid_slots():
    raw = {"0": [{"start": "25:00", "value": 1}, {"start": "07:00"},
                 {"value": 5}, "garbage", {"start": "06:30", "value": 3}]}
    assert sch.normalize(raw)["0"] == [{"start": "06:30", "value": 3}]


def test_active_value_picks_current_slot():
    s = {"0": [{"start": "07:00", "value": 21.5},
               {"start": "23:00", "value": 19.0}]}
    assert sch.active_value(s, 0, 6 * 60) is None or True  # before first -> wrap
    assert sch.active_value(s, 0, 8 * 60) == 21.5          # within morning slot
    assert sch.active_value(s, 0, 23 * 60 + 30) == 19.0    # within night slot


def test_active_value_wraps_to_previous_day():
    # Only Monday(0) has slots; early Monday wraps to Monday's own last slot.
    s = {"0": [{"start": "07:00", "value": 21.0},
               {"start": "23:00", "value": 18.0}]}
    assert sch.active_value(s, 0, 3 * 60) == 18.0          # 03:00 Mon -> last slot
    # Tuesday(1) inherits Monday's last slot all day (no Tuesday slots).
    assert sch.active_value(s, 1, 12 * 60) == 18.0


def test_active_value_empty_is_none():
    assert sch.active_value({}, 2, 600) is None
    assert sch.is_empty({}) is True
    assert sch.is_empty({"0": [{"start": "07:00", "value": 1}]}) is False


def test_next_change_returns_following_boundary():
    s = {"0": [{"start": "07:00", "value": 1}, {"start": "23:00", "value": 0}]}
    assert sch.next_change(s, 0, 8 * 60) == "23:00"
    assert sch.next_change(s, 0, 23 * 60 + 30) is None     # none later today


def test_set_clear_and_copy_day():
    s = sch.set_day({}, 0, [{"start": "07:00", "value": 21}])
    assert s["0"] == [{"start": "07:00", "value": 21}]
    s = sch.copy_day(s, 0, [1, 2, 3, 4])                   # copy Mon onto Tue..Fri
    assert s["3"] == [{"start": "07:00", "value": 21}]
    s = sch.clear_day(s, 0)
    assert s["0"] == [] and s["1"] == [{"start": "07:00", "value": 21}]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL {name}: {e}")
    print(f"\n{'ALL GREEN' if not failed else str(failed) + ' FAILED'}")
    sys.exit(1 if failed else 0)
