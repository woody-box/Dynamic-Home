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

import math
from dataclasses import dataclass, field

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

    # Vacation limits: applied instead of the normal ones while on vacation, so a
    # low/high vacation base is not clamped back by the comfort range.
    vac_target_min_heat: float = 15.0
    vac_target_max_heat: float = 19.0
    vac_target_min_cool: float = 28.0
    vac_target_max_cool: float = 31.0

    step: float = 0.5
    max_mods_heat: float = 0.8
    max_mods_cool: float = 0.8
    # Minimum change vs the last applied setpoint before pushing a new one to the
    # thermostat (anti-jitter). 0 = always apply (the engine already quantizes).
    apply_min_delta: float = 0.0

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

    # VMC compensation bias (°C, per speed) — abs magnitudes.
    vmc_bias_heat: tuple = (0.1, 0.2, 0.3)   # v1, v2, v3
    vmc_bias_cool: tuple = (0.1, 0.2, 0.3)

    # Trend (tendencia) anticipation + brake (freno)
    trend_lead_h: float = 1.0          # fallback lead when temps unavailable
    trend_max_shift: float = 0.25
    # Dynamic lead: more anticipation with more thermal inertia (bigger ΔT).
    lead_base_h: float = 1.0
    lead_per_degree_h: float = 0.05
    lead_wind_h_per_kmh: float = 0.02   # wind increases losses -> more lead
    lead_min_h: float = 0.5
    lead_max_h: float = 3.0
    trend_deadband_cph: float = 0.1          # °C/h below which trend is ignored
    trend_ema_alpha: float = 0.3
    brake_thresholds: tuple = (0.3, 0.6, 1.0)  # th1, th2, th3 (°C/h)
    brake_biases: tuple = (0.1, 0.2, 0.3)      # b1, b2, b3

    # Forecast anticipation
    forecast_gain: float = 0.1
    forecast_cap: float = 0.5
    forecast_window_h: float = 6.0

    # Adaptive lead (learned from real ON/OFF cycles) — opt-in. Port of the v4.2
    # "Adaptive Lead v2.6.1": the heating/cooling rate, overshoot and thermal lag
    # are learned per zone and drive the anticipation horizon instead of the
    # static physical model.
    adapt_alpha: float = 0.20            # EMA smoothing for the learned quantities
    adapt_gain_lr: float = 0.10          # gradient step toward the lead target
    adapt_overshoot_target: float = 0.10  # tolerated overshoot (°C) before correcting
    adapt_rate_floor_cph: float = 0.05   # floor on the heating/cooling rate (°C/h)
    adapt_lag_k: float = 1.0             # weight of the learned thermal lag
    adapt_on_rate_min_dt_h: float = 0.25  # min ON duration to trust a rate sample (h)
    adapt_on_rate_min_dt: float = 0.05   # min |ΔT| to trust a rate sample (°C)
    adapt_off_window_h: float = 3.0      # settling window watched for the peak (h)
    lead_adaptive_min_h: float = 0.0
    lead_adaptive_max_h: float = 4.0

    # Dew-point protection (radiant cooling): risk when indoor temp is within
    # this margin of the dew point.
    dew_spread_min: float = 2.0

    # Real demand signal (F27): when the valve source (c) is numeric (power, W),
    # a reading above this means the valve/relay is active. Consumed by the
    # coordinator's Adaptive Lead, not by the pure decision pipeline.
    valve_power_min: float = 5.0

    # Open-window inference (F20): when no window sensor exists, an actively
    # conditioning zone whose indoor temp moves against the demand faster than
    # window_drop_cph (°C/h) is treated as a likely open window. Debounced and
    # auto-recovering (stabilisation or timeout).
    window_drop_cph: float = 2.5      # opposing trend that flags an anomaly
    window_confirm_min: float = 3.0   # minutes the anomaly must persist to arm
    window_release_min: float = 5.0   # minutes of stability to disarm
    window_max_lockout_min: float = 30.0  # safety timeout to auto-disarm

    # Mold-risk index (F22): "hours above an RH threshold with decay". on/off are
    # the hysteresis arm/disarm thresholds (in accumulated hours).
    mold_rh_threshold: float = 70.0   # %RH at/above which risk accrues
    mold_decay_h: float = 24.0        # exponential decay time constant (h)
    mold_on_h: float = 12.0           # index (h) that arms the alert/drying
    mold_off_h: float = 6.0           # index (h) that disarms it (hysteresis)
    mold_cap_h: float = 48.0          # clamp the index here

    # Adjacent warm space / terrace (F31): advisory ΔT thresholds (adjacent minus
    # indoor, °C). open_dt: in heat, advise opening the door for free gain;
    # alarm_dt: in cool, warn if the door is open and the adjacent space is hot.
    adj_open_dt: float = 6.0
    adj_alarm_dt: float = 4.0

    # Facade solar-gain bias: max °C correction at full openness on sunlit facades.
    facade_gain_heat: float = 0.3
    facade_gain_cool: float = 0.3

    # Energy (F06): estimated power (W) while the zone is calling for heat/cool,
    # used when no real power meter is configured (idle draws nothing).
    est_w_on: float = 1000.0

    # Short-cycle protection (F09): compressor min ON/OFF (s) + max starts/hour.
    # Opt-in (compressor installs); safety always overrides (cede the min ON).
    anticycle_min_on_s: float = 600.0
    anticycle_min_off_s: float = 600.0
    anticycle_max_starts_per_h: int = 6
    # Electrical-peak staging (F03): house-level limit on simultaneous electric
    # heating starts. Opt-in; only engaged when the F26 profile is electrical and
    # not communal. peak_max_power_w > 0 switches from count mode (max zones) to
    # power mode (watt budget, real meter or est_w_on).
    peak_max_zones: int = 2
    peak_max_power_w: float = 0.0
    peak_stagger_s: float = 10.0
    # Comfort bypass: a severe deviation (°C past setpoint) skips the peak gate
    # entirely — comfort wins over peak-shaving (safety still wins above). 0 = off.
    peak_comfort_bypass_c: float = 2.5
    # Emitter staging (F25): a support emitter arms when the primary lags by more
    # than support_dev_on (°C) for support_confirm_min, and retires when the room
    # recovers under support_dev_off for support_release_min (hysteresis).
    support_dev_on: float = 0.6
    support_confirm_min: float = 15.0
    support_dev_off: float = 0.2
    support_release_min: float = 10.0
    # Shared un-zoned emitter reconciliation (F25 Phase B): per-zone demand weight
    # and the undershoot guard margin (°C) for a duct without motorized grilles.
    zone_demand_weight: float = 1.0
    shared_undershoot_margin: float = 0.5


@dataclass
class DcInputs:
    hvac_mode: str = "off"          # heat | cool | off (demanded mode)
    t_int: float | None = None
    t_ext: float | None = None
    sun_elevation: float | None = None
    vacation: bool = False

    # Catch-all for biases not yet wired (e.g. per-facade solar gain), in °C.
    extra_bias: float = 0.0

    # VMC speed (1/2/3) for the VMC compensation bias; None disables it.
    vmc_speed: int | None = None
    # Indoor temperature rate of change (°C/h), EMA-smoothed by the caller.
    trend_cph: float = 0.0
    # Forecast extreme temperature in the look-ahead window (max for heat, min
    # for cool); None disables the forecast bias.
    forecast_temp: float | None = None
    # Outdoor wind (km/h) for the lead model; None ignores the wind term.
    wind: float | None = None
    # Learned adaptive lead (hours); when set, overrides the physical lead model.
    adaptive_lead_h: float | None = None

    # Bus intent targeted at DC (consumed -> self bias).
    sdhb_intent: str = "none"

    # Safety / gating
    dew_risk: bool = False
    window_lockout: bool = False
    window_inferred: bool = False      # F20: open window inferred from temperature

    # Manual override
    override_active: bool = False
    override_temp: float | None = None

    # Weekly scheduler (F21): absolute BASE setpoint from the active slot (°C),
    # replacing the day/night base. None = no schedule (use base_active). Vacation
    # still takes precedence over a scheduled base.
    scheduled_base: float | None = None


@dataclass
class DcDecision:
    action: str          # heat | cool | off
    target: float | None
    reason: str
    published_intent: str  # what DC publishes to the shutters (or "none")
    details: dict = field(default_factory=dict)  # pipeline breakdown (observability)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def is_night(sun_elevation: float | None) -> bool:
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


def bias_exterior(cfg: DcConfig, hvac: str, t_ext: float | None) -> float:
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


def mold_index_step(prev_h: float, rh: float | None, dt_h: float,
                    cfg: DcConfig) -> float:
    """Mold-risk index (F22): accumulate hours above an RH threshold with decay.

    Above ``mold_rh_threshold`` the index grows by the elapsed hours; below it it
    decays exponentially (time constant ``mold_decay_h``). Clamped to
    ``[0, mold_cap_h]``. ``rh`` None or non-positive dt -> unchanged.
    """
    if dt_h <= 0 or rh is None:
        return max(0.0, min(prev_h, cfg.mold_cap_h))
    if rh >= cfg.mold_rh_threshold:
        idx = prev_h + dt_h
    else:
        idx = prev_h * math.exp(-dt_h / cfg.mold_decay_h) if cfg.mold_decay_h > 0 \
            else 0.0
    return max(0.0, min(idx, cfg.mold_cap_h))


def window_anomaly(hvac: str, valve_open: bool, trend_cph: float,
                   cfg: DcConfig) -> bool:
    """Instantaneous open-window signature (F20).

    True when the zone is actively conditioning (``valve_open``) but the indoor
    temperature moves *against* the demand faster than ``window_drop_cph``:
    dropping while heating, or rising while cooling. ``trend_cph`` is the
    (pre-deadbanded) indoor-temperature derivative in °C/h.
    """
    if not valve_open or hvac not in ("heat", "cool"):
        return False
    if hvac == "heat":
        return trend_cph <= -cfg.window_drop_cph
    return trend_cph >= cfg.window_drop_cph


def adjacent_advice(hvac: str, t_int: float | None, t_adj: float | None,
                    door_open: bool | None, cfg: DcConfig) -> str:
    """Advisory for an adjacent warm space / terrace (F31).

    Returns ``"open_gain"`` (heat: adjacent much warmer and the door is closed →
    open it for free solar gain), ``"close_alarm"`` (cool: adjacent much warmer
    *and* the door is open → that heat is leaking in) or ``"none"``. Advisory
    only — it never actuates the door. ``door_open`` None means no door sensor.
    """
    if t_int is None or t_adj is None or hvac not in ("heat", "cool"):
        return "none"
    dt = t_adj - t_int
    if hvac == "heat" and dt >= cfg.adj_open_dt and not door_open:
        return "open_gain"
    if hvac == "cool" and dt >= cfg.adj_alarm_dt and door_open:
        return "close_alarm"
    return "none"


def dew_point(t_c: float | None, rh: float | None) -> float | None:
    """Dew point (°C) via the Magnus formula. None if inputs missing."""
    if t_c is None or rh is None or rh <= 0:
        return None
    a, b = 17.27, 237.7
    rh = min(100.0, max(1.0, rh))
    gamma = (a * t_c) / (b + t_c) + math.log(rh / 100.0)
    return round((b * gamma) / (a - gamma), 2)


def dew_risk(cfg: DcConfig, hvac: str, t_int: float | None,
             rh: float | None) -> bool:
    """Condensation risk for radiant cooling: only in cool, when the indoor
    temperature is within ``dew_spread_min`` of the dew point."""
    if hvac != "cool":
        return False
    dp = dew_point(t_int, rh)
    if dp is None or t_int is None:
        return False
    return (t_int - dp) < cfg.dew_spread_min


def facade_bias(cfg: DcConfig, hvac: str, openness: float) -> float:
    """Solar-gain bias from sunlit, open facades (°C).

    ``openness`` is the 0..1 aggregate shutter opening of the sunlit facades.
    Solar gain through open sunlit windows eases the demand: it lowers the
    setpoint pressure both when heating (sun warms -> heat less) and when cooling
    (sun heats -> cool more). Bounded by the per-mode gain.
    """
    openness = max(0.0, min(1.0, openness))
    if hvac == "heat":
        return -cfg.facade_gain_heat * openness
    if hvac == "cool":
        return -cfg.facade_gain_cool * openness
    return 0.0


def bias_vmc(cfg: DcConfig, hvac: str, vmc_speed: int | None,
             t_int: float | None, t_ext: float | None) -> float:
    """VMC compensation bias (°C). Port of ``dc_bias_vmc``."""
    if vmc_speed not in (1, 2, 3) or t_int is None or t_ext is None:
        return 0.0
    delta = t_ext - t_int
    if abs(delta) < 0.2:
        return 0.0
    if hvac == "heat":
        b = abs(cfg.vmc_bias_heat[vmc_speed - 1])
        return b if delta < 0 else 0.0
    if hvac == "cool":
        b = abs(cfg.vmc_bias_cool[vmc_speed - 1])
        return -b if delta > 0 else b
    return 0.0


def compute_lead(cfg: DcConfig, t_int: float | None, t_ext: float | None,
                 wind: float | None = None) -> float:
    """Anticipation horizon (hours): grows with the indoor/outdoor gap (inertia)
    and with wind (higher heat losses)."""
    if t_int is None or t_ext is None:
        lead = cfg.trend_lead_h
    else:
        lead = cfg.lead_base_h + cfg.lead_per_degree_h * abs(t_int - t_ext)
    if wind is not None:
        lead += cfg.lead_wind_h_per_kmh * max(0.0, wind)
    return max(cfg.lead_min_h, min(cfg.lead_max_h, lead))


def ema(prev: float, new: float, alpha: float) -> float:
    """Exponential moving average update (rounded to 3 decimals)."""
    return round(alpha * new + (1 - alpha) * prev, 3)


def on_rate_cph(t0: float | None, t_off: float | None, dt_h: float | None,
                cfg: DcConfig) -> float | None:
    """Heating/cooling rate (°C/h) over an ON cycle, or None if untrustworthy.

    The sample is only trusted when the cycle ran long enough and moved the
    temperature enough (validity gates ``adapt_on_rate_min_dt_h`` / ``_min_dt``).
    """
    if t0 is None or t_off is None or dt_h is None or dt_h <= 0:
        return None
    d_t = t_off - t0
    if dt_h < cfg.adapt_on_rate_min_dt_h or abs(d_t) < cfg.adapt_on_rate_min_dt:
        return None
    return round(d_t / dt_h, 3)


def adaptive_lead_target(cfg: DcConfig, overshoot_ema: float, lag_ema: float,
                         rate_ema: float) -> float:
    """Lead (hours) that would keep overshoot under target, from learned EMAs.

    Two candidates: the lead needed to bleed off the excess overshoot at the
    learned rate, and the learned thermal lag. The larger wins, then clamped.
    """
    rate_eff = max(cfg.adapt_rate_floor_cph, abs(rate_ema))
    extra_os = max(0.0, abs(overshoot_ema) - abs(cfg.adapt_overshoot_target))
    lead_from_os = extra_os / rate_eff
    lead_from_lag = lag_ema * cfg.adapt_lag_k
    raw = max(lead_from_os, lead_from_lag)
    return round(max(cfg.lead_adaptive_min_h,
                     min(raw, cfg.lead_adaptive_max_h)), 3)


def step_toward(prev: float, target: float, lr: float) -> float:
    """One gradient step of the adaptive lead gain toward its target."""
    return round(prev + lr * (target - prev), 3)


def trend_bias(cfg: DcConfig, cph: float,
               lead_h: float | None = None) -> float:
    """Anticipation by indoor-temperature trend (°C). Port of ``tendencia_efectiva``.

    Rising indoor temp (cph>0) shifts the target down (and vice versa), scaled by
    the lead time and clamped. ``cph`` is expected pre-deadbanded by the caller.
    """
    lead = cfg.trend_lead_h if lead_h is None else lead_h
    shift = -cph * lead
    return max(-cfg.trend_max_shift, min(cfg.trend_max_shift, shift))


def brake_bias(cfg: DcConfig, hvac: str, cph: float) -> float:
    """Trend brake (°C). Port of ``freno_tendencia``: only brakes when the trend
    already helps the active mode, by graduated thresholds."""
    if hvac == "heat" and cph > 0:
        abs_cph, sign = cph, -1
    elif hvac == "cool" and cph < 0:
        abs_cph, sign = -cph, 1
    else:
        return 0.0
    th1, th2, th3 = cfg.brake_thresholds
    b1, b2, b3 = cfg.brake_biases
    if abs_cph >= th3:
        mag = b3
    elif abs_cph >= th2:
        mag = b2
    elif abs_cph >= th1:
        mag = b1
    else:
        mag = 0.0
    return sign * mag


def forecast_bias(cfg: DcConfig, hvac: str, t_ext: float | None,
                  forecast_temp: float | None) -> float:
    """Forecast anticipation (°C). Port of ``bias_forecast``.

    Eases the setpoint when the forecast says the outside will help the active
    mode (warming while heating / cooling while cooling). Brake-only, clamped.
    """
    if forecast_temp is None or t_ext is None or hvac not in ("heat", "cool"):
        return 0.0
    d_t = forecast_temp - t_ext
    if (hvac == "heat" and d_t <= 0) or (hvac == "cool" and d_t >= 0):
        return 0.0
    raw = -(d_t * cfg.forecast_gain)
    return max(-cfg.forecast_cap, min(cfg.forecast_cap, raw))


def sdhb_self_bias(cfg: DcConfig, intent: str, hvac: str) -> float:
    """Bias applied when DC consumes a solar intent targeted at itself."""
    if intent == INTENT_SOLAR_GAIN and hvac == "heat":
        return cfg.sdhb_bias_solar_gain_heat
    if intent == INTENT_SOLAR_SHIELD and hvac == "cool":
        return cfg.sdhb_bias_solar_shield_cool
    return 0.0


def quantize_step(value: float, step: float) -> float:
    """Round to the nearest multiple of ``step`` (half-up, matching the YAML).

    Uses floor(x/step + 0.5) so exact ``.5`` boundaries round up consistently,
    unlike Python's banker's rounding.
    """
    step = max(step, 0.1)
    return round(math.floor(value / step + 0.5) * step, 4)


def assemble_target(cfg: DcConfig, hvac: str, base: float, mods_total: float,
                    sdhb_bias: float, vacation: bool) -> float:
    """base + clamp(mods, ±lim) + sdhb_bias, clamped to range and quantized."""
    lim = cfg.max_mods_heat if hvac == "heat" else cfg.max_mods_cool
    mods_clamped = max(-lim, min(lim, mods_total))
    raw = base + mods_clamped + sdhb_bias
    if vacation:
        lo = cfg.vac_target_min_heat if hvac == "heat" else cfg.vac_target_min_cool
        hi = cfg.vac_target_max_heat if hvac == "heat" else cfg.vac_target_max_cool
    else:
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


def sunlit_facades(sun_azimuth: float | None, sun_elevation: float | None,
                   facades: dict, spans: dict | None = None,
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
    if ins.window_inferred:
        return DcDecision("off", None, "off_window_inferred", "none")
    if ins.hvac_mode not in ("heat", "cool"):
        return DcDecision("off", None, "off", "none")

    night = is_night(ins.sun_elevation)
    # Weekly schedule (F21): a programmed slot fixes the absolute BASE (no night
    # easing); vacation still wins. Biases then apply on top of this base.
    if ins.scheduled_base is not None and not ins.vacation:
        base, base_source = ins.scheduled_base, "schedule"
    else:
        base, base_source = base_active(cfg, ins.hvac_mode, night, ins.vacation), "auto"
    if ins.adaptive_lead_h is not None:
        lead = max(cfg.lead_adaptive_min_h,
                   min(ins.adaptive_lead_h, cfg.lead_adaptive_max_h))
        lead_source = "adaptive"
    else:
        lead = compute_lead(cfg, ins.t_int, ins.t_ext, ins.wind)
        lead_source = "physical"
    b_ext = bias_exterior(cfg, ins.hvac_mode, ins.t_ext)
    b_vmc = bias_vmc(cfg, ins.hvac_mode, ins.vmc_speed, ins.t_int, ins.t_ext)
    b_trend = trend_bias(cfg, ins.trend_cph, lead)
    b_brake = brake_bias(cfg, ins.hvac_mode, ins.trend_cph)
    b_forecast = forecast_bias(cfg, ins.hvac_mode, ins.t_ext, ins.forecast_temp)
    mods = b_ext + b_vmc + b_trend + b_brake + b_forecast + ins.extra_bias
    self_bias = sdhb_self_bias(cfg, ins.sdhb_intent, ins.hvac_mode)
    target = assemble_target(cfg, ins.hvac_mode, base, mods, self_bias,
                             ins.vacation)
    target_raw = round(base + mods + self_bias, 2)
    details = {
        "base": round(base, 2),
        "base_source": base_source,
        "target_raw": target_raw,
        "mods_total": round(mods, 2),
        "lead_h": round(lead, 2),
        "lead_source": lead_source,
        "night": night,
        "bias_exterior": round(b_ext, 2),
        "bias_vmc": round(b_vmc, 2),
        "bias_trend": round(b_trend, 2),
        "bias_brake": round(b_brake, 2),
        "bias_forecast": round(b_forecast, 2),
        "bias_facade": round(ins.extra_bias, 2),
        "sdhb_bias": round(self_bias, 2),
    }
    return DcDecision(ins.hvac_mode, target, ins.hvac_mode,
                      publish_intent(ins.hvac_mode), details=details)
