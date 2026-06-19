"""Dynamic Home — Home Assistant integration (DV ventilation PoC).

Sets up one VMC instance per config entry: a shared SDHB hub + a coordinator
driving a ``fan`` entity (and a few ``number`` tunables).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const
from .coordinator import DvCoordinator, SdhbHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dynamic Home from a config entry."""
    hub: SdhbHub = hass.data.setdefault(const.DOMAIN, {}).setdefault(
        "_hub", SdhbHub())

    coordinator = DvCoordinator(hass, entry, hub)
    coordinator.async_setup_listeners()
    await coordinator.async_config_entry_first_refresh()

    hass.data[const.DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, const.PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, const.PLATFORMS)
    if unloaded:
        hass.data[const.DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
