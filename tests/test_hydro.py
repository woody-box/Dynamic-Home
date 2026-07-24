"""Unit tests for the pure hydraulic minimum-flow gate (weights per zone).

Run with:  python -m pytest tests/test_hydro.py -q
"""

from custom_components.dynamic_home.hydro import HydroFlowHub


def test_small_zone_alone_is_blocked_but_registered():
    hub = HydroFlowHub()
    # Bathroom (0.5) alone: below the 2.0 minimum -> blocked, demand registered.
    allowed, reason = hub.evaluate("bath", True, 0.5, 2.0)
    assert allowed is False and reason == "hydro_min_weight"
    assert hub.total() == 0.5


def test_heavy_zone_alone_is_allowed():
    hub = HydroFlowHub()
    # Living room (4.0) alone already moves enough water.
    assert hub.evaluate("salon", True, 4.0, 2.0) == (True, "granted")


def test_combined_weights_cross_the_minimum():
    hub = HydroFlowHub()
    assert hub.evaluate("bath", True, 0.5, 2.0)[0] is False
    # The main bedroom joins (1.5): total 2.0 reaches the minimum -> both open.
    assert hub.evaluate("dorm", True, 1.5, 2.0) == (True, "granted")
    assert hub.evaluate("bath", True, 0.5, 2.0) == (True, "granted")
    assert hub.total() == 2.0


def test_partner_leaving_drops_below_minimum_again():
    hub = HydroFlowHub()
    hub.evaluate("bath", True, 0.5, 2.0)
    hub.evaluate("salon", True, 4.0, 2.0)
    assert hub.evaluate("bath", True, 0.5, 2.0)[0] is True
    # The living room satisfies -> only 0.5 demanded -> the bathroom closes.
    assert hub.evaluate("salon", False, 4.0, 2.0) == (False, "idle")
    assert hub.evaluate("bath", True, 0.5, 2.0)[0] is False
    assert hub.total() == 0.5


def test_not_wanting_deregisters():
    hub = HydroFlowHub()
    hub.evaluate("bath", True, 0.5, 2.0)
    assert hub.evaluate("bath", False, 0.5, 2.0) == (False, "idle")
    assert hub.total() == 0.0


def test_clear_removes_the_zone():
    hub = HydroFlowHub()
    hub.evaluate("bath", True, 0.5, 2.0)
    hub.clear("bath")
    assert hub.total() == 0.0


def test_weight_update_is_refreshed_on_each_report():
    hub = HydroFlowHub()
    hub.evaluate("salon", True, 4.0, 2.0)
    # The user re-tunes the weight in options: the next report replaces it.
    hub.evaluate("salon", True, 1.0, 2.0)
    assert hub.total() == 1.0


def test_exact_minimum_is_allowed_despite_float_noise():
    hub = HydroFlowHub()
    # 3 × 0.1 sums to 0.30000000000000004-style noise; >= must not flicker.
    hub.evaluate("a", True, 0.1, 0.3)
    hub.evaluate("b", True, 0.1, 0.3)
    assert hub.evaluate("c", True, 0.1, 0.3) == (True, "granted")


def test_zero_minimum_always_allows():
    hub = HydroFlowHub()
    assert hub.evaluate("bath", True, 0.5, 0.0) == (True, "granted")
