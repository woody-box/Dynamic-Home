"""House modes (F01) — pure helpers (no Home Assistant dependencies).

A "mode" (Home/Away/Sleep/Boost/Eco) biases every module at once, by scope: a
house-wide mode plus a per-zone override (resolved through the F24 zone tree).
The coordinator publishes the resolved per-module mode; each module reads its
effective mode and applies its own behaviour (DV speed cap, DC vacation, …).
"""

from __future__ import annotations

try:                                # package (HA runtime) vs standalone (tests)
    from . import zones
except ImportError:  # pragma: no cover
    import zones

MODES = ["home", "away", "sleep", "boost", "eco"]
AUTO = "auto"                       # a zone override of "auto" inherits the house

# Default VMC speed cap per mode (0..3; None = no cap). Boost forces V3 separately.
DEFAULT_CAPS = {"home": None, "eco": 2, "sleep": 1, "away": 1, "boost": None}


def effective_mode(house: str, zone_override: str | None) -> str:
    """The mode in force: the zone override unless it is auto/None, else house."""
    if zone_override and zone_override != AUTO:
        return zone_override
    return house if house in MODES else "home"


def effective_mode_for_entry(tree: dict, house: str, zone_modes: dict,
                             entry_id: str) -> str:
    """Resolve a module's mode from its zone (F24) and the per-zone overrides."""
    zid = zones.scope_for_module(tree, entry_id)["zone"]
    return effective_mode(house, zone_modes.get(zid) if zid else None)


def effective_from_published(data: dict | None, entry_id: str) -> str:
    """Resolve a module's mode from the published DATA_MODE blob (or 'home')."""
    if not data:
        return "home"
    return effective_mode_for_entry(data.get("tree") or {},
                                    data.get("house", "home"),
                                    data.get("zones") or {}, entry_id)


def dv_cap(mode: str, caps: dict | None = None) -> int | None:
    """VMC speed cap for a mode (None = uncapped)."""
    return (caps or DEFAULT_CAPS).get(mode)


def is_away(mode: str) -> bool:
    return mode == "away"


def is_boost(mode: str) -> bool:
    return mode == "boost"


def is_paused(data: dict | None, module: str) -> bool:
    """Master pause for a module: the global switch or its own (from DATA_MODE).

    ``module`` is the pause key: ``climate`` / ``vmc`` / ``shutter``.
    """
    p = (data or {}).get("pause") or {}
    return bool(p.get("all") or p.get(module))
