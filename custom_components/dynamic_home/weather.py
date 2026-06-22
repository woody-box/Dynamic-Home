"""Weather platform — the Dynamic Weather proxy (F33).

A resilient ``weather.*`` entity that mirrors the currently-active source and
forwards forecast requests to it. Consumers (DC forecast bias, free-cooling)
point at this single entity and keep working when a source falls back.
"""

from __future__ import annotations

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator_weather import WxCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(const.CONF_MODULE) != const.MODULE_WEATHER:
        return
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([ProxyWeather(coordinator, entry)])


class ProxyWeather(CoordinatorEntity[WxCoordinator], WeatherEntity):
    """Mirrors the active source and forwards its forecast (with fallback)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = (WeatherEntityFeature.FORECAST_HOURLY
                                | WeatherEntityFeature.FORECAST_DAILY)

    def __init__(self, coordinator: WxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title, manufacturer="Dynamic Home",
            model="Dynamic Weather")

    @property
    def available(self) -> bool:
        d = self.coordinator.data
        return bool(super().available and d and d.active_label != "none")

    @property
    def condition(self) -> str | None:
        d = self.coordinator.data
        return d.condition if d else None

    @property
    def native_temperature(self) -> float | None:
        d = self.coordinator.data
        return d.temperature if d else None

    @property
    def humidity(self) -> float | None:
        d = self.coordinator.data
        return d.humidity if d else None

    @property
    def native_pressure(self) -> float | None:
        d = self.coordinator.data
        return d.pressure if d else None

    @property
    def native_wind_speed(self) -> float | None:
        d = self.coordinator.data
        return d.wind_kmh if d else None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"active_source": d.active_label if d else "none"}

    async def _forward(self, kind: str):
        ent = self.coordinator.active_entity
        if not ent:
            return None
        try:
            resp = await self.hass.services.async_call(
                "weather", "get_forecasts", {"entity_id": ent, "type": kind},
                blocking=True, return_response=True)
        except Exception:  # noqa: BLE001 — source may not support forecasts
            return None
        return (resp or {}).get(ent, {}).get("forecast") or None

    async def async_forecast_hourly(self):
        return await self._forward("hourly")

    async def async_forecast_daily(self):
        return await self._forward("daily")
