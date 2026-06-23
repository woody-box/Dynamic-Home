"""Select platform — house modes (F01), on the Zones entry.

A house-wide mode plus one override per zone. Each select writes its value to the
ZonesCoordinator and republishes the resolved modes (which nudges every module to
re-evaluate). Both are restored across restarts.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import changeover, comfort, const, modes
from .coordinator_zones import ZonesCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(const.CONF_MODULE) != const.MODULE_ZONES:
        return
    coordinator: ZonesCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    ents: list[SelectEntity] = [HouseModeSelect(coordinator, entry),
                                GlobalComfortSelect(coordinator, entry),
                                ChangeoverSelect(coordinator, entry)]
    for zid, z in coordinator.tree["zones"].items():
        ents.append(ZoneModeSelect(coordinator, entry, zid, z["name"]))
        ents.append(ZoneComfortSelect(coordinator, entry, zid, z["name"]))
    async_add_entities(ents)


class ChangeoverSelect(RestoreEntity, SelectEntity):
    """F37: the community changeover direction (auto follows the supply water)."""

    _attr_has_entity_name = True
    _attr_name = "Changeover (agua)"
    _attr_icon = "mdi:sun-snowflake-variant"
    _attr_translation_key = "changeover"
    _attr_options = list(changeover.MANUAL_OPTIONS)

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry) -> None:
        self._co = coordinator
        self._attr_unique_id = f"{entry.entry_id}_changeover"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in changeover.MANUAL_OPTIONS:
            self._co.changeover_manual = last.state
        self._co.publish_changeover(notify=False)

    @property
    def current_option(self) -> str:
        return self._co.changeover_manual

    async def async_select_option(self, option: str) -> None:
        self._co.changeover_manual = option
        self.async_write_ha_state()
        self._co.publish_changeover()


class HouseModeSelect(RestoreEntity, SelectEntity):
    """The house-wide mode."""

    _attr_has_entity_name = True
    _attr_name = "Modo casa"
    _attr_icon = "mdi:home-account"
    _attr_translation_key = "house_mode"
    _attr_options = modes.MODES

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry) -> None:
        self._co = coordinator
        self._attr_unique_id = f"{entry.entry_id}_house_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in modes.MODES:
            self._co.house_mode = last.state
        self._co.publish_modes(notify=False)

    @property
    def current_option(self) -> str:
        return self._co.house_mode

    async def async_select_option(self, option: str) -> None:
        self._co.house_mode = option
        self.async_write_ha_state()
        self._co.publish_modes()


class ZoneModeSelect(RestoreEntity, SelectEntity):
    """Per-zone override (``auto`` inherits the house mode)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:home-floor-a"
    _attr_translation_key = "zone_mode"
    _attr_options = [modes.AUTO, *modes.MODES]

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry,
                 zid: str, name: str) -> None:
        self._co = coordinator
        self._zid = zid
        self._attr_name = f"Modo {name}"
        self._attr_unique_id = f"{entry.entry_id}_mode_{zid}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        state = last.state if last else modes.AUTO
        self._co.zone_modes[self._zid] = (
            state if state in self._attr_options else modes.AUTO)
        self._co.publish_modes(notify=False)

    @property
    def current_option(self) -> str:
        return self._co.zone_modes.get(self._zid, modes.AUTO)

    async def async_select_option(self, option: str) -> None:
        self._co.zone_modes[self._zid] = option
        self.async_write_ha_state()
        self._co.publish_modes()


class GlobalComfortSelect(RestoreEntity, SelectEntity):
    """The house-wide comfort↔economy preset (F23)."""

    _attr_has_entity_name = True
    _attr_name = "Confort casa"
    _attr_icon = "mdi:scale-balance"
    _attr_translation_key = "comfort"
    _attr_options = comfort.LEVELS

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry) -> None:
        self._co = coordinator
        self._attr_unique_id = f"{entry.entry_id}_comfort"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in comfort.LEVELS:
            self._co.comfort_global = last.state
        self._co.publish_modes(notify=False)

    @property
    def current_option(self) -> str:
        return self._co.comfort_global

    async def async_select_option(self, option: str) -> None:
        self._co.comfort_global = option
        self.async_write_ha_state()
        self._co.publish_modes()


class ZoneComfortSelect(RestoreEntity, SelectEntity):
    """Per-zone comfort override (``auto`` inherits the house preset)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:scale-balance"
    _attr_translation_key = "zone_comfort"
    _attr_options = [comfort.AUTO, *comfort.LEVELS]

    def __init__(self, coordinator: ZonesCoordinator, entry: ConfigEntry,
                 zid: str, name: str) -> None:
        self._co = coordinator
        self._zid = zid
        self._attr_name = f"Confort {name}"
        self._attr_unique_id = f"{entry.entry_id}_comfort_{zid}"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        state = last.state if last else comfort.AUTO
        self._co.zone_comfort[self._zid] = (
            state if state in self._attr_options else comfort.AUTO)
        self._co.publish_modes(notify=False)

    @property
    def current_option(self) -> str:
        return self._co.zone_comfort.get(self._zid, comfort.AUTO)

    async def async_select_option(self, option: str) -> None:
        self._co.zone_comfort[self._zid] = option
        self.async_write_ha_state()
        self._co.publish_modes()
