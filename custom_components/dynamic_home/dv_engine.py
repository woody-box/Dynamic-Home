"""Dynamic Ventilation — pure decision engine (no Home Assistant dependencies).

Faithful port of the DV ``control_principal`` YAML pipeline plus the gating /
failsafe / shower / adaptive layers (see ../../docs/SPEC_DV.md). No Home Assistant
imports on purpose: unit-testable in isolation and reused by the HA wrappers.

Logical speed returned by :func:`decide`: 0 = OFF, 1/2/3 = V1/V2/V3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Intents understood from the SDHB bus (subset relevant to DV).
INTENT_QUIET = {"request_quiet", "request_eco", "request_weather_protect"}
INTENT_BOOST = "request_boost"
INTENT_FREECOOL = "request_freecool"
INTENT_NORMAL = "request_normal"
INTENT_DRY = "request_dry"            # F22: DC mold alert asks the VMC to dry

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
    dew_spread_min: float = 1.5      # indoor temp within this of dew point -> risk
    # F13: only ventilate to dry when the outdoor air is meaningfully drier, i.e.
    # dp_diff (dp_in - dp_out) clears a margin, with hysteresis so it doesn't
    # chatter at the boundary.
    dry_margin: float = 1.0          # min dp_diff (°C) to ENGAGE drying ventilation
    dry_hys: float = 0.5             # disengage once dp_diff <= dry_margin - dry_hys

    # Quiet hours (F12): cap the auto/IAQ speed during a daily night window
    # unless the air is critical (health > silence). quiet_max_level 3 = no cap.
    quiet_enabled: bool = False
    quiet_start_min: int = 23 * 60   # 23:00 (minutes from midnight, local)
    quiet_end_min: int = 7 * 60      # 07:00
    quiet_max_level: int = 1         # 0=OFF, 1=V1, 2=V2 (3 = uncapped)
    quiet_critical_co2: float = 1500.0
    quiet_critical_pm: float = 50.0

    # Weekly schedule (SPEC §7): weekday(0=Mon..6=Sun) -> (on_min, off_min)
    # minutes from midnight. Empty/missing -> always allowed.
    schedule_enabled: bool = False
    schedule: dict = field(default_factory=dict)

    # Failsafe / guardrails (SPEC §6)
    # Sanity floor: a CO2 reading below this is physically impossible in an
    # occupied space (atmospheric baseline ~410 ppm) and is treated as a sensor
    # fault (a "clean 0" after a bad calibration) -> routed to the vital-KO
    # failsafe instead of poisoning the EMA. PM is NOT floored: ~0 µg/m³ is real.
    co2_sanity_floor: float = 250.0
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
    adaptive_min_samples: int = 100   # min readings before percentiles are used

    # Heat-recovery efficiency (F28): bypass / no-recovery detection thresholds.
    hrv_bypass_eff_max: float = 0.2   # η at/below this with real ΔT => bypass
    hrv_bypass_dt_min: float = 3.0    # min |extract - intake| ΔT (°C) to judge

    # Anticipatory ventilation (F11): pre-boost on a steep CO2/PM rise (the
    # EMA-smoothed derivative), with on/off thresholds + hold like the shower boost.
    anticip_enabled: bool = False
    anticip_co2_rate_on: float = 400.0   # ppm/h: engage when CO2 climbs this fast
    anticip_co2_rate_off: float = 150.0  # ppm/h: release below this (hysteresis)
    anticip_pm_rate_on: float = 20.0     # µg/m³/h: engage when PM climbs this fast
    anticip_pm_rate_off: float = 8.0     # µg/m³/h: release below this
    anticip_hold_s: float = 600.0        # anti-transient hold (as the shower boost)
    anticip_level: int = 2               # target speed while anticipating (V2, soft)
    anticip_ema_alpha: float = 0.3       # smoothing of the rate itself (advanced)

    # Filter life: total hours a filter is rated for (replacement interval).
    filter_life_hours: float = 3650.0


HRV_MIN_DT = 1.0  # min |extract - intake| ΔT (°C) to compute a stable efficiency


def hrv_efficiency(supply: float | None, intake: float | None,
                   extract: float | None) -> float | None:
    """Supply-side heat-recovery effectiveness 0..1 (F28), or None.

    η = (T_supply − T_intake) / (T_extract − T_intake). Valid in both directions
    (recovers heat in winter, coolth in summer). None if a probe is missing or the
    extract/intake ΔT is too small for a stable ratio.
    """
    if supply is None or intake is None or extract is None:
        return None
    denom = extract - intake
    if abs(denom) < HRV_MIN_DT:
        return None
    return max(0.0, min(1.0, (supply - intake) / denom))


def hrv_state(supply: float | None, intake: float | None,
              extract: float | None, cfg: DvConfig) -> str | None:
    """'recovering' / 'bypass' / 'idle' (F28), or None if not computable.

    'idle' when the ΔT is too small to judge; 'bypass' when there IS a meaningful
    ΔT but efficiency collapses (the exchanger isn't recovering).
    """
    eff = hrv_efficiency(supply, intake, extract)
    if eff is None:
        return None
    if abs(extract - intake) < cfg.hrv_bypass_dt_min:
        return "idle"
    return "bypass" if eff <= cfg.hrv_bypass_eff_max else "recovering"


def filter_life_pct(hours: float, life: float) -> float:
    """Remaining filter life as a 0..100 percentage.

    ``100·(1 − hours/life)`` clamped to [0, 100]. A non-positive ``life``
    (filter tracking effectively disabled) reports 100.
    """
    if life <= 0:
        return 100.0
    return max(0.0, min(100.0, 100.0 * (1.0 - hours / life)))


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

    # Dry mode (F13): hysteresis latch for the dew-point drying gate.
    dry_active: bool = False

    # Anticipatory ventilation (F11): slope tracking + detector latch.
    anticip_prev_co2: float = 0.0     # last effective CO2 used for the slope
    anticip_prev_pm: float = 0.0      # last effective PM
    anticip_prev_ts: float = 0.0      # timestamp of that snapshot (0 = no sample yet)
    anticip_co2_rate: float = 0.0     # EMA-smoothed CO2 slope (ppm/h)
    anticip_pm_rate: float = 0.0      # EMA-smoothed PM slope (µg/m³/h)
    anticip_active: bool = False
    anticip_hold_until: float = 0.0


@dataclass
class DvInputs:
    """Live readings + mode flags for a single decision cycle."""

    co2_raw: float | None = None
    pm_raw: float | None = None
    t_in: float | None = None
    t_ext: float | None = None
    aqi: float | None = None

    current_speed: int = 1

    # Gating. ``permitida`` left as None means "compute it from the inputs
    # below"; set a bool to force it (used by tests / manual gating).
    permitida: bool | None = None
    auto_mode: bool = True
    permiso_extra: bool = False

    manual_override: bool = False
    override_v3: bool = False
    boost_active: bool = False        # F14: timed V3 boost (service-driven)

    # Explicit shower override (timer/UI). If None, shower is derived from RH.
    shower_override: bool = False
    shower_level: str | None = None  # "v2" | "v3" | None

    dry_mode: bool = False
    dry_requested: bool = False        # F22: bus-driven dry request (DC mold)
    dew_risk: bool = False
    dew_prerisk: bool = False
    dp_diff: float | None = None

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
    rh_delta: float | None = None

    # Adaptive thresholds (only used when cfg.adaptive_enabled and provided).
    adaptive_co2_v2: float | None = None
    adaptive_co2_v3: float | None = None
    adaptive_pm_v2: float | None = None
    adaptive_pm_v3: float | None = None


@dataclass
class DvDecision:
    speed: int
    reason: str
    base_target: int | None = None
    details: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _validate(value: float | None, lo: float, hi: float) -> float | None:
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


def in_quiet_window(minute_of_day: int, cfg: DvConfig) -> bool:
    """Whether we're inside the F12 quiet-hours window (handles overnight wrap)."""
    if not cfg.quiet_enabled:
        return False
    on_m, off_m = cfg.quiet_start_min, cfg.quiet_end_min
    if on_m == off_m:
        return False
    if on_m < off_m:
        return on_m <= minute_of_day < off_m
    return minute_of_day >= on_m or minute_of_day < off_m   # overnight


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
                  rh_delta: float | None) -> bool:
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


def update_anticip_rates(state: DvState, cfg: DvConfig, now_ts: float,
                         co2_eff: float, pm_eff: float) -> None:
    """Track the EMA-smoothed CO2/PM slopes (per hour) for F11.

    Mirrors the DC trend derivative but keeps its state in ``DvState``. The first
    sample only seeds the snapshots (rate stays 0); a non-monotonic / zero clock
    step is ignored so a stale or repeated timestamp can't spike the rate.
    """
    if state.anticip_prev_ts <= 0:
        state.anticip_prev_co2 = co2_eff
        state.anticip_prev_pm = pm_eff
        state.anticip_prev_ts = now_ts
        return
    dt_h = (now_ts - state.anticip_prev_ts) / 3600.0
    if dt_h <= 0:
        return
    a = cfg.anticip_ema_alpha
    raw_co2 = (co2_eff - state.anticip_prev_co2) / dt_h
    raw_pm = (pm_eff - state.anticip_prev_pm) / dt_h
    state.anticip_co2_rate = a * raw_co2 + (1 - a) * state.anticip_co2_rate
    state.anticip_pm_rate = a * raw_pm + (1 - a) * state.anticip_pm_rate
    state.anticip_prev_co2 = co2_eff
    state.anticip_prev_pm = pm_eff
    state.anticip_prev_ts = now_ts


def update_anticip(state: DvState, cfg: DvConfig, now_ts: float) -> bool:
    """Anticipatory detector (F11): two-channel on/off hysteresis + hold.

    Engages when EITHER the CO2 or PM slope clears its on-threshold; releases only
    when BOTH are below their off-thresholds AND the hold window has elapsed —
    exactly the shower-boost pattern, but over the slopes instead of ΔRH.
    """
    if not cfg.anticip_enabled:
        if state.anticip_active and now_ts < state.anticip_hold_until:
            return True
        state.anticip_active = False
        return False

    co2_r, pm_r = state.anticip_co2_rate, state.anticip_pm_rate
    if not state.anticip_active:
        if co2_r >= cfg.anticip_co2_rate_on or pm_r >= cfg.anticip_pm_rate_on:
            state.anticip_active = True
            state.anticip_hold_until = now_ts + cfg.anticip_hold_s
    else:
        both_below = (co2_r < cfg.anticip_co2_rate_off
                      and pm_r < cfg.anticip_pm_rate_off)
        if both_below and now_ts >= state.anticip_hold_until:
            state.anticip_active = False
    return state.anticip_active


# --------------------------------------------------------------------------- #
# Main decision
# --------------------------------------------------------------------------- #
def decide(cfg: DvConfig, state: DvState, ins: DvInputs) -> DvDecision:
    """Run one full DV control cycle. Mutates ``state`` (EMA/freecool/failsafe)."""
    co2_raw = _validate(ins.co2_raw, max(CO2_MIN, cfg.co2_sanity_floor), CO2_MAX)
    pm_raw = _validate(ins.pm_raw, PM25_MIN, PM25_MAX)

    # --- EMA maintenance ---
    if cfg.co2_ema_enabled and co2_raw is not None:
        state.co2_ema = update_ema(state.co2_ema, co2_raw, cfg.co2_ema_alpha)
    if cfg.pm_ema_enabled and pm_raw is not None:
        state.pm_ema = update_ema(state.pm_ema, pm_raw, cfg.pm_ema_alpha)

    # --- Anticipatory slope (F11): track every cycle, before any early return ---
    co2_eff_a = (state.co2_ema if (cfg.co2_ema_enabled and state.co2_ema > 0)
                 else (co2_raw or 0.0))
    pm_eff_a = (state.pm_ema if (cfg.pm_ema_enabled and state.pm_ema > 0)
                else (pm_raw or 0.0))
    update_anticip_rates(state, cfg, ins.now_ts, co2_eff_a, pm_eff_a)
    anticip_on = update_anticip(state, cfg, ins.now_ts)

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

    # Timed V3 boost (F14): explicit, auto-reverting; bypasses the auto path and
    # the quiet-hours cap (it is a deliberate user request).
    if ins.boost_active:
        return DvDecision(3, "boost")

    # Dry mode (F13): gate ventilation on a dew-point advantage (dp_diff) with
    # hysteresis. Only ventilate to dry when the outdoor air is actually drier;
    # otherwise fall through to the normal IAQ/auto path (drying would add moisture).
    # F22: a bus-driven dry request (from a DC mold alert) also demands drying,
    # bypassing the local switch/dew-risk but still honouring the dp_diff gate.
    dry_demanded = (((ins.dry_mode and ins.dew_risk) or ins.dry_requested)
                    and ins.dp_diff is not None)
    if dry_demanded:
        if state.dry_active:
            state.dry_active = ins.dp_diff > (cfg.dry_margin - cfg.dry_hys)
        else:
            state.dry_active = ins.dp_diff > cfg.dry_margin
        if state.dry_active:
            if ins.dp_diff >= cfg.dry_v3_delta:
                spd = 3
            elif ins.dp_diff >= cfg.dry_v2_delta:
                spd = 2
            else:
                spd = 1
            return DvDecision(spd, "dry_mode",
                              details={"dp_diff": ins.dp_diff,
                                       "dry_margin": cfg.dry_margin})
    else:
        state.dry_active = False

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

    # 0) Anticipatory pre-boost (F11): a steep CO2/PM rise lifts speed ahead of
    # the absolute-level crossing. Never lowers an already-higher base; later
    # caps (sdhb_quiet / hostile) still apply.
    if anticip_on and t < cfg.anticip_level:
        t, reason = cfg.anticip_level, "anticipatory"

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
        or anticip_on
    )
    if not allow_raise and t > ins.current_speed:
        t, reason = ins.current_speed, "hold_antiflap"

    # 6) Quiet hours cap (F12): final authority on the auto/IAQ path — limit the
    # speed during the night window unless the air is critical (health > silence).
    if in_quiet_window(ins.minute_of_day, cfg) and t > cfg.quiet_max_level:
        critical = co2 >= cfg.quiet_critical_co2 or pm >= cfg.quiet_critical_pm
        if not critical:
            t, reason = cfg.quiet_max_level, "quiet_cap"

    return DvDecision(t, reason, base_target=base,
                      details={"co2": round(co2, 1), "pm": round(pm, 2),
                               "intent": intent})
