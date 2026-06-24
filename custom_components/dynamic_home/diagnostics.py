"""Config-entry diagnostics — downloadable JSON snapshot per module.

Home Assistant's standard diagnostics platform (Settings → Devices & Services →
the device → ⋮ → *Download diagnostics*). Gives a "save"/export of a module: its
configured sources, the tuned **option values** and a snapshot of the live computed
state (decision, profile, energy). Numbers and entity ids only — never a secret —
so it is safe to share when reporting an issue.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import const

# Nothing here is a credential (entity ids + numbers). Kept for forward-safety so a
# future sensitive field can be added in one place.
TO_REDACT: set[str] = set()

# Best-effort live state, dumped only when present on the coordinator (each module
# type exposes a different subset — getattr keeps this decoupled).
_SNAPSHOT_ATTRS = (
    "_module", "degraded", "in_grace",
    "energy_kwh", "power_w",
    "hvac_mode", "current_speed",
    "anticycle_enabled", "anticycle_hold", "anticycle_reason",
    "peak_enabled", "peak_hold", "peak_reason",
    "house_kwh", "house_cost", "house_power_w", "context",
)


def _jsonable(value: Any) -> Any:
    """Coerce a value into something JSON-serialisable (dataclass -> dict)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return dataclasses.asdict(value)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, (str, int, float, bool, type(None), dict, list)):
        return value
    return str(value)


def _coordinator_snapshot(co: Any) -> dict[str, Any]:
    """Curated, JSON-safe snapshot of a coordinator's live computed state."""
    snap: dict[str, Any] = {}
    for attr in _SNAPSHOT_ATTRS:
        if hasattr(co, attr):
            snap[attr] = _jsonable(getattr(co, attr))
    # The latest decision (DataUpdateCoordinator.data) and the F26 profile, if any.
    if getattr(co, "data", None) is not None:
        snap["decision"] = _jsonable(co.data)
    try:
        profile = getattr(co, "install_profile", None)
    except Exception:  # noqa: BLE001 — a property may read state; never break export
        profile = None
    if profile is not None:
        snap["install_profile"] = _jsonable(profile)
    return snap


async def async_get_config_entry_diagnostics(
        hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return a redacted diagnostics snapshot for one Dynamic Home module."""
    co = hass.data.get(const.DOMAIN, {}).get(entry.entry_id)
    return {
        "entry": {
            "title": entry.title,
            "module": entry.data.get(const.CONF_MODULE),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": _coordinator_snapshot(co) if co is not None else None,
    }
