"""Switch platform — shutter override/privacy toggles (DS).

- Privacy: clamp the shutter to a privacy position while on.
- Lock: pin the shutter at the lock position (manual override) while on.

Both feed the DS engine inputs and are restored across restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import const
from .coordinator import DsCoordinator


@dataclass(frozen=True)
class _ToggleDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DsCoordinator], bool]
    setter: Callable[[DsCoordinator, bool], None]


_SWITCHES: tuple[_ToggleDesc, ...] = (
    _ToggleDesc(
        "privacy", "Privacy", "mdi:blinds-horizontal",
        lambda c: c.privacy_enabled,
        lambda c, v: setattr(c, "privacy_enabled", v)),
    _ToggleDesc(
        "lock", "Lock", "mdi:lock",
        lambda c: c.lock_enabled,
        lambda c, v: setattr(c, "lock_enabled", v)),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DsCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities(DsToggle(coordinator, entry, d) for d in _SWITCHES)


class DsToggle(SwitchEntity, RestoreEntity):
    """A shutter override/privacy toggle backed by the coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DsCoordinator, entry: ConfigEntry,
                 desc: _ToggleDesc) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._desc = desc
        self._attr_name = desc.name
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
