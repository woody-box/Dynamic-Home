"""Importable option presets — real-world starting points a user can apply.

Presets are pure numbers (option keys -> value), never entities, so they are safe
to ship in the repo. Applying one merges its values into the entry options; the
engine defaults stay untouched and any unspecified field keeps its default.

Keys must be valid ``options_spec.option_key`` values for the module (tuple
elements use the ``<attr>_<idx+1>`` form). A guard test enforces this.
"""

from __future__ import annotations

from . import const

# module -> preset id -> (label_en, label_es, values)
PRESETS: dict[str, dict[str, tuple[str, str, dict[str, float]]]] = {
    const.MODULE_VMC: {
        "home_vmc": (
            "Dual-flow VMC (home)",
            "VMC doble flujo (casa)",
            {
                # IAQ (live-tuned: PM lower, tighter PM hysteresis)
                "co2_v2": 900.0, "co2_v3": 1300.0, "co2_hys": 100.0,
                "pm_v2": 8.0, "pm_v3": 20.0, "pm_hys": 3.0,
                # dry mode by dew point
                "dry_v2_delta": 0.2, "dry_v3_delta": 1.0,
                # shower boost via ΔRH (on 4.5 / off 3.5, hold 20 min, V3)
                "shower_rh_delta_on": 4.5, "shower_rh_delta_off": 3.5,
                "shower_hold_s": 1200.0, "shower_level": 3,
            },
        ),
    },
    const.MODULE_CLIMATE: {
        "salon_radiant_communal": (
            "Living room · radiant floor (communal source)",
            "Salón · suelo radiante (fuente comunitaria)",
            {
                # base setpoints
                "base_heat_day": 22.0, "base_cool_day": 26.5, "delta_night": 0.5,
                "vac_base_heat_day": 17.0, "vac_base_cool_day": 30.0,
                # limits / apply
                "target_min_heat": 20.5, "target_max_heat": 23.5,
                "target_min_cool": 25.0, "target_max_cool": 28.0,
                "step": 0.1, "apply_min_delta": 0.2,
                "max_mods_heat": 1.5, "max_mods_cool": 1.5,
                "vac_target_min_heat": 15.0, "vac_target_max_heat": 19.0,
                "vac_target_min_cool": 28.0, "vac_target_max_cool": 31.0,
                # outdoor bias (high-inertia radiant -> gentle, well insulated)
                "ext_cold_threshold": 5.0, "ext_hot_threshold": 30.0,
                "bias_ext_heat_strong": 0.30, "bias_ext_heat_mild": 0.15,
                "bias_ext_cool_strong": 0.30, "bias_ext_cool_mild": 0.15,
                "insulation_factor": 0.6,
                # VMC compensation
                "vmc_bias_heat_1": 0.05, "vmc_bias_heat_2": 0.10,
                "vmc_bias_heat_3": 0.15,
                "vmc_bias_cool_1": 0.05, "vmc_bias_cool_2": 0.10,
                "vmc_bias_cool_3": 0.15,
                # trend & lead
                "trend_lead_h": 1.5, "trend_max_shift": 0.20,
                "trend_deadband_cph": 0.12, "trend_ema_alpha": 0.25,
                "lead_min_h": 1.0, "lead_max_h": 3.0,
                # trend brake
                "brake_thresholds_1": 0.2, "brake_thresholds_2": 0.3,
                "brake_thresholds_3": 0.5,
                "brake_biases_1": 0.1, "brake_biases_2": 0.2,
                "brake_biases_3": 0.4,
                # forecast
                "forecast_gain": 0.08, "forecast_cap": 0.80,
                "forecast_window_h": 5.0,
                # adaptive lead (high inertia)
                "adapt_alpha": 0.20, "adapt_gain_lr": 0.10,
                "adapt_overshoot_target": 0.10, "adapt_rate_floor_cph": 0.05,
                "adapt_lag_k": 1.0, "adapt_on_rate_min_dt_h": 0.25,
                "adapt_on_rate_min_dt": 0.05, "adapt_off_window_h": 3.0,
                # facade solar gain
                "facade_gain_heat": 0.15, "facade_gain_cool": 0.15,
            },
        ),
        "heatpump_individual_tariff": (
            "Individual heat pump · time-of-use tariff + peak shaving",
            "Aerotermia individual · tarifa por tramos + anti-pico",
            {
                # base setpoints (a heat pump runs a touch lower than communal radiant)
                "base_heat_day": 21.5, "base_cool_day": 25.5,
                "target_min_heat": 19.0, "target_max_heat": 23.0,
                "target_min_cool": 24.0, "target_max_cool": 27.0,
                # tariff -> lead (F34): widen the lead when energy is cheap, trim it
                # at peak; a small base bias loads the thermal mass off-peak.
                "tariff_lead_cheap_mult": 1.5, "tariff_lead_peak_mult": 0.6,
                "tariff_bias_c": 0.3,
                # electrical peak (F03): one start at a time, staggered, comfort bypass
                "peak_max_zones": 1.0, "peak_stagger_s": 60.0,
                "peak_comfort_bypass_c": 2.5, "est_w_on": 1500.0,
                # compressor anti-cycle (F09): medium-inertia heat pump
                "anticycle_min_on_s": 600.0, "anticycle_min_off_s": 600.0,
                "anticycle_max_starts_per_h": 6.0,
                # lead (medium inertia: fan-coil / low-temp radiators)
                "lead_base_h": 1.0, "trend_lead_h": 1.0,
                "lead_min_h": 0.5, "lead_max_h": 3.0,
            },
        ),
    },
    const.MODULE_SHUTTER: {
        "motorized_facades": (
            "Motorized shutters · multi-facade (solar + weather)",
            "Persianas motorizadas · multi-fachada (solar + meteo)",
            {
                # weather alerts (F17): most-protective position per hazard
                "alert_pct": 0.0, "alert_hail_pct": 0.0, "alert_wind_pct": 50.0,
                "alert_hold_min": 30.0,
                # summer solar shield (F15/F16) + free-cooling purge
                "summer_min_open_pct": 20.0, "hot_delta": 1.0, "shade_step_pct": 10.0,
                "freecool_max_open_pct": 60.0, "freecool_delta": 0.8,
                # seasonal night insulation (F16)
                "night_iso_close_pct": 0.0, "night_iso_open_pct": 100.0,
                "winter_night_pct": 0.0,
                # wind cap with hysteresis (protects the slats)
                "wind_limit_kmh": 40.0, "wind_cap_span_kmh": 20.0,
                "wind_cap_hyst_kmh": 5.0, "weather_max_open_pct": 50.0,
                # gradual sunrise ramp (F19)
                "dawn_step_pct": 10.0, "dawn_step_min": 5.0,
                "dawn_target_pct": 100.0, "dawn_trigger_elevation": 0.0,
                # motor inrush staging (F03, transient channel)
                "peak_max_zones": 1.0, "peak_stagger_s": 3.0,
            },
        ),
    },
}


def preset_ids(module: str) -> list[str]:
    return list(PRESETS.get(module, {}).keys())


def preset_label(module: str, preset_id: str, lang: str) -> str:
    en, es, _ = PRESETS[module][preset_id]
    return es if lang.startswith("es") else en


def preset_values(module: str, preset_id: str) -> dict[str, float]:
    return dict(PRESETS.get(module, {}).get(preset_id, ("", "", {}))[2])
