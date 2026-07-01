"""Energy accounting (F06) — pure helpers shared by the VMC/DC/DS coordinators.

No Home Assistant imports: unit-testable in isolation. Each coordinator either
integrates an instantaneous power estimate (or a real power-meter reading) over
the elapsed time, or — for the shutter, whose moves last only seconds — adds a
per-movement estimate. The resulting kWh feeds a ``TOTAL_INCREASING`` sensor that
shows up in Home Assistant's Energy dashboard.
"""

from __future__ import annotations

# Conversion: 1 kWh = 3_600_000 W·s.
_WS_PER_KWH = 3_600_000.0


def add_kwh(prev_kwh: float, power_w: float | None, dt_s: float) -> float:
    """Accumulate energy: ``prev + power·dt``.

    A ``None``/non-positive power or a non-positive ``dt_s`` leaves the counter
    unchanged (the counter only ever grows — it is ``TOTAL_INCREASING``).
    """
    if power_w is None or power_w <= 0 or dt_s <= 0:
        return prev_kwh
    return prev_kwh + power_w * dt_s / _WS_PER_KWH


def vmc_power_w(speed: int, watts: tuple[float, float, float]) -> float:
    """Estimated VMC power (W) for a logical speed (0=off, 1/2/3 -> ``watts``)."""
    if speed in (1, 2, 3):
        return max(0.0, watts[speed - 1])
    return 0.0


def dc_power_w(on: bool, watts_on: float) -> float:
    """Estimated climate power (W): ``watts_on`` while calling for heat/cool, else 0."""
    return max(0.0, watts_on) if on else 0.0


def window_kwh(samples: list[tuple[float, float]], current_kwh: float,
               now_ts: float, window_s: float) -> float:
    """Energy consumed over the last ``window_s`` from cumulative-kWh snapshots.

    ``samples`` is an ascending list of ``(timestamp, cumulative_kwh)`` and
    ``current_kwh`` the live cumulative total. The consumption in the window is
    ``current − baseline``, where the baseline is the cumulative value at the
    window's start: the latest snapshot at or before ``now − window_s`` (or the
    earliest snapshot if the history is shorter than the window — a partial figure
    while it fills). No history yet -> 0. Never negative.
    """
    if not samples:
        return 0.0
    cutoff = now_ts - window_s
    baseline = samples[0][1]
    for ts, kwh in samples:
        if ts <= cutoff:
            baseline = kwh
        else:
            break
    return max(0.0, current_kwh - baseline)


def ds_move_kwh(delta_pct: float, motor_w: float, full_travel_s: float) -> float:
    """Energy (kWh) of one shutter movement of ``|delta_pct|`` %.

    The motor runs for the fraction of a full travel that the movement covers
    (``full_travel_s · |Δ%|/100``). A non-positive power/time or a zero move
    yields 0.
    """
    if motor_w <= 0 or full_travel_s <= 0 or not delta_pct:
        return 0.0
    travel_s = full_travel_s * abs(delta_pct) / 100.0
    return motor_w * travel_s / _WS_PER_KWH
