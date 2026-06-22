"""Zone/group hierarchy (F24) — pure helpers (no Home Assistant dependencies).

Dynamic Home's own zone → group → house structure (not HA Areas). The whole tree
lives in the "Zones" config entry's options; these helpers build, validate and
query it. Consumers (F01 mode-by-scope, F21 profiles, F25 emitter scope) read the
published tree and resolve a module's zone/group via :func:`scope_for_module`.

Tree shape::

    {"zones":  {zid: {"name": str, "modules": [entry_id, ...]}},
     "groups": {gid: {"name": str, "zones":   [zid, ...]}}}
"""

from __future__ import annotations

import re


def slug(name: str) -> str:
    """A stable id from a display name (lowercase, alnum + underscores)."""
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return s or "x"


def normalize(tree: dict | None) -> dict:
    """Return a well-formed tree (missing keys defaulted, members de-duplicated)."""
    tree = tree or {}
    zones, groups = {}, {}
    for zid, z in (tree.get("zones") or {}).items():
        z = z or {}
        zones[zid] = {"name": z.get("name", zid),
                      "modules": list(dict.fromkeys(z.get("modules") or []))}
    for gid, g in (tree.get("groups") or {}).items():
        g = g or {}
        groups[gid] = {"name": g.get("name", gid),
                       "zones": list(dict.fromkeys(g.get("zones") or []))}
    return {"zones": zones, "groups": groups}


def add_zone(tree: dict, name: str) -> dict:
    tree = normalize(tree)
    tree["zones"].setdefault(slug(name), {"name": name, "modules": []})
    return tree


def add_group(tree: dict, name: str) -> dict:
    tree = normalize(tree)
    tree["groups"].setdefault(slug(name), {"name": name, "zones": []})
    return tree


def remove_zone(tree: dict, zid: str) -> dict:
    tree = normalize(tree)
    tree["zones"].pop(zid, None)
    for g in tree["groups"].values():           # drop it from any group too
        g["zones"] = [z for z in g["zones"] if z != zid]
    return tree


def remove_group(tree: dict, gid: str) -> dict:
    tree = normalize(tree)
    tree["groups"].pop(gid, None)
    return tree


def assign_modules(tree: dict, zid: str, modules: list[str]) -> dict:
    """Set a zone's modules, evicting them from any other zone (1 module → 1 zone)."""
    tree = normalize(tree)
    if zid not in tree["zones"]:
        return tree
    chosen = list(dict.fromkeys(modules))
    for other, z in tree["zones"].items():
        if other != zid:
            z["modules"] = [m for m in z["modules"] if m not in chosen]
    tree["zones"][zid]["modules"] = chosen
    return tree


def assign_zones(tree: dict, gid: str, zones: list[str]) -> dict:
    """Set a group's zones, evicting them from any other group (1 zone → 1 group)."""
    tree = normalize(tree)
    if gid not in tree["groups"]:
        return tree
    chosen = [z for z in dict.fromkeys(zones) if z in tree["zones"]]
    for other, g in tree["groups"].items():
        if other != gid:
            g["zones"] = [z for z in g["zones"] if z not in chosen]
    tree["groups"][gid]["zones"] = chosen
    return tree


def scope_for_module(tree: dict, entry_id: str) -> dict:
    """The zone and group a module belongs to (ids or None). API for F01/F21/F25."""
    tree = normalize(tree)
    zone = next((zid for zid, z in tree["zones"].items()
                 if entry_id in z["modules"]), None)
    group = None
    if zone is not None:
        group = next((gid for gid, g in tree["groups"].items()
                      if zone in g["zones"]), None)
    return {"zone": zone, "group": group}


def counts(tree: dict) -> tuple[int, int, int]:
    """(n_zones, n_groups, n_assigned_modules)."""
    tree = normalize(tree)
    assigned = sum(len(z["modules"]) for z in tree["zones"].values())
    return len(tree["zones"]), len(tree["groups"]), assigned
