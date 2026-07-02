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
                  "candidates": 0, "reason": "no_candidates", "target": None,
                  "ttl_remaining": None, "runner_up": None,
                  "runner_up_priority": None}


def test_explain_single_candidate():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds", priority=70)
    ex = h.explain("ds")
    assert ex["winner"] == "request_solar_shield"
    assert ex["source"] == "dc1"
    assert ex["priority"] == 70
    assert ex["candidates"] == 1
    assert ex["reason"] == "single"
    assert ex["target"] == "ds"
    # A lone candidate has no runner-up.
    assert ex["runner_up"] is None and ex["runner_up_priority"] is None


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
    # The loser is surfaced as the runner-up (one only, not the full list).
    assert ex["runner_up"] == "request_solar_gain"
    assert ex["runner_up_priority"] == 70


def test_explain_ttl_remaining():
    h = SdhbHub()
    h.publish("dc1", "request_solar_shield", target="ds", priority=70,
              ttl_s=300, now_ts=1000)
    assert h.explain("ds", now_ts=1100)["ttl_remaining"] == 200
    # A never-expiring intent reports no remaining TTL.
    h.publish("dc2", "request_quiet", target="dv", priority=60)
    assert h.explain("dv", now_ts=1100)["ttl_remaining"] is None


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


def test_priority_tie_breaks_deterministically_by_source():
    # v0.97.0: equal priorities resolved by dict insertion order (whichever
    # zone booted first) — now the source name decides, stable across restarts.
    h1 = SdhbHub()
    h1.publish("dc_a", "request_solar_gain", target="ds", priority=70)
    h1.publish("dc_b", "request_solar_shield", target="ds", priority=70)
    h2 = SdhbHub()
    h2.publish("dc_b", "request_solar_shield", target="ds", priority=70)
    h2.publish("dc_a", "request_solar_gain", target="ds", priority=70)
    assert h1.winner("ds") == h2.winner("ds") == "request_solar_shield"
    assert h1.explain("ds")["winner"] == h2.explain("ds")["winner"]


def test_publish_ttl_without_clock_is_an_error():
    # A TTL'd intent with no clock would never expire (silent eternal slot).
    h = SdhbHub()
    try:
        h.publish("x", "request_quiet", target="dv", ttl_s=600)
    except ValueError:
        pass
    else:
        raise AssertionError("ttl_s without now_ts must raise")
