"""Community changeover (F37) — pure seasonal water-mode resolver (no HA deps).

Many community/central radiant systems are **2-pipe changeover**: the building feeds
hot OR cold water to the whole installation by season, and the occupant only opens a
per-zone valve. A zone can't heat while the building supplies cold water, and one
zone can't run a different direction than another. So a single **house changeover
direction** (``heat`` / ``cool`` / ``off``) gates the community (central_shared) zones.

The direction is **manual or auto**: a manual selector (``auto``/``heat``/``cool``/
``off``) wins when set; in ``auto`` it is inferred from a supply-water temperature
sensor against two thresholds — hot water means heating is available, cold means
cooling, in between means the system is idle (shoulder season). With no sensor in
``auto`` the result is ``None`` (unknown) and nothing is gated, so a zone with no
changeover configured behaves exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

MANUAL_OPTIONS = ("auto", "heat", "cool", "off")


@dataclass
class ChangeoverConfig:
    """Supply-water thresholds (°C) that map temperature to a direction."""

    heat_above_c: float = 28.0       # supply >= this -> heating is available
    cool_below_c: float = 20.0       # supply <= this -> cooling is available
    hysteresis_c: float = 2.0        # stick to the current direction within this band


def resolve(manual: str, water_temp: float | None, cfg: ChangeoverConfig,
            prev: str | None = None) -> str | None:
    """Resolve the house changeover direction (``heat``/``cool``/``off``/``None``).

    In ``auto`` the supply-water temperature decides; ``prev`` (the previous resolved
    state) adds **hysteresis** so a temperature hovering near a threshold does not
    flap: once heating, it stays heating until the water drops a full
    ``hysteresis_c`` below ``heat_above_c`` (symmetric for cooling).
    """
    if manual in ("heat", "cool", "off"):
        return manual                                  # manual override wins
    if water_temp is None:
        return None                                    # unknown -> no gating
    h, c, hy = cfg.heat_above_c, cfg.cool_below_c, cfg.hysteresis_c
    if prev == "heat" and water_temp >= h - hy:
        return "heat"                                  # hold heat across the band
    if prev == "cool" and water_temp <= c + hy:
        return "cool"                                  # hold cool across the band
    if water_temp >= h:
        return "heat"
    if water_temp <= c:
        return "cool"
    return "off"                                       # shoulder season / idle


def effective(house_state: str | None, zone_override: str | None) -> str | None:
    """The changeover in force for a zone: its override unless ``auto``, else house."""
    if zone_override and zone_override != "auto":
        return zone_override
    return house_state
