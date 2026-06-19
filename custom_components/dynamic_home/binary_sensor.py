"""Binary sensor platform — DC condensation risk (observability)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import DcCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DcCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DewRiskBinarySensor(coordinator, entry)])


class DewRiskBinarySensor(CoordinatorEntity[DcCoordinator], BinarySensorEntity):
    """Condensation risk for the zone (radiant cooling)."""

    _attr_has_entity_name = True
    _attr_name = "Riesgo de condensación"
    _attr_icon = "mdi:water-alert"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_dew_risk"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator.dew_risk_active
