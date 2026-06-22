"""Unit tests for the pure DC (climate) decision engine."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from dc_engine import (  # noqa: E402
    INTENT_SOLAR_GAIN,
    INTENT_SOLAR_SHIELD,
    DcConfig,
    DcInputs,
    adaptive_lead_target,
    assemble_target,
    base_active,
    bias_exterior,
    bias_vmc,
    brake_bias,
    compute_lead,
    decide,
    dew_point,
    dew_risk,
    ema,
    facade_bias,
    forecast_bias,
    is_night,
    mold_index_step,
    on_rate_cph,
    publish_intent,
    quantize_step,
    sdhb_self_bias,
    step_toward,
    sunlit_facades,
    trend_bias,
    window_anomaly,
)


def _cfg(**kw):
    c = DcConfig()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# --- F22: mold-risk index ---
def test_mold_index_accumulates_above_threshold():
    cfg = _cfg(mold_rh_threshold=70, mold_cap_h=48)
    idx = mold_index_step(0.0, 80.0, 2.0, cfg)      # 2 h above threshold
    assert idx == 2.0
    idx = mold_index_step(idx, 80.0, 3.0, cfg)
    assert idx == 5.0


def test_mold_index_decays_below_threshold():
    cfg = _cfg(mold_rh_threshold=70, mold_decay_h=24)
    idx = mold_index_step(10.0, 50.0, 24.0, cfg)    # one time-constant of decay
    assert 3.0 < idx < 4.0                          # 10 * e^-1 ≈ 3.68


def test_mold_index_clamps_to_cap():
    cfg = _cfg(mold_rh_threshold=70, mold_cap_h=12)
    assert mold_index_step(11.0, 90.0, 5.0, cfg) == 12.0


def test_mold_index_unchanged_without_rh_or_time():
    cfg = _cfg()
    assert mold_index_step(4.0, None, 2.0, cfg) == 4.0
    assert mold_index_step(4.0, 90.0, 0.0, cfg) == 4.0


# --- F20: open-window inference signature + decision branch ---
def test_window_anomaly_heat_dropping():
    cfg = _cfg(window_drop_cph=2.5)
    assert window_anomaly("heat", True, -3.0, cfg) is True
    assert window_anomaly("heat", True, -1.0, cfg) is False   # below threshold
    assert window_anomaly("heat", True, 2.0, cfg) is False    # rising, not a window


def test_window_anomaly_cool_rising():
    cfg = _cfg(window_drop_cph=2.5)
    assert window_anomaly("cool", True, 3.0, cfg) is True
    assert window_anomaly("cool", True, -3.0, cfg) is False


def test_window_anomaly_needs_active_demand_and_mode():
    cfg = _cfg(window_drop_cph=2.5)
    assert window_anomaly("heat", False, -5.0, cfg) is False   # valve closed
    assert window_anomaly("off", True, -5.0, cfg) is False


def test_decide_window_inferred_turns_off():
    cfg = _cfg()
    d = decide(cfg, DcInputs(hvac_mode="heat", t_int=20.0, window_inferred=True))
    assert d.action == "off" and d.reason == "off_window_inferred"
    # The real sensor lockout still takes precedence with its own reason.
    d = decide(cfg, DcInputs(hvac_mode="heat", t_int=20.0, window_lockout=True))
    assert d.action == "off" and d.reason == "off_window"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def test_is_night():
    assert is_night(-5) is True
    assert is_night(10) is False
    assert is_night(None) is False  # degraded -> day


def test_base_active_day_night():
    cfg = _cfg(base_heat_day=22.5, base_cool_day=26.5, delta_night=0.5)
    assert base_active(cfg, "heat", night=False, vacation=False) == 22.5
    assert base_active(cfg, "heat", night=True, vacation=False) == 22.0
    assert base_active(cfg, "cool", night=True, vacation=False) == 27.0


def test_base_active_vacation():
    cfg = _cfg(vac_base_heat_day=17, vac_base_cool_day=30)
    assert base_active(cfg, "heat", night=True, vacation=True) == 17
    assert base_active(cfg, "cool", night=False, vacation=True) == 30


def test_bias_exterior_heat_cold():
    cfg = _cfg(ext_cold_threshold=0, bias_ext_heat_strong=0.5, bias_ext_heat_mild=0.2)
    assert bias_exterior(cfg, "heat", -2) == 0.5   # very cold
    assert bias_exterior(cfg, "heat", 3) == 0.2    # mild (<= 0+5)
    assert bias_exterior(cfg, "heat", 10) == 0.0   # warm enough


def test_bias_exterior_cool_hot():
    cfg = _cfg(ext_hot_threshold=30, bias_ext_cool_strong=0.5, bias_ext_cool_mild=0.2)
    assert bias_exterior(cfg, "cool", 32) == 0.5
    assert bias_exterior(cfg, "cool", 27) == 0.2   # >= 30-5
    assert bias_exterior(cfg, "cool", 20) == 0.0


def test_quantize_step():
    assert quantize_step(22.3, 0.5) == 22.5
    assert quantize_step(22.24, 0.5) == 22.0
    assert quantize_step(21.7, 0.5) == 21.5


def test_assemble_target_clamps_mods_and_range():
    cfg = _cfg(max_mods_heat=0.8, target_min_heat=18, target_max_heat=26, step=0.5)
    # base 22.5 + mods clamped to +0.8 + 0 -> 23.3 -> quantized 23.5
    assert assemble_target(cfg, "heat", 22.5, 5.0, 0.0, False) == 23.5
    # range clamp: huge base
    assert assemble_target(cfg, "heat", 40, 0, 0, False) == 26.0


def test_bias_vmc_heat_only_when_outside_colder():
    cfg = _cfg(vmc_bias_heat=(0.1, 0.2, 0.3))
    # outside colder (delta<0) at V2 -> +0.2
    assert bias_vmc(cfg, "heat", 2, 21, 5) == 0.2
    # outside warmer (delta>0) -> 0 in heat
    assert bias_vmc(cfg, "heat", 2, 21, 25) == 0.0
    # speed off -> 0
    assert bias_vmc(cfg, "heat", None, 21, 5) == 0.0


def test_bias_vmc_cool_sign():
    cfg = _cfg(vmc_bias_cool=(0.1, 0.2, 0.3))
    # outside hotter (delta>0) -> more cooling (negative)
    assert bias_vmc(cfg, "cool", 3, 26, 33) == -0.3
    # outside colder (delta<0) -> ease cooling (positive)
    assert bias_vmc(cfg, "cool", 3, 26, 20) == 0.3


def test_trend_bias_anticipates_and_clamps():
    cfg = _cfg(trend_lead_h=1.0, trend_max_shift=0.25)
    # rising 0.2 °C/h -> shift -0.2
    assert trend_bias(cfg, 0.2) == -0.2
    # rising fast -> clamped to -0.25
    assert trend_bias(cfg, 5.0) == -0.25


def test_brake_bias_only_when_trend_helps_mode():
    cfg = _cfg(brake_thresholds=(0.3, 0.6, 1.0), brake_biases=(0.1, 0.2, 0.3))
    # heating and warming fast (>=th3) -> brake down 0.3
    assert brake_bias(cfg, "heat", 1.2) == -0.3
    # heating but cooling -> no brake
    assert brake_bias(cfg, "heat", -1.2) == 0.0
    # cooling and cooling (cph<0) at th2 -> +0.2
    assert brake_bias(cfg, "cool", -0.7) == 0.2


def test_forecast_bias_brake_only():
    cfg = _cfg(forecast_gain=0.1, forecast_cap=0.5)
    # heating, forecast warmer than now (dT=+4) -> ease -0.4
    assert forecast_bias(cfg, "heat", 5, 9) == -0.4
    # heating, forecast colder -> no ease
    assert forecast_bias(cfg, "heat", 5, 2) == 0.0
    # clamp at cap
    assert forecast_bias(cfg, "heat", 0, 20) == -0.5
    # no forecast data -> 0
    assert forecast_bias(cfg, "heat", 5, None) == 0.0


def test_dew_point_magnus():
    # 25°C / 50% RH -> ~13.9°C dew point
    dp = dew_point(25, 50)
    assert 13.5 < dp < 14.3
    assert dew_point(None, 50) is None
    assert dew_point(25, 0) is None


def test_dew_risk_only_in_cool_and_near_dewpoint():
    cfg = _cfg(dew_spread_min=2.0)
    # cool, indoor 24 with dew point ~22.5 (90% RH) -> spread 1.5 < 2 -> risk
    assert dew_risk(cfg, "cool", 24, 90) is True
    # cool, dry air -> low dew point -> no risk
    assert dew_risk(cfg, "cool", 24, 40) is False
    # heat -> never dew risk
    assert dew_risk(cfg, "heat", 24, 95) is False


def test_decide_dew_risk_forces_off_via_engine():
    # cool with high humidity -> engine off_dew when caller passes dew_risk
    cfg = _cfg()
    d = decide(cfg, DcInputs(hvac_mode="cool", t_int=24, dew_risk=True))
    assert d.action == "off" and d.reason == "off_dew"


def test_compute_lead_grows_with_temp_gap():
    cfg = _cfg(lead_base_h=1.0, lead_per_degree_h=0.05, lead_min_h=0.5, lead_max_h=3.0)
    # small gap -> near base
    assert compute_lead(cfg, 21, 20) == 1.05
    # big gap -> clamped to max
    assert compute_lead(cfg, 22, -20) == 3.0
    # no data -> fallback trend_lead_h
    assert compute_lead(cfg, None, 5) == cfg.trend_lead_h
    # wind adds lead (0.02 h/km/h)
    assert compute_lead(cfg, 21, 20, wind=50) == 1.05 + 0.02 * 50


def test_trend_bias_uses_dynamic_lead():
    cfg = _cfg(trend_max_shift=1.0)
    # cph 0.2, lead 2.0 -> shift -0.4
    assert trend_bias(cfg, 0.2, 2.0) == -0.4


def test_facade_bias_eases_demand_with_open_sunlit_facades():
    cfg = _cfg(facade_gain_heat=0.3, facade_gain_cool=0.3)
    assert facade_bias(cfg, "heat", 1.0) == -0.3   # fully open & sunlit
    assert facade_bias(cfg, "heat", 0.5) == -0.15
    assert facade_bias(cfg, "cool", 1.0) == -0.3
    assert facade_bias(cfg, "off", 1.0) == 0.0


def test_decide_combines_biases():
    cfg = _cfg(base_heat_day=22.0, vmc_bias_heat=(0, 0.5, 0), step=0.5)
    # base 22.0 + vmc bias 0.5 (V2, outside colder) -> 22.5
    d = decide(cfg, DcInputs(hvac_mode="heat", t_int=21, t_ext=5,
                             sun_elevation=20, vmc_speed=2))
    assert d.target == 22.5


def test_sdhb_self_bias():
    cfg = _cfg(sdhb_bias_solar_gain_heat=-0.5, sdhb_bias_solar_shield_cool=0.5)
    assert sdhb_self_bias(cfg, INTENT_SOLAR_GAIN, "heat") == -0.5
    assert sdhb_self_bias(cfg, INTENT_SOLAR_SHIELD, "cool") == 0.5
    assert sdhb_self_bias(cfg, INTENT_SOLAR_GAIN, "cool") == 0.0


# --------------------------------------------------------------------------- #
# publish_intent — DC drives the shutters
# --------------------------------------------------------------------------- #
def test_publish_intent_by_mode():
    assert publish_intent("heat") == INTENT_SOLAR_GAIN
    assert publish_intent("cool") == INTENT_SOLAR_SHIELD
    assert publish_intent("off") == "none"


# --------------------------------------------------------------------------- #
# sunlit_facades — dynamic facade targeting
# --------------------------------------------------------------------------- #
_FACADES = {"ds_f180": 180.0, "ds_f000": 0.0, "ds_f090": 90.0}


def test_sunlit_due_south_lights_south_not_north():
    lit = sunlit_facades(180, 30, _FACADES)
    assert "ds_f180" in lit
    assert "ds_f000" not in lit


def test_sunlit_southeast_lights_south_and_east():
    lit = sunlit_facades(135, 30, _FACADES)
    assert lit == {"ds_f180", "ds_f090"}


def test_sunlit_below_horizon_lights_nothing():
    assert sunlit_facades(180, -5, _FACADES) == set()


def test_sunlit_no_sun_data_lights_nothing():
    assert sunlit_facades(None, None, _FACADES) == set()


def test_sunlit_per_facade_span_narrows_match():
    # A narrow 60° facade only counts the sun when nearly head-on.
    facades = {"ds_f180": 180.0}
    spans = {"ds_f180": 60.0}
    # sun 35° off-axis: outside ±30 -> not lit
    assert sunlit_facades(215, 30, facades, spans) == set()
    # sun 20° off-axis: inside ±30 -> lit
    assert sunlit_facades(200, 30, facades, spans) == {"ds_f180"}


def test_sunlit_mixed_spans():
    facades = {"ds_f180": 180.0, "ds_f090": 90.0}
    spans = {"ds_f180": 180.0, "ds_f090": 40.0}  # east facade is narrow
    # sun ESE (az 120): south (wide) lit; east (narrow, 30° off) not lit
    assert sunlit_facades(120, 30, facades, spans) == {"ds_f180"}


# --------------------------------------------------------------------------- #
# decide
# --------------------------------------------------------------------------- #
def test_decide_off_when_no_mode():
    d = decide(_cfg(), DcInputs(hvac_mode="off"))
    assert d.action == "off" and d.target is None and d.published_intent == "none"


def test_decide_dew_risk_forces_off():
    d = decide(_cfg(), DcInputs(hvac_mode="heat", dew_risk=True, t_ext=-5))
    assert d.action == "off" and d.reason == "off_dew"
    assert d.published_intent == "none"


def test_decide_window_lockout_off():
    d = decide(_cfg(), DcInputs(hvac_mode="cool", window_lockout=True))
    assert d.action == "off" and d.reason == "off_window"


def test_decide_heat_computes_target_and_publishes_gain():
    cfg = _cfg(base_heat_day=22.5, step=0.5)
    d = decide(cfg, DcInputs(hvac_mode="heat", t_ext=-5, t_int=20,
                             sun_elevation=20))
    assert d.action == "heat"
    assert d.target == 23.0  # 22.5 (day base) + exterior bias 0.5 -> 23.0
    assert d.published_intent == INTENT_SOLAR_GAIN


def test_decide_cool_publishes_shield():
    d = decide(_cfg(), DcInputs(hvac_mode="cool", t_ext=33, t_int=27,
                                sun_elevation=30))
    assert d.action == "cool"
    assert d.published_intent == INTENT_SOLAR_SHIELD


def test_decide_override_uses_manual_temp():
    d = decide(_cfg(), DcInputs(hvac_mode="heat", override_active=True,
                                override_temp=21.0))
    assert d.target == 21.0 and d.reason == "override"


# --------------------------------------------------------------------------- #
# Adaptive lead (learned anticipation)
# --------------------------------------------------------------------------- #
def test_ema_blends_toward_new():
    assert ema(0.0, 1.0, 0.5) == 0.5
    assert ema(2.0, 2.0, 0.2) == 2.0


def test_on_rate_gates_short_or_tiny_cycles():
    c = _cfg()
    # 2°C over 1h -> 2°C/h, trusted.
    assert on_rate_cph(18.0, 20.0, 1.0, c) == 2.0
    # Too short (< min_dt_h) -> rejected.
    assert on_rate_cph(18.0, 20.0, 0.1, c) is None
    # Too small a move (< min_dt) -> rejected.
    assert on_rate_cph(20.0, 20.02, 1.0, c) is None
    # Bad inputs -> None.
    assert on_rate_cph(None, 20.0, 1.0, c) is None


def test_adaptive_lead_target_from_overshoot_and_lag():
    c = _cfg(adapt_overshoot_target=0.1, adapt_rate_floor_cph=0.1, adapt_lag_k=1.0)
    # No excess overshoot, no lag -> zero lead.
    assert adaptive_lead_target(c, 0.1, 0.0, 1.0) == 0.0
    # Excess overshoot 0.4°C at 1°C/h -> 0.4h from overshoot term.
    assert adaptive_lead_target(c, 0.5, 0.0, 1.0) == 0.4
    # Lag dominates when larger.
    assert adaptive_lead_target(c, 0.1, 1.2, 1.0) == 1.2
    # Clamped to lead_adaptive_max_h.
    assert adaptive_lead_target(_cfg(lead_adaptive_max_h=2.0), 0.1, 5.0, 1.0) == 2.0


def test_vacation_uses_vacation_limits_not_normal_ones():
    # vac_base_heat_day (17) sits below the normal heat min (18). On vacation the
    # target must clamp to the vacation min (15), i.e. stay at 17 — not be pushed
    # up to 18 by the comfort range.
    cfg = DcConfig()
    d = decide(cfg, DcInputs(hvac_mode="heat", vacation=True, t_int=18.0,
                             t_ext=10.0))
    assert d.target == 17.0


def test_adaptive_lead_target_rate_floor_is_configurable():
    # The rate floor must come from config only (no hidden 0.1 literal, RNF-1).
    # Excess overshoot 0.05°C with a learned rate of 0.05°C/h and a floor of
    # 0.05 -> 0.05/0.05 = 1.0h. A masked 0.1 floor would have given 0.5h.
    c = _cfg(adapt_overshoot_target=0.1, adapt_rate_floor_cph=0.05,
             adapt_lag_k=1.0, lead_adaptive_max_h=4.0)
    assert adaptive_lead_target(c, 0.15, 0.0, 0.05) == 1.0


def test_step_toward_is_a_partial_gradient_step():
    assert step_toward(1.0, 2.0, 0.1) == 1.1
    assert step_toward(2.0, 2.0, 0.5) == 2.0


def test_adaptive_lead_overrides_physical_model_in_decide():
    c = _cfg()
    base = decide(c, DcInputs(hvac_mode="heat", t_int=19.0, t_ext=5.0,
                              trend_cph=0.1))
    adapt = decide(c, DcInputs(hvac_mode="heat", t_int=19.0, t_ext=5.0,
                               trend_cph=0.1, adaptive_lead_h=3.0))
    assert base.details["lead_source"] == "physical"
    assert adapt.details["lead_source"] == "adaptive"
    # A bigger lead means a stronger trend anticipation (different target/bias).
    assert adapt.details["lead_h"] == 3.0
    assert adapt.details["bias_trend"] != base.details["bias_trend"]


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
