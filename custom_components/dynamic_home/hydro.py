"""Hydraulic minimum-flow gate — pure house-level aggregate (no HA deps).

In a hydronic install every open zone valve splits the pump's flow. If a single
small circuit (a bathroom loop) opens alone, ALL the flow rushes through it and
the water whistles from sheer velocity. Each zone therefore declares a *weight*
(how much water its circuit moves) and the house requires a minimum total weight
of demanding zones before any valve may open.

Each participating DC zone reports every cycle whether it *wants* to move water
and with what weight (mirroring the peak/anticycle hubs). A blocked demand stays
REGISTERED: it still counts toward the total, so when a second zone starts
demanding and the sum crosses the minimum, both open together. A zone that stops
demanding deregisters and may drop its partners below the minimum again.
"""

from __future__ import annotations

_EPS = 1e-9   # float-sum noise guard so an exact-minimum total never flickers


class HydroFlowHub:
    """House-level registry of demanding zones and their hydraulic weights."""

    def __init__(self) -> None:
        self._wants: dict[str, float] = {}   # entry_id -> weight

    def clear(self, entry_id: str) -> None:
        self._wants.pop(entry_id, None)

    def total(self) -> float:
        """Total weight currently demanding (observability + the gate itself)."""
        return sum(self._wants.values())

    def evaluate(self, entry_id: str, wants: bool, weight: float,
                 min_weight: float) -> tuple[bool, str]:
        """Report a zone's demand; return ``(allowed, reason)``.

        ``wants`` — the zone would open its valve this cycle if allowed.
        ``weight`` — the water its circuit moves (re-read each call, so a
        re-tuned option applies on the next cycle).
        ``min_weight`` — the total demanded weight required to open anything.
        """
        if not wants:
            self._wants.pop(entry_id, None)
            return False, "idle"
        self._wants[entry_id] = weight
        if self.total() >= min_weight - _EPS:
            return True, "granted"
        return False, "hydro_min_weight"
