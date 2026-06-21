"""Guard tests for the UI options catalogue.

Ensures every spec field really exists on its engine dataclass (no typos), that
defaults come from the dataclass, and that tuple fields round-trip correctly.
"""

from custom_components.dynamic_home import const, presets
from custom_components.dynamic_home import options_spec as spec
from custom_components.dynamic_home.dc_engine import DcConfig


def test_every_field_exists_on_its_dataclass():
    for module in (const.MODULE_VMC, const.MODULE_SHUTTER, const.MODULE_CLIMATE):
        cfg = spec.fresh_config(module)
        for cat in spec.categories(module):
            for opt in spec.fields(module, cat):
                assert hasattr(cfg, opt.attr), f"{module}:{opt.attr} missing"
                # current_value must resolve (incl. tuple elements).
                spec.current_value(cfg, opt)


def test_every_category_has_a_label():
    for module_cats in spec.SPEC.values():
        for cat in module_cats:
            assert cat in spec.CATEGORIES


def test_apply_scalar_and_tuple_options():
    cfg = DcConfig()
    spec.apply_options(cfg, {
        "base_heat_day": 21.0,        # scalar float
        "vmc_bias_heat_2": 0.55,      # tuple element (1-based key -> index 1)
        "brake_thresholds_3": 1.5,
    }, const.MODULE_CLIMATE)
    assert cfg.base_heat_day == 21.0
    assert cfg.vmc_bias_heat == (0.1, 0.55, 0.3)
    assert cfg.brake_thresholds == (0.3, 0.6, 1.5)


def test_apply_ignores_unknown_keys_and_keeps_defaults():
    cfg = DcConfig()
    base = DcConfig()
    spec.apply_options(cfg, {"not_a_field": 1, "base_cool_day": 25.0},
                       const.MODULE_CLIMATE)
    assert cfg.base_cool_day == 25.0
    assert cfg.base_heat_day == base.base_heat_day   # untouched default


def test_advanced_fields_hidden_in_basic_mode():
    m = const.MODULE_CLIMATE
    # Basic mode hides expert fields; advanced shows them.
    basic = {spec.option_key(o) for c in spec.categories(m, False)
             for o in spec.fields(m, c, False)}
    full = {spec.option_key(o) for c in spec.categories(m, True)
            for o in spec.fields(m, c, True)}
    assert "base_heat_day" in basic            # everyday -> always visible
    assert "adapt_alpha" not in basic          # expert -> hidden in basic
    assert "adapt_alpha" in full
    # Categories that are entirely advanced disappear from the basic menu.
    assert "adaptive_lead" not in spec.categories(m, False)
    assert "adaptive_lead" in spec.categories(m, True)
    assert "setpoints" in spec.categories(m, False)


def test_preset_keys_are_valid_option_keys():
    for module in presets.PRESETS:
        valid = {spec.option_key(o)
                 for cat in spec.SPEC[module].values() for o in cat}
        for pid in presets.preset_ids(module):
            values = presets.preset_values(module, pid)
            assert values, f"{module}:{pid} empty"
            unknown = set(values) - valid
            assert not unknown, f"{module}:{pid} unknown keys {unknown}"


def test_preset_applies_onto_config():
    cfg = DcConfig()
    values = presets.preset_values(const.MODULE_CLIMATE, "salon_radiant_communal")
    spec.apply_options(cfg, values, const.MODULE_CLIMATE)
    assert cfg.step == 0.1 and cfg.apply_min_delta == 0.2
    assert cfg.insulation_factor == 0.6
    assert cfg.vmc_bias_heat == (0.05, 0.10, 0.15)
    assert cfg.brake_biases == (0.1, 0.2, 0.4)


def test_int_fields_coerced_to_int():
    cfg = spec.fresh_config(const.MODULE_SHUTTER)
    spec.apply_options(cfg, {"slew_step_pct": "15"}, const.MODULE_SHUTTER)
    assert cfg.slew_step_pct == 15 and isinstance(cfg.slew_step_pct, int)
