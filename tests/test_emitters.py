"""Unit tests for the pure emitter-list model (F25 Phase A).

Run with:  python -m pytest tests/test_emitters.py -q
"""

from custom_components.dynamic_home import emitters


def _radiant():
    return {"name": "Radiant", "generator": "heatpump_air_water",
            "distribution": "individual", "emission": "underfloor",
            "switch": "switch.radiant", "primary_heat": True}


def _ac():
    return {"name": "AC", "generator": "heatpump_air_air",
            "emission": "split", "climate": "climate.ac", "primary_cool": True}


def test_normalize_fills_defaults_and_unique_ids():
    out = emitters.normalize([{"name": "AC"}, {"name": "AC"}])
    assert [e["id"] for e in out] == ["ac", "ac_2"]      # de-duplicated
    e = out[0]
    assert e["distribution"] == "individual"
    assert e["scope"] == "zone"
    assert e["climate"] is None and e["switch"] is None
    assert e["primary_heat"] is False and e["owner"] is False


def test_normalize_skips_non_dicts_and_bad_scope():
    out = emitters.normalize([{"name": "A", "scope": "bogus"}, 42, None])
    assert len(out) == 1
    assert out[0]["scope"] == "zone"                     # invalid scope -> zone


def test_primary_for_uses_role_per_mode():
    ems = emitters.normalize([_radiant(), _ac()])
    assert emitters.primary_for(ems, "heat")["id"] == "radiant"
    assert emitters.primary_for(ems, "cool")["id"] == "ac"


def test_primary_for_falls_back_to_single_device():
    # Only AC, no explicit heat primary -> AC is primary in both modes (REQ-EMI-7).
    ems = emitters.normalize([_ac()])
    assert emitters.primary_for(ems, "heat")["id"] == "ac"
    assert emitters.primary_for(ems, "cool")["id"] == "ac"


def test_supports_are_non_primary_with_device():
    ems = emitters.normalize([_radiant(), _ac()])
    sup = emitters.supports_for(ems, "heat")
    assert [e["id"] for e in sup] == ["ac"]              # AC supports heating
    sup_cool = emitters.supports_for(ems, "cool")
    assert [e["id"] for e in sup_cool] == ["radiant"]


def test_profile_source_prefers_heating_primary():
    ems = emitters.normalize([_radiant(), _ac()])
    assert emitters.profile_source(ems) == (
        "heatpump_air_water", "individual", "underfloor")
    # AC-only zone -> its triple.
    assert emitters.profile_source(emitters.normalize([_ac()])) == (
        "heatpump_air_air", "individual", "split")
    assert emitters.profile_source([]) is None


def test_is_multi_gate():
    assert emitters.is_multi({}) is False
    assert emitters.is_multi({"emitters": []}) is False
    assert emitters.is_multi({"emitters": [_ac()]}) is True


def test_validate_flags_missing_device_and_dup_primary():
    errs = emitters.validate([{"name": "ghost"},                     # no device
                              {"name": "h1", "switch": "switch.a", "primary_heat": True},
                              {"name": "h2", "switch": "switch.b", "primary_heat": True}])
    assert any("needs a climate entity or a switch" in e for e in errs)
    assert any("more than one primary emitter in heat" in e for e in errs)
    # A clean list has no errors.
    assert emitters.validate([_radiant(), _ac()]) == []
