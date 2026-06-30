"""Unit tests for the pure installation-profile model (F26).

Run with:  python -m pytest tests/test_install.py -q
"""

from custom_components.dynamic_home import install, options_spec
from custom_components.dynamic_home.const import MODULE_CLIMATE


def test_catalogue_shapes():
    assert "heatpump_air_water" in install.GENERATORS
    assert set(install.DISTRIBUTIONS) == {"individual", "central_shared"}
    # Every emitter declares a valid inertia class.
    for _id, (en, es, inertia) in install.EMISSIONS.items():
        assert en and es
        assert inertia in ("high", "medium", "low")


def test_forced_individual_generators():
    assert install.forced_individual("electric_direct")
    assert install.forced_individual("heatpump_air_air")
    assert not install.forced_individual("heatpump_air_water")
    assert not install.forced_individual("gas_boiler")
    # Forced generators ignore any distribution passed in.
    assert install.distribution_for("electric_direct", "central_shared") \
        == "individual"
    assert install.distribution_for("gas_boiler", "central_shared") \
        == "central_shared"


def test_inertia_lookup():
    assert install.inertia("underfloor") == "high"
    assert install.inertia("radiators") == "medium"
    assert install.inertia("fancoil") == "low"
    assert install.inertia("radiant_cooling") == "high"
    assert install.inertia("unknown") == "medium"   # safe default


def test_is_cold_surface():
    # Chilled-surface emitters (condensation forms on the surface).
    assert install.is_cold_surface("underfloor") is True
    assert install.is_cold_surface("ceiling_radiant") is True
    assert install.is_cold_surface("radiant_cooling") is True
    # Air/coil emitters: condensation is handled by the unit, not a surface.
    assert install.is_cold_surface("fancoil") is False
    assert install.is_cold_surface("split") is False
    assert install.is_cold_surface("radiators") is False
    assert install.is_cold_surface(None) is False


def test_profile_central_shared_is_community_without_flags():
    # Gas, central/communal -> the occupant only opens a valve.
    p = install.profile("gas_boiler", "central_shared", "radiators")
    assert p == {"inertia": "medium", "compressor": False,
                 "peak": False, "community": True}
    # A shared central heat pump is still community: no per-zone compressor/peak.
    p = install.profile("heatpump_air_water", "central_shared", "underfloor")
    assert p["community"] and not p["compressor"] and not p["peak"]


def test_profile_individual_heatpump_has_compressor_and_peak():
    p = install.profile("heatpump_air_water", "individual", "underfloor")
    assert p == {"inertia": "high", "compressor": True,
                 "peak": True, "community": False}
    # Air-air is forced individual -> compressor + peak even with no distribution.
    p = install.profile("heatpump_air_air", None, "split")
    assert p["compressor"] and p["peak"] and not p["community"]


def test_profile_combustion_has_no_compressor_or_peak():
    for gen in ("gas_boiler", "oil_boiler", "biomass_boiler", "wood_boiler"):
        p = install.profile(gen, "individual", "radiators")
        assert not p["compressor"], gen
        assert not p["peak"], gen           # only a pump draws power
        assert not p["community"], gen


def test_profile_direct_electric_has_peak_not_compressor():
    p = install.profile("electric_direct", None, "convectors")
    assert p["peak"] and not p["compressor"] and not p["community"]


def test_defaults_scale_with_inertia_and_are_valid_keys():
    high = install.defaults("heatpump_air_water", "individual", "underfloor")
    low = install.defaults("heatpump_air_air", None, "fancoil")
    # Slow emitters lead earlier and tolerate longer anti-cycle than fast ones.
    assert high["lead_base_h"] > low["lead_base_h"]
    assert high["trend_lead_h"] > low["trend_lead_h"]
    assert high["anticycle_min_on_s"] > low["anticycle_min_on_s"]
    assert high["anticycle_min_off_s"] > low["anticycle_min_off_s"]
    # Every emitted key must be a real climate option key.
    valid = {options_spec.option_key(o)
             for cat in options_spec.SPEC[MODULE_CLIMATE].values() for o in cat}
    for d in (high, low):
        assert set(d) <= valid, set(d) - valid


def test_defaults_apply_cleanly_onto_a_fresh_config():
    cfg = options_spec.fresh_config(MODULE_CLIMATE)
    d = install.defaults("heatpump_air_water", "individual", "underfloor")
    options_spec.apply_options(cfg, d, MODULE_CLIMATE)
    assert cfg.lead_base_h == d["lead_base_h"]
    assert cfg.anticycle_min_on_s == d["anticycle_min_on_s"]
