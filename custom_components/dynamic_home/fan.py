"""Fan platform — the VMC as a single HA fan entity.

Preset modes: auto (engine decides) / v1 / v2 / v3 (manual). The logical speed
0..3 maps to the three physical relays (SPEC §5).
"""

from __future__ import annotations

import math

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from . import const
from .coordinator import DvCoordinator

_SPEED_RANGE = (1, const.SPEED_COUNT)  # (1, 3)

# TURN_ON/TURN_OFF feature flags were added in HA 2024.8; guard for older cores.
_SUPPORTED_FEATURES = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
if hasattr(FanEntityFeature, "TURN_ON"):
    _SUPPORTED_FEATURES |= FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DvCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DvFan(coordinator, entry)])


class DvFan(CoordinatorEntity[DvCoordinator], FanEntity, RestoreEntity):
    """Represents the VMC."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_speed_count = const.SPEED_COUNT
    _attr_preset_modes = const.PRESET_MODES
    _attr_supported_features = _SUPPORTED_FEATURES

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_fan"
        self._preset = const.PRESET_AUTO
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dynamic Home",
            model="Dynamic Ventilation (VMC)",
        )

    async def async_added_to_hass(self) -> None:
        """Restore the selected preset across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.attributes.get("preset_mode") in const.PRESET_MODES:
            self._preset = last.attributes["preset_mode"]

    # --- derived state ---
    @property
    def _logical_speed(self) -> int:
        """Speed to display: engine decision in auto, manual pin otherwise."""
        if self._preset == const.PRESET_AUTO:
            data = self.coordinator.data
            return data.speed if data else self.coordinator.current_speed
        return {const.PRESET_V1: 1, const.PRESET_V2: 2,
                const.PRESET_V3: 3}[self._preset]

    @property
    def is_on(self) -> bool:
        return self._logical_speed > 0

    @property
    def percentage(self) -> int:
        spd = self._logical_speed
        if spd <= 0:
            return 0
        return ranged_value_to_percentage(_SPEED_RANGE, spd)

    @property
    def preset_mode(self) -> str:
        return self._preset

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"reason": data.reason if data else None,
                "base_target": data.base_target if data else None,
                **(data.details if data else {})}

    # --- commands ---
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._preset = preset_mode
        if preset_mode != const.PRESET_AUTO:
            await self._apply_speed(self._logical_speed)
        else:
            await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        speed = math.ceil(percentage_to_ranged_value(_SPEED_RANGE, percentage))
        self._preset = {1: const.PRESET_V1, 2: const.PRESET_V2,
                        3: const.PRESET_V3}[speed]
        await self._apply_speed(speed)
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None,
                            **kwargs) -> None:
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self.async_set_preset_mode(const.PRESET_AUTO)

    async def async_turn_off(self, **kwargs) -> None:
        sw_pwr = self._entry.data.get(const.CONF_SW_PWR)
        if sw_pwr:
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": sw_pwr}, blocking=True)
        self.async_write_ha_state()

    # --- hardware driver (SPEC §5) ---
    async def _apply_speed(self, speed: int) -> None:
        d = self._entry.data
        sw_pwr, sw_v2, sw_v3 = (d.get(const.CONF_SW_PWR),
                                d.get(const.CONF_SW_V2),
                                d.get(const.CONF_SW_V3))
        if speed <= 0:
            await self._switch(sw_pwr, False)
            return
        await self._switch(sw_pwr, True)
        # Never V2 and V3 at once.
        await self._switch(sw_v2, speed == 2)
        await self._switch(sw_v3, speed == 3)
        self.coordinator.current_speed = speed

    async def _switch(self, entity_id: str | None, on: bool) -> None:
        if not entity_id:
            return
        await self.hass.services.async_call(
            "switch", "turn_on" if on else "turn_off",
            {"entity_id": entity_id}, blocking=True)

    # --- react to coordinator (auto mode applies the decision) ---
    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if (self._preset == const.PRESET_AUTO and data
                and data.speed != self.coordinator.current_speed):
            self.hass.async_create_task(self._apply_speed(data.speed))
        super()._handle_coordinator_update()
