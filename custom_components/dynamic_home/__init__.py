"""Dynamic Home — Home Assistant integration (DV ventilation + DS shutter).

Each config entry is one module instance (a VMC or a shutter), all sharing a
single in-memory SDHB hub so they can coordinate (e.g. a solar-shield intent).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const
from .coordinator import DvCoordinator, DsCoordinator, DcCoordinator, SdhbHub


def _platforms(entry: ConfigEntry) -> list[str]:
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_SHUTTER:
        return const.PLATFORMS_SHUTTER
    if module == const.MODULE_CLIMATE:
        return const.PLATFORMS_CLIMATE
    return const.PLATFORMS_VMC


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dynamic Home from a config entry."""
    hub: SdhbHub = hass.data.setdefault(const.DOMAIN, {}).setdefault(
        "_hub", SdhbHub())

    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_SHUTTER:
        coordinator = DsCoordinator(hass, entry, hub)
    elif module == const.MODULE_CLIMATE:
        coordinator = DcCoordinator(hass, entry, hub)
    else:
        coordinator = DvCoordinator(hass, entry, hub)
        coordinator.async_setup_listeners()
    await coordinator.async_config_entry_first_refresh()

    hass.data[const.DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, _platforms(entry))
    if unloaded:
        hass.data[const.DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
