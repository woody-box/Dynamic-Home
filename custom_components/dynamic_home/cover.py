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
from homeassistant.helpers.event import async_track_state_change_event
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
        self._last_pos: int | None = None  # last position pushed to the hardware
        self._attr_unique_id = f"{entry.entry_id}_cover"
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dynamic Home",
            model="Dynamic Shutter",
        )

    async def async_added_to_hass(self) -> None:
        """Reflect the underlying cover's real position promptly when it moves."""
        await super().async_added_to_hass()
        target = self._entry.data.get(const.CONF_COVER)
        if target:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [target], self._on_real_cover_change))

    @callback
    def _on_real_cover_change(self, _event) -> None:
        self.async_write_ha_state()

    def _real_position(self) -> int | None:
        """Actual position reported by the physical cover (None if unknown)."""
        target = self._entry.data.get(const.CONF_COVER)
        if not target:
            return None
        st = self.hass.states.get(target)
        if st is None:
            return None
        pos = st.attributes.get("current_position")
        return int(pos) if pos is not None else None

    @property
    def _target_position(self) -> int | None:
        data = self.coordinator.data
        return data.pos if data else None

    @property
    def current_cover_position(self) -> int | None:
        # Report the REAL physical position; only fall back to the computed
        # target when the underlying cover gives no position feedback.
        real = self._real_position()
        return real if real is not None else self._target_position

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        return None if pos is None else pos == 0

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {"facade": self.coordinator.facade_key,
                 "target_position": self._target_position,
                 "peak_reason": self.coordinator.peak_reason}
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
        self._last_pos = position
        target = self._entry.data.get(const.CONF_COVER)
        # Observe (dry-run): track the target for display but never move the cover.
        if target and not self.coordinator.observe_enabled:
            await self.hass.services.async_call(
                "cover", "set_cover_position",
                {"entity_id": target, ATTR_POSITION: position}, blocking=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        # Only command the hardware when the target actually changed, so we
        # don't re-issue (and interrupt) the cover every cycle.
        if data is not None and data.pos != self._last_pos:
            self.hass.async_create_task(self._drive(data.pos))
        super()._handle_coordinator_update()
