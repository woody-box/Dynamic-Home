"""Dynamic Home — Home Assistant integration (DV ventilation + DS shutter).

Each config entry is one module instance (a VMC or a shutter), all sharing a
single in-memory SDHB hub so they can coordinate (e.g. a solar-shield intent).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const
from .coordinator import DcCoordinator, DsCoordinator, DvCoordinator, SdhbHub


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

    facades: dict = hass.data[const.DOMAIN].setdefault("_facades", {})

    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_SHUTTER:
        coordinator = DsCoordinator(hass, entry, hub)
        # Register this shutter's facade so climate zones can target it.
        facades[entry.entry_id] = {
            "key": coordinator.facade_key,
            "az": float(entry.data.get(const.CONF_FACADE_AZIMUTH, 0)),
            "span": coordinator.facade_span,
        }
    elif module == const.MODULE_CLIMATE:
        coordinator = DcCoordinator(hass, entry, hub)
    else:
        coordinator = DvCoordinator(hass, entry, hub)
        coordinator.async_setup_listeners()
    await coordinator.async_config_entry_first_refresh()

    hass.data[const.DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, _platforms(entry))
    if unloaded:
        coordinator = hass.data[const.DOMAIN].get(entry.entry_id)
        # A climate zone must release its bus intents so shutters don't stay
        # clamped to a ghost solar-shield after the zone is removed/reloaded.
        if isinstance(coordinator, DcCoordinator):
            coordinator.clear_published()
        hass.data[const.DOMAIN].pop(entry.entry_id, None)
        hass.data[const.DOMAIN].get("_facades", {}).pop(entry.entry_id, None)
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply option changes by refreshing — NOT reloading.

    The coordinators read options live each cycle, so a refresh picks up new
    thresholds immediately without throwing away runtime state (EMA, failsafe
    counters, trend history).
    """
    coordinator = hass.data[const.DOMAIN].get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_request_refresh()
