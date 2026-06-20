"""Fan platform — the VMC as a single HA fan entity.

Preset modes: auto (engine decides) / v1 / v2 / v3 (manual). The logical speed
0..3 maps to the three physical relays (SPEC §5).
"""

from __future__ import annotations

import asyncio
import math

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
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
        self._bootstrapped = False
        self._override_unsub = None     # cancels a pending auto-revert to auto
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
            self.coordinator.preset = self._preset
            # In a manual preset, re-assert the speed on the relays so the
            # hardware matches the restored state (auto self-heals on its own).
            if self._preset != const.PRESET_AUTO:
                await self._apply_speed(self._logical_speed)

    # --- derived state ---
    @property
    def _logical_speed(self) -> int:
        """Speed to display: engine decision in auto, manual pin otherwise."""
        if self._preset == const.PRESET_AUTO:
            data = self.coordinator.data
            return data.speed if data else self.coordinator.current_speed
        if self._preset == const.PRESET_OFF:
            return 0
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

    # --- manual-override auto-revert ---
    def _cancel_override(self) -> None:
        if self._override_unsub is not None:
            self._override_unsub()
            self._override_unsub = None
        self.coordinator.override_until = None

    def _arm_override(self) -> None:
        """Schedule a revert to auto if a manual preset and the timer is set."""
        self._cancel_override()
        if self._preset == const.PRESET_AUTO:
            return
        minutes = self.coordinator.override_minutes
        if not minutes or minutes <= 0:
            return
        self.coordinator.override_until = (
            dt_util.utcnow().timestamp() + minutes * 60)
        self._override_unsub = async_call_later(
            self.hass, minutes * 60, self._override_expired)

    @callback
    def _override_expired(self, _now) -> None:
        self._override_unsub = None
        self.hass.async_create_task(
            self.async_set_preset_mode(const.PRESET_AUTO))

    async def _select_preset(self, preset: str) -> None:
        """Common path for any preset change: pin it, drive relays, arm timer."""
        self._preset = preset
        self.coordinator.preset = preset
        if preset == const.PRESET_AUTO:
            self._cancel_override()
            await self.coordinator.async_request_refresh()
        else:
            await self._apply_speed(self._logical_speed)
            self._arm_override()
        self.async_write_ha_state()

    # --- commands ---
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._select_preset(preset_mode)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        speed = math.ceil(percentage_to_ranged_value(_SPEED_RANGE, percentage))
        await self._select_preset({1: const.PRESET_V1, 2: const.PRESET_V2,
                                   3: const.PRESET_V3}[speed])

    async def async_turn_on(self, percentage=None, preset_mode=None,
                            **kwargs) -> None:
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self.async_set_preset_mode(const.PRESET_AUTO)

    async def async_turn_off(self, **kwargs) -> None:
        # A real OFF the engine won't undo: pin the manual "off" preset (so auto
        # doesn't re-apply a speed next cycle) and stop the relays + power.
        await self._select_preset(const.PRESET_OFF)

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_override()
        await super().async_will_remove_from_hass()

    # --- hardware driver (SPEC §5) ---
    async def _apply_speed(self, speed: int) -> None:
        d = self._entry.data
        sw_pwr, sw_v2, sw_v3 = (d.get(const.CONF_SW_PWR),
                                d.get(const.CONF_SW_V2),
                                d.get(const.CONF_SW_V3))
        if speed <= 0:
            # Full stop: drop the speed relays first, then cut power.
            await self._switch(sw_v2, False)
            await self._switch(sw_v3, False)
            await self._switch(sw_pwr, False)
            self.coordinator.current_speed = 0
            return
        await self._switch(sw_pwr, True)
        # Bootstrap kick: pulse V2 ~800 ms once after startup so the motor
        # "wakes up" before settling on the target speed (opt-in, hardware quirk).
        if self.coordinator.bootstrap_enabled and not self._bootstrapped:
            self._bootstrapped = True
            await self._switch(sw_v2, True)
            await asyncio.sleep(0.8)
            await self._switch(sw_v2, False)
        # Break-before-make: never energise V2 and V3 at once. Drop both, let the
        # relays settle, then close only the wanted one (V1 = both open).
        await self._switch(sw_v2, False)
        await self._switch(sw_v3, False)
        if speed in (2, 3):
            await asyncio.sleep(const.RELAY_SETTLE_S)
            await self._switch(sw_v2, speed == 2)
            await self._switch(sw_v3, speed == 3)
        self.coordinator.current_speed = speed

    async def _switch(self, entity_id: str | None, on: bool) -> None:
        # Observe (dry-run): compute the decision but never touch the relays.
        if not entity_id or self.coordinator.observe_enabled:
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
