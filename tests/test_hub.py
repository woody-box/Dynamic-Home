"""Unit tests for the SDHB hub's multi-target arbitration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from bus import SdhbHub  # noqa: E402


def test_single_target_match():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds", priority=70)
    assert h.winner("ds") == "request_solar_shield"
    assert h.winner("dv") == "none"


def test_broadcast_matches_everyone():
    h = SdhbHub()
    h.publish("x", "request_quiet", target="", priority=60)
    assert h.winner("ds") == "request_quiet"
    assert h.winner("dv") == "request_quiet"
    assert h.winner({"ds", "ds_f180"}) == "request_quiet"


def test_facade_targeting_selects_only_matching_consumer():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds_f180", priority=70)
    # South facade listens on its facade key -> matches
    assert h.winner({"ds", "ds_f180"}) == "request_solar_shield"
    # North facade does not -> no match
    assert h.winner({"ds", "ds_f000"}) == "none"


def test_priority_arbitration_across_sources():
    h = SdhbHub()
    h.publish("dc1", "request_solar_gain", target="ds", priority=70)
    h.publish("dc2", "request_weather_protect", target="ds", priority=90)
    assert h.winner("ds") == "request_weather_protect"


def test_clear_removes_source():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds", priority=70)
    h.clear("dc1")
    assert h.winner("ds") == "none"


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
