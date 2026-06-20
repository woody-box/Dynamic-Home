"""Catalogue of UI-tunable parameters, grouped by category.

The single source of truth for *defaults* is the engine dataclass (``DvConfig`` /
``DsConfig`` / ``DcConfig``); nothing is hard-coded here but the field names and
their human labels. The options flow renders one form per category, and
:func:`apply_options` overlays whatever the user saved onto a fresh config.

Tuple fields (e.g. ``vmc_bias_heat``) are exposed as one entry per element via
``idx``; the option key is then ``<attr>_<idx+1>`` (1-based for the UI).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import const
from .dc_engine import DcConfig
from .ds_engine import DsConfig
from .dv_engine import DvConfig


@dataclass(frozen=True)
class Opt:
    attr: str
    en: str
    es: str
    idx: int | None = None


# Category id -> (label_en, label_es). Ids are shared across modules where the
# meaning matches; the flow only offers those a module actually defines.
CATEGORIES: dict[str, tuple[str, str]] = {
    "iaq": ("Air-quality thresholds", "Umbrales de calidad de aire"),
    "smoothing": ("Sensor smoothing", "Suavizado de sensores"),
    "freecool": ("Free-cooling", "Free-cooling"),
    "hostile": ("Hostile outdoor air", "Exterior hostil"),
    "dry": ("Anti-condensation", "Anticondensación"),
    "failsafe": ("Failsafe & startup", "Failsafe y arranque"),
    "shower": ("Shower boost", "Refuerzo de ducha"),
    "adaptive_iaq": ("Adaptive thresholds", "Umbrales adaptativos"),
    "positions": ("Shutter positions", "Posiciones de persiana"),
    "thermal": ("Thermal deltas", "Deltas térmicos"),
    "wind": ("Wind protection", "Protección de viento"),
    "slew": ("Slew rate", "Slew rate"),
    "geometry": ("Window geometry", "Geometría de ventana"),
    "setpoints": ("Base setpoints", "Consignas base"),
    "limits": ("Setpoint limits", "Límites de consigna"),
    "exterior": ("Outdoor bias", "Bias exterior"),
    "bus": ("Bus self-bias", "Bias del bus"),
    "vmc": ("VMC bias", "Bias VMC"),
    "trend": ("Trend & lead", "Tendencia y lead"),
    "brake": ("Trend brake", "Freno de tendencia"),
    "forecast": ("Forecast", "Forecast"),
    "adaptive_lead": ("Adaptive lead", "Lead adaptativo"),
    "condensation": ("Condensation", "Condensación"),
    "facade": ("Facade bias", "Bias de fachadas"),
}


def _v(attr, en, es) -> Opt:
    return Opt(attr, en, es)


def _tuple(attr, en, es, n) -> list[Opt]:
    return [Opt(attr, f"{en} {i + 1}", f"{es} {i + 1}", idx=i) for i in range(n)]


# --------------------------------------------------------------------------- #
# Per-module spec: category -> list of Opt. Excluded on purpose: fields driven
# by other entities (numbers/switches) or by hardware presence, e.g. the
# *_enabled gates, privacy/lock positions and facade azimuth/span.
# --------------------------------------------------------------------------- #
SPEC: dict[str, dict[str, list[Opt]]] = {
    const.MODULE_VMC: {
        "iaq": [
            _v("co2_v2", "CO₂ → V2 (ppm)", "CO₂ → V2 (ppm)"),
            _v("co2_v3", "CO₂ → V3 (ppm)", "CO₂ → V3 (ppm)"),
            _v("pm_v2", "PM2.5 → V2 (µg/m³)", "PM2.5 → V2 (µg/m³)"),
            _v("pm_v3", "PM2.5 → V3 (µg/m³)", "PM2.5 → V3 (µg/m³)"),
            _v("co2_hys", "CO₂ hysteresis (ppm)", "Histéresis CO₂ (ppm)"),
            _v("pm_hys", "PM2.5 hysteresis (µg/m³)", "Histéresis PM2.5 (µg/m³)"),
        ],
        "smoothing": [
            _v("co2_ema_enabled", "Smooth CO₂ (EMA)", "Suavizar CO₂ (EMA)"),
            _v("pm_ema_enabled", "Smooth PM2.5 (EMA)", "Suavizar PM2.5 (EMA)"),
            _v("co2_ema_alpha", "CO₂ EMA alpha", "Alpha EMA CO₂"),
            _v("pm_ema_alpha", "PM2.5 EMA alpha", "Alpha EMA PM2.5"),
        ],
        "freecool": [
            _v("freecool_t_ext_min", "Min outdoor temp (°C)", "Temp. ext. mínima (°C)"),
            _v("freecool_delta_on", "ΔT on (°C)", "ΔT activación (°C)"),
            _v("freecool_delta_off", "ΔT off (°C)", "ΔT desactivación (°C)"),
        ],
        "hostile": [
            _v("hostile_t1", "AQI threshold 1", "Umbral AQI 1"),
            _v("hostile_t2", "AQI threshold 2", "Umbral AQI 2"),
            _v("hostile_t3", "AQI threshold 3", "Umbral AQI 3"),
        ],
        "dry": [
            _v("dry_v2_delta", "Dry V2 ΔT (°C)", "ΔT seco V2 (°C)"),
            _v("dry_v3_delta", "Dry V3 ΔT (°C)", "ΔT seco V3 (°C)"),
            _v("dew_spread_min", "Dew-point margin (°C)", "Margen punto rocío (°C)"),
        ],
        "failsafe": [
            _v("stale_threshold_s", "Stale sensor (s)", "Sensor obsoleto (s)"),
            _v("startup_grace_s", "Startup grace (s)", "Gracia de arranque (s)"),
            _v("trip_window_s", "Trip window (s)", "Ventana de fallos (s)"),
            _v("trip_limit", "Trip limit", "Límite de fallos"),
            _v("lockout_s", "Lockout (s)", "Bloqueo (s)"),
        ],
        "shower": [
            _v("shower_rh_delta_on", "RH Δ on (%)", "Δ HR activación (%)"),
            _v("shower_rh_delta_off", "RH Δ off (%)", "Δ HR desactivación (%)"),
            _v("shower_hold_s", "Hold (s)", "Mantener (s)"),
            _v("shower_level", "Shower speed", "Velocidad de ducha"),
        ],
        "adaptive_iaq": [
            _v("adaptive_min_samples", "Min samples", "Muestras mínimas"),
        ],
    },
    const.MODULE_SHUTTER: {
        "positions": [
            _v("rain_close_pct", "Rain close (%)", "Cierre por lluvia (%)"),
            _v("freecool_max_open_pct", "Free-cool max open (%)", "Free-cool máx. (%)"),
            _v("summer_min_open_pct", "Summer min open (%)", "Verano mín. (%)"),
            _v("winter_night_pct", "Winter night (%)", "Noche invierno (%)"),
            _v("weather_max_open_pct", "Weather max open (%)", "Meteo máx. (%)"),
            _v("sdhb_solar_shield_max_open_pct", "Solar shield max (%)",
               "Protección solar máx. (%)"),
        ],
        "thermal": [
            _v("freecool_delta", "Free-cool ΔT (°C)", "ΔT free-cool (°C)"),
            _v("hot_delta", "Hot ΔT (°C)", "ΔT calor (°C)"),
        ],
        "wind": [
            _v("wind_limit_kmh", "Wind limit (km/h)", "Límite de viento (km/h)"),
            _v("wind_cap_span_kmh", "Wind cap span (km/h)", "Rango cap viento (km/h)"),
            _v("wind_cap_hyst_kmh", "Wind cap hysteresis (km/h)",
               "Histéresis cap viento (km/h)"),
        ],
        "slew": [
            _v("slew_enabled", "Limit slew rate", "Limitar slew rate"),
            _v("slew_step_pct", "Slew step (%)", "Paso slew (%)"),
        ],
        "geometry": [
            _v("window_height_cm", "Window height (cm)", "Altura ventana (cm)"),
            _v("overhang_cm", "Overhang (cm)", "Voladizo (cm)"),
        ],
    },
    const.MODULE_CLIMATE: {
        "setpoints": [
            _v("base_heat_day", "Heat base (°C)", "Base calor (°C)"),
            _v("base_cool_day", "Cool base (°C)", "Base frío (°C)"),
            _v("delta_night", "Night easing (°C)", "Atenuación nocturna (°C)"),
            _v("vac_base_heat_day", "Vacation heat (°C)", "Vacaciones calor (°C)"),
            _v("vac_base_cool_day", "Vacation cool (°C)", "Vacaciones frío (°C)"),
        ],
        "limits": [
            _v("target_min_heat", "Heat min (°C)", "Calor mín. (°C)"),
            _v("target_max_heat", "Heat max (°C)", "Calor máx. (°C)"),
            _v("target_min_cool", "Cool min (°C)", "Frío mín. (°C)"),
            _v("target_max_cool", "Cool max (°C)", "Frío máx. (°C)"),
            _v("step", "Quantization step (°C)", "Paso de cuantización (°C)"),
            _v("max_mods_heat", "Max heat bias (°C)", "Bias máx. calor (°C)"),
            _v("max_mods_cool", "Max cool bias (°C)", "Bias máx. frío (°C)"),
        ],
        "exterior": [
            _v("ext_cold_threshold", "Cold threshold (°C)", "Umbral frío (°C)"),
            _v("ext_hot_threshold", "Hot threshold (°C)", "Umbral calor (°C)"),
            _v("bias_ext_heat_strong", "Heat strong (°C)", "Calor fuerte (°C)"),
            _v("bias_ext_heat_mild", "Heat mild (°C)", "Calor suave (°C)"),
            _v("bias_ext_cool_strong", "Cool strong (°C)", "Frío fuerte (°C)"),
            _v("bias_ext_cool_mild", "Cool mild (°C)", "Frío suave (°C)"),
            _v("insulation_factor", "Insulation factor", "Factor aislamiento"),
        ],
        "bus": [
            _v("sdhb_bias_solar_gain_heat", "Solar gain heat (°C)",
               "Ganancia solar calor (°C)"),
            _v("sdhb_bias_solar_shield_cool", "Solar shield cool (°C)",
               "Protección solar frío (°C)"),
        ],
        "vmc": [
            *_tuple("vmc_bias_heat", "Heat bias V", "Bias calor V", 3),
            *_tuple("vmc_bias_cool", "Cool bias V", "Bias frío V", 3),
        ],
        "trend": [
            _v("trend_lead_h", "Fallback lead (h)", "Lead de respaldo (h)"),
            _v("trend_max_shift", "Max trend shift (°C)", "Desplaz. máx. tendencia (°C)"),
            _v("lead_base_h", "Lead base (h)", "Lead base (h)"),
            _v("lead_per_degree_h", "Lead per °C (h)", "Lead por °C (h)"),
            _v("lead_wind_h_per_kmh", "Lead per km/h (h)", "Lead por km/h (h)"),
            _v("lead_min_h", "Lead min (h)", "Lead mín. (h)"),
            _v("lead_max_h", "Lead max (h)", "Lead máx. (h)"),
            _v("trend_deadband_cph", "Trend deadband (°C/h)", "Banda muerta (°C/h)"),
            _v("trend_ema_alpha", "Trend EMA alpha", "Alpha EMA tendencia"),
        ],
        "brake": [
            *_tuple("brake_thresholds", "Brake threshold", "Umbral freno", 3),
            *_tuple("brake_biases", "Brake bias", "Bias freno", 3),
        ],
        "forecast": [
            _v("forecast_gain", "Forecast gain", "Ganancia forecast"),
            _v("forecast_cap", "Forecast cap (°C)", "Tope forecast (°C)"),
            _v("forecast_window_h", "Forecast window (h)", "Ventana forecast (h)"),
        ],
        "adaptive_lead": [
            _v("adapt_alpha", "EMA alpha", "Alpha EMA"),
            _v("adapt_gain_lr", "Learning rate", "Tasa de aprendizaje"),
            _v("adapt_overshoot_target", "Overshoot target (°C)",
               "Overshoot objetivo (°C)"),
            _v("adapt_rate_floor_cph", "Rate floor (°C/h)", "Suelo de tasa (°C/h)"),
            _v("adapt_lag_k", "Lag weight", "Peso del retardo"),
            _v("adapt_on_rate_min_dt_h", "Min ON duration (h)", "Duración ON mín. (h)"),
            _v("adapt_on_rate_min_dt", "Min ΔT (°C)", "ΔT mín. (°C)"),
            _v("adapt_off_window_h", "Settling window (h)", "Ventana de asentamiento (h)"),
            _v("lead_adaptive_min_h", "Adaptive lead min (h)", "Lead adapt. mín. (h)"),
            _v("lead_adaptive_max_h", "Adaptive lead max (h)", "Lead adapt. máx. (h)"),
        ],
        "condensation": [
            _v("dew_spread_min", "Dew-point margin (°C)", "Margen punto rocío (°C)"),
        ],
        "facade": [
            _v("facade_gain_heat", "Facade gain heat (°C)", "Ganancia fachada calor (°C)"),
            _v("facade_gain_cool", "Facade gain cool (°C)", "Ganancia fachada frío (°C)"),
        ],
    },
}

_FRESH = {
    const.MODULE_VMC: DvConfig,
    const.MODULE_SHUTTER: DsConfig,
    const.MODULE_CLIMATE: DcConfig,
}


def option_key(opt: Opt) -> str:
    """Stable key stored in ``entry.options`` for this field."""
    return opt.attr if opt.idx is None else f"{opt.attr}_{opt.idx + 1}"


def categories(module: str) -> list[str]:
    return list(SPEC.get(module, {}).keys())


def fields(module: str, category: str) -> list[Opt]:
    return SPEC.get(module, {}).get(category, [])


def current_value(cfg, opt: Opt):
    """Current value of a field on a config object (handles tuple elements)."""
    val = getattr(cfg, opt.attr)
    return val if opt.idx is None else val[opt.idx]


def fresh_config(module: str):
    return _FRESH[module]()


def _coerce(template, raw):
    if isinstance(template, bool):
        return bool(raw)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(raw)
    return float(raw)


def apply_options(cfg, options: dict, module: str) -> None:
    """Overlay saved options onto ``cfg`` (defaults stay in the dataclass)."""
    for cat in SPEC.get(module, {}).values():
        for opt in cat:
            key = option_key(opt)
            if key not in options:
                continue
            template = current_value(cfg, opt)
            value = _coerce(template, options[key])
            if opt.idx is None:
                setattr(cfg, opt.attr, value)
            else:
                items = list(getattr(cfg, opt.attr))
                items[opt.idx] = value
                setattr(cfg, opt.attr, tuple(items))
