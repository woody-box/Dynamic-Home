"""Climate platform — the DC zone thermostat.

Exposes the zone as a HA ``climate`` entity. The engine computes the setpoint
(base + biases + bus self-bias); the entity reflects it, publishes solar
intents to the shutters (via the coordinator), and — when a real thermostat is
configured — drives it (mode + target). Mode is restored across restarts.
"""

from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import DcCoordinator

_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DcCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DcClimate(coordinator, entry)])


class DcClimate(CoordinatorEntity[DcCoordinator], ClimateEntity, RestoreEntity):
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
        self._applied: tuple | None = None  # last (mode, target) sent to hardware
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dynamic Home",
            model="Dynamic Climate (zone)",
        )

    async def async_added_to_hass(self) -> None:
        """Restore the zone's mode across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in _HVAC_MODES:
            self.coordinator.hvac_mode = last.state
            await self.coordinator.async_refresh()

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode(self.coordinator.hvac_mode)

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.indoor_temperature()

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
        if hvac_mode != HVACMode.OFF:
            # Leaving a manual override when the user re-selects a mode.
            self.coordinator.override_active = False
        await self.coordinator.async_refresh()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            self.coordinator.hvac_mode = str(mode)
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            # Manual setpoint -> override.
            self.coordinator.override_active = True
            self.coordinator.override_temp = float(temp)
        await self.coordinator.async_refresh()
        self.async_write_ha_state()

    # --- drive the real thermostat (if configured) ---
    async def _apply(self) -> None:
        real = self._entry.data.get(const.CONF_DC_CLIMATE)
        # Observe (dry-run): compute + publish to the bus, but never drive the
        # real thermostat.
        if not real or self.coordinator.observe_enabled:
            return
        data = self.coordinator.data
        mode = self.coordinator.hvac_mode
        target = data.target if data else None
        prev_mode, prev_target = self._applied or (None, None)
        # Anti-jitter: when only the target moved and the change is below
        # apply_min_delta, don't bother the thermostat with a new setpoint.
        min_delta = getattr(self.coordinator, "apply_min_delta", 0.0)
        if (mode == prev_mode and target is not None and prev_target is not None
                and abs(target - prev_target) < min_delta):
            return
        if (mode, target) == self._applied:
            return
        self._applied = (mode, target)
        await self.hass.services.async_call(
            "climate", "set_hvac_mode",
            {"entity_id": real, ATTR_HVAC_MODE: mode}, blocking=True)
        if mode != HVACMode.OFF and target is not None:
            await self.hass.services.async_call(
                "climate", "set_temperature",
                {"entity_id": real, ATTR_TEMPERATURE: target}, blocking=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self._apply())
        super()._handle_coordinator_update()
