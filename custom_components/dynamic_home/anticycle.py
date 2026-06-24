"""Short-cycle protection (F09) — pure compressor anti-cycling (no HA deps).

A heat pump / aerothermal compressor is **shared** across the climate (DC) zones:
*any* zone calling for heat/cool wakes it, and it only stops when the *last* zone
stops. So the protection works on the **aggregate** compressor on/off, not per
zone — a single zone flapping doesn't count as a compressor start if another zone
keeps it awake.

The guard enforces a minimum ON time, a minimum OFF time and a maximum number of
starts per hour over the aggregate. Safety always wins (REQ-CYC-3): when a zone is
forced off for condensation/window/etc. and nothing else demands, the compressor
is allowed to stop even before the minimum ON elapsed.

**No per-zone fairness here (by design).** This is a mechanical *aggregate* guard:
when ``max_starts_per_h`` is reached every demanding zone gets ``anticycle_max_starts_hold``
equally, regardless of how far each is from setpoint. Priority/fairness — starting the
furthest-behind zone first — lives in the electrical-peak arbiter (F03, :mod:`peak`),
not here. F09 only answers "may the shared compressor change state now?"; F03 answers
"which zone gets to start when starts are scarce?". Do not expect deviation-ordering in
this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HOUR_S = 3600.0


@dataclass
class CompressorState:
    """Aggregate compressor state carried between cycles (one per group)."""

    on: bool = False
    last_on_ts: float = 0.0       # last off->on transition
    last_off_ts: float = 0.0      # last on->off transition
    starts: list = field(default_factory=list)  # off->on timestamps (rolling hour)


def starts_last_hour(state: CompressorState, now_ts: float) -> int:
    """Number of compressor starts within the trailing hour (prunes older)."""
    state.starts = [t for t in state.starts if now_ts - t < HOUR_S]
    return len(state.starts)


def step(state: CompressorState, any_demand: bool, force_off: bool,
         now_ts: float, cfg) -> tuple[bool, str]:
    """Advance the aggregate compressor one tick. Returns (on, reason).

    ``any_demand`` = at least one zone commands heat/cool; ``force_off`` = a
    safety stop applies and nothing else demands (the guard yields).
    """
    n_starts = starts_last_hour(state, now_ts)
    if state.on:
        if force_off:                                   # safety wins (cede min ON)
            state.on, state.last_off_ts = False, now_ts
            return False, "anticycle_safety_off"
        if any_demand:
            return True, "on"
        if now_ts - state.last_on_ts < cfg.anticycle_min_on_s:
            return True, "anticycle_min_on_hold"        # don't register the stop yet
        state.on, state.last_off_ts = False, now_ts
        return False, "off"
    # currently off
    if any_demand and not force_off:
        if now_ts - state.last_off_ts < cfg.anticycle_min_off_s:
            return False, "anticycle_min_off_hold"
        if n_starts >= cfg.anticycle_max_starts_per_h:
            return False, "anticycle_max_starts_hold"
        state.on, state.last_on_ts = True, now_ts
        state.starts.append(now_ts)
        return True, "start"
    return False, "off"


class AntiCycleHub:
    """Shared compressors keyed by **channel** (F09 full, ``compressor_id``).

    Each DC zone reports its commanded demand to one or more **compressor channels**;
    the hub runs an independent :class:`CompressorState` per channel, so two separate
    heat pumps in a house never throttle each other. A zone that declares no channel
    uses ``"default"`` — a single house-wide compressor, identical to the legacy MVP.
    """

    def __init__(self) -> None:
        self.state = CompressorState()                  # the "default" channel
        self.channels: dict[str, CompressorState] = {}  # extra named channels
        # channel -> {entry_id: (demand, safety)}
        self._reports: dict[str, dict[str, tuple[bool, bool]]] = {}

    def _chan_state(self, channel: str) -> CompressorState:
        if channel == "default":
            return self.state
        return self.channels.setdefault(channel, CompressorState())

    def clear(self, entry_id: str) -> None:
        """Drop this zone's demand from every channel (called when it stops/yields)."""
        for reps in self._reports.values():
            reps.pop(entry_id, None)

    def participates(self, entry_id: str) -> bool:
        """Whether this zone is currently part of any compressor aggregate."""
        return any(entry_id in reps for reps in self._reports.values())

    def evaluate(self, entry_id: str, desired_on: bool, safety_off: bool,
                 now_ts: float, cfg, channel: str = "default") -> tuple[bool, str]:
        """Report this zone's demand on ``channel``, step it, return (gated_on, reason)."""
        st = self._chan_state(channel)
        reps = self._reports.setdefault(channel, {})
        reps[entry_id] = (desired_on, safety_off)
        any_demand = any(d and not s for d, s in reps.values())
        force_off = any(s for _, s in reps.values()) and not any_demand
        on, reason = step(st, any_demand, force_off, now_ts, cfg)
        gated_on = on and desired_on and not safety_off
        return gated_on, reason
