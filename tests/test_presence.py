"""Unit tests for the pure presence-fusion model (F32).

Run with:  python -m pytest tests/test_presence.py -q
"""

from custom_components.dynamic_home import presence as p
from custom_components.dynamic_home.presence import PresenceConfig, ZonePresenceState

CFG = PresenceConfig()


def _state(**fired) -> ZonePresenceState:
    st = ZonePresenceState()
    st.last_fired.update(fired)
    return st


def test_pir_times_out_fast():
    st = ZonePresenceState()
    p.note_source(st, p.PIR, True, 0.0)
    assert p.zone_occupied(st, CFG, 60.0)[0] is True       # within 120 s
    # Stale PIR -> empties after the confirm debounce.
    assert p.zone_occupied(st, CFG, 200.0)[0] is True       # debouncing
    assert p.zone_occupied(st, CFG, 240.0) == (False, "empty")


def test_mmwave_holds_through_stillness():
    # Sitting still on the sofa: mmWave keeps firing -> never Empty (REQ-PRE-3).
    st = ZonePresenceState()
    occ = True
    for t in range(0, 1200, 60):            # 20 min, mmWave fresh each cycle
        p.note_source(st, p.MMWAVE, True, float(t))
        occ, reason = p.zone_occupied(st, CFG, float(t))
        assert occ is True
    assert reason == "mmwave_hold"
    # mmWave stops -> holds for its long timeout, then empties.
    assert p.zone_occupied(st, CFG, 1200 + 599)[0] is True
    assert p.zone_occupied(st, CFG, 1200 + 700)[0] is False


def test_empty_debounce():
    st = _state(pir=0.0)
    p.zone_occupied(st, CFG, 0.0)                # occupied
    # PIR stale at t=130; within empty_confirm_s it still holds, then drops.
    assert p.zone_occupied(st, CFG, 130.0) == (True, "emptying")
    assert p.zone_occupied(st, CFG, 165.0) == (False, "empty")


def test_subset_sources_do_not_crash():
    # Only mmWave configured (REQ-PRE-8).
    st = _state(mmwave=0.0)
    assert p.zone_occupied(st, CFG, 10.0)[0] is True
    # No sources at all -> empty, no error.
    assert p.zone_occupied(ZonePresenceState(), CFG, 10.0) == (False, "empty")


def test_house_away_needs_a_signal_not_just_stillness():
    # Nobody occupied but no door/phone signal -> stay occupied (conservative).
    assert p.house_state({"z1": False}, True, False, 12 * 60, False, CFG) \
        == "occupied"
    # Empty + recent door -> away (REQ-PRE-5).
    assert p.house_state({"z1": False}, True, True, 12 * 60, False, CFG) == "away"
    # Empty + phones away -> away.
    assert p.house_state({"z1": False}, False, False, 12 * 60, False, CFG) == "away"
    # Someone occupied -> never away even with a door event.
    assert p.house_state({"z1": True}, True, True, 12 * 60, True, CFG) == "occupied"


def test_house_sleeping_in_window_without_motion():
    night = 2 * 60                       # 02:00, inside 23:00-07:00
    assert p.house_state({"z1": True}, True, False, night, False, CFG) == "sleeping"
    # Motion in the window -> not sleeping.
    assert p.house_state({"z1": True}, True, False, night, True, CFG) == "occupied"
    # Daytime -> not sleeping.
    assert p.house_state({"z1": True}, True, False, 12 * 60, False, CFG) == "occupied"


def test_sleep_window_wraps_midnight():
    assert p.in_sleep_window(23 * 60 + 30, CFG) is True
    assert p.in_sleep_window(3 * 60, CFG) is True
    assert p.in_sleep_window(12 * 60, CFG) is False


def test_door_and_motion_recent_helpers():
    states = [_state(door=100.0), _state(pir=50.0)]
    assert p.door_recent(states, CFG, 200.0) is True        # 100 s < 300 s
    assert p.door_recent(states, CFG, 500.0) is False
    assert p.motion_recent(states, CFG, 100.0) is True       # PIR = movement
    assert p.motion_recent(states, CFG, 2000.0) is False     # > 1800 s
    # mmWave is presence, not movement -> does not count for sleep stillness.
    assert p.motion_recent([_state(mmwave=50.0)], CFG, 100.0) is False


def test_state_to_mode_mapping():
    assert p.STATE_TO_MODE == {"occupied": "home", "away": "away",
                               "sleeping": "sleep"}
