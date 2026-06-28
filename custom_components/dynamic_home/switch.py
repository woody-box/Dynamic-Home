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

    @property
    def is_on(self) -> bool:
        return self._desc.getter(self._coordinator)

    async def async_turn_on(self, **kwargs) -> None:
        self._desc.setter(self._coordinator, True)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._desc.setter(self._coordinator, False)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()
