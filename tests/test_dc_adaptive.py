"""Unit tests for the DC adaptive-lead state machine (coordinator side).

The learning loop lives on ``DcCoordinator`` but is pure Python: we drive it on
a bare instance (``__new__``, no Home Assistant needed) one tick at a time.
"""

from custom_components.dynamic_home.coordinator_dc import DcCoordinator
from custom_components.dynamic_home.dc_engine import DcConfig


def _coord() -> DcCoordinator:
    c = DcCoordinator.__new__(DcCoordinator)
    c.adaptive_enabled = True
    c.degraded = False
    c.learn_rate_ema = 0.0
    c.learn_overshoot_ema = 0.0
    c.learned_lag_h = 0.0
    c.lead_gain_adaptive = 0.0
    c.adapt_ok_count = 0
    c.adapt_abort_count = 0
    c._valve_open = False
    c._on_t0 = None
    c._on_t0_ts = None
    c._settling = False
    c._off_sp = None
    c._off_peak = None
    c._off_peak_ts = None
    c._off_ts = None
    c._off_hvac = None
    return c


def test_valve_demand_heat_cool():
    c = _coord()
    assert c._valve_demand("heat", 18.0, 21.0) is True
    assert c._valve_demand("heat", 22.0, 21.0) is False
    assert c._valve_demand("cool", 26.0, 24.0) is True
    assert c._valve_demand("cool", 22.0, 24.0) is False
    assert c._valve_demand("off", 18.0, 21.0) is False
    assert c._valve_demand("heat", None, 21.0) is False


def test_learns_a_full_heat_cycle():
    c = _coord()
    cfg = DcConfig()
    c._learn_step(cfg, 0, "heat", 18.0, 21.0, False, False)       # valve ON
    c._learn_step(cfg, 3600, "heat", 21.5, 21.0, False, False)    # valve OFF
    assert c._settling
    assert round(c.learn_rate_ema, 2) == 0.7   # 3.5°C/1h, EMA(0, 3.5, 0.2)
    c._learn_step(cfg, 3660, "heat", 21.8, 21.0, False, False)    # peak rises
    assert c._off_peak == 21.8
    c._learn_step(cfg, 14400, "heat", 21.8, 21.0, False, False)   # window elapsed
    assert not c._settling
    assert c.adapt_ok_count == 1
    assert c.adapt_abort_count == 0
    assert c.learn_overshoot_ema > 0   # peak 21.8 over setpoint 21.0
    assert c.lead_gain_adaptive > 0    # gradient stepped toward a positive lead


def test_aborts_when_window_opens_during_settling():
    c = _coord()
    cfg = DcConfig()
    c._learn_step(cfg, 0, "heat", 18.0, 21.0, False, False)
    c._learn_step(cfg, 3600, "heat", 21.5, 21.0, False, False)
    c._learn_step(cfg, 3660, "heat", 21.8, 21.0, True, False)     # window -> abort
    assert not c._settling
    assert c.adapt_abort_count == 1
    assert c.adapt_ok_count == 0


def test_reopening_valve_aborts_settling():
    c = _coord()
    cfg = DcConfig()
    c._learn_step(cfg, 0, "heat", 18.0, 21.0, False, False)
    c._learn_step(cfg, 3600, "heat", 21.5, 21.0, False, False)
    # Temp falls back below setpoint -> valve reopens -> previous cycle aborts.
    c._learn_step(cfg, 3700, "heat", 20.5, 21.0, False, False)
    assert c.adapt_abort_count == 1
    assert c._valve_open is True   # a fresh ON cycle started
