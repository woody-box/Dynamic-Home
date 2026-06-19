"""Button platform — VMC maintenance actions (DV)."""

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
    coordinator: DvCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([FilterResetButton(coordinator, entry)])


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
