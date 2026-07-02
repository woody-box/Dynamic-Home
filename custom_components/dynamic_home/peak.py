"""Electrical-peak / load staging (F03) — pure house-level arbiter (no HA deps).

Avoids ICP-tripping inrush by limiting how many electrical loads start at once and
spacing their starts. The arbiter is a house-level aggregate (one per *channel*) to
which each participant reports its demand every cycle; the hub decides whether that
participant may start now.

Two physically different loads keep **separate channels** (separate hub instances):

* **Sustained loads** (electric heating zones): a slot lives while the zone keeps
  demanding and is released when it stops. Budget = simultaneous zones (count mode)
  or watts (power mode).
* **Transient loads** (shutter motors): a slot is a short pulse of ``hold_s`` (the
  travel time) that auto-expires, modelling the start-up inrush only.

Both honour a budget (``max_units``: a zone/cover count, or a wattage) and a stagger
window (``stagger_s``): a fresh start is refused until that long after the previous
grant, so a burst of demands ramps up one at a time instead of simultaneously.
Already-running slots are never interrupted — the gate only governs *new* starts.
Gating is opt-in and, for climate, only engaged when the F26 install profile says
the load is electrical and not communal.

**This is where start fairness lives.** When starts are scarce, the ``priority`` arg
(F03: temperature deviation) orders them so the furthest-behind zone starts first, and
a fitting candidate yields to a hungrier waiter. The compressor anti-cycle guard
(F09, :mod:`anticycle`) is a separate, *aggregate* mechanical guard with no per-zone
ordering — deviation-based fairness is owned here, not there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

INF = float("inf")


@dataclass
class PeakState:
    """Per-channel arbiter state carried between cycles."""

    active: dict = field(default_factory=dict)   # entry_id -> (units, expiry_ts)
    last_start_ts: float = -INF                   # last fresh grant (for stagger)
    # entry_id -> (priority, last_seen_ts, units) of a demand that couldn't start
    waiters: dict = field(default_factory=dict)


class PeakLoadHub:
    """House-level load arbiter for one channel (heating zones OR shutter motors)."""

    def __init__(self) -> None:
        self.state = PeakState()

    def clear(self, entry_id: str) -> None:
        self.state.active.pop(entry_id, None)
        self.state.waiters.pop(entry_id, None)

    def used(self, now_ts: float) -> float:
        """Units currently in use (prunes expired transient slots)."""
        self._prune(now_ts)
        return sum(u for u, _ in self.state.active.values())

    def _prune(self, now_ts: float) -> None:
        st = self.state
        st.active = {k: (u, e) for k, (u, e) in st.active.items() if e > now_ts}

    def evaluate(self, entry_id: str, *, demand: bool, units: float,
                 sustained: bool, hold_s: float, now_ts: float,
                 max_units: float, stagger_s: float, priority: float = 0.0,
                 wait_window_s: float = 120.0) -> tuple[bool, str]:
        """Report a participant's demand; return ``(allowed, reason)``.

        ``demand`` — the participant wants to be on / to start a move this cycle.
        ``units`` — its contribution (1 in count mode, watts in power mode).
        ``sustained`` — True keeps the slot while demanded (heating); False makes it
        a transient pulse of ``hold_s`` seconds (a shutter move's inrush).
        ``priority`` — higher wins a tight budget (F03: temperature deviation). A
        candidate that fits the budget still **yields** to a higher-priority waiter
        seen within ``wait_window_s`` so the furthest-behind zone starts first.
        """
        st = self.state
        self._prune(now_ts)
        st.waiters = {k: pv for k, pv in st.waiters.items()
                      if now_ts - pv[1] <= wait_window_s}
        if entry_id in st.active:
            if sustained and not demand:
                del st.active[entry_id]
                return False, "idle"
            if sustained:
                # Refresh the slot with the LIVE units (a real power meter): the
                # request was booked at the estimate, but the budget must track
                # what the load actually draws once running.
                _, exp = st.active[entry_id]
                st.active[entry_id] = (units, exp)
            return True, "on"                      # already running -> never interrupt
        if not demand:
            st.waiters.pop(entry_id, None)
            return False, "idle"
        used = sum(u for u, _ in st.active.values())
        if used + units > max_units:
            st.waiters[entry_id] = (priority, now_ts, units)
            return False, "peak_over_budget"
        if now_ts - st.last_start_ts < stagger_s:
            st.waiters[entry_id] = (priority, now_ts, units)
            return False, "peak_stagger"
        top = max((pv for k, pv in st.waiters.items() if k != entry_id),
                  key=lambda pv: pv[0], default=None)
        if (top is not None and priority < top[0]
                and used + top[2] <= max_units):
            # Yield only when the hungrier waiter actually FITS the budget now;
            # a small load that fits must not idle the budget forever behind a
            # big one that never will.
            st.waiters[entry_id] = (priority, now_ts, units)
            return False, "peak_yield"
        st.active[entry_id] = (units, INF if sustained else now_ts + hold_s)
        st.last_start_ts = now_ts
        st.waiters.pop(entry_id, None)
        return True, "granted"

    def is_active(self, entry_id: str) -> bool:
        """Whether this participant currently holds a slot."""
        return entry_id in self.state.active

    def force_grant(self, entry_id: str, units: float, now_ts: float) -> None:
        """Book an unconditional sustained slot (comfort/safety bypass).

        The zone runs regardless of the gate, so its watts MUST count against
        the budget — otherwise the others fill it and the total trips the ICP.
        """
        st = self.state
        self._prune(now_ts)
        if entry_id not in st.active:
            st.last_start_ts = now_ts              # its start is inrush too
        st.active[entry_id] = (units, INF)
        st.waiters.pop(entry_id, None)
