"""Guard tests for the UI options catalogue.

Ensures every spec field really exists on its engine dataclass (no typos), that
defaults come from the dataclass, and that tuple fields round-trip correctly.
"""

from custom_components.dynamic_home import const
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


def test_int_fields_coerced_to_int():
    cfg = spec.fresh_config(const.MODULE_SHUTTER)
    spec.apply_options(cfg, {"slew_step_pct": "15"}, const.MODULE_SHUTTER)
    assert cfg.slew_step_pct == 15 and isinstance(cfg.slew_step_pct, int)
