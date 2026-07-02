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
    alert_active,
    decide_cover,
    geo_shade_pos,
    quantize10,
    solar_impact,
    solar_penetration_m,
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


def test_solar_impact_overhang_offset_reduces_shading():
    base = dict(facade_azimuth_deg=180, facade_span_deg=180,
                window_height_cm=100, overhang_cm=60)
    flush = solar_impact(_cfg(**base), 180, 45, True)
    raised = solar_impact(_cfg(**base, overhang_offset_cm=30), 180, 45, True)
    assert raised > flush       # lifting the eave off the window head shades less


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


def test_weather_protect_off_ignores_rain():
    # With weather protection off for this shutter, rain no longer closes it.
    d = decide_cover(_cfg(rain_close_pct=0, slew_enabled=False), DsState(),
                     DsInputs(weather_protect_enabled=False, raining=True))
    assert d.reason != "meteo_rain"


def test_privacy_time():
    d = decide_cover(_cfg(privacy_pos_pct=40, slew_enabled=False), DsState(),
                     DsInputs(privacy_active=True))
    assert d.pos == 40 and d.reason == "privacy_time"


def test_manual_hold_beats_comfort():
    # A manual hold pins the position over all the comfort logic (no trap).
    cfg = _cfg(slew_enabled=False, summer_min_open_pct=20)
    base = dict(hvac_mode="cool", impact=80, t_in=24, t_out=30)   # would solar-shield
    d_auto = decide_cover(cfg, DsState(), DsInputs(**base))
    assert d_auto.reason == "summer_solar_shield"                 # closes by default
    d_hold = decide_cover(cfg, DsState(), DsInputs(**base, manual_pos=90))
    assert d_hold.pos == 90 and d_hold.reason == "manual_hold"    # stays where you left it
    # Also outranks privacy and the dawn ramp.
    d = decide_cover(cfg, DsState(),
                     DsInputs(manual_pos=70, privacy_active=True, dawn_pos=30))
    assert d.pos == 70 and d.reason == "manual_hold"


def test_manual_hold_beats_everything_including_lock():
    # A manual hold outranks EVERY condition — weather alert, rain, and since
    # v0.94.2 the lock too: what you just did by hand stands, and the lock
    # re-imposes its position only once the hold expires (coordinator drops
    # manual_pos) or the user resumes auto.
    cfg = _cfg(rain_close_pct=0, slew_enabled=False)
    d = decide_cover(cfg, DsState(),
                     DsInputs(manual_pos=90, weather_protect_enabled=True,
                              raining=True))
    assert d.pos == 90 and d.reason == "manual_hold"          # rain doesn't undo it
    d = decide_cover(cfg, DsState(), DsInputs(manual_pos=90, alert_pos=0))
    assert d.pos == 90 and d.reason == "manual_hold"          # nor a weather alert
    # The lock yields to a fresh hand command...
    d = decide_cover(cfg, DsState(),
                     DsInputs(manual_pos=90, override_mode="lock", override_pos=10))
    assert d.pos == 90 and d.reason == "manual_hold"
    # ...and re-imposes once the hold is gone.
    d = decide_cover(cfg, DsState(),
                     DsInputs(manual_pos=None, override_mode="lock", override_pos=10))
    assert d.pos == 10 and d.reason == "ov_lock"


def test_manual_hold_is_protected_from_slew():
    # PROTECTED: the slew limiter doesn't drag a manual hold toward its old spot.
    cfg = _cfg(slew_enabled=True, slew_step_pct=10)
    d = decide_cover(cfg, DsState(), DsInputs(manual_pos=100, current_pos=0))
    assert d.pos == 100 and d.reason == "manual_hold"


def test_dawn_ramp_drives_position():
    # F19: an active sunrise ramp sets the stepped opening.
    d = decide_cover(_cfg(slew_enabled=False), DsState(), DsInputs(dawn_pos=30))
    assert d.pos == 30 and d.reason == "dawn_ramp"


def test_dawn_ramp_yields_to_safety_and_privacy():
    # Override / rain / privacy outrank the dawn ramp.
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(dawn_pos=30, override_mode="lock", override_pos=0))
    assert d.reason == "ov_lock"
    d = decide_cover(_cfg(privacy_pos_pct=40, slew_enabled=False), DsState(),
                     DsInputs(dawn_pos=30, privacy_active=True))
    assert d.reason == "privacy_time"


def test_dawn_yields_to_solar_shield():
    # Cooling + direct sun + hot: the dawn ramp must NOT open into the sun; the
    # solar shield owns it instead.
    d = decide_cover(_cfg(hot_delta=0.8, summer_min_open_pct=20, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=26, t_out=28,
                              dawn_pos=50))
    assert d.reason == "summer_solar_shield" and d.pos != 50


def test_dawn_yields_to_heat_shield():
    # Cooling + hot + no sun + shield on: the dawn ramp yields to the heat shield.
    d = decide_cover(_cfg(hot_delta=0.8, heat_shield_pct=0, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="cool", impact=0, t_in=26, t_out=28,
                              heat_shield=True, dawn_pos=50))
    assert d.reason == "summer_heat_shield"


def test_dawn_runs_when_no_cooling_threat():
    # Cooling but not hotter outside -> no protection needed -> dawn ramps.
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=0, t_in=26, t_out=24,
                              dawn_pos=50))
    assert d.reason == "dawn_ramp" and d.pos == 50


def test_dawn_yields_to_direct_sun_shield_before_it_is_hot():
    # East facade at dawn: cooling + direct sun on the facade + direct-sun shield
    # armed, but the air outside is NOT hotter yet. The ramp must still yield so it
    # doesn't open into the rising sun only to claw back closed once it heats up.
    d = decide_cover(_cfg(summer_min_open_pct=20, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=26, t_out=24,
                              sun_gain_shield=True, dawn_pos=50))
    assert d.reason != "dawn_ramp" and d.pos != 50


def test_dawn_runs_without_direct_sun_shield_optin():
    # Same conditions but the direct-sun shield is OFF: with no opt-in to protect
    # before it's hot, the ramp keeps opening (legacy behaviour preserved).
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=26, t_out=24,
                              sun_gain_shield=False, dawn_pos=50))
    assert d.reason == "dawn_ramp" and d.pos == 50


def test_dawn_runs_in_heat_season():
    # Heating: the gradual sunrise still gives morning light/gain (unaffected).
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=80, t_in=20, t_out=2,
                              dawn_pos=50))
    assert d.reason == "dawn_ramp" and d.pos == 50


def test_weather_alert_protects_and_is_protected():
    # F17: an active alert drives the protection position with reason meteo_alert.
    d = decide_cover(_cfg(slew_enabled=False), DsState(), DsInputs(alert_pos=0))
    assert d.pos == 0 and d.reason == "meteo_alert"
    # PROTECTED: slew does not soften it even with a far current position.
    d = decide_cover(_cfg(slew_enabled=True, slew_step_pct=10), DsState(),
                     DsInputs(alert_pos=0, current_pos=100))
    assert d.pos == 0 and d.reason == "meteo_alert"


def test_alert_active_binary():
    # binary_sensor / input_boolean shapes (back-compat with Open-Meteo).
    cfg = DsConfig()
    assert alert_active("on", "generic", cfg) is True
    assert alert_active("off", "wind", cfg) is False
    assert alert_active(None, "hail", cfg) is False
    for s in ("unknown", "unavailable", "none", ""):
        assert alert_active(s, "generic", cfg) is False


def test_alert_active_numeric_threshold():
    # Numeric sensor (e.g. Google Weather): wind -> gust km/h, else probability %.
    cfg = DsConfig(alert_gust_kmh=50.0, alert_prob_pct=70.0)
    assert alert_active("55", "wind", cfg) is True       # gust over threshold
    assert alert_active("40", "wind", cfg) is False
    assert alert_active("80", "hail", cfg) is True       # probability over threshold
    assert alert_active("60", "generic", cfg) is False
    # rain -> precipitation mm over the (small) threshold.
    assert alert_active("0.4", "rain", cfg) is True
    assert alert_active("0.0", "rain", cfg) is False
    # 0 disables the numeric threshold.
    assert alert_active("90", "wind", DsConfig(alert_gust_kmh=0.0)) is False


def test_alert_active_condition_keyword():
    # Condition/weather sensor: HA condition vocabulary per kind.
    cfg = DsConfig()
    assert alert_active("lightning", "hail", cfg) is True
    assert alert_active("hail", "hail", cfg) is True
    assert alert_active("windy", "wind", cfg) is True
    assert alert_active("windy", "hail", cfg) is False   # wrong kind
    assert alert_active("rainy", "generic", cfg) is True
    assert alert_active("sunny", "generic", cfg) is False
    assert alert_active("Lightning-Rainy", "hail", cfg) is True  # case-insensitive
    assert alert_active("pouring", "rain", cfg) is True
    assert alert_active("cloudy", "rain", cfg) is False


def test_weather_alert_yields_to_override():
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(alert_pos=0, override_mode="lock", override_pos=80))
    assert d.reason == "ov_lock" and d.pos == 80


def test_night_insulate_drives_position():
    # F16: an active night strategy sets the position.
    d = decide_cover(_cfg(slew_enabled=False), DsState(), DsInputs(night_pos=0))
    assert d.pos == 0 and d.reason == "night_insulate"


def test_presence_sim_drives_position():
    # Away presence simulation sets the position with its own reason.
    d = decide_cover(_cfg(slew_enabled=False), DsState(), DsInputs(sim_pos=50))
    assert d.pos == 50 and d.reason == "presence_sim"


def test_presence_sim_yields_to_weather():
    # Rain (safety) wins over the simulation.
    d = decide_cover(_cfg(rain_close_pct=0, slew_enabled=False), DsState(),
                     DsInputs(sim_pos=50, weather_protect_enabled=True,
                              raining=True))
    assert d.reason == "meteo_rain"


def test_sleep_mode_closes():
    d = decide_cover(_cfg(slew_enabled=False), DsState(), DsInputs(sleep_pos=0))
    assert d.pos == 0 and d.reason == "mode_sleep"


def test_sleep_yields_to_weather():
    d = decide_cover(_cfg(rain_close_pct=0, slew_enabled=False), DsState(),
                     DsInputs(sleep_pos=0, weather_protect_enabled=True,
                              raining=True))
    assert d.reason == "meteo_rain"


def test_night_purge_reason_when_opening():
    # F16: opening to vent the thermal mass reads night_purge (vs night_insulate
    # when closing), so the Motivo tells the two apart.
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(night_pos=100, night_purge=True))
    assert d.pos == 100 and d.reason == "night_purge"


def test_night_insulate_yields_to_safety():
    d = decide_cover(_cfg(rain_close_pct=0, slew_enabled=False), DsState(),
                     DsInputs(night_pos=100, weather_protect_enabled=True,
                              raining=True))
    assert d.reason == "meteo_rain"


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


def test_direct_sun_shield_needs_opt_in_when_cooler_outside():
    # Cooling + direct sun, but cooler outside: legacy = no shield (stays open).
    cfg = _cfg(summer_min_open_pct=20, hot_delta=0.8, slew_enabled=False)
    ins = dict(hvac_mode="cool", impact=70, t_in=26, t_out=22)   # 22 < 26 -> not hot
    d_off = decide_cover(cfg, DsState(), DsInputs(**ins))
    assert d_off.reason == "default" and d_off.pos == 100
    # With the direct-sun shield opt-in, the sun alone shades (solar gain).
    d_on = decide_cover(cfg, DsState(), DsInputs(**ins, sun_gain_shield=True))
    assert d_on.reason == "summer_solar_shield" and d_on.pos == 30


def test_winter_solar_gain():
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=50))
    assert d.pos == 100 and d.reason == "winter_solar_gain"


def test_winter_night_insulate():
    # No sun info (sun below horizon / unknown) -> always insulate (legacy).
    d = decide_cover(_cfg(winter_night_pct=0, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=0))
    assert d.pos == 0 and d.reason == "winter_night_insulate"


def test_winter_cold_shield_day_colder_outside():
    # Shield on, daytime (sun up), no direct sun, colder outside -> insulate.
    d = decide_cover(_cfg(winter_night_pct=0, cold_delta=0.8, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="heat", impact=0, t_in=21, t_out=8,
                              sun_elevation=20, heat_shield=True))
    assert d.pos == 0 and d.reason == "winter_cold_shield"


def test_winter_mild_day_opens_for_light():
    # Shield on, daytime, no direct sun, mild/warmer outside -> stay open (light).
    d = decide_cover(_cfg(winter_night_pct=0, cold_delta=0.8, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="heat", impact=0, t_in=21, t_out=22,
                              sun_elevation=20, heat_shield=True))
    assert d.pos == 100 and d.reason == "winter_mild_open"


def test_winter_night_insulates_even_if_mild():
    # Sun below horizon -> insulate regardless of the outdoor temperature.
    d = decide_cover(_cfg(winter_night_pct=0, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=0, t_in=21, t_out=22,
                              sun_elevation=-5, heat_shield=True))
    assert d.pos == 0 and d.reason == "winter_night_insulate"


def test_winter_shield_off_always_insulates_by_day():
    # Shield OFF (default): heating with no sun insulates even on a mild day.
    d = decide_cover(_cfg(winter_night_pct=0, cold_delta=0.8, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="heat", impact=0, t_in=21, t_out=22,
                              sun_elevation=20))
    assert d.pos == 0 and d.reason == "winter_night_insulate"


def test_heat_shield_closes_when_hot_outside_no_direct_sun():
    # Shield on, cooling, hotter outside, but no direct sun (impact 0): don't open
    # into the ambient heat -> hold the heat-shield position (0).
    d = decide_cover(_cfg(heat_shield_pct=0, hot_delta=0.8, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="cool", impact=0, t_in=24, t_out=30,
                              heat_shield=True))
    assert d.pos == 0 and d.reason == "summer_heat_shield"


def test_heat_shield_position_configurable():
    d = decide_cover(_cfg(heat_shield_pct=40, hot_delta=0.8, slew_enabled=False),
                     DsState(),
                     DsInputs(hvac_mode="cool", impact=0, t_in=24, t_out=30,
                              heat_shield=True))
    assert d.pos == 40 and d.reason == "summer_heat_shield"


def test_heat_shield_not_when_not_hotter_outside():
    # Shield on but outside not hotter than inside -> behaves as before (opens).
    d = decide_cover(_cfg(hot_delta=0.8, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=0, t_in=24, t_out=24,
                              heat_shield=True))
    assert d.pos == 100 and d.reason == "default"


def test_heat_shield_off_opens_in_summer():
    # Shield OFF (default): cooling with no sun opens as before, even if hot out.
    d = decide_cover(_cfg(hot_delta=0.8, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=0, t_in=24, t_out=30))
    assert d.pos == 100 and d.reason == "default"


def test_cool_cap_applies_with_direct_sun_when_shield_on():
    # Shield on + direct sun: the cooling cap (0) wins over the daylight shield.
    d = decide_cover(_cfg(heat_shield_pct=0, hot_delta=0.8, summer_min_open_pct=20,
                          slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=24, t_out=30,
                              heat_shield=True))
    assert d.pos == 0 and d.reason == "summer_heat_shield"


def test_cool_cap_lets_geo_close_further():
    # Cap 40 but the fixed shield wants 30 (more closed) -> the more-closed wins.
    d = decide_cover(_cfg(heat_shield_pct=40, hot_delta=0.8, summer_min_open_pct=20,
                          slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=24, t_out=30,
                              heat_shield=True))
    assert d.pos == 30 and d.reason == "summer_solar_shield"


def test_direct_sun_shield_unchanged_when_shield_off():
    # Shield off: the daylight (fixed/geo) shield owns it, no cooling cap.
    d = decide_cover(_cfg(heat_shield_pct=0, hot_delta=0.8, summer_min_open_pct=20,
                          slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="cool", impact=70, t_in=24, t_out=30))
    assert d.pos == 30 and d.reason == "summer_solar_shield"


def test_heat_gain_cap_limits_opening():
    # Heating + sun + shield on: gain capped at heat_max_open_pct.
    d = decide_cover(_cfg(heat_max_open_pct=80, slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=80, t_in=20, t_out=2,
                              heat_shield=True))
    assert d.pos == 80 and d.reason == "winter_solar_gain"


def test_heat_gain_full_when_shield_off_or_default():
    # Shield off -> full gain; shield on with default 100 -> full gain too.
    off = decide_cover(_cfg(heat_max_open_pct=80, slew_enabled=False), DsState(),
                       DsInputs(hvac_mode="heat", impact=80, t_in=20, t_out=2))
    assert off.pos == 100 and off.reason == "winter_solar_gain"
    dflt = decide_cover(_cfg(slew_enabled=False), DsState(),
                        DsInputs(hvac_mode="heat", impact=80, t_in=20, t_out=2,
                                 heat_shield=True))
    assert dflt.pos == 100


def test_heat_shield_only_in_cooling():
    # Heat mode + no sun -> winter insulation, never the heat shield.
    d = decide_cover(_cfg(slew_enabled=False), DsState(),
                     DsInputs(hvac_mode="heat", impact=0, t_in=24, t_out=30,
                              heat_shield=True))
    assert d.reason != "summer_heat_shield"


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


def test_wind_cap_reacts_to_gust():
    # The cap reacts to the worst of steady wind and gust: a strong gust caps
    # even with the mean wind below the limit (no local wind sensor needed).
    cfg = _cfg(wind_limit_kmh=40, wind_cap_span_kmh=20, weather_max_open_pct=30,
               slew_enabled=False)
    d = decide_cover(cfg, DsState(),
                     DsInputs(weather_protect_enabled=True, wind=10, gust=60))
    assert d.pos == 30 and d.reason == "meteo_wind_cap"
    # Calm gust, calm wind -> no cap.
    d2 = decide_cover(cfg, DsState(),
                      DsInputs(weather_protect_enabled=True, wind=10, gust=20))
    assert d2.reason != "meteo_wind_cap"


def test_wind_cap_yields_to_manual_and_lock():
    # A manual hold (or lock) is a firm decision: the wind cap must NOT slam it
    # shut, or a manually-opened shutter would trap someone on the terrace.
    cfg = _cfg(wind_limit_kmh=40, wind_cap_span_kmh=20, weather_max_open_pct=30,
               slew_enabled=False)
    windy = dict(weather_protect_enabled=True, wind=60)   # well over the limit
    # Manual hold open -> stays open despite the wind.
    d = decide_cover(cfg, DsState(), DsInputs(manual_pos=100, **windy))
    assert d.pos == 100 and d.reason == "manual_hold"
    # Lock open -> stays open despite the wind.
    d = decide_cover(cfg, DsState(),
                     DsInputs(override_mode="lock", override_pos=100, **windy))
    assert d.pos == 100 and d.reason == "ov_lock"
    # But an automatic (non-protected) state still gets wind-capped.
    d = decide_cover(cfg, DsState(), DsInputs(**windy))
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


def test_sdhb_solar_shield_yields_to_manual_and_lock():
    # A climate zone's solar-shield request must NOT clamp a manually-opened /
    # locked shutter shut (that trapped someone): PROTECTED reasons are exempt,
    # like the wind/slew caps.
    cfg = _cfg(sdhb_solar_shield_max_open_pct=30, slew_enabled=False)
    shield = dict(sdhb_allow_override=True, sdhb_request_solar_shield=True)
    # Manual hold open -> stays open despite the bus solar-shield request.
    d = decide_cover(cfg, DsState(), DsInputs(manual_pos=100, **shield))
    assert d.pos == 100 and d.reason == "manual_hold"
    # Lock open -> stays open too.
    d = decide_cover(cfg, DsState(),
                     DsInputs(override_mode="lock", override_pos=100, **shield))
    assert d.pos == 100 and d.reason == "ov_lock"
    # An automatic (non-protected) state still gets clamped.
    d = decide_cover(cfg, DsState(), DsInputs(**shield))
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


# --------------------------------------------------------------------------- #
# F15: geometric solar penetration / shading
# --------------------------------------------------------------------------- #
def _geo_cfg(**kw):
    # summer_min_open_pct defaults to 20 on DsConfig (kept as the geo floor).
    base = dict(facade_azimuth_deg=180, facade_span_deg=180,
                window_height_cm=100, overhang_cm=0, sill_height_cm=90,
                room_depth_m=4.0, target_penetration_m=0.5, shade_step_pct=25)
    base.update(kw)
    return _cfg(**base)


def test_penetration_high_sun_shallower_than_low_sun():
    cfg = _geo_cfg()
    high = solar_penetration_m(cfg, 180, 70, True)
    low = solar_penetration_m(cfg, 180, 30, True)
    assert high is not None and low is not None
    assert high < low                       # high sun -> sun stays near the window


def test_penetration_none_when_sun_not_in_front():
    cfg = _geo_cfg()
    assert solar_penetration_m(cfg, 0, 45, True) is None     # sun behind facade
    assert solar_penetration_m(cfg, 180, -2, True) is None   # below horizon
    assert solar_penetration_m(cfg, 180, 45, False) is None  # not effective


def test_penetration_overhang_reduces():
    base = solar_penetration_m(_geo_cfg(), 180, 45, True)
    shaded = solar_penetration_m(_geo_cfg(overhang_cm=50), 180, 45, True)
    assert base is not None and shaded is not None
    assert shaded < base


def test_penetration_overhang_offset_reduces_shading():
    # A high eave (offset gap above the window) shades less -> deeper sun.
    shaded = solar_penetration_m(_geo_cfg(overhang_cm=80), 180, 45, True)
    raised = solar_penetration_m(
        _geo_cfg(overhang_cm=80, overhang_offset_cm=40), 180, 45, True)
    assert shaded is not None and raised is not None
    assert raised > shaded


def test_penetration_clamped_to_room_depth():
    cfg = _geo_cfg(room_depth_m=4.0)
    # Very low sun would project far beyond the room -> clamped to the depth.
    assert solar_penetration_m(cfg, 180, 10, True) == 4.0


def test_geo_shade_no_shade_when_below_target():
    cfg = _geo_cfg()
    # Very high sun: penetration below the target -> keep fully open.
    assert geo_shade_pos(cfg, 180, 85, True) == 100


def test_geo_shade_partial_step_when_above_target():
    cfg = _geo_cfg()
    pos = geo_shade_pos(cfg, 180, 70, True)
    assert pos is not None
    assert 20 <= pos < 100 and pos % 25 == 0       # quantized, partly closed


def test_geo_shade_floors_at_summer_min():
    cfg = _geo_cfg()
    # Low sun the shutter cannot fully shield -> floored at the summer minimum.
    assert geo_shade_pos(cfg, 180, 30, True) == 20


def test_geo_shade_none_when_sun_not_applicable():
    cfg = _geo_cfg()
    assert geo_shade_pos(cfg, 0, 45, True) is None      # behind facade
    assert geo_shade_pos(cfg, 180, -1, True) is None    # below horizon


def test_decide_cover_geo_shade_branch():
    cfg = _geo_cfg()
    ins = DsInputs(hvac_mode="cool", t_in=24.0, t_out=30.0, geo_shade=True,
                   sun_azimuth=180, sun_elevation=70, sun_effective=True)
    d = decide_cover(cfg, DsState(), ins)
    assert d.reason == "summer_solar_geo"
    assert d.pos == geo_shade_pos(cfg, 180, 70, True)
    assert "penetration_m" in d.details


def test_decide_cover_falls_back_to_fixed_shield_without_geo():
    cfg = _geo_cfg()
    ins = DsInputs(hvac_mode="cool", t_in=24.0, t_out=30.0, geo_shade=False,
                   sun_azimuth=180, sun_elevation=70, sun_effective=True)
    d = decide_cover(cfg, DsState(), ins)
    assert d.reason == "summer_solar_shield"       # no regression when opted out


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
