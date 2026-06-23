"""Emitter catalogue (F25) — pure per-zone emitter list (no HA deps).

A climate (DC) zone keeps ONE brain (``dc_engine.decide``) but may drive **several
emitters**: e.g. underfloor radiant as the heating primary and an AC split as the
cooling primary / heating support. Each emitter declares its own F26 triple
(generator/distribution/emission, reused from :mod:`install`) and the real device it
drives — a ``climate`` entity and/or a bare ``switch``/valve — plus its role per mode
(primary in heat and/or cool) and, for ducted units shared across a group, its scope
and shared-channel ownership.

This module is the pure schema + role resolution; the staging state machine lives in
:mod:`staging` and the shared-duct reconciler in :mod:`shared_emitter`. A zone with no
emitter list keeps the legacy single-device behaviour (REQ-EMI-7), so :func:`is_multi`
is the back-compat gate the coordinator/entity check before taking the new path.
"""

from __future__ import annotations

from .zones import slug

# Emitter scope (REQ-EMI-4): a per-room device, a shared un-zoned duct, or a shared
# duct with per-zone motorized grilles ("air valve").
_SCOPES = ("zone", "group_unzoned", "group_grilles")
# Reconciliation policy for a shared un-zoned duct (REQ-EMI-5). Weighted is the
# default; worst-stuck is offered but never the default (pendulum/undershoot risk).
POLICIES = ("weighted", "mean", "priority", "worst_stuck")


def has_device(emitter: dict) -> bool:
    """Whether the emitter drives a real device (a climate entity or a switch)."""
    return bool(emitter.get("climate") or emitter.get("switch"))


def normalize(raw) -> list[dict]:
    """Return a well-formed emitter list (defaults filled, ids unique)."""
    out: list[dict] = []
    seen: set[str] = set()
    for i, e in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or f"Emitter {i + 1}")
        eid = str(e.get("id") or slug(name))
        base, n = eid, 2
        while eid in seen:                          # de-duplicate ids
            eid, n = f"{base}_{n}", n + 1
        seen.add(eid)
        scope = e.get("scope") if e.get("scope") in _SCOPES else "zone"
        out.append({
            "id": eid,
            "name": name,
            "generator": e.get("generator") or "",
            "distribution": e.get("distribution") or "individual",
            "emission": e.get("emission") or "",
            "climate": e.get("climate") or None,
            "switch": e.get("switch") or None,
            "primary_heat": bool(e.get("primary_heat", False)),
            "primary_cool": bool(e.get("primary_cool", False)),
            # F09 full: which physical compressor this emitter shares. Heat-pump
            # emitters with the same id are anti-cycled together; "default" keeps
            # the legacy single house compressor (back-compat).
            "compressor_id": str(e.get("compressor_id") or "default"),
            "scope": scope,
            "shared_emitter_id": e.get("shared_emitter_id") or None,
            "owner": bool(e.get("owner", False)),
            "policy": e.get("policy") if e.get("policy") in POLICIES else "weighted",
        })
    return out


def primary_for(emitters: list[dict], hvac: str) -> dict | None:
    """The primary emitter for ``hvac`` (heat/cool), with a sensible fallback.

    Falls back to the first emitter that drives a device, so a single-emitter zone
    (only radiant, or only AC) treats it as primary in both modes (REQ-EMI-7).
    """
    flag = "primary_cool" if hvac == "cool" else "primary_heat"
    explicit = [e for e in emitters if e.get(flag) and has_device(e)]
    if explicit:
        return explicit[0]
    with_dev = [e for e in emitters if has_device(e)]
    if with_dev:
        return with_dev[0]
    return emitters[0] if emitters else None


def supports_for(emitters: list[dict], hvac: str) -> list[dict]:
    """Non-primary emitters with a device (the staging candidates) for ``hvac``."""
    p = primary_for(emitters, hvac)
    return [e for e in emitters if e is not p and has_device(e)]


def profile_source(emitters: list[dict]):
    """The triple (gen, dist, emission) that drives F09/F03 gating for the zone.

    Prefers the heating primary (where compressor/peak matter most), then cooling,
    then any emitter that declares a generator. ``None`` if none is declared.
    """
    for hvac in ("heat", "cool"):
        p = primary_for(emitters, hvac)
        if p and p["generator"]:
            return (p["generator"], p["distribution"], p["emission"])
    for e in emitters:
        if e["generator"]:
            return (e["generator"], e["distribution"], e["emission"])
    return None


def is_multi(options: dict) -> bool:
    """Whether the zone uses the multi-emitter path (a non-empty emitter list)."""
    return bool(normalize(options.get("emitters")))


def validate(emitters) -> list[str]:
    """Human-readable problems with an emitter list (empty list == OK)."""
    errs: list[str] = []
    norm = normalize(emitters)
    for e in norm:
        if not has_device(e):
            errs.append(f"{e['id']}: needs a climate entity or a switch")
    for hvac, flag in (("heat", "primary_heat"), ("cool", "primary_cool")):
        if sum(1 for e in norm if e.get(flag)) > 1:
            errs.append(f"more than one primary emitter in {hvac}")
    return errs
