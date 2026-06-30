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
from .coordinator_weather import WxCoordinator
from .coordinator_zones import ZonesCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_WEATHER:
        async_add_entities([WeatherAlertBinarySensor(coordinator, entry)])
        return
    if module == const.MODULE_ENERGY:
        async_add_entities([ScarcityBinarySensor(coordinator, entry)])
        return
    if module == const.MODULE_ZONES:
        # F32: a per-zone occupancy sensor for each zone with sources + a
        # house-level presence sensor (only when presence is configured).
        sources = entry.options.get(const.CONF_PRESENCE_SOURCES) or {}
        phones = entry.options.get(const.CONF_PRESENCE_PHONES) or []
        ents: list[BinarySensorEntity] = [
            ZoneOccupancyBinarySensor(coordinator, entry, zid, z["name"])
            for zid, z in coordinator.tree["zones"].items() if sources.get(zid)]
        if sources or phones:
            ents.append(HousePresenceBinarySensor(coordinator, entry))
        async_add_entities(ents)
        return
    # DV/DS expose the transversal "Estado" health sensor (F07); DS adds the
    # "In sun" facade signal. The rest below are DC-specific.
    if module == const.MODULE_VMC:
        async_add_entities([DegradedBinarySensor(coordinator, entry)])
        return
    if module == const.MODULE_SHUTTER:
        async_add_entities([DegradedBinarySensor(coordinator, entry),
                            InSunBinarySensor(coordinator, entry)])
        return
    entities = [DewRiskBinarySensor(coordinator, entry),
                DegradedBinarySensor(coordinator, entry)]
    if coordinator.has_real_demand():
        entities.append(RealDemandBinarySensor(coordinator, entry))
    if coordinator.has_window_infer():
        entities.append(WindowInferredBinarySensor(coordinator, entry))
    async_add_entities(entities)


class ScarcityBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Energy scarcity (F34): on when expensive with no PV surplus."""

    _attr_has_entity_name = True
    _attr_translation_key = "scarcity"
    _attr_icon = "mdi:flash-alert"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_scarcity"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.context.get("scarcity"))


class ZoneOccupancyBinarySensor(CoordinatorEntity[ZonesCoordinator],
                                BinarySensorEntity):
    """Per-zone fused occupancy (F32)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:account-eye"

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry,
                 zid: str, name: str) -> None:
        super().__init__(coordinator)
        self._zid = zid
        self._attr_translation_key = "zone_occupancy"
        self._attr_translation_placeholders = {"zone": name}
        self._attr_unique_id = f"{entry.entry_id}_occupancy_{zid}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.presence_occupied.get(self._zid))

    @property
    def extra_state_attributes(self) -> dict:
        return {"reason": self.coordinator.presence_reasons.get(self._zid, "empty")}


class HousePresenceBinarySensor(CoordinatorEntity[ZonesCoordinator],
                                BinarySensorEntity):
    """House presence (F32): on while occupied/sleeping, off when away."""

    _attr_has_entity_name = True
    _attr_translation_key = "house_presence"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_house_presence"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator.house_presence != "away"

    @property
    def extra_state_attributes(self) -> dict:
        return {"state": self.coordinator.house_presence}


class DewRiskBinarySensor(CoordinatorEntity[DcCoordinator], BinarySensorEntity):
    """Condensation risk for the zone (radiant cooling)."""

    _attr_has_entity_name = True
    _attr_translation_key = "dew_risk"
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
    _attr_translation_key = "real_demand"
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
    _attr_translation_key = "window_inferred"
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


class WeatherAlertBinarySensor(CoordinatorEntity[WxCoordinator],
                               BinarySensorEntity):
    """Generic weather alert derived from the active source (F33 → F17)."""

    _attr_has_entity_name = True
    _attr_translation_key = "weather_alert"
    _attr_icon = "mdi:weather-lightning"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: WxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_wx_alert"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator.alert_active

    @property
    def extra_state_attributes(self) -> dict:
        return {"source": self.coordinator.active_label}


class DegradedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Module health: ON when a required source is missing (F07, DV/DS/DC)."""

    _attr_has_entity_name = True
    # device_class PROBLEM -> HA shows the state as OK / Problema, so "Estado"
    # reads naturally ("Estado: OK") instead of the odd "Degradado: OK".
    _attr_translation_key = "degraded"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_degraded"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator.degraded

    @property
    def extra_state_attributes(self) -> dict:
        # Per-source breakdown so the user can see *why* something is unavailable
        # (configured-but-down vs simply not configured) without guessing.
        report = getattr(self.coordinator, "health_report", None)
        return report() if report else {}


class InSunBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """DS: ON when direct sun is reaching this facade (impact > 0).

    Accounts for orientation (facade azimuth/span), the horizon and the overhang
    shading — so it's 'in sun' only when the sun actually hits the window.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "in_sun"
    _attr_icon = "mdi:weather-sunny"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_in_sun"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self.coordinator.sun_impact > 0

    @property
    def extra_state_attributes(self) -> dict:
        return {"impact": round(self.coordinator.sun_impact)}
