"""Number platform — IAQ thresholds as first-class tunable entities.

These replace a handful of the YAML ``input_number`` helpers. Editing them
updates the config entry options, which reloads the coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const
from .coordinator import DvCoordinator


@dataclass(frozen=True)
class ThresholdDesc:
    key: str
    name: str
    default: float
    min_v: float
    max_v: float
    step: float
    unit: str


THRESHOLDS: tuple[ThresholdDesc, ...] = (
    ThresholdDesc(const.OPT_CO2_V2, "CO₂ V2 threshold", 900, 700, 1200, 25, "ppm"),
    ThresholdDesc(const.OPT_CO2_V3, "CO₂ V3 threshold", 1300, 1000, 1600, 25, "ppm"),
    ThresholdDesc(const.OPT_PM_V2, "PM2.5 V2 threshold", 15, 5, 25, 1, "µg/m³"),
    ThresholdDesc(const.OPT_PM_V3, "PM2.5 V3 threshold", 40, 20, 60, 5, "µg/m³"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DvCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities(ThresholdNumber(coordinator, entry, d) for d in THRESHOLDS)


class ThresholdNumber(NumberEntity):
    """A single IAQ threshold backed by config-entry options."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 desc: ThresholdDesc) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._desc = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_name = desc.name
        self._attr_native_min_value = desc.min_v
        self._attr_native_max_value = desc.max_v
        self._attr_native_step = desc.step
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> float:
        return self._entry.options.get(self._desc.key, self._desc.default)

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self._entry.options)
        options[self._desc.key] = value
        self.hass.config_entries.async_update_entry(
            self._entry, options=options)
