"""Dynamic Shutter (DS) — pure decision engine (no Home Assistant dependencies).

Faithful port of the DS ``target_decision`` YAML cascade (see ../../docs/SPEC_DS.md):
a single priority cascade that yields a target cover position 0..100 (% open)
and a reason code, followed by caps (wind / SDHB bus / slew).

No Home Assistant imports: unit-testable and reused by the HA cover wrapper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Reasons that must not be overridden by the soft caps (wind/SDHB/slew).
PROTECTED = {"ov_lock", "ov_hold", "ov_ttl", "meteo_rain",
             "meteo_wind_cap", "privacy_time"}


@dataclass
class DsConfig:
    """Tunables. Defaults mirror the YAML ``initial:`` values."""

    rain_close_pct: int = 0
    privacy_pos_pct: int = 40
    freecool_max_open_pct: int = 60
    freecool_delta: float = 0.8
    summer_min_open_pct: int = 20
    hot_delta: float = 0.8
    winter_night_pct: int = 0

    wind_limit_kmh: float = 40.0
    wind_cap_span_kmh: float = 20.0
    wind_cap_hyst_kmh: float = 5.0
    weather_max_open_pct: int = 30

    sdhb_solar_shield_max_open_pct: int = 30

    slew_enabled: bool = True
    slew_step_pct: int = 10

    # Facade geometry (solar impact model)
    facade_azimuth_deg: float = 180.0   # window orientation
    facade_span_deg: float = 180.0      # angular acceptance
    window_height_cm: float = 100.0
    overhang_cm: float = 0.0


@dataclass
class DsState:
    wind_cap_active: bool = False


@dataclass
class DsInputs:
    # Override
    override_mode: str = "none"     # none | lock | hold | ttl
    override_pos: int = 0
    hold_ok: bool = False
    ttl_ok: bool = False

    # Climate context
    hvac_mode: str = "off"          # cool | heat | off
    impact: int | None = None    # solar impact 0..100; None -> compute from sun
    night: bool = False
    t_in: float | None = None
    t_out: float | None = None
    sleep_mode: bool = False

    # Weather protect
    weather_protect_enabled: bool = False
    raining: bool = False
    wind: float | None = None

    # Privacy (time window resolved by the caller)
    privacy_active: bool = False

    # Current physical position (for slew + quiet freeze)
    current_pos: int | None = None

    # SDHB bus consumption
    sdhb_allow_override: bool = False
    sdhb_request_solar_shield: bool = False
    sdhb_request_quiet: bool = False
    quiet_respect_enabled: bool = True

    # Sun geometry (used only when impact is None)
    sun_azimuth: float | None = None
    sun_elevation: float | None = None
    sun_effective: bool = True


@dataclass
class DsDecision:
    pos: int
    reason: str
    details: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def quantize10(raw: float) -> int:
    """Floor to multiples of 10 (port of ``(raw/10)|round(0,'floor')*10``)."""
    return int(math.floor(raw / 10.0) * 10)


def solar_impact(cfg: DsConfig, sun_azimuth: float, sun_elevation: float,
                 sun_effective: bool) -> int:
    """Geometric solar impact 0..100 (port of ``ds_solar_impact_pct``).

    Accounts for whether the sun faces the window (within the facade span) and
    the shading produced by an overhang at the current elevation.
    """
    half = cfg.facade_span_deg / 2.0
    diff = ((sun_azimuth - cfg.facade_azimuth_deg + 540) % 360) - 180
    in_front = abs(diff) <= half
    if sun_elevation <= 0:
        exposed = 0.0
    else:
        shadow = cfg.overhang_cm * math.tan(math.radians(sun_elevation))
        shaded = max(0.0, min(1.0, shadow / cfg.window_height_cm))
        exposed = 1.0 - shaded
    impact = exposed if (in_front and sun_effective) else 0.0
    step10 = math.floor(impact * 10) / 10.0
    return int(step10 * 100)


def compute_wind_cap(cfg: DsConfig, ins: DsInputs) -> int:
    """Wind cap percentage (100 = no cap). Port of the wind-cap ramp."""
    if not ins.weather_protect_enabled or ins.wind is None:
        return 100
    if ins.wind < cfg.wind_limit_kmh:
        return 100
    if cfg.wind_cap_span_kmh > 0:
        ratio = (ins.wind - cfg.wind_limit_kmh) / cfg.wind_cap_span_kmh
        ratio = max(0.0, min(1.0, ratio))
        raw = 100 - ratio * (100 - cfg.weather_max_open_pct)
        raw = max(cfg.weather_max_open_pct, min(100, raw))
        return quantize10(raw)
    return cfg.weather_max_open_pct  # span == 0 -> fixed cap


def update_wind_cap_active(state: DsState, cfg: DsConfig, ins: DsInputs) -> bool:
    """Wind-cap activation with hysteresis (start vs start-hyst release)."""
    if not ins.weather_protect_enabled or ins.wind is None:
        state.wind_cap_active = False
        return False
    if state.wind_cap_active:
        if ins.wind < cfg.wind_limit_kmh - cfg.wind_cap_hyst_kmh:
            state.wind_cap_active = False
    else:
        if ins.wind >= cfg.wind_limit_kmh:
            state.wind_cap_active = True
    return state.wind_cap_active


# --------------------------------------------------------------------------- #
# Main decision
# --------------------------------------------------------------------------- #
def decide_cover(cfg: DsConfig, state: DsState, ins: DsInputs) -> DsDecision:
    """Run one DS control cycle. Returns target position + reason."""
    pos = 100
    reason = "default"
    detail: dict = {}

    impact = ins.impact
    if impact is None and ins.sun_azimuth is not None and ins.sun_elevation is not None:
        impact = solar_impact(cfg, ins.sun_azimuth, ins.sun_elevation, ins.sun_effective)
    impact = impact or 0

    # 1) Override (lock / hold / ttl)
    if ins.override_mode == "lock":
        pos, reason = ins.override_pos, "ov_lock"
    elif ins.override_mode == "hold" and ins.hold_ok:
        pos, reason = ins.override_pos, "ov_hold"
    elif ins.override_mode == "ttl" and ins.ttl_ok:
        pos, reason = ins.override_pos, "ov_ttl"
    # 2) Meteo rain
    elif ins.weather_protect_enabled and ins.raining:
        pos, reason = cfg.rain_close_pct, "meteo_rain"
    # 3) Privacy by time
    elif ins.privacy_active:
        pos, reason = cfg.privacy_pos_pct, "privacy_time"
    else:
        is_cool = ins.hvac_mode == "cool"
        is_heat = ins.hvac_mode == "heat"
        temps_ok = ins.t_in is not None and ins.t_out is not None

        free_ok = (is_cool and ins.night and temps_ok
                   and ins.t_out <= ins.t_in - cfg.freecool_delta)
        shield_ok = (is_cool and impact > 0 and temps_ok
                     and ins.t_out >= ins.t_in + cfg.hot_delta)

        if free_ok and not ins.sleep_mode:
            pos, reason = cfg.freecool_max_open_pct, "freecool_night"
        elif shield_ok:
            raw = max(100 - impact, cfg.summer_min_open_pct)
            pos, reason = quantize10(raw), "summer_solar_shield"
            detail = {"impact": impact}
        elif is_heat and impact > 0:
            pos, reason = 100, "winter_solar_gain"
        elif is_heat and impact == 0:
            pos, reason = cfg.winter_night_pct, "winter_night_insulate"
        else:
            pos, reason = 100, "default"

    # --- Caps (applied after the branch) ---

    # Wind cap (advanced, with hysteresis)
    cap_pct = compute_wind_cap(cfg, ins)
    wind_active = update_wind_cap_active(state, cfg, ins)
    if wind_active and pos > cap_pct and reason != "meteo_rain":
        pos, reason = cap_pct, "meteo_wind_cap"
        detail = {"wind": ins.wind, "cap_pct": cap_pct}

    # SDHB quiet: freeze at current position (don't move)
    if (ins.sdhb_allow_override and ins.quiet_respect_enabled
            and ins.sdhb_request_quiet and reason not in PROTECTED):
        if ins.current_pos is not None:
            pos = ins.current_pos
        reason = "sdhb_quiet"

    # SDHB solar shield: clamp max opening
    if (ins.sdhb_allow_override and ins.sdhb_request_solar_shield
            and pos > cfg.sdhb_solar_shield_max_open_pct):
        pos = cfg.sdhb_solar_shield_max_open_pct
        if reason not in PROTECTED:
            reason = "sdhb_solar_shield"

    # Slew rate: limit movement per cycle
    if (cfg.slew_enabled and ins.current_pos is not None
            and reason not in PROTECTED):
        if abs(pos - ins.current_pos) > cfg.slew_step_pct:
            step = cfg.slew_step_pct if pos > ins.current_pos else -cfg.slew_step_pct
            pos = ins.current_pos + step
            detail = dict(detail, slew_applied=True)

    return DsDecision(int(pos), reason, details=detail)
