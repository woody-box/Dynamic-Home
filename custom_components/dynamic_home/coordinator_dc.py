"""DC coordinator: evaluates the climate (DC) pipeline and publishes to the bus.

DC is the brain: while heating it publishes ``request_solar_gain`` and while
cooling ``request_solar_shield`` to its shutter target, so DS reacts. It also
consumes intents aimed at itself (self-bias) from the same shared hub.
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const, events
from .bus import SdhbHub
from .dc_engine import (
    DcConfig,
    DcDecision,
    DcInputs,
    adaptive_lead_target,
    dew_point,
    dew_risk,
    ema,
    facade_bias,
    on_rate_cph,
    step_toward,
    sunlit_facades,
)
from .dc_engine import (
    decide as decide_climate,
)
from .options_spec import apply_options

_LOGGER = logging.getLogger(__name__)


class DcCoordinator(DataUpdateCoordinator):
    """Evaluates the DC (climate) pipeline and PUBLISHES intents to the bus.

    DC is the brain: while heating it publishes ``request_solar_gain`` and while
    cooling ``request_solar_shield`` to its shutter target, so DS reacts. It also
    consumes intents aimed at itself (self-bias) from the same shared hub.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 hub: SdhbHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_dc",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S),
        )
        self.entry = entry
        self.hub = hub
        self.hvac_mode = "off"          # desired mode, set from the climate entity
        self.override_active = False
        self.override_temp: float | None = None
        self.vacation_enabled = False
        self.observe_enabled = False    # dry-run: compute but do not act on hw
        self.apply_min_delta = 0.0      # anti-jitter gate read by the climate entity
        self._source = f"dc_{entry.entry_id}"
        self._active_sources: set[str] = set()  # bus slots this DC currently owns
        # Bus-conflict observability (the intent THIS zone consumes as self-bias).
        self.bus_explain: dict = self.hub.explain(self.bus_listen_targets())
        self._prev_winner: str | None = None
        self.dew_point_c: float | None = None   # observability
        self.dew_risk_active = False
        # Trend (indoor temp derivative) state.
        self._prev_tint: float | None = None
        self._prev_ts: float | None = None
        self._cph: float = 0.0
        # Adaptive lead (learned). Opt-in via the "Adaptive Lead" switch.
        self.adaptive_enabled = False
        self.degraded = False
        self.learn_rate_ema = 0.0        # learned heating/cooling rate (°C/h)
        self.learn_overshoot_ema = 0.0   # learned overshoot beyond setpoint (°C)
        self.learned_lag_h = 0.0         # learned thermal lag OFF->peak (h)
        self.lead_gain_adaptive = 0.0    # learned anticipation horizon (h)
        self.adapt_ok_count = 0
        self.adapt_abort_count = 0
        # Cycle state machine (ON capture -> OFF settling -> peak).
        self._valve_open = False
        self._on_t0: float | None = None
        self._on_t0_ts: float | None = None
        self._settling = False
        self._off_sp: float | None = None
        self._off_peak: float | None = None
        self._off_peak_ts: float | None = None
        self._off_ts: float | None = None
        self._off_hvac: str | None = None

    # --- adaptive lead learning (port of "Adaptive Lead v2.6.1") ---
    def _valve_demand(self, hvac: str, t_int: float | None,
                      target: float | None) -> bool:
        """Whether the zone is actively calling for heat/cool (our 'valve open')."""
        if hvac not in ("heat", "cool") or t_int is None or target is None:
            return False
        return t_int < target if hvac == "heat" else t_int > target

    def _finalize_cycle(self, cfg: DcConfig) -> None:
        """Settling window elapsed: learn overshoot, lag and step the lead gain."""
        if self._off_peak is None or self._off_sp is None or self._off_ts is None:
            return
        overshoot = self._off_peak - self._off_sp
        self.learn_overshoot_ema = ema(self.learn_overshoot_ema, overshoot,
                                       cfg.adapt_alpha)
        lag_h = (max(0.0, (self._off_peak_ts - self._off_ts) / 3600.0)
                 if self._off_peak_ts else 0.0)
        self.learned_lag_h = ema(self.learned_lag_h, lag_h, cfg.adapt_alpha)
        target_lead = adaptive_lead_target(cfg, self.learn_overshoot_ema,
                                           self.learned_lag_h, self.learn_rate_ema)
        self.lead_gain_adaptive = step_toward(self.lead_gain_adaptive, target_lead,
                                              cfg.adapt_gain_lr)
        self.adapt_ok_count += 1

    def _learn_step(self, cfg: DcConfig, now_ts: float, hvac: str,
                    t_int: float | None, target: float | None,
                    window_open: bool, override: bool) -> None:
        """Drive the ON/OFF cycle state machine for one coordinator tick."""
        valve = self._valve_demand(hvac, t_int, target)
        rising = valve and not self._valve_open
        falling = (not valve) and self._valve_open

        # Settling window in progress (between valve OFF and the temperature peak).
        if self._settling:
            if rising or hvac != self._off_hvac or window_open or override:
                self.adapt_abort_count += 1   # cycle disturbed -> no learning
                self._settling = False
            else:
                if t_int is not None and self._off_peak is not None:
                    peak = (max(self._off_peak, t_int) if self._off_hvac == "heat"
                            else min(self._off_peak, t_int))
                    if peak != self._off_peak:
                        self._off_peak, self._off_peak_ts = peak, now_ts
                if now_ts - self._off_ts >= cfg.adapt_off_window_h * 3600:
                    self._finalize_cycle(cfg)
                    self._settling = False

        # Edges: capture ON baseline / learn the ON-rate and open a settling window.
        if rising:
            self._on_t0, self._on_t0_ts = t_int, now_ts
        elif falling and hvac in ("heat", "cool"):
            if self._on_t0_ts is not None:
                dt_h = (now_ts - self._on_t0_ts) / 3600.0
                rate = on_rate_cph(self._on_t0, t_int, dt_h, cfg)
                if rate is not None:
                    self.learn_rate_ema = ema(self.learn_rate_ema, rate,
                                              cfg.adapt_alpha)
            self._settling = True
            self._off_sp, self._off_peak = target, t_int
            self._off_peak_ts = self._off_ts = now_ts
            self._off_hvac = hvac

        self._valve_open = valve

    def reset_learning(self) -> None:
        """Wipe all learned adaptive-lead state and the cycle state machine.

        Backs the ``reset_learning`` service: lets a user discard a poisoned
        model (e.g. after swapping a heat pump) without deleting the config
        entry. Also clears the in-flight ON/OFF cycle so a mid-cycle reset does
        not leave a stale settling window that would corrupt the next sample.
        """
        self.learn_rate_ema = 0.0
        self.learn_overshoot_ema = 0.0
        self.learned_lag_h = 0.0
        self.lead_gain_adaptive = 0.0
        self.adapt_ok_count = 0
        self.adapt_abort_count = 0
        self._valve_open = False
        self._on_t0 = None
        self._on_t0_ts = None
        self._settling = False
        self._off_sp = None
        self._off_peak = None
        self._off_peak_ts = None
        self._off_ts = None
        self._off_hvac = None

    def bus_listen_targets(self):
        """Targets this zone consumes from the bus (self-bias intents)."""
        return "dc"

    def _refresh_bus_explain(self, now_ts: float | None) -> None:
        """Recompute the consumed bus intent and fire a conflict event on change."""
        self.bus_explain = self.hub.explain(self.bus_listen_targets(), now_ts)
        winner = self.bus_explain["winner"]
        if winner != self._prev_winner:
            if not (self._prev_winner is None and winner == "none"):
                events.fire_conflict(self.hass, self.entry,
                                     const.MODULE_CLIMATE, self.bus_explain)
            self._prev_winner = winner

    def clear_published(self) -> None:
        """Remove all bus slots owned by this zone (called on unload/reload)."""
        for src in self._active_sources:
            self.hub.clear(src)
        self._active_sources = set()

    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

    def _num(self, key: str) -> float | None:
        ent = self._hw(key)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    def _is_on(self, key: str) -> bool:
        ent = self._hw(key)
        return bool(ent) and self.hass.states.is_state(ent, "on")

    def indoor_temperature(self) -> float | None:
        """Current indoor temperature of the zone (for the climate entity)."""
        return self._num(const.CONF_DC_T_INT)

    def _cfg(self) -> DcConfig:
        """Build the DC config, overlaying any UI-tunable options."""
        cfg = DcConfig()
        apply_options(cfg, self.entry.options, const.MODULE_CLIMATE)
        return cfg

    def _sun(self) -> tuple[float | None, float | None]:
        st = self.hass.states.get("sun.sun")
        if st is None:
            return None, None
        return st.attributes.get("azimuth"), st.attributes.get("elevation")

    def _registered_facades(self) -> tuple[dict, dict]:
        """({facade_key: azimuth}, {facade_key: span}) of all shutters."""
        reg = self.hass.data.get(const.DOMAIN, {}).get("_facades", {})
        facades = {v["key"]: v["az"] for v in reg.values()}
        spans = {v["key"]: v.get("span", 180.0) for v in reg.values()}
        return facades, spans

    def _publish(self, desired: dict, now_ts: float | None = None) -> None:
        """Reconcile the bus slots this DC owns with ``desired`` (key->(intent,target))."""
        for stale in self._active_sources - set(desired):
            self.hub.clear(stale)
        for src, (intent, target) in desired.items():
            # TTL so a stale zone's intent expires on its own (matches the YAML).
            self.hub.publish(source=src, intent=intent, target=target,
                             priority=70, ttl_s=1800, now_ts=now_ts)
        self._active_sources = set(desired)

    def _vmc_speed(self) -> int | None:
        """VMC speed 1/2/3 from the configured entity (fan percentage or sensor)."""
        ent = self._hw(const.CONF_DC_VMC)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in ("unknown", "unavailable", "none", ""):
            return None
        if ent.startswith("fan."):
            if st.state != "on":
                return None
            pct = st.attributes.get("percentage")
            if not pct:
                return None
            return min(3, max(1, math.ceil(pct / (100 / 3))))
        try:
            v = int(float(st.state))
            return v if v in (1, 2, 3) else None
        except (TypeError, ValueError):
            return None

    def _update_trend(self, cfg: DcConfig, t_int: float | None,
                      now_ts: float) -> float:
        """EMA-smoothed indoor-temp derivative (°C/h), with a deadband."""
        if t_int is None:
            self._prev_tint, self._prev_ts = None, None
            return self._cph
        if self._prev_tint is not None and self._prev_ts is not None:
            dt_h = (now_ts - self._prev_ts) / 3600.0
            if dt_h > 0:
                raw = (t_int - self._prev_tint) / dt_h
                a = cfg.trend_ema_alpha
                self._cph = a * raw + (1 - a) * self._cph
        self._prev_tint, self._prev_ts = t_int, now_ts
        return 0.0 if abs(self._cph) < cfg.trend_deadband_cph else self._cph

    async def _forecast_temp(self, cfg: DcConfig, hvac: str) -> float | None:
        """Extreme forecast temp in the look-ahead window (max heat / min cool)."""
        ent = self._hw(const.CONF_DC_WEATHER)
        if not ent or hvac not in ("heat", "cool"):
            return None
        try:
            resp = await self.hass.services.async_call(
                "weather", "get_forecasts",
                {"entity_id": ent, "type": "hourly"},
                blocking=True, return_response=True)
        except Exception:  # noqa: BLE001 — weather entity may not support it
            return None
        forecasts = (resp or {}).get(ent, {}).get("forecast", [])
        end = dt_util.utcnow() + timedelta(hours=cfg.forecast_window_h)
        temps = []
        for f in forecasts:
            ts = dt_util.parse_datetime(f.get("datetime", "")) if f.get("datetime") else None
            t = f.get("temperature")
            if ts is not None and t is not None and ts <= end:
                temps.append(float(t))
        if not temps:
            return None
        return max(temps) if hvac == "heat" else min(temps)

    def _facade_openness(self, lit: set) -> float:
        """Mean 0..1 shutter opening of the sunlit facades (0 if none)."""
        reg = self.hass.data.get(const.DOMAIN, {}).get("_facades", {})
        vals = []
        for eid, fac in reg.items():
            if fac["key"] in lit:
                ds = self.hass.data[const.DOMAIN].get(eid)
                if ds is not None and ds.data is not None:
                    vals.append(ds.data.pos / 100.0)
        return sum(vals) / len(vals) if vals else 0.0

    async def _async_update_data(self) -> DcDecision:
        cfg = self._cfg()
        self.apply_min_delta = cfg.apply_min_delta
        sun_az, sun_el = self._sun()
        t_int = self._num(const.CONF_DC_T_INT)
        rh = self._num(const.CONF_DC_HUMIDITY)
        now_ts = dt_util.utcnow().timestamp()
        self._refresh_bus_explain(now_ts)

        self.dew_point_c = dew_point(t_int, rh)
        self.dew_risk_active = dew_risk(cfg, self.hvac_mode, t_int, rh)

        # Degraded when a core source is missing while a mode is demanded; this
        # pauses learning so stale readings don't poison the EMAs.
        self.degraded = self.hvac_mode in ("heat", "cool") and t_int is None

        facades, spans = self._registered_facades()
        lit = sunlit_facades(sun_az, sun_el, facades, spans)
        facade_b = facade_bias(cfg, self.hvac_mode, self._facade_openness(lit))

        # Feed the learned lead only once the loop is enabled, healthy and has
        # completed at least one cycle; otherwise the engine uses its physical model.
        adaptive_lead = (self.lead_gain_adaptive
                         if (self.adaptive_enabled and self.adapt_ok_count > 0
                             and not self.degraded)
                         else None)

        ins = DcInputs(
            hvac_mode=self.hvac_mode,
            t_int=t_int,
            t_ext=self._num(const.CONF_DC_T_EXT),
            sun_elevation=sun_el,
            sdhb_intent=self.bus_explain["winner"],
            override_active=self.override_active,
            override_temp=self.override_temp,
            vmc_speed=self._vmc_speed(),
            trend_cph=self._update_trend(cfg, t_int, now_ts),
            forecast_temp=await self._forecast_temp(cfg, self.hvac_mode),
            wind=self._num(const.CONF_DC_WIND),
            vacation=self.vacation_enabled,
            window_lockout=self._is_on(const.CONF_DC_WINDOW),
            dew_risk=self.dew_risk_active,
            extra_bias=facade_b,
            adaptive_lead_h=adaptive_lead,
        )
        decision = decide_climate(cfg, ins)

        # Learn from real cycles (paused while disabled or degraded).
        if self.adaptive_enabled and not self.degraded:
            self._learn_step(cfg, now_ts, self.hvac_mode, t_int, decision.target,
                             self._is_on(const.CONF_DC_WINDOW), self.override_active)
        else:
            self._valve_open = self._valve_demand(self.hvac_mode, t_int,
                                                  decision.target)
            self._settling = False

        intent = decision.published_intent
        if intent == "none":
            desired = {}
        elif lit:
            # Dynamic: target only the sunlit facades.
            desired = {f"{self._source}__{fk}": (intent, fk) for fk in lit}
        elif facades and sun_el is not None:
            # Facades known but none sunlit -> publish nothing.
            desired = {}
        else:
            # Fallback: broadcast to the configured target.
            target = self.entry.data.get(const.CONF_DC_TARGET) or "ds"
            desired = {self._source: (intent, target)}
        self._publish(desired, now_ts)
        return decision
