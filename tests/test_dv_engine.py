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
    in_quiet_window,
    in_schedule,
    update_anticip,
    update_anticip_rates,
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


# --- F13: dew-point drying gate (dp_diff margin + hysteresis) ---
def _dry_ins(dp_diff, **kw):
    base = dict(dry_mode=True, dew_risk=True, dp_diff=dp_diff,
                co2_raw=500, pm_raw=5, current_speed=1, trigger_is_iaq=True)
    base.update(kw)
    return DvInputs(**base)


def _dry_cfg():
    return _cfg(co2_ema_enabled=False, pm_ema_enabled=False,
                dry_margin=1.0, dry_hys=0.5)


def test_dry_gate_blocks_below_margin():
    # Outdoor not meaningfully drier -> do NOT ventilate to dry; fall through.
    d = decide(_dry_cfg(), DvState(), _dry_ins(0.5))
    assert d.reason == "iaq" and d.speed == 1


def test_dry_gate_opens_above_margin():
    d = decide(_dry_cfg(), DvState(), _dry_ins(1.5))
    assert d.reason == "dry_mode" and d.speed == 3


def test_dry_gate_hysteresis_holds_and_does_not_arm_in_band():
    # 0.5 (off) < 0.7 <= 1.0 (on): stays on if active, does not arm if not.
    d_on = decide(_dry_cfg(), DvState(dry_active=True), _dry_ins(0.7))
    assert d_on.reason == "dry_mode"
    d_off = decide(_dry_cfg(), DvState(), _dry_ins(0.7))
    assert d_off.reason == "iaq"


def test_dry_gate_turns_off_below_off_threshold():
    st = DvState(dry_active=True)
    d = decide(_dry_cfg(), st, _dry_ins(0.4))
    assert d.reason != "dry_mode" and st.dry_active is False


def test_dry_gate_resets_when_dry_mode_off():
    st = DvState(dry_active=True)
    decide(_dry_cfg(), st, _dry_ins(2.0, dry_mode=False))
    assert st.dry_active is False


def test_dry_gate_none_dp_diff_falls_through():
    d = decide(_dry_cfg(), DvState(), _dry_ins(None))
    assert d.reason == "iaq"


# --- F11: anticipatory ventilation (CO2/PM slope detector) ---
def _anticip_cfg(**kw):
    base = dict(co2_ema_enabled=False, pm_ema_enabled=False,
                anticip_enabled=True, anticip_co2_rate_on=400,
                anticip_co2_rate_off=150, anticip_pm_rate_on=20,
                anticip_pm_rate_off=8, anticip_hold_s=600,
                anticip_level=2, anticip_ema_alpha=1.0)
    base.update(kw)
    return _cfg(**base)


def _ains(co2, pm, now_ts, **kw):
    base = dict(co2_raw=co2, pm_raw=pm, current_speed=1, now_ts=now_ts,
                trigger_is_iaq=False)
    base.update(kw)
    return DvInputs(**base)


def test_anticip_rates_bootstrap_then_slope():
    cfg, st = _anticip_cfg(), DvState()
    update_anticip_rates(st, cfg, 100.0, 600, 5)            # bootstrap -> rate 0
    assert st.anticip_co2_rate == 0.0 and st.anticip_pm_rate == 0.0
    update_anticip_rates(st, cfg, 100.0 + 3600, 1000, 5)    # +400 ppm over 1 h
    assert st.anticip_co2_rate == 400.0
    assert st.anticip_pm_rate == 0.0


def test_anticip_rates_dt_guard():
    cfg, st = _anticip_cfg(), DvState()
    update_anticip_rates(st, cfg, 100.0, 600, 5)            # bootstrap
    update_anticip_rates(st, cfg, 100.0, 800, 5)            # dt == 0 -> ignored
    assert st.anticip_co2_rate == 0.0
    update_anticip_rates(st, cfg, 50.0, 800, 5)             # dt < 0 -> ignored
    assert st.anticip_co2_rate == 0.0


def test_anticip_detector_on_off_hold():
    cfg, st = _anticip_cfg(), DvState()
    st.anticip_co2_rate = 500                               # >= on (400)
    assert update_anticip(st, cfg, 100) is True
    assert st.anticip_hold_until == 100 + 600
    st.anticip_co2_rate = 50                                # below off, pm 0
    assert update_anticip(st, cfg, 200) is True             # within hold -> stays
    assert update_anticip(st, cfg, 800) is False            # past hold & below off


def test_anticip_detector_pm_channel():
    cfg, st = _anticip_cfg(), DvState()
    st.anticip_pm_rate = 25                                 # >= on (20)
    assert update_anticip(st, cfg, 100) is True


def test_anticip_detector_disabled_keeps_hold():
    cfg = _anticip_cfg(anticip_enabled=False)
    st = DvState(anticip_active=True, anticip_hold_until=500)
    assert update_anticip(st, cfg, 200) is True             # within hold
    assert update_anticip(st, cfg, 600) is False            # past hold -> off


def test_anticip_steep_co2_lifts_to_level():
    cfg, st = _anticip_cfg(), DvState()
    d1 = decide(cfg, st, _ains(600, 5, 100.0))             # bootstrap, clean -> V1
    assert d1.speed == 1 and d1.reason in ("iaq", "hold_antiflap")
    # +280 ppm over 30 min = 560 ppm/h >= on, while 880 < co2_v2 (900) -> base V1.
    d2 = decide(cfg, st, _ains(880, 5, 100.0 + 1800))
    assert d2.reason == "anticipatory" and d2.speed == 2


def test_anticip_flat_trend_no_lift():
    cfg, st = _anticip_cfg(), DvState()
    decide(cfg, st, _ains(600, 5, 100.0))
    d = decide(cfg, st, _ains(605, 5, 100.0 + 1800))       # ~10 ppm/h
    assert d.reason != "anticipatory" and d.speed == 1


def test_anticip_hold_then_release():
    cfg, st = _anticip_cfg(), DvState()
    decide(cfg, st, _ains(600, 5, 100.0))
    d2 = decide(cfg, st, _ains(880, 5, 100.0 + 1800))
    assert d2.reason == "anticipatory"
    # within hold, slope now flat -> latch keeps it on
    d3 = decide(cfg, st, _ains(882, 5, 100.0 + 1860))
    assert d3.reason == "anticipatory"
    # past hold, slope low -> releases
    d4 = decide(cfg, st, _ains(820, 5, 100.0 + 2600))
    assert d4.reason != "anticipatory"


def test_anticip_pm_driven_lift():
    cfg, st = _anticip_cfg(), DvState()
    decide(cfg, st, _ains(500, 5, 100.0))
    # +8 µg/m³ over 20 min = 24 µg/m³/h >= on, while 13 < pm_v2 (15) -> base V1.
    d = decide(cfg, st, _ains(500, 13, 100.0 + 1200))
    assert d.reason == "anticipatory" and d.speed == 2


def test_anticip_does_not_override_higher_base():
    cfg, st = _anticip_cfg(), DvState()
    decide(cfg, st, _ains(600, 5, 100.0))
    d = decide(cfg, st, _ains(1400, 5, 100.0 + 1800))      # base V3
    assert d.speed == 3 and d.reason != "anticipatory"


def test_anticip_hostile_cap_still_applies():
    cfg = _anticip_cfg(hostile_enabled=True, hostile_t1=50, hostile_t2=100,
                       hostile_t3=150)
    st = DvState()
    decide(cfg, st, _ains(600, 5, 100.0, aqi=120))
    d = decide(cfg, st, _ains(880, 5, 100.0 + 1800, aqi=120))
    assert d.reason == "hostile_cap_v1" and d.speed == 1


def test_anticip_disabled_no_lift():
    cfg = _anticip_cfg(anticip_enabled=False)
    st = DvState()
    decide(cfg, st, _ains(600, 5, 100.0))
    d = decide(cfg, st, _ains(880, 5, 100.0 + 1800))
    assert d.reason != "anticipatory"


# --- CO2 sanity floor (robustness): reject physically-absurd low readings ---
def test_co2_sanity_floor_rejects_absurd_low():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False, co2_sanity_floor=250)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=0, pm_raw=5, current_speed=1, now_ts=1000,
                        startup_grace_active=False, trigger_is_iaq=True))
    assert d.reason == "failsafe_vital_ko" and d.speed == 1


def test_co2_sanity_floor_allows_normal():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False, co2_sanity_floor=250)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, current_speed=1, now_ts=1000,
                        startup_grace_active=False, trigger_is_iaq=True))
    assert d.reason == "iaq" and d.speed == 1


def test_co2_sanity_floor_does_not_pollute_ema():
    cfg = _cfg(co2_sanity_floor=250)            # EMA enabled (default)
    st = DvState(co2_ema=800.0)
    decide(cfg, st, DvInputs(co2_raw=0, pm_raw=5, now_ts=1000,
                             startup_grace_active=False))
    assert st.co2_ema == 800.0                  # absurd-low reading ignored


def test_co2_sanity_floor_configurable_off():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False, co2_sanity_floor=0)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=0, pm_raw=5, current_speed=1, now_ts=1000,
                        startup_grace_active=False, trigger_is_iaq=True))
    assert d.reason != "failsafe_vital_ko"      # floor disabled -> 0 accepted


def test_pm_low_is_not_floored():
    """PM2.5 ~0 is physically real (clean air) and must not trigger a fault."""
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False, co2_sanity_floor=250)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=0, current_speed=1, now_ts=1000,
                        startup_grace_active=False, trigger_is_iaq=True))
    assert d.reason == "iaq" and d.speed == 1


# --- F12: quiet hours (night cap OFF/V1/V2 with critical-air exception) ---
def _quiet_cfg(**kw):
    base = dict(co2_ema_enabled=False, pm_ema_enabled=False,
                quiet_enabled=True, quiet_start_min=23 * 60, quiet_end_min=7 * 60,
                quiet_max_level=1, quiet_critical_co2=1500, quiet_critical_pm=50)
    base.update(kw)
    return _cfg(**base)


def _qins(co2, minute, **kw):
    base = dict(co2_raw=co2, pm_raw=5, current_speed=1, now_ts=0, weekday=0,
                minute_of_day=minute, trigger_is_iaq=True)
    base.update(kw)
    return DvInputs(**base)


def test_in_quiet_window_overnight():
    cfg = _quiet_cfg()
    assert in_quiet_window(23 * 60 + 30, cfg) is True   # 23:30
    assert in_quiet_window(3 * 60, cfg) is True          # 03:00
    assert in_quiet_window(12 * 60, cfg) is False        # 12:00


def test_in_quiet_window_disabled():
    assert in_quiet_window(3 * 60, _quiet_cfg(quiet_enabled=False)) is False


def test_quiet_caps_auto_speed():
    d = decide(_quiet_cfg(quiet_max_level=1), DvState(), _qins(1400, 3 * 60))
    assert d.reason == "quiet_cap" and d.speed == 1


def test_quiet_caps_to_off():
    d = decide(_quiet_cfg(quiet_max_level=0), DvState(), _qins(1400, 3 * 60))
    assert d.reason == "quiet_cap" and d.speed == 0


def test_quiet_critical_co2_lifts_cap():
    d = decide(_quiet_cfg(quiet_max_level=1), DvState(), _qins(1600, 3 * 60))
    assert d.reason != "quiet_cap" and d.speed == 3


def test_quiet_no_cap_outside_window():
    d = decide(_quiet_cfg(quiet_max_level=1), DvState(), _qins(1400, 12 * 60))
    assert d.reason != "quiet_cap" and d.speed == 3


def test_quiet_max_level_v3_no_cap():
    d = decide(_quiet_cfg(quiet_max_level=3), DvState(), _qins(1400, 3 * 60))
    assert d.speed == 3 and d.reason != "quiet_cap"


def test_quiet_does_not_cap_manual_override():
    d = decide(_quiet_cfg(quiet_max_level=1), DvState(),
               _qins(500, 3 * 60, manual_override=True, override_v3=True))
    assert d.reason == "manual_override" and d.speed == 3


# --- F14: timed V3 boost (service-driven, auto-reverting) ---
def test_boost_forces_v3():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, boost_active=True, now_ts=0))
    assert d.speed == 3 and d.reason == "boost"


def test_boost_overrides_quiet_cap():
    d = decide(_quiet_cfg(quiet_max_level=1), DvState(),
               DvInputs(co2_raw=500, pm_raw=5, boost_active=True, now_ts=0,
                        weekday=0, minute_of_day=3 * 60))
    assert d.speed == 3 and d.reason == "boost"


def test_boost_inactive_is_normal():
    cfg = _cfg(co2_ema_enabled=False, pm_ema_enabled=False)
    d = decide(cfg, DvState(),
               DvInputs(co2_raw=500, pm_raw=5, boost_active=False, now_ts=0,
                        trigger_is_iaq=True))
    assert d.reason == "iaq"


def test_boost_respects_not_permitted():
    d = decide(_cfg(), DvState(), DvInputs(permitida=False, boost_active=True))
    assert d.speed == 0


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
