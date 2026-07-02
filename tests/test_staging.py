"""Unit tests for the pure primary/support staging machine (F25 Phase A).

Run with:  python -m pytest tests/test_staging.py -q
"""

from custom_components.dynamic_home import staging
from custom_components.dynamic_home.dc_engine import DcConfig

CFG = DcConfig(support_dev_on=0.6, support_confirm_min=15.0,
               support_dev_off=0.2, support_release_min=10.0)
CONFIRM_S = 15.0 * 60.0
RELEASE_S = 10.0 * 60.0


def test_deviation_direction():
    assert staging.deviation("heat", 19.0, 21.0) == 2.0     # 2°C short of heat
    assert staging.deviation("cool", 27.0, 25.0) == 2.0     # 2°C over cool
    assert staging.deviation("heat", 22.0, 21.0) == -1.0    # already past
    assert staging.deviation("off", 19.0, 21.0) == 0.0
    assert staging.deviation("heat", None, 21.0) == 0.0


def test_support_arms_only_after_confirm_time():
    st = staging.StagingState()
    # Big lag, but not yet confirmed.
    on, reason = staging.step(st, "heat", 19.0, 21.0, 0.0, CFG)
    assert on is False and reason == "support_arming"
    # Still within the confirm window.
    assert staging.step(st, "heat", 19.0, 21.0, CONFIRM_S - 1, CFG)[0] is False
    # Past the confirm window -> support engages.
    on, reason = staging.step(st, "heat", 19.0, 21.0, CONFIRM_S, CFG)
    assert on is True and reason == "support_on"


def test_arming_resets_if_lag_clears():
    st = staging.StagingState()
    staging.step(st, "heat", 19.0, 21.0, 0.0, CFG)          # start arming
    # Recovers before confirm -> timer resets, stays off.
    on, reason = staging.step(st, "heat", 21.0, 21.0, 100.0, CFG)
    assert on is False and reason == "idle"
    assert st.lag_since is None


def test_support_retires_with_hysteresis():
    st = staging.StagingState(on=True)
    # Recovered under the off-band, but must hold for release time first.
    on, reason = staging.step(st, "heat", 20.9, 21.0, 0.0, CFG)   # dev 0.1 < 0.2
    assert on is True and reason == "support_settling"
    assert staging.step(st, "heat", 20.9, 21.0, RELEASE_S - 1, CFG)[0] is True
    on, reason = staging.step(st, "heat", 20.9, 21.0, RELEASE_S, CFG)
    assert on is False and reason == "support_off"


def test_settle_resets_if_lag_returns():
    st = staging.StagingState(on=True)
    staging.step(st, "heat", 20.9, 21.0, 0.0, CFG)          # start settling
    # Falls behind again -> stays on, settle timer cleared.
    on, reason = staging.step(st, "heat", 19.5, 21.0, 100.0, CFG)
    assert on is True and reason == "support_on"
    assert st.settle_since is None


def test_off_mode_drops_support():
    st = staging.StagingState(on=True)
    on, reason = staging.step(st, "off", 19.0, 21.0, 0.0, CFG)
    assert on is False and reason == "off"
    assert st.on is False


def test_cool_direction_arms_on_overshoot():
    st = staging.StagingState()
    staging.step(st, "cool", 27.0, 25.0, 0.0, CFG)          # 2°C over -> arming
    assert staging.step(st, "cool", 27.0, 25.0, CONFIRM_S, CFG)[0] is True


def test_direction_flip_resets_the_support_latch():
    # v0.97.0: a support armed for heating must not stay latched on into a
    # cooling run, waiting out the release hysteresis in the wrong direction.
    cfg = DcConfig(support_dev_on=0.6, support_confirm_min=0.0)
    st = staging.StagingState()
    on, _ = staging.step(st, "heat", 18.0, 21.0, 0.0, cfg)   # lag -> arms
    assert on is True
    on, reason = staging.step(st, "cool", 18.0, 21.0, 60.0, cfg)
    assert on is False                                        # reset, re-evaluated
