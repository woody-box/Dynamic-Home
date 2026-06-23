"""Primary/support staging (F25) — pure emitter-staging state machine (no HA deps).

The zone's primary emitter always carries the engine setpoint. A *support* emitter
(e.g. an AC backing up slow underfloor radiant) only kicks in when the primary is
**falling behind**: the active-direction deviation stays above a threshold for a
confirm time, and it retires once the room recovers under a tighter band for a
release time (hysteresis, no flapping). This mirrors the debounce/latch idiom of the
open-window inference in ``coordinator_dc``.

Thresholds/times live on :class:`dc_engine.DcConfig` (``support_*`` fields) so they are
UI-tunable; :func:`step` reads them off the ``cfg`` it is handed. One
:class:`StagingState` is kept per (zone, support emitter) in the coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StagingState:
    """Support-emitter latch carried between cycles."""

    on: bool = False
    lag_since: float | None = None       # when the lag first exceeded the on-band
    settle_since: float | None = None     # when recovery under the off-band began


def deviation(hvac: str, current: float | None, target: float | None) -> float:
    """Active-direction lag (°C): >0 means the room is short of the setpoint."""
    if current is None or target is None:
        return 0.0
    if hvac == "heat":
        return target - current
    if hvac == "cool":
        return current - target
    return 0.0


def step(state: StagingState, hvac: str, current: float | None,
         target: float | None, now_ts: float, cfg) -> tuple[bool, str]:
    """Advance one support emitter a tick. Returns ``(support_on, reason)``."""
    if hvac not in ("heat", "cool"):
        state.on = False
        state.lag_since = state.settle_since = None
        return False, "off"
    dev = deviation(hvac, current, target)
    if not state.on:
        if dev > cfg.support_dev_on:
            if state.lag_since is None:
                state.lag_since = now_ts
            if now_ts - state.lag_since >= cfg.support_confirm_min * 60.0:
                state.on, state.lag_since, state.settle_since = True, None, None
                return True, "support_on"
            return False, "support_arming"
        state.lag_since = None
        return False, "idle"
    # currently on -> retire only after sustained recovery (hysteresis)
    if dev < cfg.support_dev_off:
        if state.settle_since is None:
            state.settle_since = now_ts
        if now_ts - state.settle_since >= cfg.support_release_min * 60.0:
            state.on, state.settle_since = False, None
            return False, "support_off"
        return True, "support_settling"
    state.settle_since = None
    return True, "support_on"
