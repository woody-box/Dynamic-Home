"""Zones coordinator (F24): parses the zone/group tree and publishes it.

Read-only and config-time: the tree only changes when the user edits the "Zones"
entry's options (which reloads the entry). It publishes the normalised tree to
``hass.data[DOMAIN][DATA_ZONES]`` so other modules (F01 mode-by-scope, F21, F25)
can resolve a module's zone/group via :func:`zones.scope_for_module`.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import const, zones

_LOGGER = logging.getLogger(__name__)


class ZonesCoordinator(DataUpdateCoordinator):
    """Holds the zone/group hierarchy and exposes it to the rest of the domain."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=f"{const.DOMAIN}_zones",
                         update_interval=None)   # config-time only, no polling
        self.entry = entry

    @property
    def tree(self) -> dict:
        return zones.normalize(self.entry.options.get(const.CONF_ZONES_TREE))

    async def _async_update_data(self) -> dict:
        tree = self.tree
        self.hass.data.setdefault(const.DOMAIN, {})[const.DATA_ZONES] = tree
        return tree
