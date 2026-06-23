"""Unit tests for the pure community-changeover resolver (F37).

Run with:  python -m pytest tests/test_changeover.py -q
"""

from custom_components.dynamic_home import changeover as co
from custom_components.dynamic_home.changeover import ChangeoverConfig

CFG = ChangeoverConfig(heat_above_c=28.0, cool_below_c=20.0)


def test_manual_override_wins():
    assert co.resolve("heat", 12.0, CFG) == "heat"      # ignores cold water
    assert co.resolve("cool", 40.0, CFG) == "cool"
    assert co.resolve("off", 40.0, CFG) == "off"


def test_auto_infers_from_supply_water():
    assert co.resolve("auto", 35.0, CFG) == "heat"      # hot water
    assert co.resolve("auto", 12.0, CFG) == "cool"      # cold water
    assert co.resolve("auto", 24.0, CFG) == "off"       # shoulder season
    # Threshold edges are inclusive.
    assert co.resolve("auto", 28.0, CFG) == "heat"
    assert co.resolve("auto", 20.0, CFG) == "cool"


def test_auto_without_sensor_is_unknown():
    assert co.resolve("auto", None, CFG) is None        # no gating (back-compat)


def test_custom_thresholds():
    warm = ChangeoverConfig(heat_above_c=30.0, cool_below_c=18.0)
    assert co.resolve("auto", 29.0, warm) == "off"      # below the higher threshold
    assert co.resolve("auto", 17.0, warm) == "cool"
