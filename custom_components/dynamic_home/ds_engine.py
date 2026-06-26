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
             "meteo_wind_cap", "meteo_alert", "privacy_time"}


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
    # Ambient heat shield: in cooling season, when it is hotter outside than in
    # (by hot_delta) but the sun no longer hits this facade, keep the shutter
    # closed against the ambient/terrace heat instead of opening. 0 = fully shut
    # (default); raise it (e.g. 20/40) to let some daylight in.
    heat_shield_pct: int = 0

    wind_limit_kmh: float = 40.0
    wind_cap_span_kmh: float = 20.0
    wind_cap_hyst_kmh: float = 5.0
    weather_max_open_pct: int = 30

    sdhb_solar_shield_max_open_pct: int = 30

    slew_enabled: bool = True
    slew_step_pct: int = 10

    # Gradual sunrise (F19): opt-in per zone. At dawn, raise the shutter in
    # steps instead of snapping open. The coordinator owns the ramp state and
    # passes the stepped position in via DsInputs.dawn_pos.
    dawn_step_pct: int = 10              # % opened per step
    dawn_step_min: float = 5.0          # minutes between steps
    dawn_target_pct: int = 100          # opening the ramp climbs to
    dawn_trigger_elevation: float = 0.0  # sun elevation that starts the ramp

    # Seasonal night insulation (F16): opt-in per zone. At night (sun below the
    # horizon), heat -> close to insulate; cool -> open to purge the thermal mass
    # when the outside is cooler, otherwise close to protect it. The coordinator
    # owns the decision and passes the position in via DsInputs.night_pos.
    night_iso_close_pct: int = 0        # closed position (insulate / protect)
    night_iso_open_pct: int = 100       # open position (nocturnal purge)

    # Weather alerts (F17): anticipatory protection. The coordinator picks the
    # most protective position among the active alerts and holds it.
    alert_pct: int = 0                  # generic alert protection position
    alert_hail_pct: int = 0             # hail/storm (fully closed protects best)
    alert_wind_pct: int = 50            # wind (a mid position protects the slats)
    alert_hold_min: float = 30.0        # keep protecting after the alert clears

    # Facade geometry (solar impact model)
    facade_azimuth_deg: float = 180.0   # window orientation
    facade_span_deg: float = 180.0      # angular acceptance
    window_height_cm: float = 100.0
    overhang_cm: float = 0.0
    # Vertical gap between the overhang/eave and the top of the window. The
    # overhang's shadow only starts shading the glass once it has dropped past
    # this gap, so a high eave (covered terrace) shades far less than one flush
    # with the window head. 0 = flush (legacy behaviour).
    overhang_offset_cm: float = 0.0

    # Geometric shading (F15): opt-in real solar-penetration model. The shutter
    # closes from the top just enough to keep direct sun off the floor beyond
    # ``target_penetration_m`` into the room, in steps of ``shade_step_pct``.
    sill_height_cm: float = 90.0        # window sill height above the floor
    room_depth_m: float = 4.0           # floor depth (penetration is clamped here)
    target_penetration_m: float = 0.5   # allowed sunlit depth before shading
    shade_step_pct: int = 25            # quantization of the geometric position

    # Energy (F06): estimated shutter-motor power (W) and full-travel time (s),
    # used to estimate the (marginal) energy of each movement.
    est_w_motor: float = 150.0
    full_travel_s: float = 20.0
    # Electrical-peak staging (F03): house-level limit on simultaneous shutter
    # starts (motor inrush). Opt-in. peak_max_power_w > 0 uses a watt budget
    # (est_w_motor per move) instead of a max-covers count.
    peak_max_zones: int = 2
    peak_max_power_w: float = 0.0
    peak_stagger_s: float = 10.0


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

    # Gradual sunrise (F19): stepped target while the ramp is active, else None.
    dawn_pos: int | None = None

    # Seasonal night insulation (F16): position while active at night, else None.
    night_pos: int | None = None

    # Geometric shading (F15): opt-in. When True, the summer solar-shield branch
    # uses the real solar-penetration model instead of the fixed impact shield.
    geo_shade: bool = False

    # Weather alert (F17): anticipatory protection position while active, else None.
    alert_pos: int | None = None

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
        shadow = max(0.0, cfg.overhang_cm * math.tan(math.radians(sun_elevation))
                     - cfg.overhang_offset_cm)
        shaded = max(0.0, min(1.0, shadow / cfg.window_height_cm))
        exposed = 1.0 - shaded
    impact = exposed if (in_front and sun_effective) else 0.0
    step10 = math.floor(impact * 10) / 10.0
    return int(step10 * 100)


def _sun_in_front(cfg: DsConfig, sun_azimuth: float) -> float | None:
    """cos(Δazimuth) if the sun faces the window (within the span), else None."""
    half = cfg.facade_span_deg / 2.0
    diff = ((sun_azimuth - cfg.facade_azimuth_deg + 540) % 360) - 180
    if abs(diff) > half:
        return None
    return math.cos(math.radians(diff))


def solar_penetration_m(cfg: DsConfig, sun_azimuth: float | None,
                        sun_elevation: float | None,
                        sun_effective: bool) -> float | None:
    """Perpendicular depth (m) that direct sun reaches across the floor (F15).

    Geometry: the highest unshaded point of the window (head height, lowered by
    the overhang's shadow) projects onto the floor at a horizontal run of
    ``height / tan(elevation)``; the component perpendicular into the room is
    scaled by ``cos(Δazimuth)``. Returns ``None`` when the sun is below the
    horizon, not effective, or not facing this facade. Clamped to the room depth.
    """
    if (sun_azimuth is None or sun_elevation is None or not sun_effective
            or sun_elevation <= 0):
        return None
    cos_diff = _sun_in_front(cfg, sun_azimuth)
    if cos_diff is None or cos_diff <= 0:
        return None
    tan_el = math.tan(math.radians(sun_elevation))
    if tan_el <= 0:
        return None
    shadow = max(0.0, cfg.overhang_cm * tan_el               # overhang shades top
                 - cfg.overhang_offset_cm)                   # ... minus the eave gap
    unshaded_h = max(0.0, cfg.window_height_cm - shadow)
    top_m = (cfg.sill_height_cm + unshaded_h) / 100.0       # highest sunlit point
    pen = (top_m / tan_el) * cos_diff
    return max(0.0, min(pen, cfg.room_depth_m))


def geo_shade_pos(cfg: DsConfig, sun_azimuth: float | None,
                  sun_elevation: float | None,
                  sun_effective: bool) -> int | None:
    """Cover position (0..100) that keeps sun penetration ≤ target (F15).

    Returns ``100`` when no shading is needed, ``None`` when the sun does not
    apply (caller falls back to the fixed impact shield). Otherwise the shutter
    is closed from the top so the top of the opening drops to the height whose
    projection lands at ``target_penetration_m``; the result is quantized down to
    ``shade_step_pct`` and floored at ``summer_min_open_pct``.
    """
    if (sun_azimuth is None or sun_elevation is None or not sun_effective
            or sun_elevation <= 0):
        return None
    cos_diff = _sun_in_front(cfg, sun_azimuth)
    if cos_diff is None or cos_diff <= 0:
        return None
    pen = solar_penetration_m(cfg, sun_azimuth, sun_elevation, sun_effective)
    if pen is None or pen <= cfg.target_penetration_m:
        return 100                                          # already fine
    tan_el = math.tan(math.radians(sun_elevation))
    # Height (m above floor) of the highest sunlit point allowed by the target.
    top_allowed = cfg.target_penetration_m * tan_el / cos_diff
    if cfg.window_height_cm <= 0:
        return cfg.summer_min_open_pct
    # Position exposing the lower p% of the window: exposed top = sill + h·p/100.
    raw = (top_allowed * 100.0 - cfg.sill_height_cm) / cfg.window_height_cm * 100.0
    step = cfg.shade_step_pct if cfg.shade_step_pct > 0 else 1
    quant = int(math.floor(max(0.0, raw) / step) * step)
    return max(cfg.summer_min_open_pct, min(100, quant))


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
    # 1b) Weather alert (F17): anticipatory protection (above rain/wind).
    elif ins.alert_pos is not None:
        pos, reason = ins.alert_pos, "meteo_alert"
    # 2) Meteo rain
    elif ins.weather_protect_enabled and ins.raining:
        pos, reason = cfg.rain_close_pct, "meteo_rain"
    # 3) Privacy by time
    elif ins.privacy_active:
        pos, reason = cfg.privacy_pos_pct, "privacy_time"
    # 4) Gradual sunrise ramp (F19): drives the morning opening in steps. Yields
    # to override/rain/privacy above; the coordinator only sets dawn_pos when the
    # ramp is active and never below the current position (it only ever opens).
    elif ins.dawn_pos is not None:
        pos, reason = ins.dawn_pos, "dawn_ramp"
    # 5) Seasonal night insulation (F16): owns the night strategy when enabled.
    elif ins.night_pos is not None:
        pos, reason = ins.night_pos, "night_insulate"
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
            geo = (geo_shade_pos(cfg, ins.sun_azimuth, ins.sun_elevation,
                                 ins.sun_effective) if ins.geo_shade else None)
            if geo is not None:
                pen = solar_penetration_m(cfg, ins.sun_azimuth, ins.sun_elevation,
                                          ins.sun_effective)
                pos, reason = geo, "summer_solar_geo"
                detail = {"penetration_m": round(pen, 2) if pen is not None else None}
            else:
                raw = max(100 - impact, cfg.summer_min_open_pct)
                pos, reason = quantize10(raw), "summer_solar_shield"
                detail = {"impact": impact}
        elif is_cool and temps_ok and ins.t_out >= ins.t_in + cfg.hot_delta:
            # Cooling and hotter outside, but no direct sun on this facade: don't
            # open into the ambient/terrace heat — hold the heat-shield position.
            pos, reason = cfg.heat_shield_pct, "summer_heat_shield"
            detail = {"t_in": ins.t_in, "t_out": ins.t_out}
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
