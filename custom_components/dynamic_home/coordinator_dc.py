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

from . import const
from .bus import SdhbHub
from .dc_engine import (
    DcConfig,
    DcDecision,
    DcInputs,
    dew_point,
    dew_risk,
    facade_bias,
    sunlit_facades,
)
from .dc_engine import (
    decide as decide_climate,
)

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
        self._source = f"dc_{entry.entry_id}"
        self._active_sources: set[str] = set()  # bus slots this DC currently owns
        self.dew_point_c: float | None = None   # observability
        self.dew_risk_active = False
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

    def _is_on(self, key: str) -> bool:
        ent = self._hw(key)
        return bool(ent) and self.hass.states.is_state(ent, "on")

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

        self.dew_point_c = dew_point(t_int, rh)
        self.dew_risk_active = dew_risk(cfg, self.hvac_mode, t_int, rh)

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
            forecast_temp=await self._forecast_temp(cfg, self.hvac_mode),
            wind=self._num(const.CONF_DC_WIND),
            vacation=self.vacation_enabled,
            window_lockout=self._is_on(const.CONF_DC_WINDOW),
            dew_risk=self.dew_risk_active,
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
