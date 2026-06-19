"""Unit tests for the pure DC (climate) decision engine."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from dc_engine import (  # noqa: E402
    DcConfig, DcInputs, decide, base_active, bias_exterior, sdhb_self_bias,
    assemble_target, quantize_step, publish_intent, is_night, sunlit_facades,
    INTENT_SOLAR_GAIN, INTENT_SOLAR_SHIELD,
)


def _cfg(**kw):
    c = DcConfig()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


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
