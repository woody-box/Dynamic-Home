"""Climate platform — the DC zone thermostat.

Exposes the zone as a HA ``climate`` entity. The engine computes the setpoint
(base + biases + bus self-bias); the entity reflects it, publishes solar
intents to the shutters (via the coordinator), and — when a real thermostat is
configured — drives it (mode + target). Mode is restored across restarts.
"""

from __future__ import annotations

import asyncio

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import const
from .coordinator import DcCoordinator

_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
# F37: community zones also offer HEAT_COOL = "follow the building" (the changeover
# decides heat vs cool); honest UI instead of showing "heat" while actually cooling.
_HVAC_MODES_COMMUNITY = _HVAC_MODES + [HVACMode.HEAT_COOL]

# Fallback range ends (Home Assistant's climate defaults) for the idle-in-mode
# setpoint when the driven thermostat exposes no min_temp / max_temp.
_IDLE_MIN_TEMP = 7.0
_IDLE_MAX_TEMP = 35.0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DcCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DcClimate(coordinator, entry)])


class DcClimate(CoordinatorEntity[DcCoordinator], ClimateEntity, RestoreEntity):
    """The managed climate zone."""

    _attr_has_entity_name = True
    # Suffix the Dynamic Home tag so this managed climate is told apart from the
    # physical thermostat it drives (e.g. "Zona Salón - DH-DC"). The device name
    # still leads, so renaming the device propagates as usual.
    _attr_name = f"- {const.MODULE_TAG[const.MODULE_CLIMATE]}"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
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
        # Stable object_id (climate.<zone>) despite the "- DH-DC" display suffix;
        # existing entities keep their registered id.
        self.entity_id = f"climate.{slugify(entry.title)}"
        self._applied: tuple | None = None  # last (mode, target) — legacy single device
        self._applied_per: dict[str, tuple] = {}   # F25: per-emitter last (mode, target)
        # Serialize hardware drives: _apply awaits blocking service calls, so two
        # overlapping ticks could interleave mode/target on the real thermostat.
        self._apply_lock = asyncio.Lock()
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
        if last and last.state in _HVAC_MODES_COMMUNITY:
            if last.state == HVACMode.HEAT_COOL:
                self.coordinator.follow_changeover = True
            else:
                self.coordinator.follow_changeover = False
                self.coordinator.hvac_mode = last.state
            await self.coordinator.async_refresh()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Offer HEAT_COOL only on community zones (F37 follow-the-building)."""
        profile = self.coordinator.install_profile
        if profile and profile.get("community"):
            return _HVAC_MODES_COMMUNITY
        return _HVAC_MODES

    @property
    def hvac_mode(self) -> HVACMode:
        if self.coordinator.follow_changeover:
            return HVACMode.HEAT_COOL
        return HVACMode(self.coordinator.hvac_mode)

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.indoor_temperature()

    @property
    def target_temperature(self) -> float | None:
        data = self.coordinator.data
        return data.target if data else None

    @property
    def hvac_action(self) -> HVACAction:
        """What the zone is really doing (F37: reflects the community changeover)."""
        data = self.coordinator.data
        if not data or data.action not in ("heat", "cool"):
            return HVACAction.OFF
        demanding = getattr(self.coordinator, "_valve_open", False)
        if data.action == "heat":
            return HVACAction.HEATING if demanding else HVACAction.IDLE
        return HVACAction.COOLING if demanding else HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if not data:
            return {}
        return {"reason": data.reason,
                "published_intent": data.published_intent,
                "anticycle_hold": self.coordinator.anticycle_hold,
                "anticycle_reason": self.coordinator.anticycle_reason,
                "peak_hold": self.coordinator.peak_hold,
                "peak_reason": self.coordinator.peak_reason,
                # F37: the direction the zone really runs (community zones are
                # gated by the building changeover) and whether the user's mode
                # contradicts the water — the zone rests instead of inverting.
                "hvac_effective": self.coordinator.hvac_effective,
                "changeover_conflict": self.coordinator.changeover_conflict}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT_COOL:
            # "Follow the building": the refresh resolves it from the changeover.
            self.coordinator.follow_changeover = True
        else:
            self.coordinator.follow_changeover = False
            self.coordinator.hvac_mode = str(hvac_mode)
        if hvac_mode != HVACMode.OFF:
            # Leaving a manual override when the user re-selects a mode.
            self.coordinator.override_active = False
        await self.coordinator.async_refresh()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            if mode == HVACMode.HEAT_COOL:
                self.coordinator.follow_changeover = True
            else:
                self.coordinator.follow_changeover = False
                self.coordinator.hvac_mode = str(mode)
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            # Manual setpoint -> override.
            self.coordinator.override_active = True
            self.coordinator.override_temp = float(temp)
        await self.coordinator.async_refresh()
        self.async_write_ha_state()

    # --- drive the real thermostat(s) ---
    async def _apply(self) -> None:
        async with self._apply_lock:
            await self._apply_locked()

    async def _apply_locked(self) -> None:
        # Observe (dry-run) or paused: compute but never drive hardware.
        if self.coordinator.observe_effective:
            return
        # F25: multi-emitter zone -> drive each emitter by its command. An empty map
        # keeps the legacy single-device path below (back-compat, REQ-EMI-7).
        cmds = self.coordinator.emitter_commands
        if cmds:
            await self._apply_emitters(cmds)
            return
        real = self._entry.data.get(const.CONF_DC_CLIMATE)
        if not real:
            return
        data = self.coordinator.data
        # F09/F03: a protective hold (compressor anti-cycling / house peak budget)
        # idles the thermostat IN mode — keep heat/cool but push the setpoint out
        # of reach — so a DS thermal-shield reference survives and the unit
        # re-engages on its own when the hold clears. Only a genuine off
        # (user/safety) drops the mode to OFF.
        held = (getattr(self.coordinator, "anticycle_hold", False)
                or getattr(self.coordinator, "peak_hold", False))
        mode = self.coordinator.hvac_mode
        if held and mode in ("heat", "cool"):
            target = self._idle_target(real, HVACMode(mode))
        elif held:
            mode, target = HVACMode.OFF, None
        else:
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
        await self.hass.services.async_call(
            "climate", "set_hvac_mode",
            {"entity_id": real, ATTR_HVAC_MODE: mode}, blocking=True)
        if mode != HVACMode.OFF and target is not None:
            await self.hass.services.async_call(
                "climate", "set_temperature",
                {"entity_id": real, ATTR_TEMPERATURE: target}, blocking=True)
        # Recorded only after the calls succeeded: a failed service must not
        # leave _applied claiming a state the device never reached.
        self._applied = (mode, target)

    async def _apply_emitters(self, cmds: dict) -> None:
        """F25: drive each emitter's device (climate and/or switch) by its command.

        Iterates the COMMANDS (not the emitter list): a farewell OFF for a
        removed emitter embeds its entities in the command itself.
        """
        min_delta = getattr(self.coordinator, "apply_min_delta", 0.0)
        ems = {em["id"]: em for em in self.coordinator._emitters}
        for eid, cmd in cmds.items():
            em = ems.get(eid, cmd)
            mode = HVACMode(cmd["mode"]) if cmd["mode"] in (
                "heat", "cool", "off") else HVACMode.OFF
            # A protective hold keeps the direction (mode) but idles the emitter;
            # a genuine off drops the mode. target is None while idle/off.
            idle = cmd.get("idle", False)
            target = cmd["target"]
            prev = self._applied_per.get(eid)
            if prev is not None:
                prev_mode, prev_target = prev
                if (mode == prev_mode and target is not None
                        and prev_target is not None
                        and abs(target - prev_target) < min_delta):
                    continue
            if (mode, target) == prev:
                continue
            self._applied_per[eid] = (mode, target)
            if em.get("climate"):
                # Idle-in-mode: keep heat/cool, push the setpoint out of reach.
                eff_target = (self._idle_target(em["climate"], mode)
                              if idle else target)
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode",
                    {"entity_id": em["climate"], ATTR_HVAC_MODE: mode}, blocking=True)
                if mode != HVACMode.OFF and eff_target is not None:
                    await self.hass.services.async_call(
                        "climate", "set_temperature",
                        {"entity_id": em["climate"], ATTR_TEMPERATURE: eff_target},
                        blocking=True)
            if em.get("switch"):
                # A bare switch has no mode to preserve: idle == off for it.
                on = mode != HVACMode.OFF and not idle
                service = "turn_on" if on else "turn_off"
                await self.hass.services.async_call(
                    "homeassistant", service,
                    {"entity_id": em["switch"]}, blocking=True)

    def _idle_target(self, entity_id: str, mode: HVACMode) -> float:
        """A setpoint that idles the emitter WITHOUT leaving its heat/cool mode:
        the far end of its range, so the driven thermostat sees no demand. Used by
        protective holds so the direction (and a DS shield's reference) survives
        and the unit re-engages on its own when the hold clears."""
        st = self.hass.states.get(entity_id)
        lo = st.attributes.get("min_temp") if st else None
        hi = st.attributes.get("max_temp") if st else None
        lo = _IDLE_MIN_TEMP if lo is None else float(lo)
        hi = _IDLE_MAX_TEMP if hi is None else float(hi)
        return hi if mode == HVACMode.COOL else lo

    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self._apply())
        super()._handle_coordinator_update()
