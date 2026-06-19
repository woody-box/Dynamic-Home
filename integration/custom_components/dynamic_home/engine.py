"""Dynamic Ventilation — pure decision engine (no Home Assistant dependencies).

Faithful port of the DV ``control_principal`` YAML pipeline plus the gating /
failsafe / shower / adaptive layers (see ../../SPEC.md). No Home Assistant
imports on purpose: unit-testable in isolation and reused by the HA wrappers.

Logical speed returned by :func:`decide`: 0 = OFF, 1/2/3 = V1/V2/V3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Intents understood from the SDHB bus (subset relevant to DV).
INTENT_QUIET = {"request_quiet", "request_eco", "request_weather_protect"}
INTENT_BOOST = "request_boost"
INTENT_FREECOOL = "request_freecool"
INTENT_NORMAL = "request_normal"

# Safe-range validation (SPEC §2).
CO2_MIN, CO2_MAX = 0.0, 5000.0
PM25_MIN, PM25_MAX = 0.0, 500.0


@dataclass
class DvConfig:
    """Tunables. Defaults mirror the YAML ``initial:`` values."""

    # IAQ thresholds / hysteresis
    co2_v2: float = 900.0
    co2_v3: float = 1300.0
    pm_v2: float = 15.0
    pm_v3: float = 40.0
    co2_hys: float = 100.0
    pm_hys: float = 5.0

    # EMA
    co2_ema_enabled: bool = True
    pm_ema_enabled: bool = True
    co2_ema_alpha: float = 0.2
    pm_ema_alpha: float = 0.2

    # Free-cooling
    freecool_enabled: bool = False
    freecool_t_ext_min: float = 5.0
    freecool_delta_on: float = 2.0
    freecool_delta_off: float = 1.0

    # Hostile outside (AQI)
    hostile_enabled: bool = False
    hostile_t1: float = 50.0
    hostile_t2: float = 100.0
    hostile_t3: float = 150.0

    # Dry mode (dew point)
    dry_v2_delta: float = 0.2
    dry_v3_delta: float = 1.0

    # Weekly schedule (SPEC §7): weekday(0=Mon..6=Sun) -> (on_min, off_min)
    # minutes from midnight. Empty/missing -> always allowed.
    schedule_enabled: bool = False
    schedule: dict = field(default_factory=dict)

    # Failsafe / guardrails (SPEC §6)
    stale_threshold_s: float = 120.0
    startup_grace_s: float = 120.0
    trip_window_s: float = 7200.0
    trip_limit: int = 3
    lockout_s: float = 1800.0

    # Shower boost via ΔRH (SPEC §7)
    shower_enabled: bool = False
    shower_rh_delta_on: float = 8.0
    shower_rh_delta_off: float = 4.0
    shower_hold_s: float = 600.0
    shower_level: int = 3  # target speed while a shower is detected

    # Adaptive thresholds (SPEC §7) — engine uses them when provided & ready.
    adaptive_enabled: bool = False


@dataclass
class DvState:
    """State the engine carries between cycles."""

    co2_ema: float = 0.0
    pm_ema: float = 0.0
    freecool_active: bool = False

    # Failsafe
    trips: list = field(default_factory=list)  # timestamps of vital-KO trips
    lockout_until: float = 0.0
    prev_vital_ko: bool = False

    # Shower
    shower_active: bool = False
    shower_hold_until: float = 0.0


@dataclass
class DvInputs:
    """Live readings + mode flags for a single decision cycle."""

    co2_raw: Optional[float] = None
    pm_raw: Optional[float] = None
    t_in: Optional[float] = None
    t_ext: Optional[float] = None
    aqi: Optional[float] = None

    current_speed: int = 1

    # Gating. ``permitida`` left as None means "compute it from the inputs
    # below"; set a bool to force it (used by tests / manual gating).
    permitida: Optional[bool] = None
    auto_mode: bool = True
    permiso_extra: bool = False

    manual_override: bool = False
    override_v3: bool = False

    # Explicit shower override (timer/UI). If None, shower is derived from RH.
    shower_override: bool = False
    shower_level: Optional[str] = None  # "v2" | "v3" | None

    dry_mode: bool = False
    dew_risk: bool = False
    dew_prerisk: bool = False
    dp_diff: Optional[float] = None

    sdhb_intent: str = "none"

    trigger_is_iaq: bool = False
    override_recent: bool = False

    # Time / schedule / failsafe context
    now_ts: float = 0.0
    weekday: int = 0
    minute_of_day: int = 0
    co2_age_s: float = 0.0
    pm_age_s: float = 0.0
    startup_grace_active: bool = False

    # Shower humidity delta (bath RH rise). None disables RH-derived shower.
    rh_delta: Optional[float] = None

    # Adaptive thresholds (only used when cfg.adaptive_enabled and provided).
    adaptive_co2_v2: Optional[float] = None
    adaptive_co2_v3: Optional[float] = None
    adaptive_pm_v2: Optional[float] = None
    adaptive_pm_v3: Optional[float] = None


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


def in_schedule(weekday: int, minute_of_day: int, cfg: DvConfig) -> bool:
    """Weekly schedule gate (SPEC §4, port of ``en_horario``).

    Handles overnight wrap (on_min > off_min). Missing day -> allowed.
    """
    if not cfg.schedule_enabled:
        return True
    window = cfg.schedule.get(weekday)
    if not window:
        return True
    on_m, off_m = window
    if on_m is None or off_m is None or on_m == off_m:
        return True
    if on_m < off_m:
        return on_m <= minute_of_day < off_m
    # overnight
    return minute_of_day >= on_m or minute_of_day < off_m


def update_failsafe(state: DvState, cfg: DvConfig, now_ts: float,
                    vital_ko: bool) -> bool:
    """Trip-counter + lockout (SPEC §6). Returns True if lockout is active.

    A trip is registered on the rising edge of ``vital_ko``. ``trip_limit``
    trips within ``trip_window_s`` arm a lockout for ``lockout_s``.
    """
    # prune trips outside the window
    state.trips = [t for t in state.trips if now_ts - t <= cfg.trip_window_s]

    if vital_ko and not state.prev_vital_ko:
        state.trips.append(now_ts)
        if len(state.trips) >= cfg.trip_limit:
            state.lockout_until = now_ts + cfg.lockout_s
            state.trips = []
    state.prev_vital_ko = vital_ko

    return now_ts < state.lockout_until


def update_shower(state: DvState, cfg: DvConfig, now_ts: float,
                  rh_delta: Optional[float]) -> bool:
    """Shower detection via ΔRH with hysteresis + hold (SPEC §7)."""
    if not cfg.shower_enabled or rh_delta is None:
        # keep holding if within hold window, else clear
        if state.shower_active and now_ts < state.shower_hold_until:
            return True
        state.shower_active = False
        return False

    if not state.shower_active:
        if rh_delta >= cfg.shower_rh_delta_on:
            state.shower_active = True
            state.shower_hold_until = now_ts + cfg.shower_hold_s
    else:
        if rh_delta < cfg.shower_rh_delta_off and now_ts >= state.shower_hold_until:
            state.shower_active = False
    return state.shower_active


def base_target(co2: float, pm: float, co2_v2: float, co2_v3: float,
                pm_v2: float, pm_v3: float, v_actual: int,
                co2_hys: float, pm_hys: float) -> int:
    """IAQ hysteresis state machine (SPEC §4.1)."""
    if co2 >= co2_v3 or pm >= pm_v3:
        return 3
    if v_actual == 3:
        can_drop = (co2 < co2_v3 - co2_hys) and (pm < pm_v3 - pm_hys)
        if can_drop:
            return 2 if (co2 >= co2_v2 or pm >= pm_v2) else 1
        return 3
    if co2 >= co2_v2 or pm >= pm_v2:
        return 2
    if v_actual == 2:
        can_drop2 = (co2 < co2_v2 - co2_hys) and (pm < pm_v2 - pm_hys)
        return 1 if can_drop2 else 2
    return 1


# --------------------------------------------------------------------------- #
# Main decision
# --------------------------------------------------------------------------- #
def decide(cfg: DvConfig, state: DvState, ins: DvInputs) -> DvDecision:
    """Run one full DV control cycle. Mutates ``state`` (EMA/freecool/failsafe)."""
    co2_raw = _validate(ins.co2_raw, CO2_MIN, CO2_MAX)
    pm_raw = _validate(ins.pm_raw, PM25_MIN, PM25_MAX)

    # --- EMA maintenance ---
    if cfg.co2_ema_enabled and co2_raw is not None:
        state.co2_ema = update_ema(state.co2_ema, co2_raw, cfg.co2_ema_alpha)
    if cfg.pm_ema_enabled and pm_raw is not None:
        state.pm_ema = update_ema(state.pm_ema, pm_raw, cfg.pm_ema_alpha)

    # --- Failsafe: vital sensor KO (stale or invalid), gated by startup grace ---
    vital_ko = (not ins.startup_grace_active) and (
        co2_raw is None or pm_raw is None
        or ins.co2_age_s > cfg.stale_threshold_s
        or ins.pm_age_s > cfg.stale_threshold_s
    )
    lockout = update_failsafe(state, cfg, ins.now_ts, vital_ko)

    # --- Permitida gate (SPEC §4) ---
    if ins.permitida is not None:
        permitida = ins.permitida
    else:
        sched_ok = in_schedule(ins.weekday, ins.minute_of_day, cfg)
        permitida = ins.auto_mode and (not lockout) and (sched_ok or ins.permiso_extra)

    if not permitida:
        return DvDecision(0, "lockout" if lockout else "not_permitted")

    # --- Mode precedence (SPEC §4) ---
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

    # Shower: explicit override, or derived from ΔRH.
    shower_on = update_shower(state, cfg, ins.now_ts, ins.rh_delta)
    if ins.shower_override:
        spd = {"v3": 3, "v2": 2}.get(ins.shower_level or "", 1)
        return DvDecision(spd, "shower_override")
    if shower_on:
        return DvDecision(cfg.shower_level, "shower_rh")

    # --- Auto / IAQ path ---
    # Safety: in auto, missing/stale vital data -> force V1.
    if vital_ko:
        return DvDecision(1, "failsafe_vital_ko")

    co2 = state.co2_ema if (cfg.co2_ema_enabled and state.co2_ema > 0) else (co2_raw or 0.0)
    pm = state.pm_ema if (cfg.pm_ema_enabled and state.pm_ema > 0) else (pm_raw or 0.0)

    # Adaptive thresholds (SPEC §7): override config when enabled & provided.
    co2_v2, co2_v3 = cfg.co2_v2, cfg.co2_v3
    pm_v2, pm_v3 = cfg.pm_v2, cfg.pm_v3
    if cfg.adaptive_enabled:
        if ins.adaptive_co2_v2 is not None:
            co2_v2 = ins.adaptive_co2_v2
        if ins.adaptive_co2_v3 is not None:
            co2_v3 = ins.adaptive_co2_v3
        if ins.adaptive_pm_v2 is not None:
            pm_v2 = ins.adaptive_pm_v2
        if ins.adaptive_pm_v3 is not None:
            pm_v3 = ins.adaptive_pm_v3

    co2_hys = cfg.co2_hys
    pm_hys = cfg.pm_hys
    if ins.override_recent and ins.current_speed == 3:
        co2_hys *= 0.5
        pm_hys *= 0.5

    base = base_target(co2, pm, co2_v2, co2_v3, pm_v2, pm_v3,
                       ins.current_speed, co2_hys, pm_hys)
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
