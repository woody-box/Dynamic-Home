"""Dynamic Home — Home Assistant integration (DV ventilation + DS shutter).

Each config entry is one module instance (a VMC or a shutter), all sharing a
single in-memory SDHB hub so they can coordinate (e.g. a solar-shield intent).
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service as service_helper

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
    _async_register_services(hass)
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
        # Tear the services down with the last entry so they don't linger as
        # no-ops after the integration is fully removed.
        if not _entry_ids(hass):
            _async_unregister_services(hass)
    return unloaded


# --------------------------------------------------------------------------- #
# Services — registered once for the whole integration, targetable by
# entity / device / area. Each resolves the target(s) to the owning config
# entries and acts on their coordinators.
# --------------------------------------------------------------------------- #
def _entry_ids(hass: HomeAssistant) -> list[str]:
    """Config-entry ids currently loaded (skips the private ``_*`` book-keeping)."""
    return [k for k in hass.data.get(const.DOMAIN, {}) if not k.startswith("_")]


async def _coordinators_for_call(hass: HomeAssistant, call: ServiceCall) -> list:
    """Coordinators referenced by a service call's entity/device/area target."""
    data = hass.data.get(const.DOMAIN, {})
    entry_ids = await service_helper.async_extract_config_entry_ids(hass, call)
    return [data[eid] for eid in entry_ids if eid in data]


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.data[const.DOMAIN].get(const.DATA_SERVICES_REGISTERED):
        return

    async def _reset_learning(call: ServiceCall) -> None:
        for co in await _coordinators_for_call(hass, call):
            if isinstance(co, DcCoordinator):
                co.reset_learning()

    async def _set_observe(call: ServiceCall) -> None:
        enabled = call.data[const.ATTR_ENABLED]
        for co in await _coordinators_for_call(hass, call):
            co.observe_enabled = enabled
            await co.async_request_refresh()

    async def _reset_filter(call: ServiceCall) -> None:
        for co in await _coordinators_for_call(hass, call):
            if isinstance(co, DvCoordinator):
                co.reset_filter_hours()

    async def _recalibrate(call: ServiceCall) -> None:
        for co in await _coordinators_for_call(hass, call):
            await co.async_request_refresh()

    hass.services.async_register(
        const.DOMAIN, const.SERVICE_RESET_LEARNING, _reset_learning)
    hass.services.async_register(
        const.DOMAIN, const.SERVICE_SET_OBSERVE, _set_observe,
        schema=vol.Schema({vol.Required(const.ATTR_ENABLED): cv.boolean},
                          extra=vol.ALLOW_EXTRA))
    hass.services.async_register(
        const.DOMAIN, const.SERVICE_RESET_FILTER, _reset_filter)
    hass.services.async_register(
        const.DOMAIN, const.SERVICE_RECALIBRATE, _recalibrate)
    hass.data[const.DOMAIN][const.DATA_SERVICES_REGISTERED] = True


def _async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (const.SERVICE_RESET_LEARNING, const.SERVICE_SET_OBSERVE,
                const.SERVICE_RESET_FILTER, const.SERVICE_RECALIBRATE):
        hass.services.async_remove(const.DOMAIN, svc)
    hass.data[const.DOMAIN].pop(const.DATA_SERVICES_REGISTERED, None)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply option changes by refreshing — NOT reloading.

    The coordinators read options live each cycle, so a refresh picks up new
    thresholds immediately without throwing away runtime state (EMA, failsafe
    counters, trend history).
    """
    coordinator = hass.data[const.DOMAIN].get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_request_refresh()
