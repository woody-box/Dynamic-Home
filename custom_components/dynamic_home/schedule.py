"""Weekly scheduler (F21) — pure model shared by DC and DV (no HA imports).

The *editor* and *format* are shared, but each config entry keeps its own
independent profile: a climate (DC) zone programs its absolute BASE setpoint per
slot, a VMC (DV) its base speed/on-off per slot. Up to 4 slots per weekday.

Profile shape (as stored in ``entry.options[CONF_SCHEDULE]``)::

    {"0": [{"start": "07:00", "value": 21.5}, {"start": "23:00", "value": 19.0}],
     "1": [...], ... "6": []}

Weekday keys are "0".."6" (Monday..Sunday, matching ``datetime.weekday()``). The
slot active at a given moment is the one with the greatest ``start`` not after
now; before the first slot of the day the schedule wraps to the most recent prior
day's last slot, so the program is continuous across midnight. An empty profile
yields ``None`` (no schedule -> the caller falls back to its default).
"""

from __future__ import annotations

MAX_SLOTS = 4


def _to_min(hhmm) -> int | None:
    """Parse 'HH:MM' or 'HH:MM:SS' into minutes from midnight, else None."""
    if not isinstance(hhmm, str):
        return None
    parts = hhmm.split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize(raw) -> dict[str, list[dict]]:
    """Return a well-formed profile: 7 weekday lists, sorted, deduped, capped."""
    out: dict[str, list[dict]] = {}
    raw = raw if isinstance(raw, dict) else {}
    for d in range(7):
        slots = raw.get(str(d))
        if slots is None:
            slots = raw.get(d, [])
        by_start: dict[int, dict] = {}
        for s in slots if isinstance(slots, list) else []:
            if not isinstance(s, dict):
                continue
            m = _to_min(s.get("start"))
            val = s.get("value")
            if m is None or val is None:
                continue
            by_start[m] = {"start": _fmt(m), "value": val}  # last wins per start
        ordered = [by_start[k] for k in sorted(by_start)][:MAX_SLOTS]
        out[str(d)] = ordered
    return out


def is_empty(sched) -> bool:
    """Whether the (normalized) profile has no slots at all."""
    return all(not v for v in normalize(sched).values())


def active_value(sched, weekday: int, minute_of_day: int):
    """Value of the slot active at ``weekday``/``minute_of_day`` (None if empty)."""
    norm = normalize(sched)
    today = norm.get(str(weekday % 7), [])
    current = [s for s in today if _to_min(s["start"]) <= minute_of_day]
    if current:
        return current[-1]["value"]            # today's list is sorted ascending
    for back in range(1, 8):                    # wrap to a prior day's last slot
        slots = norm.get(str((weekday - back) % 7), [])
        if slots:
            return slots[-1]["value"]
    return None


def next_change(sched, weekday: int, minute_of_day: int) -> str | None:
    """'HH:MM' of the next slot boundary on or after now (today only), else None."""
    today = normalize(sched).get(str(weekday % 7), [])
    for s in today:
        if _to_min(s["start"]) > minute_of_day:
            return s["start"]
    return None


def set_day(sched, weekday: int, slots: list[dict]) -> dict:
    """Replace one weekday's slots (normalized), returning the new profile."""
    out = normalize(sched)
    out[str(weekday % 7)] = normalize({str(weekday % 7): slots})[str(weekday % 7)]
    return out


def clear_day(sched, weekday: int) -> dict:
    out = normalize(sched)
    out[str(weekday % 7)] = []
    return out


def copy_day(sched, src_weekday: int, dst_weekdays) -> dict:
    """Copy ``src_weekday``'s slots onto each of ``dst_weekdays``."""
    out = normalize(sched)
    src = [dict(s) for s in out.get(str(src_weekday % 7), [])]
    for d in dst_weekdays:
        out[str(int(d) % 7)] = [dict(s) for s in src]
    return out
