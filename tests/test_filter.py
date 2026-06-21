"""Unit tests for the pure filter-life helper (F08)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "custom_components", "dynamic_home"))

from dv_engine import filter_life_pct  # noqa: E402


def test_fresh_filter_is_full():
    assert filter_life_pct(0, 3650) == 100.0


def test_half_life():
    assert filter_life_pct(1825, 3650) == 50.0


def test_exactly_spent_is_zero():
    assert filter_life_pct(3650, 3650) == 0.0


def test_over_life_clamps_to_zero():
    assert filter_life_pct(5000, 3650) == 0.0


def test_nonpositive_life_reports_full():
    assert filter_life_pct(1000, 0) == 100.0
    assert filter_life_pct(1000, -5) == 100.0


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
