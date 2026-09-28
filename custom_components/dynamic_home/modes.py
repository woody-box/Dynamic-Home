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


def in_window(minute_of_day: int, start: int | None, end: int | None) -> bool:
    """Whether ``minute_of_day`` is inside [start, end) (wraps midnight).

    No schedule (either end None) or start == end -> never inside.
    """
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


# Manual picks a sleep-schedule edge hands back to the schedule. Long-lived
# choices (away / eco / boost) are left alone.
SCHEDULE_AXIS = ("home", "sleep")


def schedule_step(manual: str, in_now: bool,
                  prev_in: bool | None) -> tuple[str, str]:
    """One tick of a zone's sleep schedule -> ``(manual, published)``.

    The zone's manual pick wins until the next window edge; the edge (entering
    or leaving the window) returns a home/sleep pick to ``auto`` so the schedule
    governs again. While ``auto``, inside the window publishes ``sleep``,
    outside inherits the house (``auto``). ``prev_in`` None = first reading
    (a restart): never an edge, so a restored manual pick survives.
    """
    if prev_in is not None and prev_in != in_now and manual in SCHEDULE_AXIS:
        manual = AUTO
    if manual != AUTO:
        return manual, manual
    return manual, ("sleep" if in_now else AUTO)


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
