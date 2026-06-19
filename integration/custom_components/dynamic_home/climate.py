"""Climate platform — the DC zone thermostat.

Exposes the zone as a HA ``climate`` entity. The engine computes the target
setpoint (base + biases + bus self-bias); the entity reflects it and, by mode,
drives the bus (publishing solar-gain/shield to the shutters via the
coordinator).
"""

from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import DcCoordinator

_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DcCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DcClimate(coordinator, entry)])


class DcClimate(CoordinatorEntity[DcCoordinator], ClimateEntity):
    """The managed climate zone."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = _HVAC_MODES
    _attr_target_temperature_step = 0.5
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    # TURN_ON/OFF flags arrived in HA 2024.8; add only if available.
    if hasattr(ClimateEntityFeature, "TURN_ON"):
        _attr_supported_features |= (
            ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: DcCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dynamic Home",
            model="Dynamic Climate (zone)",
        )

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode(self.coordinator.hvac_mode)

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator._num(const.CONF_DC_T_INT)

    @property
    def target_temperature(self) -> float | None:
        data = self.coordinator.data
        return data.target if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if not data:
            return {}
        return {"reason": data.reason,
                "published_intent": data.published_intent}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self.coordinator.hvac_mode = str(hvac_mode)
        await self.coordinator.async_refresh()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        # Manual setpoint -> override.
        self.coordinator.override_active = True
        self.coordinator.override_temp = float(temp)
        await self.coordinator.async_refresh()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
