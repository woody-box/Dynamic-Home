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


def test_ttl_expires_intent():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds", priority=70,
              ttl_s=300, now_ts=1000)
    # within TTL -> present
    assert h.winner("ds", now_ts=1200) == "request_solar_shield"
    # past TTL -> expired and pruned
    assert h.winner("ds", now_ts=1400) == "none"


def test_no_ttl_never_expires():
    h = SdhbHub()
    h.publish("dc1", "request_quiet", target="ds", priority=60)  # ttl_s=0
    assert h.winner("ds", now_ts=10 ** 9) == "request_quiet"


def test_explain_no_candidates():
    h = SdhbHub()
    ex = h.explain("ds")
    assert ex == {"winner": "none", "source": None, "priority": None,
                  "candidates": 0, "reason": "no_candidates"}


def test_explain_single_candidate():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds", priority=70)
    ex = h.explain("ds")
    assert ex["winner"] == "request_solar_shield"
    assert ex["source"] == "dc1"
    assert ex["priority"] == 70
    assert ex["candidates"] == 1
    assert ex["reason"] == "single"


def test_explain_priority_tiebreak_and_count():
    h = SdhbHub()
    h.publish("dc1", "request_solar_gain", target="ds", priority=70)
    h.publish("dc2", "request_weather_protect", target="ds", priority=90)
    ex = h.explain("ds")
    assert ex["winner"] == "request_weather_protect"
    assert ex["source"] == "dc2"
    assert ex["priority"] == 90
    assert ex["candidates"] == 2
    assert ex["reason"] == "priority"


def test_explain_matches_winner():
    """explain()'s winner must always agree with winner()."""
    h = SdhbHub()
    h.publish("dc1", "request_solar_gain", target="ds_f180", priority=70)
    h.publish("x", "request_quiet", target="", priority=60)
    for targets in ("ds", {"ds", "ds_f180"}, {"ds", "ds_f000"}, "dv"):
        assert h.explain(targets)["winner"] == h.winner(targets)


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
