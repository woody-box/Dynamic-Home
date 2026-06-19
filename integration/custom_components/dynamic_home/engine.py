"""Dynamic Ventilation — pure decision engine (no Home Assistant dependencies).

This module is a faithful port of the DV ``control_principal`` YAML pipeline
(see ../../SPEC.md). It has NO Home Assistant imports on purpose so it can be
unit-tested in isolation and reused by the HA wrappers (coordinator/fan).

Logical speed domain returned by :func:`decide`:
    0 = OFF, 1/2/3 = V1/V2/V3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Intents understood from the SDHB bus (subset relevant to DV).
INTENT_QUIET = {"request_quiet", "request_eco", "request_weather_protect"}
INTENT_BOOST = "request_boost"
INTENT_FREECOOL = "request_freecool"
INTENT_NORMAL = "request_normal"

# Safe-range validation (see SPEC §2).
CO2_MIN, CO2_MAX = 0.0, 5000.0
PM25_MIN, PM25_MAX = 0.0, 500.0


@dataclass
class DvConfig:
    """Tunables. Defaults mirror the YAML ``initial:`` values."""

    co2_v2: float = 900.0
    co2_v3: float = 1300.0
    pm_v2: float = 15.0
    pm_v3: float = 40.0
    co2_hys: float = 100.0
    pm_hys: float = 5.0

    co2_ema_enabled: bool = True
    pm_ema_enabled: bool = True
    co2_ema_alpha: float = 0.2
    pm_ema_alpha: float = 0.2

    freecool_enabled: bool = False
    freecool_t_ext_min: float = 5.0
    freecool_delta_on: float = 2.0
    freecool_delta_off: float = 1.0

    hostile_enabled: bool = False
    hostile_t1: float = 50.0
    hostile_t2: float = 100.0
    hostile_t3: float = 150.0

    dry_v2_delta: float = 0.2
    dry_v3_delta: float = 1.0


@dataclass
class DvState:
    """State the engine carries between cycles."""

    co2_ema: float = 0.0
    pm_ema: float = 0.0
    freecool_active: bool = False


@dataclass
class DvInputs:
    """Live readings + mode flags for a single decision cycle."""

    co2_raw: Optional[float] = None
    pm_raw: Optional[float] = None
    t_in: Optional[float] = None
    t_ext: Optional[float] = None
    aqi: Optional[float] = None

    current_speed: int = 1

    permitida: bool = True
    manual_override: bool = False
    override_v3: bool = False
    shower_override: bool = False
    shower_level: Optional[str] = None  # "v2" | "v3" | None

    dry_mode: bool = False
    dew_risk: bool = False
    dew_prerisk: bool = False
    dp_diff: Optional[float] = None

    sdhb_intent: str = "none"

    # True when this cycle was triggered by an IAQ change (gates allow_raise).
    trigger_is_iaq: bool = False
    # True when a manual override happened in the last 300s (hysteresis halving).
    override_recent: bool = False


@dataclass
class DvDecision:
    speed: int
    reason: str
    base_target: Optional[int] = None
    details: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _validate(value: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Range-validate a reading; out-of-range / None -> None (SPEC §2)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def update_ema(prev: float, x: float, alpha: float) -> float:
    """EMA update (SPEC §3). ``prev <= 0`` bootstraps to ``x``."""
    if prev <= 0:
        return x
    return alpha * x + (1.0 - alpha) * prev


def compute_freecool(cfg: DvConfig, ins: DvInputs, prev_active: bool) -> bool:
    """Free-cooling with its own hysteresis (SPEC §4.2.1)."""
    if not cfg.freecool_enabled or ins.t_in is None or ins.t_ext is None:
        return False
    if ins.t_ext < cfg.freecool_t_ext_min:
        return False
    delta = ins.t_in - ins.t_ext
    threshold = cfg.freecool_delta_off if prev_active else cfg.freecool_delta_on
    return delta >= threshold


def base_target(co2: float, pm: float, cfg: DvConfig, v_actual: int,
                co2_hys: float, pm_hys: float) -> int:
    """IAQ hysteresis state machine (SPEC §4.1)."""
    if co2 >= cfg.co2_v3 or pm >= cfg.pm_v3:
        return 3
    if v_actual == 3:
        can_drop = (co2 < cfg.co2_v3 - co2_hys) and (pm < cfg.pm_v3 - pm_hys)
        if can_drop:
            return 2 if (co2 >= cfg.co2_v2 or pm >= cfg.pm_v2) else 1
        return 3
    if co2 >= cfg.co2_v2 or pm >= cfg.pm_v2:
        return 2
    if v_actual == 2:
        can_drop2 = (co2 < cfg.co2_v2 - co2_hys) and (pm < cfg.pm_v2 - pm_hys)
        return 1 if can_drop2 else 2
    return 1


# --------------------------------------------------------------------------- #
# Main decision
# --------------------------------------------------------------------------- #
def decide(cfg: DvConfig, state: DvState, ins: DvInputs) -> DvDecision:
    """Run one full DV control cycle. Mutates ``state`` (EMA/freecool)."""
    # --- EMA maintenance (would be called on its own 1-min cadence in HA, but
    # we keep it here so the engine is self-contained for tests). ---
    co2_raw = _validate(ins.co2_raw, CO2_MIN, CO2_MAX)
    pm_raw = _validate(ins.pm_raw, PM25_MIN, PM25_MAX)
    if cfg.co2_ema_enabled and co2_raw is not None:
        state.co2_ema = update_ema(state.co2_ema, co2_raw, cfg.co2_ema_alpha)
    if cfg.pm_ema_enabled and pm_raw is not None:
        state.pm_ema = update_ema(state.pm_ema, pm_raw, cfg.pm_ema_alpha)

    # --- Mode precedence (SPEC §4) ---
    if not ins.permitida:
        return DvDecision(0, "not_permitted")

    if ins.manual_override:
        return DvDecision(3 if ins.override_v3 else 2, "manual_override")

    stage3_active = ins.dry_mode and ins.dew_risk and ins.dp_diff is not None
    if stage3_active:
        if ins.dp_diff >= cfg.dry_v3_delta:
            spd = 3
        elif ins.dp_diff >= cfg.dry_v2_delta:
            spd = 2
        else:
            spd = 1
        return DvDecision(spd, "dry_mode", details={"dp_diff": ins.dp_diff})

    if ins.shower_override:
        spd = {"v3": 3, "v2": 2}.get(ins.shower_level or "", 1)
        return DvDecision(spd, "shower_override")

    # --- Auto / IAQ path (SPEC §4.1) ---
    co2 = state.co2_ema if (cfg.co2_ema_enabled and state.co2_ema > 0) else (co2_raw or 0.0)
    pm = state.pm_ema if (cfg.pm_ema_enabled and state.pm_ema > 0) else (pm_raw or 0.0)

    co2_hys = cfg.co2_hys
    pm_hys = cfg.pm_hys
    if ins.override_recent and ins.current_speed == 3:
        co2_hys *= 0.5
        pm_hys *= 0.5

    base = base_target(co2, pm, cfg, ins.current_speed, co2_hys, pm_hys)
    t = base
    reason = "iaq"

    # 1) Free-cooling
    state.freecool_active = compute_freecool(cfg, ins, state.freecool_active)
    if state.freecool_active and t < 2:
        t, reason = 2, "freecool"

    # 2) Pre-risk dew
    if ins.dry_mode and ins.dew_prerisk and not ins.dew_risk and t < 2:
        t, reason = 2, "dew_prerisk"

    # 3) SDHB intent (after freecool; can force/cap)
    intent = ins.sdhb_intent
    if intent not in ("none", "unknown", "unavailable", ""):
        if intent in INTENT_QUIET:
            t, reason = 1, "sdhb_quiet"
        elif intent == INTENT_BOOST:
            t, reason = 3, "sdhb_boost"
        elif intent == INTENT_FREECOOL:
            if t < 2:
                t, reason = 2, "sdhb_freecool"
        # request_normal -> no-op

    # 4) Hostile outside cap (SPEC §4.2.4)
    if cfg.hostile_enabled and ins.aqi is not None:
        if ins.aqi >= cfg.hostile_t3:
            t, reason = 0, "hostile_off"
        elif ins.aqi >= cfg.hostile_t2 and t > 1:
            t, reason = 1, "hostile_cap_v1"
        elif ins.aqi >= cfg.hostile_t1 and t > 2:
            t, reason = 2, "hostile_cap_v2"

    # 5) Anti-flapping: only raise on allowed triggers (SPEC §4.2.5)
    allow_raise = (
        ins.trigger_is_iaq
        or intent in (INTENT_BOOST, INTENT_FREECOOL)
        or ins.dew_risk
        or ins.dew_prerisk
        or ins.dry_mode
    )
    if not allow_raise and t > ins.current_speed:
        t, reason = ins.current_speed, "hold_antiflap"

    return DvDecision(t, reason, base_target=base,
                      details={"co2": round(co2, 1), "pm": round(pm, 2),
                               "intent": intent})
