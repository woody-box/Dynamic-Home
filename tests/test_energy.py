"""Unit tests for the pure energy helpers (F06).

Run with:  python -m pytest tests/test_energy.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from energy import (  # noqa: E402
    add_kwh,
    dc_power_w,
    ds_move_kwh,
    vmc_power_w,
    window_kwh,
)


def test_add_kwh_integrates_power_over_time():
    # 1000 W for one hour = 1 kWh.
    assert add_kwh(0.0, 1000.0, 3600.0) == 1.0
    # Accumulates on top of the previous value.
    assert add_kwh(1.0, 1000.0, 1800.0) == 1.5


def test_add_kwh_ignores_nonpositive_or_none():
    assert add_kwh(2.0, None, 3600.0) == 2.0
    assert add_kwh(2.0, 0.0, 3600.0) == 2.0
    assert add_kwh(2.0, 1000.0, 0.0) == 2.0
    assert add_kwh(2.0, 1000.0, -10.0) == 2.0


def test_vmc_power_w_per_speed():
    watts = (15.0, 30.0, 55.0)
    assert vmc_power_w(0, watts) == 0.0
    assert vmc_power_w(1, watts) == 15.0
    assert vmc_power_w(2, watts) == 30.0
    assert vmc_power_w(3, watts) == 55.0


def test_dc_power_w_only_when_on():
    assert dc_power_w(True, 1000.0) == 1000.0
    assert dc_power_w(False, 1000.0) == 0.0


def test_ds_move_kwh_scales_with_delta():
    # 150 W motor, 20 s full travel, 50 % move -> 10 s of run.
    assert ds_move_kwh(50, 150.0, 20.0) == 150.0 * 10.0 / 3_600_000.0
    # Sign-independent and zero move costs nothing.
    assert ds_move_kwh(-50, 150.0, 20.0) == ds_move_kwh(50, 150.0, 20.0)
    assert ds_move_kwh(0, 150.0, 20.0) == 0.0


def test_window_kwh_consumption_over_rolling_window():
    # (ts, cumulative_kWh) snapshots ascending; live cumulative = 10.0, now = 1000.
    samples = [(0.0, 2.0), (100.0, 3.0), (500.0, 6.0)]
    # Last 600 s (cutoff 400): baseline = latest snapshot <= 400 = 3.0 -> 10 − 3.
    assert window_kwh(samples, 10.0, 1000.0, 600.0) == 7.0
    # Window longer than the history -> earliest snapshot (2.0), partial -> 8.
    assert window_kwh(samples, 10.0, 1000.0, 10_000.0) == 8.0
    # No history yet -> 0.
    assert window_kwh([], 10.0, 1000.0, 600.0) == 0.0
    # Never negative (cumulative below the baseline snapshot).
    assert window_kwh([(0.0, 20.0)], 10.0, 1000.0, 10_000.0) == 0.0


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
