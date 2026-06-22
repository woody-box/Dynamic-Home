"""Unit tests for the pure Comfort↔Economy presets (F23).

Run with:  python -m pytest tests/test_comfort.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

import comfort  # noqa: E402
import zones  # noqa: E402
from dc_engine import DcConfig  # noqa: E402
from dv_engine import DvConfig  # noqa: E402


# --- scope resolution (mirrors modes) ---
def test_effective_level_zone_override_wins():
    assert comfort.effective_level("eco", "comfort") == "comfort"
    assert comfort.effective_level("eco", comfort.AUTO) == "eco"     # auto inherits
    assert comfort.effective_level("eco", None) == "eco"
    assert comfort.effective_level("nonsense", None) == "balanced"   # invalid -> safe


def test_effective_from_published_default_and_zone_override():
    assert comfort.effective_from_published(None, "m1") == "balanced"
    tree = zones.assign_modules(zones.add_zone({}, "Salon"), "salon", ["m1"])
    data = {"tree": tree, "comfort": "balanced",
            "zone_comfort": {"salon": "comfort"}}
    assert comfort.effective_from_published(data, "m1") == "comfort"
    assert comfort.effective_from_published(data, "other") == "balanced"


def test_eco_house_mode_links_to_eco_preset():
    # Dial left neutral + house mode eco -> eco preset (F01 link).
    data = {"tree": {}, "house": "eco", "comfort": "balanced"}
    assert comfort.effective_from_published(data, "m1") == "eco"
    # An explicit comfort choice still wins over the mode link.
    data2 = {"tree": {}, "house": "eco", "comfort": "comfort"}
    assert comfort.effective_from_published(data2, "m1") == "comfort"
    # Non-eco mode + neutral dial -> balanced.
    data3 = {"tree": {}, "house": "home", "comfort": "balanced"}
    assert comfort.effective_from_published(data3, "m1") == "balanced"


# --- DC config shifts ---
def test_apply_dc_eco_widens_band_and_softens():
    base, cfg = DcConfig(), DcConfig()
    comfort.apply_dc(cfg, "eco")
    assert cfg.base_heat_day < base.base_heat_day      # heat down -> save
    assert cfg.base_cool_day > base.base_cool_day      # cool up -> save
    assert cfg.delta_night > base.delta_night          # more night easing
    assert cfg.lead_base_h < base.lead_base_h          # softer anticipation
    assert cfg.apply_min_delta > base.apply_min_delta  # less fidgeting


def test_apply_dc_comfort_tightens_and_anticipates():
    base, cfg = DcConfig(), DcConfig()
    comfort.apply_dc(cfg, "comfort")
    assert cfg.base_heat_day > base.base_heat_day      # tighter band
    assert cfg.base_cool_day < base.base_cool_day
    assert cfg.delta_night < base.delta_night
    assert cfg.lead_base_h > base.lead_base_h          # more anticipation


def test_apply_dc_balanced_is_identity():
    base, cfg = DcConfig(), DcConfig()
    comfort.apply_dc(cfg, "balanced")
    assert (cfg.base_heat_day, cfg.base_cool_day, cfg.delta_night,
            cfg.lead_base_h) == (base.base_heat_day, base.base_cool_day,
                                 base.delta_night, base.lead_base_h)


# --- DV config shifts ---
def test_apply_dv_eco_ventilates_less():
    base, cfg = DvConfig(), DvConfig()
    comfort.apply_dv(cfg, "eco")
    assert cfg.co2_v2 > base.co2_v2 and cfg.co2_v3 > base.co2_v3
    assert cfg.pm_v2 > base.pm_v2 and cfg.co2_hys > base.co2_hys


def test_apply_dv_comfort_ventilates_sooner_and_keeps_order():
    base, cfg = DvConfig(), DvConfig()
    comfort.apply_dv(cfg, "comfort")
    assert cfg.co2_v2 < base.co2_v2 and cfg.co2_v3 < base.co2_v3
    assert cfg.co2_v3 > cfg.co2_v2 and cfg.pm_v3 > cfg.pm_v2   # ordering preserved


def test_apply_dv_balanced_is_identity():
    base, cfg = DvConfig(), DvConfig()
    comfort.apply_dv(cfg, "balanced")
    assert (cfg.co2_v2, cfg.co2_v3, cfg.pm_v2, cfg.pm_v3, cfg.co2_hys) == (
        base.co2_v2, base.co2_v3, base.pm_v2, base.pm_v3, base.co2_hys)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL {name}: {e}")
    print(f"\n{'ALL GREEN' if not failed else str(failed) + ' FAILED'}")
    sys.exit(1 if failed else 0)
