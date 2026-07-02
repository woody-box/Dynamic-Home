"""Unit tests for the pure electrical-peak arbiter (F03).

Run with:  python -m pytest tests/test_peak.py -q
"""

from custom_components.dynamic_home.peak import PeakLoadHub


def _ev(hub, eid, demand, now, *, units=1.0, sustained=True, hold_s=0.0,
        max_units=2.0, stagger_s=0.0, priority=0.0):
    return hub.evaluate(eid, demand=demand, units=units, sustained=sustained,
                        hold_s=hold_s, now_ts=now, max_units=max_units,
                        stagger_s=stagger_s, priority=priority)


def test_count_budget_limits_simultaneous_starts():
    hub = PeakLoadHub()
    assert _ev(hub, "a", True, 0, max_units=2)[0] is True
    assert _ev(hub, "b", True, 0, max_units=2)[0] is True
    allowed, reason = _ev(hub, "c", True, 0, max_units=2)   # 3rd over budget
    assert allowed is False and reason == "peak_over_budget"
    # When one releases, the waiting one fits.
    assert _ev(hub, "a", False, 1, max_units=2) == (False, "idle")
    assert _ev(hub, "c", True, 1, max_units=2)[0] is True


def test_stagger_spaces_fresh_starts():
    hub = PeakLoadHub()
    assert _ev(hub, "a", True, 0, max_units=5, stagger_s=10)[0] is True
    # Within the stagger window the next start is deferred even with budget left.
    allowed, reason = _ev(hub, "b", True, 5, max_units=5, stagger_s=10)
    assert allowed is False and reason == "peak_stagger"
    # After the window it is granted.
    assert _ev(hub, "b", True, 11, max_units=5, stagger_s=10)[0] is True


def test_already_running_is_never_interrupted():
    hub = PeakLoadHub()
    assert _ev(hub, "a", True, 0, max_units=1)[0] is True
    # 'a' keeps running on later cycles even though the budget is full.
    assert _ev(hub, "a", True, 60, max_units=1) == (True, "on")
    # A different zone is still blocked.
    assert _ev(hub, "b", True, 60, max_units=1)[0] is False


def test_sustained_release_frees_the_slot():
    hub = PeakLoadHub()
    _ev(hub, "a", True, 0, max_units=1)
    assert hub.used(0) == 1.0
    assert _ev(hub, "a", False, 1, max_units=1) == (False, "idle")
    assert hub.used(1) == 0.0


def test_transient_slot_expires_after_hold():
    hub = PeakLoadHub()
    # A shutter move: transient pulse of 20 s.
    assert _ev(hub, "cover", True, 0, sustained=False, hold_s=20,
               max_units=1)[0] is True
    assert hub.used(10) == 1.0                       # still travelling
    assert hub.used(25) == 0.0                       # pulse expired/pruned
    # After expiry a fresh move is allowed again.
    assert _ev(hub, "cover", True, 25, sustained=False, hold_s=20,
               max_units=1)[0] is True


def test_power_mode_budget_in_watts():
    hub = PeakLoadHub()
    assert _ev(hub, "a", True, 0, units=1500, max_units=3500)[0] is True
    assert _ev(hub, "b", True, 0, units=1500, max_units=3500)[0] is True   # 3000
    allowed, reason = _ev(hub, "c", True, 0, units=1500, max_units=3500)    # 4500
    assert allowed is False and reason == "peak_over_budget"


def test_priority_grants_highest_deviation_waiter_first():
    hub = PeakLoadHub()
    # b registers as a waiter (over the 1-slot budget) with high priority.
    assert _ev(hub, "b", True, 0, max_units=1, priority=3.0)[0] is True
    # a tries while the budget is full and b is hungrier -> a registers too.
    assert _ev(hub, "a", True, 1, max_units=1, priority=1.0)[0] is False
    # b releases its slot; now a fits but must yield to the hungrier waiter... none
    # left (b is the only other) -> a is granted.
    # Build the real contested case: budget 1, b waiting (pri 3), a waiting (pri 1).
    hub2 = PeakLoadHub()
    _ev(hub2, "x", True, 0, max_units=1, priority=0.0)        # x holds the only slot
    assert _ev(hub2, "a", True, 0, max_units=1, priority=1.0)[0] is False  # waiter
    assert _ev(hub2, "b", True, 0, max_units=1, priority=3.0)[0] is False  # waiter
    _ev(hub2, "x", False, 1, max_units=1)                     # x releases
    # a fits but yields to b (higher priority); b is then granted.
    assert _ev(hub2, "a", True, 1, max_units=1, priority=1.0) == (False, "peak_yield")
    assert _ev(hub2, "b", True, 1, max_units=1, priority=3.0)[0] is True


def test_priority_default_is_first_come():
    # No priority -> equal -> whoever fits the budget is granted (today's behaviour).
    hub = PeakLoadHub()
    assert _ev(hub, "a", True, 0, max_units=1)[0] is True
    assert _ev(hub, "b", True, 0, max_units=1) == (False, "peak_over_budget")


def test_waiters_age_out_across_cycles():
    hub = PeakLoadHub()
    _ev(hub, "x", True, 0, max_units=1)                       # x holds the slot
    _ev(hub, "hungry", True, 0, max_units=1, priority=9.0)    # registers as waiter
    _ev(hub, "x", False, 1, max_units=1)                      # x releases
    # Long after the wait window, the stale hungry waiter no longer blocks a grant.
    assert _ev(hub, "a", True, 1000, max_units=1, priority=0.0)[0] is True


def test_clear_removes_a_participant():
    hub = PeakLoadHub()
    _ev(hub, "a", True, 0, max_units=1)
    hub.clear("a")
    assert hub.used(0) == 0.0
    assert _ev(hub, "b", True, 0, max_units=1)[0] is True


def test_yield_is_transient_no_permanent_starvation():
    """F03: ``peak_yield`` delays a mid-priority zone behind hungrier ones but
    never starves it. The instant a hungrier waiter is *granted* it moves to the
    active set and leaves the waiter pool, so a mid-priority zone is served as
    soon as the hotter ones clear — which is why no priority aging is needed.

    Covers the "medium-priority waiter under sustained higher-priority pressure"
    case: it yields repeatedly, then is granted once the finite stream relents.
    """
    hub = PeakLoadHub()
    _ev(hub, "x", True, 0, max_units=1, priority=0.0)          # x holds the only slot
    _ev(hub, "med", True, 0, max_units=1, priority=2.0)        # registers as a waiter
    _ev(hub, "hot", True, 0, max_units=1, priority=5.0)        # a hungrier waiter
    _ev(hub, "x", False, 1, max_units=1)                       # x releases the slot
    # The freed slot fits 'med', but it yields to the hungrier waiter...
    assert _ev(hub, "med", True, 1, max_units=1, priority=2.0) == (False, "peak_yield")
    assert _ev(hub, "hot", True, 1, max_units=1, priority=5.0)[0] is True   # hot served

    # Sustained pressure: another, still-hungrier zone keeps arriving while 'med'
    # waits. 'med' yields again — but each served zone leaves the pool.
    _ev(hub, "hot", False, 2, max_units=1)                     # hot reaches setpoint
    _ev(hub, "hot2", True, 2, max_units=1, priority=4.0)       # new hungrier grabs slot
    assert _ev(hub, "med", True, 2, max_units=1, priority=2.0)[0] is False  # waits
    _ev(hub, "hot2", False, 3, max_units=1)                    # hot2 done, slot frees

    # The stream is exhausted -> nothing hungrier remains -> 'med' is granted.
    assert _ev(hub, "med", True, 3, max_units=1, priority=2.0)[0] is True



def test_comfort_bypass_slot_counts_against_budget():
    # v0.96.0: a comfort-bypass zone runs regardless, but its watts occupy the
    # budget — otherwise the others fill it and the TOTAL trips the ICP.
    hub = PeakLoadHub()
    hub.force_grant("bypass", 1500.0, 0)
    assert hub.is_active("bypass") is True
    allowed, reason = _ev(hub, "b", True, 1, units=1000.0, max_units=2000.0)
    assert allowed is False and reason == "peak_over_budget"
    allowed, _ = _ev(hub, "c", True, 2, units=400.0, max_units=2000.0)
    assert allowed is True                                  # 1500 + 400 fits


def test_yield_only_when_the_hungrier_waiter_fits():
    # v0.96.0: a small load that fits must not idle the budget forever behind a
    # big waiter that never will.
    hub = PeakLoadHub()
    # 'big' (3000 W, very hungry) can never fit a 2000 W budget -> waits.
    allowed, reason = _ev(hub, "big", True, 0, units=3000.0, max_units=2000.0,
                          priority=2.0)
    assert allowed is False and reason == "peak_over_budget"
    # 'small' (1000 W, less hungry) fits and must NOT yield to 'big'.
    allowed, reason = _ev(hub, "small", True, 1, units=1000.0, max_units=2000.0,
                          priority=1.0)
    assert allowed is True
    # But when the hungrier waiter DOES fit, the smaller one still yields.
    hub2 = PeakLoadHub()
    _ev(hub2, "cold", True, 0, units=1500.0, max_units=1000.0, priority=2.0)
    allowed, reason = _ev(hub2, "warm", True, 1, units=800.0, max_units=2000.0,
                          priority=1.0)
    assert allowed is False and reason == "peak_yield"


def test_running_slot_units_follow_the_live_meter():
    # v0.96.0: the slot is booked at the estimate but tracks the live meter
    # once running, so the budget reflects the real draw.
    hub = PeakLoadHub()
    assert _ev(hub, "a", True, 0, units=1000.0, max_units=3000.0)[0] is True
    _ev(hub, "a", True, 1, units=2200.0, max_units=3000.0)   # live refresh
    allowed, reason = _ev(hub, "b", True, 2, units=1000.0, max_units=3000.0)
    assert allowed is False and reason == "peak_over_budget"  # 2200 + 1000 > 3000
