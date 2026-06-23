"""Unit tests for the pure energy engine (F34).

Run with:  python -m pytest tests/test_energy_engine.py -q
"""

from custom_components.dynamic_home import energy_engine as e
from custom_components.dynamic_home.energy_engine import EnergyConfig

CFG = EnergyConfig(contracted_w=5750.0, cheap_below=0.10, peak_above=0.20)


def test_tariff_state_thresholds():
    assert e.tariff_state(0.05, CFG) == "cheap"
    assert e.tariff_state(0.15, CFG) == "normal"
    assert e.tariff_state(0.30, CFG) == "peak"
    # Edges are inclusive.
    assert e.tariff_state(0.10, CFG) == "cheap"
    assert e.tariff_state(0.20, CFG) == "peak"


def test_tariff_state_fixed_when_no_price():
    assert e.tariff_state(None, CFG) == "normal"
    assert e.tariff_state(None, EnergyConfig(fixed_tariff="peak")) == "peak"
    assert e.tariff_state(None, EnergyConfig(fixed_tariff="bogus")) == "normal"


def test_import_headroom():
    assert e.import_headroom(2000.0, CFG) == 3750.0
    assert e.import_headroom(None, CFG) is None              # no meter -> degrade
    # Clamped at the floor (over the contracted power -> 0, not negative).
    assert e.import_headroom(7000.0, CFG) == 0.0


def test_surplus_gated_on_pv():
    assert e.surplus(None, 1000.0) is None                  # no PV inputs
    assert e.surplus(3000.0, 1000.0) == 2000.0
    assert e.surplus(500.0, None) == 500.0                  # consumption optional


def test_scarcity_truth_table():
    assert e.scarcity("peak", None) is True                 # expensive, no PV
    assert e.scarcity("peak", -100.0) is True               # expensive, importing
    assert e.scarcity("peak", 500.0) is False               # expensive but surplus
    assert e.scarcity("normal", None) is False
    assert e.scarcity("cheap", None) is False


def test_resolve_context_without_pv():
    blob = e.resolve_context({"grid_w": 2000.0, "price": 0.30}, CFG)
    assert blob["tariff_state"] == "peak"
    assert blob["import_headroom_w"] == 3750.0
    assert blob["contracted_w"] == 5750.0
    assert blob["scarcity"] is True
    assert "surplus_w" not in blob                          # absent, not a crash


def test_resolve_context_with_pv_and_no_meter():
    blob = e.resolve_context(
        {"price": 0.05, "pv_w": 3000.0, "consumption_w": 1000.0}, CFG)
    assert blob["import_headroom_w"] is None                # no grid meter
    assert blob["surplus_w"] == 2000.0
    assert blob["tariff_state"] == "cheap"
    assert blob["scarcity"] is False
