"""Weather coordinator (F33): resilient multi-source forecast/alert provider.

Picks the first healthy source from a prioritised list (other ``weather.*``
entities, then a raw-sensor fallback) and derives a generic alert. Read-only: it
never actuates anything; it just exposes a normalised view that DC (forecast
bias), DS (F17 alert) and free-cooling can consume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .options_spec import apply_options
from .weather_engine import WxConfig, derive_alert, is_fresh, pick_source

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = ("unknown", "unavailable", "none", "")


@dataclass
class WxData:
    active_label: str          # "none" | the active source's entity_id | "sensors"
    active_entity: str | None  # active weather.* entity (forecast source), else None
    alert: bool
    condition: str | None
    temperature: float | None
    humidity: float | None
    pressure: float | None
    wind_kmh: float | None


class WxCoordinator(DataUpdateCoordinator):
    """Evaluates the prioritised weather sources and exposes the active one."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{const.DOMAIN}_wx",
            update_interval=timedelta(seconds=const.UPDATE_INTERVAL_S))
        self.entry = entry
        self.active_label = "none"
        self.active_entity: str | None = None
        self.active_since: float | None = None
        self.alert_active = False

    def _cfg(self) -> WxConfig:
        cfg = WxConfig()
        apply_options(cfg, self.entry.options, const.MODULE_WEATHER)
        return cfg

    def _hw(self, key: str) -> str | None:
        return self.entry.data.get(key)

    def _num(self, key: str) -> float | None:
        ent = self._hw(key)
        if not ent:
            return None
        st = self.hass.states.get(ent)
        if st is None or st.state in _UNAVAILABLE:
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    def _weather_sources(self) -> list[str]:
        keys = (const.CONF_WX_SOURCE_1, const.CONF_WX_SOURCE_2,
                const.CONF_WX_SOURCE_3)
        return [e for e in (self._hw(k) for k in keys) if e]

    def has_raw(self) -> bool:
        return bool(self._hw(const.CONF_WX_TEMP))

    def _source_ok(self, entity_id: str, now_ts: float, cfg: WxConfig) -> bool:
        st = self.hass.states.get(entity_id)
        if st is None or st.state in _UNAVAILABLE:
            return False
        age = now_ts - st.last_updated.timestamp()
        return is_fresh(age, cfg)

    async def _async_update_data(self) -> WxData:
        cfg = self._cfg()
        now_ts = dt_util.utcnow().timestamp()
        sources = self._weather_sources()

        avail = [self._source_ok(e, now_ts, cfg) for e in sources]
        if self.has_raw():
            avail.append(self._num(const.CONF_WX_TEMP) is not None)
        idx = pick_source(avail)

        label, active_entity = "none", None
        condition = temperature = humidity = pressure = wind = None
        if idx is not None and idx < len(sources):
            active_entity = sources[idx]
            label = active_entity
            st = self.hass.states.get(active_entity)
            condition = st.state if st else None
            a = st.attributes if st else {}
            temperature = a.get("temperature")
            humidity = a.get("humidity")
            pressure = a.get("pressure")
            wind = a.get("wind_speed")
        elif idx is not None:                       # raw-sensor fallback
            label = "sensors"
            temperature = self._num(const.CONF_WX_TEMP)
            wind = self._num(const.CONF_WX_WIND)

        precip = self._num(const.CONF_WX_PRECIP)
        self.alert_active = derive_alert(condition, wind, precip, cfg)

        if label != self.active_label:
            self.active_since = now_ts
            self.hass.bus.async_fire(const.EVENT_WEATHER_SOURCE, {
                "entry_id": self.entry.entry_id, "name": self.entry.title,
                "module": const.MODULE_WEATHER, "source": label})
        self.active_label = label
        self.active_entity = active_entity

        return WxData(
            active_label=label, active_entity=active_entity,
            alert=self.alert_active, condition=condition,
            temperature=_f(temperature), humidity=_f(humidity),
            pressure=_f(pressure), wind_kmh=_f(wind))


def _f(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
