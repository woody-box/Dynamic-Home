"""Binary sensor platform — DC condensation risk (observability)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import DcCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DcCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    entities = [DewRiskBinarySensor(coordinator, entry),
                DegradedBinarySensor(coordinator, entry)]
    if coordinator.has_real_demand():
        entities.append(RealDemandBinarySensor(coordinator, entry))
    if coordinator.has_window_infer():
        entities.append(WindowInferredBinarySensor(coordinator, entry))
    async_add_entities(entities)


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


class RealDemandBinarySensor(CoordinatorEntity[DcCoordinator], BinarySensorEntity):
    """Real heating/cooling demand (F27): reflects the actual valve/relay state."""

    _attr_has_entity_name = True
    _attr_name = "Demanda real"
    _attr_icon = "mdi:heating-coil"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_real_demand"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.real_demand_open

    @property
    def extra_state_attributes(self) -> dict:
        return {"source": self.coordinator.real_demand_source}


class WindowInferredBinarySensor(CoordinatorEntity[DcCoordinator],
                                 BinarySensorEntity):
    """Open window inferred from temperature (F20): ON forces the zone OFF."""

    _attr_has_entity_name = True
    _attr_name = "Ventana (inferida)"
    _attr_icon = "mdi:window-open-variant"
    _attr_device_class = BinarySensorDeviceClass.WINDOW
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_window_inferred"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator._window_inferred

    @property
    def extra_state_attributes(self) -> dict:
        return {"trend_cph": round(self.coordinator._cph, 2)}


class DegradedBinarySensor(CoordinatorEntity[DcCoordinator], BinarySensorEntity):
    """Zone health: ON when a core source is missing (learning is paused)."""

    _attr_has_entity_name = True
    _attr_name = "Degradado"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_degraded"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator.degraded
