"""Dynamic Energy (F34) — pure helpers (no Home Assistant dependencies).

A house-level energy brain that **publishes context** (not commands): how much room
is left under the contracted power (ICP), the tariff state (cheap/normal/peak) and
whether energy is *scarce* (expensive with no PV surplus). Other modules read this
context and modulate their own aggressiveness; nobody is commanded and safety always
wins (RNF-3/4). It consolidates F03 (anti-peak), F04 (price) and F06 (cost).

Everything here is pure and unit-tested like ``weather_engine``/``changeover``. The
PV/battery fields are **present but gated**: ``surplus`` returns ``None`` when no PV
inputs are given, so adding PV later is non-breaking and the absence is structural,
not a crash (REQ-ENG-5 / REQ-PVS-4). Defaults live in :class:`EnergyConfig` (RNF-1).
"""

from __future__ import annotations

from dataclasses import dataclass

TARIFF_STATES = ("cheap", "normal", "peak")


@dataclass
class EnergyConfig:
    """Tunables for the energy layer (€/kWh thresholds, contracted power)."""

    contracted_w: float = 5750.0     # contracted power / ICP (typical ES 5.75 kW)
    cheap_below: float = 0.10        # price <= this -> cheap (€/kWh)
    peak_above: float = 0.20         # price >= this -> peak (€/kWh)
    fixed_tariff: str = "normal"     # tariff when no price sensor is configured
    headroom_floor_w: float = 0.0    # never publish a negative import budget
    n_loads_default: int = 2         # degraded count budget when no grid meter


def tariff_state(price: float | None, cfg: EnergyConfig) -> str:
    """Map a €/kWh price to ``cheap``/``normal``/``peak`` (edges inclusive).

    With no price sensor (``price is None``) the configured fixed tariff is returned,
    so the price-less path is deterministic (REQ-TAR-1/2).
    """
    if price is None:
        return cfg.fixed_tariff if cfg.fixed_tariff in TARIFF_STATES else "normal"
    if price <= cfg.cheap_below:
        return "cheap"
    if price >= cfg.peak_above:
        return "peak"
    return "normal"


def import_headroom(grid_w: float | None, cfg: EnergyConfig) -> float | None:
    """Watts left under the contracted power; ``None`` when no grid meter (degrade)."""
    if grid_w is None:
        return None
    return max(cfg.headroom_floor_w, cfg.contracted_w - grid_w)


def surplus(pv_w: float | None, consumption_w: float | None) -> float | None:
    """PV surplus (production − consumption); ``None`` when PV inputs are absent."""
    if pv_w is None:
        return None
    return pv_w - (consumption_w or 0.0)


def scarcity(tariff: str, surplus_w: float | None) -> bool:
    """Energy is scarce when it is expensive AND there is no PV surplus."""
    return tariff == "peak" and not (surplus_w is not None and surplus_w > 0)


def resolve_context(inputs: dict, cfg: EnergyConfig) -> dict:
    """Assemble the published ``DATA_ENERGY`` blob from the available inputs.

    ``inputs`` keys (any may be missing): ``grid_w``, ``price``, ``pv_w``,
    ``consumption_w``. The ``surplus_w`` key is **omitted** when no PV is present so
    its absence is structural (REQ-ENG-4/6, acceptance §8.1).
    """
    tariff = tariff_state(inputs.get("price"), cfg)
    headroom = import_headroom(inputs.get("grid_w"), cfg)
    blob: dict = {
        "tariff_state": tariff,
        "import_headroom_w": headroom,
        "contracted_w": cfg.contracted_w,
    }
    sur = surplus(inputs.get("pv_w"), inputs.get("consumption_w"))
    if sur is not None:                                # PV present -> expose surplus
        blob["surplus_w"] = sur
    blob["scarcity"] = scarcity(tariff, sur)
    return blob
