"""Comfort↔Economy presets (F23) — pure helpers (no Home Assistant deps).

A single discrete dial — ``eco`` / ``balanced`` / ``comfort`` — that scales the
system's aggressiveness coherently across DC (climate) and DV (ventilation), by
scope: a house-wide level plus a per-zone override, resolved through the F24 zone
tree exactly like the F01 house mode. ``balanced`` is the neutral identity.

The per-level shifts are built in (predictable, REQ-CMF-1) and applied at runtime
on top of the user's config — they are not separately user-tunable. Eco widens the
comfort band, eases more at night, softens the lead and ventilates less; Comfort
does the opposite.
"""

from __future__ import annotations

try:                                # package (HA runtime) vs standalone (tests)
    from . import modes, zones
except ImportError:  # pragma: no cover
    import modes
    import zones

LEVELS = ["eco", "balanced", "comfort"]
AUTO = "auto"                       # a zone override of "auto" inherits the global


# --------------------------------------------------------------------------- #
# Scope resolution (mirrors modes.py)
# --------------------------------------------------------------------------- #
def effective_level(global_level: str, zone_override: str | None) -> str:
    """The level in force: the zone override unless auto/None, else the global."""
    if zone_override and zone_override != AUTO:
        return zone_override if zone_override in LEVELS else "balanced"
    return global_level if global_level in LEVELS else "balanced"


def effective_level_for_entry(tree: dict, global_level: str,
                              zone_levels: dict, entry_id: str) -> str:
    """Resolve a module's level from its zone (F24) and the per-zone overrides."""
    zid = zones.scope_for_module(tree, entry_id)["zone"]
    return effective_level(global_level, zone_levels.get(zid) if zid else None)


def effective_from_published(data: dict | None, entry_id: str) -> str:
    """Resolve a module's comfort level from the published DATA_MODE blob.

    Falls back to ``balanced``. F01 link (REQ-CMF-4): when the dial is left at the
    neutral ``balanced`` and the effective house mode is ``eco``, follow it to the
    eco preset (an explicit comfort/eco choice on the dial still wins).
    """
    if not data:
        return "balanced"
    level = effective_level_for_entry(
        data.get("tree") or {}, data.get("comfort", "balanced"),
        data.get("zone_comfort") or {}, entry_id)
    if level == "balanced" and modes.effective_from_published(data, entry_id) == "eco":
        return "eco"
    return level


# --------------------------------------------------------------------------- #
# Config shifts (built-in, coherent, bounded). balanced -> no-op.
# --------------------------------------------------------------------------- #
def apply_dc(cfg, level: str) -> None:
    """Shift a DcConfig for the comfort level (in place). balanced is identity."""
    if level == "eco":
        # Wider comfort band, more night easing, softer lead, less fidgeting.
        cfg.base_heat_day = max(cfg.target_min_heat, cfg.base_heat_day - 0.7)
        cfg.base_cool_day = min(cfg.target_max_cool, cfg.base_cool_day + 0.7)
        cfg.delta_night += 0.3
        cfg.lead_base_h *= 0.6
        cfg.trend_lead_h *= 0.6
        cfg.apply_min_delta += 0.2
    elif level == "comfort":
        # Tighter band, less night easing, more anticipation.
        cfg.base_heat_day = min(cfg.target_max_heat, cfg.base_heat_day + 0.5)
        cfg.base_cool_day = max(cfg.target_min_cool, cfg.base_cool_day - 0.5)
        cfg.delta_night *= 0.5
        cfg.lead_base_h *= 1.4
        cfg.trend_lead_h *= 1.4


def apply_dv(cfg, level: str) -> None:
    """Shift a DvConfig for the comfort level (in place). balanced is identity."""
    if level == "eco":
        # Ventilate less: raise the thresholds and the hysteresis band.
        cfg.co2_v2 += 150.0
        cfg.co2_v3 += 150.0
        cfg.pm_v2 += 5.0
        cfg.pm_v3 += 10.0
        cfg.co2_hys += 50.0
    elif level == "comfort":
        # Ventilate sooner: lower the thresholds (kept ordered and positive).
        cfg.co2_v2 = max(500.0, cfg.co2_v2 - 150.0)
        cfg.co2_v3 = max(cfg.co2_v2 + 100.0, cfg.co2_v3 - 150.0)
        cfg.pm_v2 = max(2.0, cfg.pm_v2 - 3.0)
        cfg.pm_v3 = max(cfg.pm_v2 + 5.0, cfg.pm_v3 - 10.0)


def apply_ds(cfg, level: str) -> None:
    """Shift a DsConfig for the comfort level (in place). balanced is identity.

    Scales the cooling-season solar aggressiveness: eco shades harder (less open
    against the sun -> less AC load), comfort favours light/views (opens more).
    """
    if level == "eco":
        cfg.heat_shield_pct = max(0, cfg.heat_shield_pct - 15)
        cfg.summer_min_open_pct = max(0, cfg.summer_min_open_pct - 10)
    elif level == "comfort":
        cfg.heat_shield_pct = min(100, cfg.heat_shield_pct + 15)
        cfg.summer_min_open_pct = min(100, cfg.summer_min_open_pct + 10)
