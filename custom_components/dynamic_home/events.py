"""Native Home Assistant events fired by Dynamic Home.

A thin glue layer between the pure coordinators and the HA event bus. Keeping
the firing here — instead of inline in each coordinator — gives one place that
owns the event names and payload schema, and a single seam to test against.

All events carry a common envelope (``entry_id``, ``name``, ``module``) so a
dashboard automation can branch on the originating module without parsing the
event type.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const


def _base(entry: ConfigEntry, module: str) -> dict:
    return {"entry_id": entry.entry_id, "name": entry.title, "module": module}


def fire_degraded(hass: HomeAssistant, entry: ConfigEntry, module: str,
                  degraded: bool, missing: list[str]) -> None:
    """A module entered (or left) the degraded state (a core source is missing)."""
    data = _base(entry, module)
    data["degraded"] = degraded
    data["missing"] = list(missing)
    hass.bus.async_fire(const.EVENT_DEGRADED, data)


def fire_conflict(hass: HomeAssistant, entry: ConfigEntry, module: str,
                  explain: dict) -> None:
    """The winning bus intent for this consumer changed.

    ``explain`` is the dict returned by :meth:`bus.SdhbHub.explain`
    (winner / source / priority / candidates / reason).
    """
    data = _base(entry, module)
    data.update(explain)
    hass.bus.async_fire(const.EVENT_CONFLICT, data)


def fire_mold(hass: HomeAssistant, entry: ConfigEntry, module: str,
              active: bool, index: float) -> None:
    """The zone's mold-risk index armed/disarmed (fired once per transition)."""
    data = _base(entry, module)
    data["active"] = active
    data["index"] = round(index, 1)
    hass.bus.async_fire(const.EVENT_MOLD, data)


def fire_mode_changed(hass: HomeAssistant, entry: ConfigEntry,
                      house: str, zone_modes: dict) -> None:
    """The house mode or a zone override changed (F01)."""
    data = _base(entry, "zones")
    data["house"] = house
    data["zones"] = dict(zone_modes)
    hass.bus.async_fire(const.EVENT_MODE_CHANGED, data)


def fire_adjacent(hass: HomeAssistant, entry: ConfigEntry, module: str,
                  advice: str, dt: float) -> None:
    """Adjacent warm-space advisory changed (F31): open_gain / close_alarm / none."""
    data = _base(entry, module)
    data["advice"] = advice
    data["dt"] = round(dt, 1)
    hass.bus.async_fire(const.EVENT_ADJACENT, data)


def fire_window(hass: HomeAssistant, entry: ConfigEntry, module: str,
                inferred: bool, trend_cph: float) -> None:
    """An open window was inferred from temperature (or cleared) — F20."""
    data = _base(entry, module)
    data["inferred"] = inferred
    data["trend_cph"] = round(trend_cph, 2)
    hass.bus.async_fire(const.EVENT_WINDOW, data)


def fire_filter_due(hass: HomeAssistant, entry: ConfigEntry, module: str,
                    pct: float, hours: float, life: float) -> None:
    """The VMC filter crossed the replacement threshold (fired once per crossing)."""
    data = _base(entry, module)
    data["pct"] = round(pct, 1)
    data["hours"] = round(hours, 1)
    data["life"] = life
    hass.bus.async_fire(const.EVENT_FILTER_DUE, data)
