"""Switch platform — shutter override/privacy toggles (DS).

- Privacy: clamp the shutter to a privacy position while on.
- Lock: pin the shutter at the lock position (manual override) while on.

Both feed the DS engine inputs and are restored across restarts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import const

if TYPE_CHECKING:
    from .coordinator import DsCoordinator


@dataclass(frozen=True)
class _ToggleDesc:
    key: str
    name: str
    icon: str
    getter: Callable
    setter: Callable


# Observe (dry-run): compute decisions but never touch hardware. Shared by all
# three module types.
_OBSERVE = _ToggleDesc(
    "observe", "Observe only", "mdi:eye-outline",
    lambda c: c.observe_enabled,
    lambda c, v: setattr(c, "observe_enabled", v))


_SHUTTER_SWITCHES: tuple[_ToggleDesc, ...] = (
    _ToggleDesc(
        "privacy", "Privacy", "mdi:blinds-horizontal",
        lambda c: c.privacy_enabled,
        lambda c, v: setattr(c, "privacy_enabled", v)),
    _ToggleDesc(
        "lock", "Lock", "mdi:lock",
        lambda c: c.lock_enabled,
        lambda c, v: setattr(c, "lock_enabled", v)),
    _ToggleDesc(
        "dawn", "Gradual sunrise", "mdi:weather-sunset-up",
        lambda c: c.dawn_enabled,
        lambda c, v: setattr(c, "dawn_enabled", v)),
    _ToggleDesc(
        "night_iso", "Night insulation", "mdi:weather-night",
        lambda c: c.night_iso_enabled,
        lambda c, v: setattr(c, "night_iso_enabled", v)),
    _ToggleDesc(
        "geo_shade", "Geometric shading", "mdi:sun-angle",
        lambda c: c.geo_shade_enabled,
        lambda c, v: setattr(c, "geo_shade_enabled", v)),
    _ToggleDesc(
        "heat_shield", "Thermal shield", "mdi:sun-thermometer",
        lambda c: c.heat_shield_enabled,
        lambda c, v: setattr(c, "heat_shield_enabled", v)),
    _ToggleDesc(
        "sun_shield", "Direct-sun shield", "mdi:weather-sunny-alert",
        lambda c: c.sun_shield_enabled,
        lambda c, v: setattr(c, "sun_shield_enabled", v)),
    _ToggleDesc(
        "weather_protect", "Weather protection", "mdi:weather-cloudy-alert",
        lambda c: c.weather_protect,
        lambda c, v: setattr(c, "weather_protect", v)),
    _ToggleDesc(
        "track_external", "Follow manual moves", "mdi:gesture-tap",
        lambda c: c.track_external,
        lambda c, v: setattr(c, "track_external", v)),
    _ToggleDesc(
        "sim_exclude", "Exclude from presence simulation", "mdi:account-off",
        lambda c: c.sim_excluded,
        lambda c, v: setattr(c, "sim_excluded", v)),
    _ToggleDesc(
        "peak", "Peak limiting", "mdi:flash-alert",
        lambda c: c.peak_enabled,
        lambda c, v: setattr(c, "peak_enabled", v)),
    _OBSERVE,
)

_VMC_SWITCHES: tuple[_ToggleDesc, ...] = (
    _ToggleDesc(
        "adaptive", "Adaptive thresholds", "mdi:brain",
        lambda c: c.adaptive_enabled,
        lambda c, v: setattr(c, "adaptive_enabled", v)),
    _ToggleDesc(
        "bootstrap", "Startup kick", "mdi:fan-auto",
        lambda c: c.bootstrap_enabled,
        lambda c, v: setattr(c, "bootstrap_enabled", v)),
    _ToggleDesc(
        "dry_mode", "Dry mode", "mdi:water-percent",
        lambda c: c.dry_mode_enabled,
        lambda c, v: setattr(c, "dry_mode_enabled", v)),
    _ToggleDesc(
        "freecool", "Free-cooling", "mdi:snowflake-thermometer",
        lambda c: c.freecool_enabled,
        lambda c, v: setattr(c, "freecool_enabled", v)),
    _ToggleDesc(
        "anticipatory", "Anticipatory boost", "mdi:trending-up",
        lambda c: c.anticip_enabled,
        lambda c, v: setattr(c, "anticip_enabled", v)),
    _ToggleDesc(
        "schedule", "Schedule", "mdi:calendar-clock",
        lambda c: c.schedule_enabled,
        lambda c, v: setattr(c, "schedule_enabled", v)),
    _ToggleDesc(
        "quiet_hours", "Quiet hours", "mdi:volume-mute",
        lambda c: c.quiet_enabled,
        lambda c, v: setattr(c, "quiet_enabled", v)),
    _OBSERVE,
)


_CLIMATE_SWITCHES: tuple[_ToggleDesc, ...] = (
    _ToggleDesc(
        "vacation", "Vacation", "mdi:bag-suitcase",
        lambda c: c.vacation_enabled,
        lambda c, v: setattr(c, "vacation_enabled", v)),
    _ToggleDesc(
        "adaptive_lead", "Adaptive lead", "mdi:brain",
        lambda c: c.adaptive_enabled,
        lambda c, v: setattr(c, "adaptive_enabled", v)),
    _ToggleDesc(
        "schedule", "Schedule", "mdi:calendar-clock",
        lambda c: c.schedule_enabled,
        lambda c, v: setattr(c, "schedule_enabled", v)),
    _ToggleDesc(
        "anticycle", "Anti short-cycle", "mdi:sync-alert",
        lambda c: c.anticycle_enabled,
        lambda c, v: setattr(c, "anticycle_enabled", v)),
    _ToggleDesc(
        "anticycle_autosize", "Adaptive anti-cycle", "mdi:sync-alert",
        lambda c: c.anticycle_autosize_enabled,
        lambda c, v: setattr(c, "anticycle_autosize_enabled", v)),
    _ToggleDesc(
        "peak", "Peak limiting", "mdi:flash-alert",
        lambda c: c.peak_enabled,
        lambda c, v: setattr(c, "peak_enabled", v)),
    _OBSERVE,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_ZONES:
        ents: list[SwitchEntity] = [
            ZonesPauseSwitch(coordinator, entry, k, a, i)
            for k, a, i in _PAUSE_SWITCHES]
        ents.append(PresenceSimSwitch(coordinator, entry))
        async_add_entities(ents)
        return
    if module == const.MODULE_SHUTTER_COMMON:
        # The auto-created "Común" entry: global shutter switches (blunt masters
        # that fan a toggle out to EVERY shutter at once).
        async_add_entities(GlobalDsToggle(hass, entry, d) for d in _GLOBAL_SWITCHES)
        return
    if module == const.MODULE_SHUTTER:
        descs = _SHUTTER_SWITCHES
    elif module == const.MODULE_CLIMATE:
        descs = _CLIMATE_SWITCHES
    else:
        descs = _VMC_SWITCHES
    async_add_entities(DsToggle(coordinator, entry, d) for d in descs)


class DsToggle(SwitchEntity, RestoreEntity):
    """A toggle backed by a coordinator attribute (shutter or VMC)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DsCoordinator, entry: ConfigEntry,
                 desc: _ToggleDesc) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._desc = desc
        self._attr_translation_key = desc.key   # name from translations (i18n)
        self._attr_icon = desc.icon
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._desc.setter(self._coordinator, last.state == "on")
        # A global switch on the "Común" screen may flip this coordinator's attr
        # directly; refresh our UI when it does so we don't show a stale state.
        self.async_on_remove(async_dispatcher_connect(
            self.hass, const.SIGNAL_DS_TOGGLES, self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return self._desc.getter(self._coordinator)

    async def async_turn_on(self, **kwargs) -> None:
        self._desc.setter(self._coordinator, True)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, const.SIGNAL_DS_TOGGLES)

    async def async_turn_off(self, **kwargs) -> None:
        self._desc.setter(self._coordinator, False)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, const.SIGNAL_DS_TOGGLES)


# Global shutter switches on the "Común" screen: (translation_key, coordinator
# attribute, icon). A curated subset that makes sense house-wide; the very
# per-shutter ones (privacy, lock, exclude-from-sim, follow-manual) stay local.
_GLOBAL_SWITCHES: tuple[tuple[str, str, str], ...] = (
    ("global_observe", "observe_enabled", "mdi:eye-outline"),
    ("global_weather_protect", "weather_protect", "mdi:weather-cloudy-alert"),
    ("global_heat_shield", "heat_shield_enabled", "mdi:sun-thermometer"),
    ("global_sun_shield", "sun_shield_enabled", "mdi:weather-sunny-alert"),
    ("global_night_iso", "night_iso_enabled", "mdi:weather-night"),
    ("global_dawn", "dawn_enabled", "mdi:weather-sunset-up"),
    ("global_geo_shade", "geo_shade_enabled", "mdi:sun-angle"),
    ("global_peak", "peak_enabled", "mdi:flash-alert"),
)


class GlobalDsToggle(SwitchEntity):
    """A blunt master toggle applied to EVERY shutter at once.

    ON sets the attribute True on all shutters, OFF sets it False on all. It does
    NOT remember each shutter's previous state (see the note sensor). ``is_on``
    reads True only when the function is on in every shutter, so the master
    reflects "all on"; any per-shutter switch flip updates it via the dispatcher.
    """

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 desc: tuple[str, str, str]) -> None:
        self._hass = hass
        key, attr, icon = desc
        self._attr = attr
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{const.DOMAIN}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, const.SHUTTERS_DEVICE_ID)},
            name="Dynamic Shutter · Común")

    def _shutters(self) -> list:
        from .coordinator import DsCoordinator
        return [co for co in self._hass.data.get(const.DOMAIN, {}).values()
                if isinstance(co, DsCoordinator)]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Reflect per-shutter flips (and the initial state) on this master.
        self.async_on_remove(async_dispatcher_connect(
            self.hass, const.SIGNAL_DS_TOGGLES, self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return bool(self._shutters())

    @property
    def is_on(self) -> bool:
        shutters = self._shutters()
        return bool(shutters) and all(getattr(co, self._attr) for co in shutters)

    async def _apply(self, value: bool) -> None:
        for co in self._shutters():
            setattr(co, self._attr, value)
            await co.async_request_refresh()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, const.SIGNAL_DS_TOGGLES)

    async def async_turn_on(self, **kwargs) -> None:
        await self._apply(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._apply(False)


# Master pause switches on the Zones (Dynamic Home) entry: (translation_key,
# coordinator attribute, icon). Global first so it reads as the master.
_PAUSE_SWITCHES: tuple[tuple[str, str, str], ...] = (
    ("pause_all", "pause_all", "mdi:pause-octagon"),
    ("pause_climate", "pause_climate", "mdi:thermostat-box"),
    ("pause_vmc", "pause_vmc", "mdi:fan-off"),
    ("pause_shutter", "pause_shutter", "mdi:window-shutter-alert"),
)


class ZonesPauseSwitch(SwitchEntity, RestoreEntity):
    """Master pause (global or per-module) on the Zones entry.

    On = that module(s) stop actuating hardware AND stop influencing the bus
    (compute + sensors stay alive). Off by default.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, key: str, attr: str,
                 icon: str) -> None:
        self._coordinator = coordinator
        self._attr = attr
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            setattr(self._coordinator, self._attr, last.state == "on")
            self._coordinator.publish_modes()

    @property
    def is_on(self) -> bool:
        return getattr(self._coordinator, self._attr)

    async def _set(self, value: bool) -> None:
        setattr(self._coordinator, self._attr, value)
        self._coordinator.publish_modes()       # propagate to the modules
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)


class PresenceSimSwitch(SwitchEntity, RestoreEntity):
    """House-level presence simulation toggle (on the Zones entry).

    When on and the house (or a zone) is in Away, the shutters mimic an occupant
    (day open / night close, jittered) instead of staying static. Off by default.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "presence_sim"
    _attr_icon = "mdi:account-clock"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_presence_sim"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._coordinator.presence_sim = last.state == "on"
            self._coordinator.publish_modes()

    @property
    def is_on(self) -> bool:
        return self._coordinator.presence_sim

    async def _set(self, value: bool) -> None:
        self._coordinator.presence_sim = value
        self._coordinator.publish_modes()       # propagate to the shutters
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
