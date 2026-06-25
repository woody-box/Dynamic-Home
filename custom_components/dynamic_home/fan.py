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
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
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
    ents: list[FanEntity] = [DvFan(coordinator, entry)]
    if coordinator.has_hood():
        ents.append(HoodFan(coordinator, entry))
    async_add_entities(ents)


class HoodFan(CoordinatorEntity[DvCoordinator], FanEntity, RestoreEntity):
    """Coordinated extractor hood (F35): 3 relays, one per speed (none on = OFF).

    Auto: the speed follows the indoor PM (engine ``hood_speed``). Manual presets
    pin a speed. The relay driver is **break-before-make** (drop the other relays,
    let them settle, then close only the target), and an interlock watcher
    force-corrects if two speed relays are ever energised at once.
    """

    _attr_has_entity_name = True
    _attr_name = "Campana"
    _attr_icon = "mdi:range-hood"
    _attr_speed_count = const.SPEED_COUNT
    _attr_preset_modes = const.PRESET_MODES
    _attr_supported_features = _SUPPORTED_FEATURES

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_hood"
        self._preset = const.PRESET_AUTO
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    @property
    def _relays(self) -> list[str | None]:
        d = self._entry.data
        return [d.get(const.CONF_HOOD_V1), d.get(const.CONF_HOOD_V2),
                d.get(const.CONF_HOOD_V3)]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.attributes.get("preset_mode") in const.PRESET_MODES:
            self._preset = last.attributes["preset_mode"]
        relays = [r for r in self._relays if r]
        if relays:
            self.async_on_remove(async_track_state_change_event(
                self.hass, relays, self._interlock_check))
        if self._preset != const.PRESET_AUTO:
            await self._apply_hood(self._logical_speed)

    @property
    def _logical_speed(self) -> int:
        if self._preset == const.PRESET_AUTO:
            return self.coordinator.hood_speed_auto
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
        return ranged_value_to_percentage(_SPEED_RANGE, spd) if spd > 0 else 0

    @property
    def preset_mode(self) -> str:
        return self._preset

    @property
    def extra_state_attributes(self) -> dict:
        return {"source": self._preset,
                "auto_speed": self.coordinator.hood_speed_auto}

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._preset = preset_mode
        if preset_mode == const.PRESET_AUTO:
            await self.coordinator.async_request_refresh()
            await self._apply_hood(self._logical_speed)
        else:
            await self._apply_hood(self._logical_speed)
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_set_preset_mode(const.PRESET_OFF)
            return
        speed = math.ceil(percentage_to_ranged_value(_SPEED_RANGE, percentage))
        await self.async_set_preset_mode({1: const.PRESET_V1, 2: const.PRESET_V2,
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
        await self.async_set_preset_mode(const.PRESET_OFF)

    # --- hardware driver (break-before-make, 1-of-3) ---
    async def _apply_hood(self, speed: int) -> None:
        relays = self._relays
        for i, ent in enumerate(relays, start=1):     # drop every non-target first
            if i != speed:
                await self._switch(ent, False)
        if speed in (1, 2, 3):
            await asyncio.sleep(const.RELAY_SETTLE_S)
            await self._switch(relays[speed - 1], True)
        self.coordinator.hood_current = speed

    async def _switch(self, entity_id: str | None, on: bool) -> None:
        if not entity_id or self.coordinator.observe_enabled:
            return
        await self.hass.services.async_call(
            "switch", "turn_on" if on else "turn_off",
            {"entity_id": entity_id}, blocking=True)

    @callback
    def _interlock_check(self, event) -> None:
        """If two speed relays are ever on at once, re-assert the wanted speed."""
        ons = sum(1 for r in self._relays
                  if r and self.hass.states.is_state(r, "on"))
        if ons > 1:
            self.hass.async_create_task(self._apply_hood(self._logical_speed))

    @callback
    def _handle_coordinator_update(self) -> None:
        if (self._preset == const.PRESET_AUTO
                and self.coordinator.hood_speed_auto != self.coordinator.hood_current):
            self.hass.async_create_task(
                self._apply_hood(self.coordinator.hood_speed_auto))
        super()._handle_coordinator_update()


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
        attrs = {"reason": data.reason if data else None,
                 "base_target": data.base_target if data else None,
                 **(data.details if data else {})}
        # F13: name the bathroom whose humidity rise drove the shower boost.
        if data and data.reason == "shower_rh" and self.coordinator.shower_bathroom:
            attrs["shower_bathroom"] = self.coordinator.shower_bathroom
        # Adaptive thresholds: surface what was learned (vs the fixed values), so
        # they can be compared/graphed. None until enough samples accumulate.
        if self.coordinator.adaptive_enabled:
            attrs["adaptive_samples"] = self.coordinator.adaptive_samples
            attrs["adaptive_co2_v2"] = self.coordinator.adaptive_co2_v2
            attrs["adaptive_co2_v3"] = self.coordinator.adaptive_co2_v3
            attrs["adaptive_pm_v2"] = self.coordinator.adaptive_pm_v2
            attrs["adaptive_pm_v3"] = self.coordinator.adaptive_pm_v3
        return attrs

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
