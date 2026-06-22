"""Dynamic Weather (F33) — pure helpers (no Home Assistant dependencies).

A resilient, provider-agnostic weather layer: it does not fetch anything itself,
it picks the first healthy source from a prioritised list (other HA ``weather.*``
entities and/or raw sensors) and derives a generic alert. The HA wrappers
(coordinator + proxy weather entity) translate state and forward forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass

# Weather conditions that, on their own, warrant a protective alert.
ALERT_CONDITIONS = frozenset({
    "lightning", "lightning-rainy", "hail", "exceptional", "snowy-rainy",
})


@dataclass
class WxConfig:
    """Tunables for the weather layer."""

    stale_after_h: float = 6.0      # a source older than this counts as down
    alert_wind_kmh: float = 60.0    # wind at/above this raises the alert
    alert_precip_mm: float = 10.0   # precipitation at/above this raises the alert


def pick_source(available: list[bool]) -> int | None:
    """Index of the first healthy source in priority order, or None if all down."""
    for i, ok in enumerate(available):
        if ok:
            return i
    return None


def is_fresh(age_s: float | None, cfg: WxConfig) -> bool:
    """Whether a source's age is within the staleness window (None age = fresh)."""
    return age_s is None or age_s <= cfg.stale_after_h * 3600.0


def derive_alert(condition: str | None, wind_kmh: float | None,
                 precip_mm: float | None, cfg: WxConfig) -> bool:
    """Generic weather alert from the active source (F33 → F17).

    True when the condition is hazardous, or wind/precipitation cross their
    thresholds. Consumed by DS as a plain alert (provider-agnostic).
    """
    if condition in ALERT_CONDITIONS:
        return True
    if wind_kmh is not None and wind_kmh >= cfg.alert_wind_kmh:
        return True
    if precip_mm is not None and precip_mm >= cfg.alert_precip_mm:
        return True
    return False
