"""Coordinator: bridges Home Assistant state into the pure DV engine.

It reads the configured hardware entities, builds :class:`engine.DvInputs`,
runs :func:`engine.decide`, and exposes the resulting logical speed. The fan
entity drives the physical relays from this result.

A minimal in-memory SDHB hub lives here too (see :class:`SdhbHub`): in the full
suite this is the shared coordination bus across DC/DV/DS. For the PoC it simply
holds the winning intent for the ``dv`` target.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .bus import SdhbHub
from .engine import DvConfig, DvState, DvInputs, DvDecision, decide
from .ds_engine import DsConfig, DsState, DsInputs, DsDecision, decide_cover
from .dc_engine import (
    DcConfig, DcInputs, DcDecision, decide as decide_climate, sunlit_facades,
    dew_risk, facade_bias,
)

_LOGGER = logging.getLogger(__name__)


class DvCoordinator(DataUpdateCoordinator[DvDecision]):
    """Periodically evaluates the DV pipeline and tracks source-entity changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 hub: SdhbHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_dv",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S),
        )
        self.entry = entry
        self.hub = hub
        self.state_data = DvState()
        self.current_speed = 1
        self.auto_mode = True
        self._iaq_dirty = False
        self._setup_ts = dt_util.utcnow().timestamp()
        # Telemetry (hours), accumulated between updates; persisted by sensors.
        self.speed_hours = {1: 0.0, 2: 0.0, 3: 0.0}
        self.machine_hours = 0.0
        self.filter_hours = 0.0
        self._accum_ts: float | None = None
        # Adaptive thresholds: rolling history (~7 days @ 1 sample/min).
        self.adaptive_enabled = False
        self._co2_hist: deque[float] = deque(maxlen=10080)
        self._pm_hist: deque[float] = deque(maxlen=10080)

    def _accumulate(self, now_ts: float) -> None:
        """Add elapsed time to the running-hours counters."""
        if self._accum_ts is not None:
            dt_h = (now_ts - self._accum_ts) / 3600.0
            spd = self.current_speed
            if spd in (1, 2, 3) and dt_h > 0:
                self.speed_hours[spd] += dt_h
                self.machine_hours += dt_h
                self.filter_hours += dt_h
        self._accum_ts = now_ts

    def reset_filter_hours(self) -> None:
        self.filter_hours = 0.0

    # --- config helpers ---
    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

    def _cfg(self) -> DvConfig:
        o = self.entry.options
        cfg = DvConfig()
        cfg.co2_v2 = o.get(const.OPT_CO2_V2, cfg.co2_v2)
        cfg.co2_v3 = o.get(const.OPT_CO2_V3, cfg.co2_v3)
        cfg.pm_v2 = o.get(const.OPT_PM_V2, cfg.pm_v2)
        cfg.pm_v3 = o.get(const.OPT_PM_V3, cfg.pm_v3)
        cfg.freecool_enabled = bool(self._hw(const.CONF_T_IN) and
                                    self._hw(const.CONF_T_EXT))
        cfg.hostile_enabled = bool(self._hw(const.CONF_AQI))
        cfg.shower_enabled = bool(self._hw(const.CONF_HUM_BATH) and
                                  self._hw(const.CONF_HUM_EXT))
        cfg.adaptive_enabled = self.adaptive_enabled
        return cfg

    def _update_adaptive(self, cfg: DvConfig, co2: float | None,
                         pm: float | None) -> tuple:
        """Append readings and derive adaptive thresholds from percentiles.

        Returns (co2_v2, co2_v3, pm_v2, pm_v3), each None until enough samples.
        """
        if co2 is not None and 0 <= co2 <= 5000:
            self._co2_hist.append(co2)
        if pm is not None and 0 <= pm <= 500:
            self._pm_hist.append(pm)
        if not self.adaptive_enabled:
            return (None, None, None, None)

        def pct(hist: deque, p: float) -> float | None:
            if len(hist) < cfg.adaptive_min_samples:
                return None
            s = sorted(hist)
            return s[min(len(s) - 1, int(p / 100.0 * len(s)))]

        return (pct(self._co2_hist, 90), pct(self._co2_hist, 95),
                pct(self._pm_hist, 90), pct(self._pm_hist, 95))

    def _age_s(self, key: str) -> float:
        """Seconds since the source entity last changed (large if missing)."""
        ent = self._hw(key)
        if not ent:
            return 1e9
        st = self.hass.states.get(ent)
        if st is None:
            return 1e9
        return (dt_util.utcnow() - st.last_updated).total_seconds()

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

    # --- entity tracking ---
    @callback
    def async_setup_listeners(self) -> None:
        sources = [self._hw(k) for k in (const.CONF_CO2, const.CONF_PM25)]
        sources = [s for s in sources if s]
        if sources:
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, sources, self._on_iaq_change)
            )

    @callback
    def _on_iaq_change(self, event) -> None:
        self._iaq_dirty = True
        self.hass.async_create_task(self.async_request_refresh())

    # --- the actual update ---
    def _rh_delta(self) -> float | None:
        bath = self._num(const.CONF_HUM_BATH)
        ext = self._num(const.CONF_HUM_EXT)
        if bath is None or ext is None:
            return None
        return bath - ext

    async def _async_update_data(self) -> DvDecision:
        cfg = self._cfg()
        trigger_is_iaq = self._iaq_dirty
        self._iaq_dirty = False

        now = dt_util.now()  # local time for the weekly schedule
        now_ts = now.timestamp()
        self._accumulate(now_ts)
        grace_active = (now_ts - self._setup_ts) < cfg.startup_grace_s

        co2_raw = self._num(const.CONF_CO2)
        pm_raw = self._num(const.CONF_PM25)
        a_co2_v2, a_co2_v3, a_pm_v2, a_pm_v3 = self._update_adaptive(
            cfg, co2_raw, pm_raw)

        ins = DvInputs(
            co2_raw=co2_raw,
            pm_raw=pm_raw,
            adaptive_co2_v2=a_co2_v2,
            adaptive_co2_v3=a_co2_v3,
            adaptive_pm_v2=a_pm_v2,
            adaptive_pm_v3=a_pm_v3,
            t_in=self._num(const.CONF_T_IN),
            t_ext=self._num(const.CONF_T_EXT),
            aqi=self._num(const.CONF_AQI),
            current_speed=self.current_speed,
            permitida=None,  # computed by the engine (schedule + failsafe gate)
            auto_mode=self.auto_mode,
            sdhb_intent=self.hub.winner("dv", now_ts),
            trigger_is_iaq=trigger_is_iaq,
            now_ts=now_ts,
            weekday=now.weekday(),
            minute_of_day=now.hour * 60 + now.minute,
            co2_age_s=self._age_s(const.CONF_CO2),
            pm_age_s=self._age_s(const.CONF_PM25),
            startup_grace_active=grace_active,
            rh_delta=self._rh_delta(),
        )
        return decide(cfg, self.state_data, ins)


class DsCoordinator(DataUpdateCoordinator):
    """Evaluates the DS (shutter) cascade and tracks the source entities.

    Shares the same :class:`SdhbHub` as the VMC coordinators: when another
    module (e.g. DC) publishes ``request_solar_shield`` to the bus, this
    coordinator consumes it and clamps the cover.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 hub: SdhbHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_ds",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S),
        )
        self.entry = entry
        self.hub = hub
        self.ds_state = DsState()
        # UI-controlled state (set by the shutter's switch/number entities).
        self.privacy_enabled = False
        self.privacy_pct = 40
        self.lock_enabled = False
        self.lock_pct = 50

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

    def _cfg(self) -> DsConfig:
        cfg = DsConfig()
        az = self.entry.data.get(const.CONF_FACADE_AZIMUTH)
        if az is not None:
            cfg.facade_azimuth_deg = float(az)
        cfg.facade_span_deg = self.facade_span
        return cfg

    @property
    def facade_key(self) -> str:
        """Bus target for this shutter's facade, e.g. ``ds_f180`` (3-digit azimuth)."""
        az = int(round(self.entry.data.get(const.CONF_FACADE_AZIMUTH, 0))) % 360
        return f"ds_f{az:03d}"

    @property
    def facade_span(self) -> float:
        """Acceptance angle of this facade (degrees)."""
        return float(self.entry.data.get(const.CONF_FACADE_SPAN, 180.0))

    def _listen_targets(self) -> set[str]:
        """Targets this shutter consumes: broadcast ``ds`` plus its facade."""
        return {"ds", self.facade_key}

    def _hvac_mode(self) -> str:
        ent = self._hw(const.CONF_CLIMATE)
        if not ent:
            return "off"
        st = self.hass.states.get(ent)
        return st.state if st else "off"

    def _current_pos(self) -> int | None:
        ent = self._hw(const.CONF_COVER)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None:
            return None
        pos = st.attributes.get("current_position")
        return int(pos) if pos is not None else None

    def _sun(self) -> tuple[float | None, float | None, bool]:
        st = self.hass.states.get("sun.sun")
        if st is None:
            return None, None, False
        az = st.attributes.get("azimuth")
        el = st.attributes.get("elevation")
        above = st.state == "above_horizon"
        return az, el, above

    async def _async_update_data(self) -> DsDecision:
        cfg = self._cfg()
        cfg.privacy_pos_pct = int(self.privacy_pct)
        now_ts = dt_util.utcnow().timestamp()
        winner = self.hub.winner(self._listen_targets(), now_ts)
        sun_az, sun_el, sun_above = self._sun()

        ins = DsInputs(
            hvac_mode=self._hvac_mode(),
            t_in=self._num(const.CONF_DS_T_IN),
            t_out=self._num(const.CONF_DS_T_OUT),
            weather_protect_enabled=bool(self._hw(const.CONF_WIND) or
                                         self._hw(const.CONF_RAIN)),
            raining=self._is_on(const.CONF_RAIN),
            wind=self._num(const.CONF_WIND),
            current_pos=self._current_pos(),
            privacy_active=self.privacy_enabled,
            override_mode="lock" if self.lock_enabled else "none",
            override_pos=int(self.lock_pct),
            sdhb_allow_override=winner not in ("none", "unknown", ""),
            sdhb_request_solar_shield=winner == "request_solar_shield",
            sdhb_request_quiet=winner == "request_quiet",
            sun_azimuth=sun_az,
            sun_elevation=sun_el,
            sun_effective=sun_above,
        )
        return decide_cover(cfg, self.ds_state, ins)


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
        self._source = f"dc_{entry.entry_id}"
        self._active_sources: set[str] = set()  # bus slots this DC currently owns
        # Trend (indoor temp derivative) state.
        self._prev_tint: float | None = None
        self._prev_ts: float | None = None
        self._cph: float = 0.0

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

    def indoor_temperature(self) -> float | None:
        """Current indoor temperature of the zone (for the climate entity)."""
        return self._num(const.CONF_DC_T_INT)

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
        cfg = DcConfig()
        sun_az, sun_el = self._sun()
        t_int = self._num(const.CONF_DC_T_INT)
        rh = self._num(const.CONF_DC_HUMIDITY)
        now_ts = dt_util.utcnow().timestamp()

        facades, spans = self._registered_facades()
        lit = sunlit_facades(sun_az, sun_el, facades, spans)
        facade_b = facade_bias(cfg, self.hvac_mode, self._facade_openness(lit))

        ins = DcInputs(
            hvac_mode=self.hvac_mode,
            t_int=t_int,
            t_ext=self._num(const.CONF_DC_T_EXT),
            sun_elevation=sun_el,
            sdhb_intent=self.hub.winner("dc", now_ts),
            override_active=self.override_active,
            override_temp=self.override_temp,
            vmc_speed=self._vmc_speed(),
            trend_cph=self._update_trend(cfg, t_int, now_ts),
            dew_risk=dew_risk(cfg, self.hvac_mode, t_int, rh),
            forecast_temp=await self._forecast_temp(cfg, self.hvac_mode),
            wind=self._num(const.CONF_DC_WIND),
            extra_bias=facade_b,
        )
        decision = decide_climate(cfg, ins)

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
