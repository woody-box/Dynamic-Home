"""Sensor platform — VMC telemetry (DV).

Running hours per speed, total machine hours and filter hours (all restored
across restarts), plus the current speed and decision reason for diagnostics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import DvCoordinator


@dataclass(frozen=True)
class _HoursDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DvCoordinator], float]
    setter: Callable[[DvCoordinator, float], None]


_HOURS: tuple[_HoursDesc, ...] = (
    _HoursDesc("hours_v1", "Hours V1", "mdi:fan-speed-1",
               lambda c: c.speed_hours[1],
               lambda c, v: c.speed_hours.__setitem__(1, v)),
    _HoursDesc("hours_v2", "Hours V2", "mdi:fan-speed-2",
               lambda c: c.speed_hours[2],
               lambda c, v: c.speed_hours.__setitem__(2, v)),
    _HoursDesc("hours_v3", "Hours V3", "mdi:fan-speed-3",
               lambda c: c.speed_hours[3],
               lambda c, v: c.speed_hours.__setitem__(3, v)),
    _HoursDesc("hours_machine", "Machine hours", "mdi:fan-clock",
               lambda c: c.machine_hours,
               lambda c, v: setattr(c, "machine_hours", v)),
    _HoursDesc("hours_filter", "Filter hours", "mdi:air-filter",
               lambda c: c.filter_hours,
               lambda c, v: setattr(c, "filter_hours", v)),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    if entry.data.get(const.CONF_MODULE) == const.MODULE_CLIMATE:
        async_add_entities(DcSensor(coordinator, entry, d) for d in _DC_SENSORS)
        return
    entities: list[SensorEntity] = [HoursSensor(coordinator, entry, d)
                                    for d in _HOURS]
    entities.append(SpeedSensor(coordinator, entry))
    entities.append(ReasonSensor(coordinator, entry))
    entities.append(ModeSensor(coordinator, entry))
    async_add_entities(entities)


class _Base(CoordinatorEntity[DvCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})


class HoursSensor(_Base, RestoreSensor):
    """Cumulative running-hours counter, restored across restarts."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 desc: _HoursDesc) -> None:
        super().__init__(coordinator, entry, desc.key)
        self._desc = desc
        self._attr_name = desc.name
        self._attr_icon = desc.icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._desc.setter(self.coordinator, float(last.native_value))

    @property
    def native_value(self) -> float:
        return round(self._desc.getter(self.coordinator), 3)


class SpeedSensor(_Base):
    _attr_name = "Speed"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "speed")

    @property
    def native_value(self) -> int:
        return self.coordinator.current_speed


class ReasonSensor(_Base):
    _attr_name = "Reason"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "reason")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        return data.reason if data else None


class ModeSensor(_Base):
    _attr_name = "Mode"
    _attr_icon = "mdi:fan-auto"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "mode")

    @property
    def native_value(self) -> str:
        return self.coordinator.preset


# --------------------------------------------------------------------------- #
# DC (climate) diagnostic sensors — expose the pipeline for dashboards
# --------------------------------------------------------------------------- #
from homeassistant.const import UnitOfTemperature  # noqa: E402

from .coordinator import DcCoordinator  # noqa: E402


@dataclass(frozen=True)
class _DcDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DcCoordinator], object]
    unit: str | None = None
    diagnostic: bool = False
    attrs: Callable[[DcCoordinator], dict] | None = None


def _detail(co: DcCoordinator, k: str):
    d = co.data
    return d.details.get(k) if d else None


_DC_SENSORS: tuple[_DcDesc, ...] = (
    _DcDesc("target", "Target", "mdi:thermometer-check",
            lambda c: c.data.target if c.data else None,
            UnitOfTemperature.CELSIUS,
            attrs=lambda c: dict(c.data.details) if c.data else {}),
    _DcDesc("base", "Base activa", "mdi:home-thermometer",
            lambda c: _detail(c, "base"), UnitOfTemperature.CELSIUS),
    _DcDesc("target_raw", "Target RAW", "mdi:thermometer-lines",
            lambda c: _detail(c, "target_raw"), UnitOfTemperature.CELSIUS),
    _DcDesc("dew_point", "Temperatura de condensación", "mdi:thermometer-water",
            lambda c: c.dew_point_c, UnitOfTemperature.CELSIUS),
    _DcDesc("mods_total", "Mods total", "mdi:sigma",
            lambda c: _detail(c, "mods_total"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("lead", "Lead", "mdi:clock-fast",
            lambda c: _detail(c, "lead_h"), "h", diagnostic=True),
    _DcDesc("reason", "Rama de decisión", "mdi:directions-fork",
            lambda c: c.data.reason if c.data else None, diagnostic=True),
    # One dedicated sensor per bias (1:1 with dashboard chips).
    _DcDesc("bias_exterior", "Bias exterior", "mdi:home-thermometer-outline",
            lambda c: _detail(c, "bias_exterior"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_vmc", "Bias VMC", "mdi:fan",
            lambda c: _detail(c, "bias_vmc"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_trend", "Bias tendencia", "mdi:trending-up",
            lambda c: _detail(c, "bias_trend"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_brake", "Bias freno", "mdi:car-brake-alert",
            lambda c: _detail(c, "bias_brake"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_forecast", "Bias forecast", "mdi:weather-partly-cloudy",
            lambda c: _detail(c, "bias_forecast"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("bias_facade", "Bias fachadas", "mdi:window-shutter",
            lambda c: _detail(c, "bias_facade"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
    _DcDesc("sdhb_bias", "Bias bus", "mdi:transit-connection-variant",
            lambda c: _detail(c, "sdhb_bias"), UnitOfTemperature.CELSIUS,
            diagnostic=True),
)


class DcSensor(CoordinatorEntity[DcCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry,
                 desc: _DcDesc) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_name = desc.name
        self._attr_icon = desc.icon
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        if desc.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self):
        return self._desc.getter(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._desc.attrs(self.coordinator) if self._desc.attrs else None
