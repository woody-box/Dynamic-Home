"""Shared un-zoned emitter reconciliation (F25 Phase B) — pure (no HA deps).

A ducted unit can serve several zones of a group. Since one un-zoned duct can't cut
flow per room, the zones' demands must be reconciled into a **single** command. Each
group-sibling DC zone reports its demand to a house-level :class:`SharedEmitterHub`
(keyed by a shared-channel id, mirroring the peak/anticycle hubs); exactly one zone —
the declared owner, or a deterministic fallback — drives the physical unit from the
reconciled command.

Reconciliation (REQ-EMI-5) blends the zones' setpoints by a selectable policy
(weighted default / mean / priority / worst-stuck) and, **without** motorized grilles,
applies an undershoot guard (REQ-EMI-8): the unit cuts when the *most satisfied* zone
reaches its setpoint ∓ margin, to avoid over-conditioning small rooms. With motorized
grilles each zone throttles its own flow, so the unit just carries the most-demanding
setpoint and the guard does not apply (REQ-EMI-4).
"""

from __future__ import annotations

from dataclasses import dataclass

from .staging import deviation

_EPS = 0.05


@dataclass
class ZoneDemand:
    """One zone's demand on a shared duct, reported each cycle."""

    entry_id: str
    hvac: str                       # heat | cool | off
    current: float | None
    target: float | None            # this zone's engine setpoint
    weight: float = 1.0             # zone_demand_weight (REQ-EMI-9)
    undershoot_margin: float = 0.5  # shared_undershoot_margin (REQ-EMI-9)
    owner: bool = False             # declared owner of the shared unit


def _active(demands: list[ZoneDemand], hvac: str) -> list[ZoneDemand]:
    return [d for d in demands if d.hvac == hvac and d.target is not None]


def aggregate_setpoint(demands: list[ZoneDemand], hvac: str,
                       policy: str = "weighted") -> float | None:
    """Blend the zones' setpoints into one, per ``policy``."""
    active = _active(demands, hvac)
    if not active:
        return None
    if policy == "mean":
        return sum(d.target for d in active) / len(active)
    if policy == "priority":
        return max(active, key=lambda d: d.weight).target
    if policy == "worst_stuck":
        return max(active, key=lambda d: deviation(hvac, d.current, d.target)).target
    num = den = 0.0                                # weighted (default)
    for d in active:
        w = d.weight * max(deviation(hvac, d.current, d.target), _EPS)
        num += w * d.target
        den += w
    return num / den if den else sum(d.target for d in active) / len(active)


def undershoot_cut(demands: list[ZoneDemand], hvac: str) -> bool:
    """REQ-EMI-8: stop once a zone is OVER-conditioned past setpoint + margin.

    v0.96.0: the old form cut at ``setpoint - margin`` — *below* the target of the
    most satisfied zone — so a bedroom already at 20 °C with a 19 °C setpoint
    starved a living room stuck at 18 °C forever. The guard now only cuts on the
    over-conditioned side, and never while another zone still genuinely lags
    (protect the satisfied room without starving the hungry one).
    """
    over = lagging = False
    for d in _active(demands, hvac):
        if d.current is None:
            continue
        if hvac == "heat":
            over = over or d.current >= d.target + d.undershoot_margin
            lagging = lagging or d.current < d.target - d.undershoot_margin
        else:
            over = over or d.current <= d.target - d.undershoot_margin
            lagging = lagging or d.current > d.target + d.undershoot_margin
    return over and not lagging


def demanded_direction(demands: list[ZoneDemand]) -> str | None:
    """The direction the reporting zones actually ask for (majority wins)."""
    dirs = [d.hvac for d in demands if d.hvac in ("heat", "cool")]
    if not dirs:
        return None
    return max(("heat", "cool"), key=dirs.count)


def reconcile(demands: list[ZoneDemand], hvac: str, policy: str = "weighted",
              grilles: bool = False) -> dict:
    """One command for the shared unit: ``{mode, target, reason}``."""
    if hvac not in ("heat", "cool"):
        # The owner being off/idle must not kill the duct for its sisters: run
        # in the direction the demanding zones ask for (v0.96.0).
        hvac = demanded_direction(demands) or hvac
    active = _active(demands, hvac)
    if hvac not in ("heat", "cool") or not active:
        return {"mode": "off", "target": None, "reason": "idle"}
    if grilles:
        # Each grille throttles its own flow -> run the unit at the most-demanding
        # setpoint; no aggregation/guard (REQ-EMI-4).
        worst = max(active, key=lambda d: deviation(hvac, d.current, d.target))
        return {"mode": hvac, "target": worst.target, "reason": "grilles"}
    if undershoot_cut(demands, hvac):
        return {"mode": "off", "target": None, "reason": "undershoot_cut"}
    return {"mode": hvac, "target": aggregate_setpoint(demands, hvac, policy),
            "reason": "reconciled"}


class SharedEmitterHub:
    """House-level reconciler: one channel per shared duct (mirrors PeakLoadHub)."""

    def __init__(self) -> None:
        self._chan: dict[str, dict[str, ZoneDemand]] = {}

    def report(self, channel: str, demand: ZoneDemand) -> None:
        self._chan.setdefault(channel, {})[demand.entry_id] = demand

    def clear(self, channel: str, entry_id: str) -> None:
        ch = self._chan.get(channel)
        if ch is not None:
            ch.pop(entry_id, None)
            if not ch:
                self._chan.pop(channel, None)

    def clear_entry(self, entry_id: str) -> None:
        """Drop a zone from every channel (used on unload)."""
        for channel in list(self._chan):
            self.clear(channel, entry_id)

    def is_owner(self, channel: str, entry_id: str) -> bool:
        """The declared owner (lowest id if several), else the lowest reporter id."""
        ch = self._chan.get(channel, {})
        if entry_id not in ch:
            return False
        declared = sorted(eid for eid, d in ch.items() if d.owner)
        if declared:
            return entry_id == declared[0]
        return entry_id == min(ch)

    def reconcile(self, channel: str, hvac: str, policy: str = "weighted",
                  grilles: bool = False) -> dict:
        return reconcile(list(self._chan.get(channel, {}).values()), hvac,
                         policy, grilles)
