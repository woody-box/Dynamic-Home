"""Unit tests for the pure DV decision engine.

These run WITHOUT Home Assistant and replace the YAML "golden scenarios".
Run with:  python -m pytest integration/tests/ -q
       or:  python integration/tests/test_engine.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from engine import (  # noqa: E402
    DvConfig, DvState, DvInputs, decide, base_target, update_ema,
    compute_freecool,
)


def _cfg(**kw):
    c = DvConfig()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# --------------------------------------------------------------------------- #
# EMA
# --------------------------------------------------------------------------- #
def test_ema_bootstrap_and_step():
    assert update_ema(0, 800, 0.2) == 800            # bootstrap
    assert update_ema(800, 1300, 0.2) == 0.2 * 1300 + 0.8 * 800


# --------------------------------------------------------------------------- #
# Hysteresis state machine
# --------------------------------------------------------------------------- #
def test_base_target_clean_air_is_v1():
    assert base_target(500, 5, _cfg(), 1, 100, 5) == 1


def test_base_target_high_co2_is_v3():
    assert base_target(1400, 5, _cfg(), 1, 100, 5) == 3


def test_base_target_holds_v3_within_hysteresis():
    # co2 just below v3 but within hysteresis band -> stays at 3
    assert base_target(1250, 5, _cfg(), 3, 100, 5) == 3


def test_base_target_drops_from_v3_to_v2_below_band():
    # co2 below v3-hys but still above v2 -> 2
    assert base_target(1100, 5, _cfg(), 3, 100, 5) == 2


# --------------------------------------------------------------------------- #
# Free-cooling
# --------------------------------------------------------------------------- #
def test_freecool_hysteresis():
    cfg = _cfg(freecool_enabled=True, freecool_t_ext_min=5,
               freecool_delta_on=2, freecool_delta_off=1)
    ins = DvInputs(t_in=24, t_ext=21)  # delta 3 >= on(2)
    assert compute_freecool(cfg, ins, prev_active=False) is True
    ins2 = DvInputs(t_in=22.5, t_ext=21)  # delta 1.5: < on but >= off
    assert compute_freecool(cfg, ins2, prev_active=True) is True
    assert compute_freecool(cfg, ins2, prev_active=False) is False
    ins3 = DvInputs(t_in=24, t_ext=3)  # t_ext below min
    assert compute_freecool(cfg, ins3, prev_active=False) is False


# --------------------------------------------------------------------------- #
# Full pipeline
# --------------------------------------------------------------------------- #
def test_not_permitted_is_off():
    d = decide(_cfg(), DvState(), DvInputs(permitida=False))
    assert d.speed == 0 and d.reason == "not_permitted"


def test_manual_override_v3():
    d = decide(_cfg(), DvState(),
               DvInputs(manual_override=True, override_v3=True))
    assert d.speed == 3 and d.reason == "manual_override"


def test_dry_mode_targets_by_dp_diff():
    cfg = _cfg(dry_v2_delta=0.2, dry_v3_delta=1.0)
    d = decide(cfg, DvState(),
               DvInputs(dry_mode=True, dew_risk=True, dp_diff=1.5))
    assert d.speed == 3 and d.reason == "dry_mode"


def test_auto_clean_air_v1():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, current_speed=1,
                        trigger_is_iaq=True))
    assert d.speed == 1 and d.reason == "iaq"


def test_auto_high_co2_raises_v3_on_iaq_trigger():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=1400, pm_raw=5, current_speed=1,
                        trigger_is_iaq=True))
    assert d.speed == 3


def test_freecool_lifts_to_v2():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False,
               freecool_enabled=True, freecool_t_ext_min=5,
               freecool_delta_on=2, freecool_delta_off=1)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, t_in=24, t_ext=21,
                        current_speed=1, trigger_is_iaq=True))
    assert d.speed == 2 and d.reason == "freecool"


def test_sdhb_quiet_caps_to_v1():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=1400, pm_raw=5, current_speed=3,
                        sdhb_intent="request_quiet", trigger_is_iaq=True))
    assert d.speed == 1 and d.reason == "sdhb_quiet"


def test_hostile_aqi_extreme_turns_off():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False,
               hostile_enabled=True, hostile_t1=50, hostile_t2=100, hostile_t3=150)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=1400, pm_raw=5, aqi=200, current_speed=2,
                        trigger_is_iaq=True))
    assert d.speed == 0 and d.reason == "hostile_off"


def test_antiflap_blocks_raise_without_iaq_trigger():
    # Clock tick (not IAQ) wanting to raise from v1 -> held at v1.
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=1400, pm_raw=5, current_speed=1,
                        trigger_is_iaq=False))
    assert d.speed == 1 and d.reason == "hold_antiflap"


def test_boost_overrides_antiflap():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, current_speed=1,
                        sdhb_intent="request_boost", trigger_is_iaq=False))
    assert d.speed == 3 and d.reason == "sdhb_boost"


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
