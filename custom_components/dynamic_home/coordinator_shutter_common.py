"""Coordinator for the auto-created "Dynamic Shutter · Común" entry.

Minimal by design: it owns no hardware. It just ticks so the house-wide shutter
count sensors re-arm their cover tracking (catching shutters added/removed since
the last cycle), and it offers helpers the global switches use to fan a toggle
out to every DS coordinator at once.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import const

_LOGGER = logging.getLogger(__name__)


class ShutterCommonCoordinator(DataUpdateCoordinator):
    """House-wide shutter summary: fan-out helpers (no hardware, no polling).

    No update_interval: it owns no data of its own. The count sensors stay live
    from the shutters' cover listeners plus the SIGNAL_DS_COVERS dispatcher each
    DS coordinator fires on its tick — so there is no idle timer to leak.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=f"{const.DOMAIN}_shutter_common")
        self.entry = entry
        self.mirrors_enabled = False   # unused here; set by __init__ uniformly

    def ds_coordinators(self) -> list:
        """Every live DS (shutter) coordinator in the house."""
        from .coordinator import DsCoordinator
        return [co for co in self.hass.data.get(const.DOMAIN, {}).values()
                if isinstance(co, DsCoordinator)]

    async def _async_update_data(self) -> int:
        return len(self.ds_coordinators())
