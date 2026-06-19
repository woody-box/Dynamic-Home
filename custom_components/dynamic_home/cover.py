"""Cover platform — the managed shutter (DS).

Represents one window. In auto it drives the underlying physical cover to the
position decided by the DS engine (and the shared SDHB bus); manual
``set_cover_position`` passes straight through to the underlying cover.
"""

from __future__ import annotations

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import DsCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DsCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities([DsCover(coordinator, entry)])


class DsCover(CoordinatorEntity[DsCoordinator], CoverEntity):
    """Managed shutter driven by the DS cascade."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator: DsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_cover"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dynamic Home",
            model="Dynamic Shutter",
        )

    @property
    def current_cover_position(self) -> int | None:
        data = self.coordinator.data
        return data.pos if data else None

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        return None if pos is None else pos == 0

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {"facade": self.coordinator.facade_key}
        data = self.coordinator.data
        if data:
            attrs["reason"] = data.reason
            attrs.update(data.details)
        return attrs

    # --- commands pass through to the underlying cover ---
    async def async_set_cover_position(self, **kwargs) -> None:
        await self._drive(kwargs[ATTR_POSITION])

    async def async_open_cover(self, **kwargs) -> None:
        await self._drive(100)

    async def async_close_cover(self, **kwargs) -> None:
        await self._drive(0)

    async def _drive(self, position: int) -> None:
        target = self._entry.data.get(const.CONF_COVER)
        if target:
            await self.hass.services.async_call(
                "cover", "set_cover_position",
                {"entity_id": target, ATTR_POSITION: position}, blocking=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not None:
            self.hass.async_create_task(self._drive(data.pos))
        super()._handle_coordinator_update()
