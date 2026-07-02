"""Unit tests for the pure compressor anti-cycling model (F09).

Run with:  python -m pytest tests/test_anticycle.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from anticycle import AntiCycleHub, CompressorState, step  # noqa: E402
from dc_engine import DcConfig  # noqa: E402


def _cfg(**kw):
    c = DcConfig()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_start_when_off_and_demand_after_min_off():
    cfg = _cfg(anticycle_min_off_s=600, anticycle_max_starts_per_h=6)
    st = CompressorState(on=False, last_off_ts=0.0)
    on, reason = step(st, any_demand=True, force_off=False, now_ts=1000.0, cfg=cfg)
    assert on is True and reason == "start"
    assert st.starts == [1000.0]


def test_min_off_blocks_quick_restart():
    cfg = _cfg(anticycle_min_off_s=600)
    st = CompressorState(on=False, last_off_ts=1000.0)
    on, reason = step(st, True, False, now_ts=1000.0 + 100, cfg=cfg)  # only 100 s
    assert on is False and reason == "anticycle_min_off_hold"


def test_max_starts_per_hour_caps():
    cfg = _cfg(anticycle_min_off_s=0, anticycle_max_starts_per_h=6)
    st = CompressorState(on=False, starts=[100.0, 200.0, 300.0, 400.0, 500.0, 600.0])
    on, reason = step(st, True, False, now_ts=700.0, cfg=cfg)   # 6 in the last hour
    assert on is False and reason == "anticycle_max_starts_hold"
    # An hour later the old starts age out and a start is allowed again.
    on, reason = step(st, True, False, now_ts=100.0 + 3601, cfg=cfg)
    assert on is True and reason == "start"


def test_min_on_stop_is_registered_and_restart_respects_min_off():
    # v0.96.0: the hub cannot force the physical compressor to stay on, so a
    # stop inside min-ON is REAL — it is recorded, and an immediate re-demand
    # must respect min-OFF and count as a start (the actual short cycle F09
    # exists to prevent).
    cfg = _cfg(anticycle_min_on_s=600, anticycle_min_off_s=300)
    st = CompressorState(on=True, last_on_ts=1000.0)
    on, reason = step(st, any_demand=False, force_off=False,
                      now_ts=1000.0 + 100, cfg=cfg)
    assert on is False and reason == "anticycle_min_on_hold"
    assert st.on is False and st.last_off_ts == 1100.0
    # Re-demand 60 s later: min-OFF blocks the restart.
    on, reason = step(st, True, False, now_ts=1000.0 + 160, cfg=cfg)
    assert on is False and reason == "anticycle_min_off_hold"
    # After min-OFF it restarts (and the start is counted).
    on, reason = step(st, True, False, now_ts=1000.0 + 500, cfg=cfg)
    assert on is True and reason == "start" and len(st.starts) == 1


def test_safety_off_cedes_min_on():
    cfg = _cfg(anticycle_min_on_s=600)
    st = CompressorState(on=True, last_on_ts=1000.0)
    on, reason = step(st, any_demand=False, force_off=True,
                      now_ts=1000.0 + 10, cfg=cfg)        # well within min ON
    assert on is False and reason == "anticycle_safety_off"


# --- aggregate hub: any zone keeps the shared compressor awake ---
def test_hub_other_zone_keeps_compressor_on_no_extra_start():
    cfg = _cfg(anticycle_min_off_s=600, anticycle_max_starts_per_h=6)
    hub = AntiCycleHub()
    # Both zones call -> one compressor start.
    hub.evaluate("a", True, False, 1000.0, cfg)
    hub.evaluate("b", True, False, 1000.0, cfg)
    assert hub.state.on and len(hub.state.starts) == 1

    # Zone A stops but zone B keeps demanding -> compressor stays on (no stop).
    a_on, _ = hub.evaluate("a", False, False, 1100.0, cfg)
    assert a_on is False and hub.state.on is True

    # Zone A calls again -> joins the running compressor, NOT a new start.
    a_on, _ = hub.evaluate("a", True, False, 1200.0, cfg)
    assert a_on is True and len(hub.state.starts) == 1     # still a single start


def test_hub_holds_zone_off_when_compressor_blocked():
    cfg = _cfg(anticycle_min_off_s=600)
    hub = AntiCycleHub()
    hub.state = CompressorState(on=False, last_off_ts=1000.0)   # just stopped
    gated, reason = hub.evaluate("a", True, False, 1000.0 + 60, cfg)
    assert gated is False and reason == "anticycle_min_off_hold"


# --- F09 full: independent compressor channels ---
def test_hub_channels_are_independent():
    cfg = _cfg(anticycle_min_off_s=600, anticycle_max_starts_per_h=6)
    hub = AntiCycleHub()
    # Channel "hp_a" was just stopped -> a fresh demand on it is held off.
    hub.channels["hp_a"] = CompressorState(on=False, last_off_ts=1000.0)
    held, reason = hub.evaluate("z1", True, False, 1000.0 + 60, cfg, channel="hp_a")
    assert held is False and reason == "anticycle_min_off_hold"
    # A different compressor "hp_b" is unaffected and starts normally.
    on, reason = hub.evaluate("z2", True, False, 1000.0 + 60, cfg, channel="hp_b")
    assert on is True and reason == "start"


def test_hub_participates_and_clear_across_channels():
    cfg = _cfg()
    hub = AntiCycleHub()
    hub.evaluate("z1", True, False, 1000.0, cfg, channel="hp_a")
    assert hub.participates("z1") is True
    hub.clear("z1")
    assert hub.participates("z1") is False


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
