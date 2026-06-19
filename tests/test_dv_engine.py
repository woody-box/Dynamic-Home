"""Unit tests for the pure DV decision engine.

These run WITHOUT Home Assistant and replace the YAML "golden scenarios".
Run with:  python -m pytest integration/tests/ -q
       or:  python integration/tests/test_dv_engine.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from dv_engine import (  # noqa: E402
    DvConfig,
    DvInputs,
    DvState,
    base_target,
    compute_freecool,
    decide,
    in_schedule,
    update_ema,
    update_failsafe,
    update_shower,
)


def _cfg(**kw):
    c = DvConfig()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _bt(co2, pm, v_actual, cfg=None, co2_hys=100, pm_hys=5):
    """Adapter for base_target using a DvConfig's thresholds."""
    c = cfg or _cfg()
    return base_target(co2, pm, c.co2_v2, c.co2_v3, c.pm_v2, c.pm_v3,
                       v_actual, co2_hys, pm_hys)


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
    assert _bt(500, 5, 1) == 1


def test_base_target_high_co2_is_v3():
    assert _bt(1400, 5, 1) == 3


def test_base_target_holds_v3_within_hysteresis():
    # co2 just below v3 but within hysteresis band -> stays at 3
    assert _bt(1250, 5, 3) == 3


def test_base_target_drops_from_v3_to_v2_below_band():
    # co2 below v3-hys but still above v2 -> 2
    assert _bt(1100, 5, 3) == 2


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


# --------------------------------------------------------------------------- #
# Weekly schedule
# --------------------------------------------------------------------------- #
def test_schedule_disabled_always_allowed():
    assert in_schedule(0, 0, _cfg()) is True


def test_schedule_daytime_window():
    cfg = _cfg(schedule_enabled=True, schedule={0: (8 * 60, 22 * 60)})
    assert in_schedule(0, 10 * 60, cfg) is True   # 10:00 inside
    assert in_schedule(0, 23 * 60, cfg) is False  # 23:00 outside


def test_schedule_overnight_wrap():
    cfg = _cfg(schedule_enabled=True, schedule={0: (22 * 60, 6 * 60)})
    assert in_schedule(0, 23 * 60, cfg) is True   # 23:00 inside (overnight)
    assert in_schedule(0, 2 * 60, cfg) is True    # 02:00 inside
    assert in_schedule(0, 12 * 60, cfg) is False  # 12:00 outside


def test_not_permitted_outside_schedule():
    cfg = _cfg(schedule_enabled=True, schedule={0: (8 * 60, 22 * 60)})
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, weekday=0, minute_of_day=23 * 60))
    assert d.speed == 0 and d.reason == "not_permitted"


def test_permiso_extra_overrides_schedule():
    cfg = _cfg(schedule_enabled=True, schedule={0: (8 * 60, 22 * 60)})
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, weekday=0, minute_of_day=23 * 60,
                        permiso_extra=True, trigger_is_iaq=True))
    assert d.speed >= 1 and d.reason != "not_permitted"


# --------------------------------------------------------------------------- #
# Failsafe
# --------------------------------------------------------------------------- #
def test_vital_ko_forces_v1():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    # co2 missing -> vital KO -> V1 in auto
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=None, pm_raw=5, current_speed=2))
    assert d.speed == 1 and d.reason == "failsafe_vital_ko"


def test_startup_grace_suppresses_vital_ko():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=None, pm_raw=None, current_speed=1,
                        startup_grace_active=True, trigger_is_iaq=True))
    # during grace, no vital KO -> falls through to auto with co2/pm 0 -> V1
    assert d.reason != "failsafe_vital_ko"


def test_trip_counter_arms_lockout():
    cfg = _cfg(trip_limit=3, trip_window_s=7200, lockout_s=1800,
               stale_threshold_s=120)
    st = DvState()
    # 3 rising edges of vital KO within window -> lockout armed
    update_failsafe(st, cfg, 0, True)      # trip 1 (edge)
    update_failsafe(st, cfg, 10, False)
    update_failsafe(st, cfg, 20, True)     # trip 2
    update_failsafe(st, cfg, 30, False)
    locked = update_failsafe(st, cfg, 40, True)  # trip 3 -> lockout
    assert locked is True
    assert st.lockout_until == 40 + 1800


def test_decide_returns_lockout_when_active():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    st = DvState(lockout_until=1000)
    d = decide(cfg, st, DvInputs(co2_raw=500, pm_raw=5, now_ts=500))
    assert d.speed == 0 and d.reason == "lockout"


# --------------------------------------------------------------------------- #
# Shower boost (ΔRH)
# --------------------------------------------------------------------------- #
def test_shower_rh_triggers_and_holds():
    cfg = _cfg(shower_enabled=True, shower_rh_delta_on=8, shower_rh_delta_off=4,
               shower_hold_s=600, shower_level=3)
    st = DvState()
    assert update_shower(st, cfg, 0, 10) is True       # rise >= on
    assert update_shower(st, cfg, 100, 2) is True       # within hold -> stays
    assert update_shower(st, cfg, 700, 2) is False      # past hold & below off


def test_shower_drives_speed():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False,
               shower_enabled=True, shower_rh_delta_on=8, shower_level=3)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, rh_delta=12, now_ts=0))
    assert d.speed == 3 and d.reason == "shower_rh"


# --------------------------------------------------------------------------- #
# Adaptive thresholds
# --------------------------------------------------------------------------- #
def test_adaptive_thresholds_override_config():
    # Base config would keep V1 at co2=850 (below v2=900). With an adaptive
    # lower v2 of 800, the same reading should request V2.
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False, adaptive_enabled=True)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=850, pm_raw=5, current_speed=1,
                        adaptive_co2_v2=800, trigger_is_iaq=True))
    assert d.speed == 2


def test_adaptive_ignored_when_disabled():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False, adaptive_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=850, pm_raw=5, current_speed=1,
                        adaptive_co2_v2=800, trigger_is_iaq=True))
    assert d.speed == 1


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
