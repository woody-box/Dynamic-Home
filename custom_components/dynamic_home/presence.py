"""Presence fusion (F32) — pure per-zone occupancy + house state (no HA deps).

Each zone fuses the user's own source entities (RNF-6): PIR (fast, short hold),
mmWave (sustained — holds presence through stillness, the anti-flap key), and a
door contact; the house also folds in phone ``device_tracker``s (Home/Away). A zone
is **Occupied** while *any* of its sources is fresh within its per-kind timeout, and
only flips to **Empty** after a short debounce once all sources go stale — so sitting
still on the sofa under an mmWave never reads Empty (REQ-PRE-3).

The house rolls up to ``occupied`` / ``away`` / ``sleeping``: it goes ``away`` only
when no zone is occupied **and** there was a recent door opening or the phones say
away (REQ-PRE-5, never on mere stillness); ``sleeping`` when occupied, inside the
night window and with no recent motion (REQ-PRE-6). The coordinator maps this onto
the F01 house mode (home/away/sleep) when auto-drive is on.

Everything here is pure and unit-tested like ``staging.py``; defaults live in
:class:`PresenceConfig` (RNF-1) and the UI overlays them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Source kinds (user-provided entities). BLE/identity is a later cycle.
PIR = "pir"
MMWAVE = "mmwave"
DOOR = "door"
MOTION_KINDS = (PIR, MMWAVE)


@dataclass
class PresenceConfig:
    """Fusion thresholds (seconds) + night window (minutes from midnight)."""

    pir_timeout_s: float = 120.0          # fast source, short hold
    mmwave_timeout_s: float = 600.0       # sustained/still, long hold (anti-flap)
    empty_confirm_s: float = 30.0         # debounce before declaring Empty
    away_door_window_s: float = 300.0     # "recent door opening" for Away
    sleep_no_motion_s: float = 1800.0     # stillness before Sleeping
    sleep_start_min: int = 23 * 60        # night window start (23:00)
    sleep_end_min: int = 7 * 60           # night window end (07:00)


def kind_timeout(cfg: PresenceConfig, kind: str) -> float:
    return cfg.mmwave_timeout_s if kind == MMWAVE else cfg.pir_timeout_s


@dataclass
class ZonePresenceState:
    """Per-zone presence latch carried between cycles."""

    occupied: bool = False
    last_fired: dict = field(default_factory=dict)   # kind -> last 'on' timestamp
    empty_since: float | None = None


def note_source(state: ZonePresenceState, kind: str, fired: bool,
                now_ts: float) -> None:
    """Record a source firing (binary 'on') for later freshness checks."""
    if fired:
        state.last_fired[kind] = now_ts


def _fresh_motion(state: ZonePresenceState, cfg: PresenceConfig,
                  now_ts: float) -> list[str]:
    return [k for k in MOTION_KINDS
            if k in state.last_fired
            and now_ts - state.last_fired[k] < kind_timeout(cfg, k)]


def zone_occupied(state: ZonePresenceState, cfg: PresenceConfig,
                  now_ts: float) -> tuple[bool, str]:
    """Advance a zone's occupancy latch. Returns ``(occupied, reason)``."""
    fresh = _fresh_motion(state, cfg, now_ts)
    if fresh:
        state.occupied, state.empty_since = True, None
        return True, "mmwave_hold" if MMWAVE in fresh else fresh[0]
    if not state.occupied:
        return False, "empty"
    if state.empty_since is None:
        state.empty_since = now_ts
    if now_ts - state.empty_since < cfg.empty_confirm_s:
        return True, "emptying"                       # debounce
    state.occupied, state.empty_since = False, None
    return False, "empty"


def door_recent(states, cfg: PresenceConfig, now_ts: float) -> bool:
    """Whether any zone saw a door opening within the Away window."""
    return any(DOOR in s.last_fired and now_ts - s.last_fired[DOOR]
               < cfg.away_door_window_s for s in states)


def motion_recent(states, cfg: PresenceConfig, now_ts: float) -> bool:
    """Whether real *movement* (PIR) fired within the sleep stillness window.

    Only PIR counts as movement: a still person under an mmWave is Occupied but not
    moving, which is exactly the Sleeping case (REQ-PRE-6).
    """
    return any(PIR in s.last_fired and now_ts - s.last_fired[PIR]
               < cfg.sleep_no_motion_s for s in states)


def in_sleep_window(minute_of_day: int, cfg: PresenceConfig) -> bool:
    """Whether ``minute_of_day`` is inside the night window (wraps midnight)."""
    s, e = cfg.sleep_start_min, cfg.sleep_end_min
    if s == e:
        return False
    if s < e:
        return s <= minute_of_day < e
    return minute_of_day >= s or minute_of_day < e


def house_state(zones_occupied: dict, phone_home: bool, door_recent_flag: bool,
                minute_of_day: int, motion_recent_flag: bool,
                cfg: PresenceConfig, prev: str = "occupied",
                phone_present: bool = False) -> str:
    """Roll zones + phones into ``occupied`` / ``away`` / ``sleeping``.

    ``prev`` latches Away: once away, an empty house STAYS away until a zone
    is occupied again or a phone positively comes home (``phone_present``) —
    the old form fell back to "occupied" 5 minutes after leaving, when the
    door window expired, re-enabling comfort for an empty house.
    """
    any_occ = any(zones_occupied.values())
    if not any_occ:
        if phone_present:
            return "occupied"          # someone's phone is home; sensors quiet
        if door_recent_flag or not phone_home or prev == "away":
            return "away"                             # REQ-PRE-5: needs a signal
        return "occupied"
    if in_sleep_window(minute_of_day, cfg) and not motion_recent_flag:
        return "sleeping"                             # REQ-PRE-6
    return "occupied"


# House presence state -> F01 house mode (only the home/away/sleep axis).
STATE_TO_MODE = {"occupied": "home", "away": "away", "sleeping": "sleep"}
