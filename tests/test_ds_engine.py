"""Unit tests for the pure DS (shutter) decision engine.

Run with:  python integration/tests/test_ds_engine.py
       or:  python -m pytest integration/tests/ -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from ds_engine import (  # noqa: E402
    DsConfig,
    DsInputs,
    DsState,
    decide_cover,
    quantize10,
    solar_impact,
    update_wind_cap_active,
)


def _cfg(**kw):
    c = DsConfig()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def test_quantize10_floors_to_tens():
    assert quantize10(67) == 60
    assert quantize10(70) == 70
    assert quantize10(9) == 0


def test_solar_impact_sun_in_front_no_overhang():
    cfg = _cfg(facade_azimuth_deg=180, facade_span_deg=180,
               window_height_cm=100, overhang_cm=0)
    # sun due south, high -> fully exposed
    assert solar_impact(cfg, 180, 45, True) == 100


def test_solar_impact_sun_behind_facade():
    cfg = _cfg(facade_azimuth_deg=180, facade_span_deg=180)
    # sun to the north -> not in front -> 0
    assert solar_impact(cfg, 0, 45, True) == 0


def test_solar_impact_below_horizon():
    cfg = _cfg(facade_azimuth_deg=180, facade_span_deg=180)
    assert solar_impact(cfg, 180, -5, True) == 0


def test_solar_impact_overhang_shades():
    cfg = _cfg(facade_azimuth_deg=180, facade_span_deg=180,
               window_height_cm=100, overhang_cm=100)
    # high sun + overhang -> heavily shaded -> low impact
    assert solar_impact(cfg, 180, 60, True) < 50


# --------------------------------------------------------------------------- #
# Cascade — base branches
# --------------------------------------------------------------------------- #
def test_default_fully_open():
    d = decide_cover(_cfg(slew_enabled=False), DsState(), DsInputs())
    assert d.pos == 100 and d.reason == "default"


def test_override_lock():
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(override_mode="lock", override_pos=25))
    assert d.pos == 25 and d.reason == "ov_lock"


def test_rain_closes():
    d = decide_cover(_cfg(rain_close_pct=0, slew_enabled=False), DsState(),
                     DsInputs(weather_protect_enabled=True, raining=True))
    assert d.pos == 0 and d.reason == "meteo_rain"


def test_privacy_time():
    d = decide_cover(_cfg(privacy_pos_pct=40, slew_enabled=False), DsState(),
                     DsInputs(privacy_active=True))
    assert d.pos == 40 and d.reason == "privacy_time"


def test_freecool_night_opens():
    d = decide_cover(_cfg(freecool_max_open_pct=60, freecool_delta=0.8,
                          slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", night=True, t_in=26, t_out=22))
    assert d.pos == 60 and d.reason == "freecool_night"


def test_summer_solar_shield():
    # impact 70, hot outside -> raw = 100-70 = 30 -> shield to 30
    d = decide_cover(_cfg(summer_min_open_pct=20, hot_delta=0.8,
                          slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=24, t_out=30))
    assert d.pos == 30 and d.reason == "summer_solar_shield"


def test_summer_shield_respects_min_open():
    # impact 90 -> raw 10 -> clamped to summer_min 20
    d = decide_cover(_cfg(summer_min_open_pct=20, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=90, t_in=24, t_out=30))
    assert d.pos == 20


def test_winter_solar_gain():
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=50))
    assert d.pos == 100 and d.reason == "winter_solar_gain"


def test_winter_night_insulate():
    d = decide_cover(_cfg(winter_night_pct=0, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=0))
    assert d.pos == 0 and d.reason == "winter_night_insulate"


# --------------------------------------------------------------------------- #
# Caps
# --------------------------------------------------------------------------- #
def test_wind_cap_limits_opening():
    cfg = _cfg(wind_limit_kmh=40, wind_cap_span_kmh=20, weather_max_open_pct=30,
               slew_enabled=False)
    st = DsState()
    # wind 60 = limit+span -> full cap to weather_max_open 30
    d = decide_cover(cfg, st, DsInputs(weather_protect_enabled=True, wind=60))
    assert d.pos == 30 and d.reason == "meteo_wind_cap"


def test_wind_cap_hysteresis():
    cfg = _cfg(wind_limit_kmh=40, wind_cap_hyst_kmh=5)
    st = DsState()
    assert update_wind_cap_active(st, cfg, DsInputs(weather_protect_enabled=True, wind=42)) is True
    # drop to 38: above release (35) -> stays active
    assert update_wind_cap_active(st, cfg, DsInputs(weather_protect_enabled=True, wind=38)) is True
    # drop to 34: below release -> off
    assert update_wind_cap_active(st, cfg, DsInputs(weather_protect_enabled=True, wind=34)) is False


def test_sdhb_solar_shield_clamps():
    cfg = _cfg(sdhb_solar_shield_max_open_pct=30, slew_enabled=False)
    d = decide_cover(cfg, DsState(),
                     DsInputs(sdhb_allow_override=True,
                              sdhb_request_solar_shield=True))  # default would be 100
    assert d.pos == 30 and d.reason == "sdhb_solar_shield"


def test_sdhb_quiet_freezes_position():
    cfg = _cfg(slew_enabled=False)
    d = decide_cover(cfg, DsState(),
                     DsInputs(sdhb_allow_override=True, sdhb_request_quiet=True,
                              quiet_respect_enabled=True, current_pos=55))
    assert d.pos == 55 and d.reason == "sdhb_quiet"


def test_rain_not_overridden_by_wind_cap():
    cfg = _cfg(rain_close_pct=0, wind_limit_kmh=40, slew_enabled=False)
    d = decide_cover(cfg, DsState(),
                     DsInputs(weather_protect_enabled=True, raining=True, wind=80))
    assert d.reason == "meteo_rain" and d.pos == 0


# --------------------------------------------------------------------------- #
# Slew
# --------------------------------------------------------------------------- #
def test_slew_limits_step():
    cfg = _cfg(slew_enabled=True, slew_step_pct=10)
    # target default 100, current 50 -> move only +10 -> 60
    d = decide_cover(cfg, DsState(), DsInputs(current_pos=50))
    assert d.pos == 60 and d.details.get("slew_applied") is True


def test_slew_not_applied_to_rain():
    cfg = _cfg(slew_enabled=True, slew_step_pct=10, rain_close_pct=0)
    d = decide_cover(cfg, DsState(),
                     DsInputs(weather_protect_enabled=True, raining=True,
                              current_pos=100))
    assert d.pos == 0 and d.reason == "meteo_rain"


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
