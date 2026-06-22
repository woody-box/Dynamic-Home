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


def test_min_on_holds_before_registering_stop():
    cfg = _cfg(anticycle_min_on_s=600)
    st = CompressorState(on=True, last_on_ts=1000.0)
    on, reason = step(st, any_demand=False, force_off=False,
                      now_ts=1000.0 + 100, cfg=cfg)
    assert on is True and reason == "anticycle_min_on_hold"
    on, reason = step(st, False, False, now_ts=1000.0 + 700, cfg=cfg)
    assert on is False and reason == "off"


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
