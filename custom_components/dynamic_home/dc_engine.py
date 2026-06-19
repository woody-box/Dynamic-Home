"""Dynamic Climate (DC) — pure decision engine (no Home Assistant dependencies).

Faithful port of the DC target pipeline (see ../../docs/SPEC_DC.md):

    target_final = quantize( clamp( base + clamp(Σ biases, ±lim) + sdhb_bias,
                                    [min, max] ),
                             step )

DC is the "brain" of the suite: besides computing its own setpoint, it
*publishes* intents to the bus (``request_solar_gain`` when heating,
``request_solar_shield`` when cooling) that DS/DV consume.

No Home Assistant imports: unit-testable and reused by the HA climate wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Intents DC publishes to the shutters depending on its mode.
INTENT_SOLAR_GAIN = "request_solar_gain"
INTENT_SOLAR_SHIELD = "request_solar_shield"

NIGHT_ELEVATION_DEG = -3.0  # sun elevation at/below which it is "night"


@dataclass
class DcConfig:
    """Tunables. Defaults mirror the YAML ``initial:`` values."""

    base_heat_day: float = 22.5
    base_cool_day: float = 26.5
    delta_night: float = 0.5

    vac_base_heat_day: float = 17.0
    vac_base_cool_day: float = 30.0

    target_min_heat: float = 18.0
    target_max_heat: float = 26.0
    target_min_cool: float = 22.0
    target_max_cool: float = 29.0

    step: float = 0.5
    max_mods_heat: float = 0.8
    max_mods_cool: float = 0.8

    # Exterior bias thresholds / magnitudes
    ext_cold_threshold: float = 0.0    # u_frio
    ext_hot_threshold: float = 30.0    # u_calor
    bias_ext_heat_strong: float = 0.5
    bias_ext_heat_mild: float = 0.2
    bias_ext_cool_strong: float = 0.5
    bias_ext_cool_mild: float = 0.2
    insulation_factor: float = 1.0     # aislamiento

    # Self-bias applied when DC *consumes* a solar intent targeted at it.
    sdhb_bias_solar_gain_heat: float = -0.5
    sdhb_bias_solar_shield_cool: float = 0.5


@dataclass
class DcInputs:
    hvac_mode: str = "off"          # heat | cool | off (demanded mode)
    t_int: Optional[float] = None
    t_ext: Optional[float] = None
    sun_elevation: Optional[float] = None
    vacation: bool = False

    # Sum of the other biases (vmc + facades + forecast + trend + brake),
    # computed by the caller. Defaults to 0.
    extra_bias: float = 0.0

    # Bus intent targeted at DC (consumed -> self bias).
    sdhb_intent: str = "none"

    # Safety / gating
    dew_risk: bool = False
    window_lockout: bool = False

    # Manual override
    override_active: bool = False
    override_temp: Optional[float] = None


@dataclass
class DcDecision:
    action: str          # heat | cool | off
    target: Optional[float]
    reason: str
    published_intent: str  # what DC publishes to the shutters (or "none")


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def is_night(sun_elevation: Optional[float]) -> bool:
    """Conservative degradation: unknown elevation -> day."""
    return sun_elevation is not None and sun_elevation <= NIGHT_ELEVATION_DEG


def base_active(cfg: DcConfig, hvac: str, night: bool, vacation: bool) -> float:
    """Active base setpoint (day/night, heat/cool, vacation)."""
    if vacation:
        return cfg.vac_base_heat_day if hvac == "heat" else cfg.vac_base_cool_day
    base_day = cfg.base_heat_day if hvac == "heat" else cfg.base_cool_day
    if not night:
        return base_day
    # at night, heating eases down, cooling eases up
    return base_day - cfg.delta_night if hvac == "heat" else base_day + cfg.delta_night


def bias_exterior(cfg: DcConfig, hvac: str, t_ext: Optional[float]) -> float:
    """Outdoor-temperature compensation bias (°C)."""
    if t_ext is None:
        return 0.0
    ais = cfg.insulation_factor
    if hvac == "heat":
        if t_ext <= cfg.ext_cold_threshold:
            return cfg.bias_ext_heat_strong * ais
        if t_ext <= cfg.ext_cold_threshold + 5:
            return cfg.bias_ext_heat_mild * ais
        return 0.0
    if hvac == "cool":
        if t_ext >= cfg.ext_hot_threshold:
            return cfg.bias_ext_cool_strong * ais
        if t_ext >= cfg.ext_hot_threshold - 5:
            return cfg.bias_ext_cool_mild * ais
        return 0.0
    return 0.0


def sdhb_self_bias(cfg: DcConfig, intent: str, hvac: str) -> float:
    """Bias applied when DC consumes a solar intent targeted at itself."""
    if intent == INTENT_SOLAR_GAIN and hvac == "heat":
        return cfg.sdhb_bias_solar_gain_heat
    if intent == INTENT_SOLAR_SHIELD and hvac == "cool":
        return cfg.sdhb_bias_solar_shield_cool
    return 0.0


def quantize_step(value: float, step: float) -> float:
    """Round to the nearest multiple of ``step`` (step floored to 0.1)."""
    step = max(step, 0.1)
    return round(round(value / step) * step, 4)


def assemble_target(cfg: DcConfig, hvac: str, base: float, mods_total: float,
                    sdhb_bias: float, vacation: bool) -> float:
    """base + clamp(mods, ±lim) + sdhb_bias, clamped to range and quantized."""
    lim = cfg.max_mods_heat if hvac == "heat" else cfg.max_mods_cool
    mods_clamped = max(-lim, min(lim, mods_total))
    raw = base + mods_clamped + sdhb_bias
    lo = cfg.target_min_heat if hvac == "heat" else cfg.target_min_cool
    hi = cfg.target_max_heat if hvac == "heat" else cfg.target_max_cool
    clamped = max(lo, min(hi, raw))
    return quantize_step(clamped, cfg.step)


def publish_intent(action: str) -> str:
    """Intent DC publishes to the shutters for the given active mode."""
    if action == "heat":
        return INTENT_SOLAR_GAIN
    if action == "cool":
        return INTENT_SOLAR_SHIELD
    return "none"


def sunlit_facades(sun_azimuth: Optional[float], sun_elevation: Optional[float],
                   facades: dict, spans: Optional[dict] = None,
                   default_span: float = 180.0) -> set:
    """Facade keys currently lit by the sun.

    ``facades`` maps facade key (e.g. ``ds_f180``) to its azimuth. ``spans``
    optionally maps the same keys to their acceptance angle (degrees); facades
    without an entry use ``default_span``. A facade is lit when the sun is above
    the horizon and within ``span/2`` of the facade orientation. With no sun
    data, nothing is lit.
    """
    if sun_azimuth is None or sun_elevation is None or sun_elevation <= 0:
        return set()
    spans = spans or {}
    out = set()
    for key, az in facades.items():
        half = spans.get(key, default_span) / 2.0
        diff = ((sun_azimuth - az + 540) % 360) - 180
        if abs(diff) <= half:
            out.add(key)
    return out


# --------------------------------------------------------------------------- #
# Main decision
# --------------------------------------------------------------------------- #
def decide(cfg: DcConfig, ins: DcInputs) -> DcDecision:
    """Run one DC control cycle: setpoint + mode + intent to publish."""
    # Manual override wins.
    if ins.override_active and ins.override_temp is not None:
        action = ins.hvac_mode if ins.hvac_mode in ("heat", "cool") else "off"
        return DcDecision(action, ins.override_temp, "override",
                          publish_intent(action))

    # Safety / gating -> OFF (and clear any published intent).
    if ins.dew_risk:
        return DcDecision("off", None, "off_dew", "none")
    if ins.window_lockout:
        return DcDecision("off", None, "off_window", "none")
    if ins.hvac_mode not in ("heat", "cool"):
        return DcDecision("off", None, "off", "none")

    night = is_night(ins.sun_elevation)
    base = base_active(cfg, ins.hvac_mode, night, ins.vacation)
    mods = bias_exterior(cfg, ins.hvac_mode, ins.t_ext) + ins.extra_bias
    self_bias = sdhb_self_bias(cfg, ins.sdhb_intent, ins.hvac_mode)
    target = assemble_target(cfg, ins.hvac_mode, base, mods, self_bias,
                             ins.vacation)
    return DcDecision(ins.hvac_mode, target, ins.hvac_mode,
                      publish_intent(ins.hvac_mode))
