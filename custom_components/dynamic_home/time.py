"""Time platform — VMC weekly-schedule window (DV).

Two times (on / off) applied every day; the schedule gate is enabled by the
"Schedule" switch. Restored across restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from collections.abc import Callable

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import const
from .coordinator import DvCoordinator


@dataclass(frozen=True)
class _TimeDesc:
    key: str
    name: str
    icon: str
    getter: Callable[[DvCoordinator], dtime]
    setter: Callable[[DvCoordinator, dtime], None]


_TIMES: tuple[_TimeDesc, ...] = (
    _TimeDesc("schedule_on", "Schedule on", "mdi:clock-start",
              lambda c: c.schedule_on,
              lambda c, v: setattr(c, "schedule_on", v)),
    _TimeDesc("schedule_off", "Schedule off", "mdi:clock-end",
              lambda c: c.schedule_off,
              lambda c, v: setattr(c, "schedule_off", v)),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: DvCoordinator = hass.data[const.DOMAIN][entry.entry_id]
    async_add_entities(ScheduleTime(coordinator, entry, d) for d in _TIMES)


class ScheduleTime(TimeEntity, RestoreEntity):
    """A schedule boundary time backed by the coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DvCoordinator, entry: ConfigEntry,
                 desc: _TimeDesc) -> None:
        self._coordinator = coordinator
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
            try:
                h, m, *_ = last.state.split(":")
                self._desc.setter(self._coordinator, dtime(int(h), int(m)))
            except (ValueError, AttributeError):
                pass

    @property
    def native_value(self) -> dtime:
        return self._desc.getter(self._coordinator)

    async def async_set_value(self, value: dtime) -> None:
        self._desc.setter(self._coordinator, value)
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()
