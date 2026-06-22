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

from . import comfort, const, events, modes, zones

_LOGGER = logging.getLogger(__name__)


class ZonesCoordinator(DataUpdateCoordinator):
    """Holds the zone/group hierarchy + house modes, and publishes them."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=f"{const.DOMAIN}_zones",
                         update_interval=None)   # config-time only, no polling
        self.entry = entry
        # F01: house mode + per-zone overrides (set/restored by the select entities).
        self.house_mode = "home"
        self.zone_modes: dict[str, str] = {}
        # F23: comfort↔economy preset (global + per-zone overrides), same selects.
        self.comfort_global = "balanced"
        self.zone_comfort: dict[str, str] = {}

    @property
    def tree(self) -> dict:
        return zones.normalize(self.entry.options.get(const.CONF_ZONES_TREE))

    @property
    def mode_caps(self) -> dict:
        caps = dict(modes.DEFAULT_CAPS)
        caps.update(self.entry.options.get(const.CONF_MODE_CAPS) or {})
        return caps

    def effective_for(self, entry_id: str) -> str:
        """The mode in force for a module entry (zone override ?? house)."""
        return modes.effective_mode_for_entry(
            self.tree, self.house_mode, self.zone_modes, entry_id)

    def effective_comfort_for(self, entry_id: str) -> str:
        """The comfort level in force for a module entry (F23)."""
        return comfort.effective_level_for_entry(
            self.tree, self.comfort_global, self.zone_comfort, entry_id)

    def publish_modes(self, notify: bool = True) -> None:
        """Publish the resolved modes + comfort for consumers, and nudge modules."""
        data = self.hass.data.setdefault(const.DOMAIN, {})
        data[const.DATA_MODE] = {"house": self.house_mode,
                                 "zones": dict(self.zone_modes),
                                 "caps": self.mode_caps, "tree": self.tree,
                                 "comfort": self.comfort_global,
                                 "zone_comfort": dict(self.zone_comfort)}
        events.fire_mode_changed(self.hass, self.entry, self.house_mode,
                                 self.zone_modes)
        if notify:                          # re-evaluate every module right away
            for key, co in list(data.items()):
                if not key.startswith("_") and co is not self \
                        and hasattr(co, "async_request_refresh"):
                    self.hass.async_create_task(co.async_request_refresh())

    async def _async_update_data(self) -> dict:
        tree = self.tree
        self.hass.data.setdefault(const.DOMAIN, {})[const.DATA_ZONES] = tree
        self.publish_modes(notify=False)
        return tree
