"""Button platform — VMC maintenance actions (DV) + shutter resume-auto (DS)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const
from .coordinator import DvCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[const.DOMAIN][entry.entry_id]
    module = entry.data.get(const.CONF_MODULE)
    if module == const.MODULE_SHUTTER:
        async_add_entities([ResumeAutoButton(coordinator, entry)])
        return
    if module == const.MODULE_SHUTTER_COMMON:
        async_add_entities([GlobalResumeAutoButton(hass, entry)])
        return
    async_add_entities([FilterResetButton(coordinator, entry)])


class GlobalResumeAutoButton(ButtonEntity):
    """Clears the manual hold on EVERY shutter (whole-house "back to auto")."""

    _attr_has_entity_name = True
    _attr_translation_key = "global_resume_auto"
    _attr_icon = "mdi:autorenew"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._attr_unique_id = f"{const.DOMAIN}_global_resume_auto"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, const.SHUTTERS_DEVICE_ID)},
            name="Dynamic Shutter · Común")

    async def async_press(self) -> None:
        from .coordinator import DsCoordinator
        for co in self._hass.data.get(const.DOMAIN, {}).values():
            if isinstance(co, DsCoordinator):
                co.clear_manual_override()


class ResumeAutoButton(ButtonEntity):
    """Clears the manual hold so the shutter goes back to automatic control."""

    _attr_has_entity_name = True
    _attr_translation_key = "resume_auto"
    _attr_icon = "mdi:autorenew"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_resume_auto"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        self._coordinator.clear_manual_override()


class FilterResetButton(ButtonEntity):
    """Resets the filter-hours counter."""

    _attr_has_entity_name = True
    _attr_name = "Reset filter hours"
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_filter_reset"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        self._coordinator.reset_filter_hours()
