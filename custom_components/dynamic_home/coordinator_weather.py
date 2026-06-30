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
from .weather_engine import WxConfig, derive_alert, is_fresh

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = ("unknown", "unavailable", "none", "")


# Per-field resolution table: (field key, weather-entity attribute, raw-sensor
# conf). Each field is resolved by per-field failover — the first *fresh* source
# that actually has it wins — then the optional raw sensor. ``None`` means that
# path doesn't apply. This is what squeezes every drop out of rich providers
# (Google Weather, AEMET…): humidity from one, gusts/UV/cloud from another.
WX_FIELDS: tuple[tuple[str, str | None, str | None], ...] = (
    ("temperature", "temperature", const.CONF_WX_TEMP),
    ("humidity", "humidity", const.CONF_WX_HUMIDITY),
    ("pressure", "pressure", const.CONF_WX_PRESSURE),
    ("wind", "wind_speed", const.CONF_WX_WIND),
    ("wind_bearing", "wind_bearing", None),
    ("gust", "wind_gust_speed", const.CONF_WX_GUST),
    ("uv", "uv_index", const.CONF_WX_UV),
    ("cloud", "cloud_coverage", const.CONF_WX_CLOUD),
    ("dewpoint", "dew_point", const.CONF_WX_DEWPOINT),
    ("precip", None, const.CONF_WX_PRECIP),
    ("storm_prob", None, const.CONF_WX_STORM_PROB),
    ("precip_prob", None, const.CONF_WX_PRECIP_PROB),
)


@dataclass
class WxData:
    active_label: str          # "none" | the active source's entity_id | "sensors"
    active_entity: str | None  # active weather.* entity (forecast source), else None
    alert: bool
    condition: str | None
    values: dict               # field key -> float | None
    sources: dict              # field key -> provider label that supplied it | None

    # Back-compat accessors used across the codebase / the weather entity.
    @property
    def temperature(self) -> float | None:
        return self.values.get("temperature")

    @property
    def humidity(self) -> float | None:
        return self.values.get("humidity")

    @property
    def pressure(self) -> float | None:
        return self.values.get("pressure")

    @property
    def wind_kmh(self) -> float | None:
        return self.values.get("wind")

    @property
    def wind_bearing(self) -> float | None:
        return self.values.get("wind_bearing")

    @property
    def precip(self) -> float | None:
        return self.values.get("precip")


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

    def has_precip(self) -> bool:
        return bool(self._hw(const.CONF_WX_PRECIP))

    def _source_ok(self, entity_id: str, now_ts: float, cfg: WxConfig) -> bool:
        st = self.hass.states.get(entity_id)
        if st is None or st.state in _UNAVAILABLE:
            return False
        age = now_ts - st.last_updated.timestamp()
        return is_fresh(age, cfg)

    def _resolve_field(self, attr: str | None, raw: str | None,
                       fresh: list) -> tuple[float | None, str | None]:
        """Per-field failover: first fresh source with the attribute, then raw."""
        if attr:
            for ent, st in fresh:
                v = _f(st.attributes.get(attr))
                if v is not None:
                    return v, ent
        if raw:
            v = self._num(raw)
            if v is not None:
                return v, "sensors"
        return None, None

    async def _async_update_data(self) -> WxData:
        cfg = self._cfg()
        now_ts = dt_util.utcnow().timestamp()
        sources = self._weather_sources()

        # Fresh weather sources in priority order (each may fill different fields).
        fresh = []
        for e in sources:
            if self._source_ok(e, now_ts, cfg):
                st = self.hass.states.get(e)
                if st is not None:
                    fresh.append((e, st))

        active_entity = fresh[0][0] if fresh else None
        condition = fresh[0][1].state if fresh else None

        values: dict = {}
        field_sources: dict = {}
        for key, attr, raw in WX_FIELDS:
            val, src = self._resolve_field(attr, raw, fresh)
            values[key] = val
            field_sources[key] = src

        if active_entity is not None:
            label = active_entity
        elif values.get("temperature") is not None:
            label = "sensors"                       # all weather down, raw serves
        else:
            label = "none"

        self.alert_active = derive_alert(
            condition, values.get("wind"), values.get("precip"), cfg)

        if label != self.active_label:
            self.active_since = now_ts
            self.hass.bus.async_fire(const.EVENT_WEATHER_SOURCE, {
                "entry_id": self.entry.entry_id, "name": self.entry.title,
                "module": const.MODULE_WEATHER, "source": label})
        self.active_label = label
        self.active_entity = active_entity

        # Publish so DC (forecast bias) and DS (alert) auto-consume it when set,
        # without wiring each module by hand. Per-module config still overrides.
        self.hass.data.setdefault(const.DOMAIN, {})[const.DATA_WEATHER] = {
            "source": active_entity,        # current best weather.* (for forecasts)
            "alert": self.alert_active,
            "values": dict(values),         # full per-field view (gust/storm/…)
        }

        return WxData(
            active_label=label, active_entity=active_entity,
            alert=self.alert_active, condition=condition,
            values=values, sources=field_sources)


def _f(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
