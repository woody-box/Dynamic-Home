"""Human-readable text for each module's decision reason code.

The ``Motivo`` sensors expose a raw code (``cool``, ``dawn_ramp``, ``dry_mode``…);
these tables turn it into a phrase so a dashboard card can show *why* the module
is doing what it does without templating. Unknown codes fall back to the raw
string (forward-compatible if a new reason appears before its text is added).
"""
from __future__ import annotations

from . import const

# DC (climate): the decision is the active direction or a safety stop.
_DC: dict[str, str] = {
    "heat": "Calentando",
    "cool": "Refrigerando",
    "off": "En reposo (sin demanda)",
    "off_dew": "Parado: riesgo de condensación",
    "off_window": "Parado: ventana abierta",
    "off_window_inferred": "Parado: ventana abierta (inferida)",
    "override": "Modo manual (consigna fijada)",
}

# DS (shutter): the cascade branch that won.
_DS: dict[str, str] = {
    "ov_lock": "Bloqueada (posición fija)",
    "ov_hold": "Retención manual",
    "ov_ttl": "Retención temporal",
    "meteo_alert": "Protección por alerta meteo",
    "meteo_rain": "Protección por lluvia",
    "manual_hold": "Movimiento manual (respetado)",
    "presence_sim": "Simulación de presencia",
    "mode_sleep": "Modo noche / descanso",
    "privacy_time": "Privacidad (horario)",
    "dawn_ramp": "Apertura por amanecer",
    "night_purge": "Ventilación nocturna (purga)",
    "night_insulate": "Aislamiento nocturno (cerrada)",
    "freecool_night": "Free-cooling nocturno",
    "summer_solar_geo": "Sombreado solar (geométrico)",
    "summer_solar_shield": "Escudo solar de verano",
    "summer_heat_shield": "Escudo térmico de verano",
    "winter_solar_gain": "Ganancia solar de invierno",
    "winter_night_insulate": "Aislamiento nocturno de invierno",
    "winter_cold_shield": "Escudo de frío de invierno",
    "winter_mild_open": "Invierno templado (abierta)",
    "sdhb_solar_shield": "Escudo solar (coordinado por clima)",
    "sdhb_quiet": "Silencio coordinado",
    "meteo_wind_cap": "Límite por viento",
    "peak_stagger": "Espera por pico de potencia",
    "default": "Posición por defecto",
    "off": "Sin actuar",
}

# DV (ventilation): the reason the VMC speed/state was chosen.
_DV: dict[str, str] = {
    "lockout": "Bloqueada (seguridad)",
    "not_permitted": "No permitida (fuera de horario)",
    "manual_override": "Modo manual",
    "boost": "Boost (máxima)",
    "shower_rh": "Humedad de ducha",
    "failsafe_vital_ko": "Failsafe: sensor vital caído",
    "iaq": "Calidad de aire (ventilando)",
    "iaq_ok": "Calidad de aire correcta",
    "schedule_base": "Programación (base)",
    "anticipatory": "Refuerzo anticipatorio",
    "freecool": "Free-cooling",
    "sdhb_quiet": "Silencio coordinado",
    "sdhb_boost": "Boost coordinado",
    "sdhb_freecool": "Free-cooling coordinado",
    "hostile_off": "Aire exterior hostil (parada)",
    "hostile_cap_v1": "Aire exterior hostil (límite V1)",
    "hostile_cap_v2": "Aire exterior hostil (límite V2)",
    "hold_antiflap": "Antioscilación (mantiene)",
    "quiet_cap": "Límite por horas de silencio",
    "mode_boost": "Modo casa: boost",
    "mode_cap": "Modo casa: límite de velocidad",
    "dry_mode": "Modo secado",
}

_TABLES: dict[str, dict[str, str]] = {
    const.MODULE_CLIMATE: _DC,
    const.MODULE_SHUTTER: _DS,
    const.MODULE_VMC: _DV,
}


def humanize(module: str, code: str | None) -> str | None:
    """Human phrase for a reason ``code`` of ``module`` (raw code if unmapped)."""
    if code is None:
        return None
    return _TABLES.get(module, {}).get(code, code)
