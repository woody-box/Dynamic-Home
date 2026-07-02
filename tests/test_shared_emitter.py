"""Unit tests for the pure shared-emitter reconciler (F25 Phase B).

Run with:  python -m pytest tests/test_shared_emitter.py -q
"""

from custom_components.dynamic_home import shared_emitter as se
from custom_components.dynamic_home.shared_emitter import SharedEmitterHub, ZoneDemand


def _z(eid, current, target, weight=1.0, margin=0.5, owner=False, hvac="heat"):
    return ZoneDemand(eid, hvac, current, target, weight, margin, owner)


def test_aggregate_policies():
    # Two zones, same lag, different target.
    a = _z("a", 19.0, 21.0)
    b = _z("b", 21.0, 23.0)
    assert se.aggregate_setpoint([a, b], "heat", "mean") == 22.0
    # Weighted with equal weight+lag == mean here.
    assert round(se.aggregate_setpoint([a, b], "heat", "weighted"), 2) == 22.0
    # Priority -> the highest-weight zone's target.
    assert se.aggregate_setpoint([_z("a", 19, 21, weight=3), b],
                                 "heat", "priority") == 21.0
    # Worst-stuck -> the most-behind zone's target (a is 2 short, b is 0).
    assert se.aggregate_setpoint([_z("a", 19, 21), _z("b", 23, 23)],
                                 "heat", "worst_stuck") == 21.0


def test_weight_biases_aggregate_toward_zone():
    a = _z("a", 19.0, 21.0)
    b = _z("b", 19.0, 23.0)             # same lag (2.0), different target
    base = se.aggregate_setpoint([a, b], "heat", "weighted")
    heavier_a = se.aggregate_setpoint([_z("a", 19, 21, weight=4), b],
                                      "heat", "weighted")
    assert heavier_a < base            # biased toward Salón a's lower target


def test_undershoot_cut_on_overconditioning_without_starving():
    # v0.96.0: the guard cuts on the OVER-conditioned side (setpoint + margin)
    # and never while another zone still genuinely lags — the old form cut at
    # setpoint - margin, so a satisfied bedroom starved the living room forever.
    salon = _z("salon", 19.0, 21.0)                  # genuinely lagging
    dorm_over = _z("dorm", 23.6, 23.0, margin=0.5)   # over-conditioned
    assert se.undershoot_cut([dorm_over], "heat") is True      # protect it
    assert se.undershoot_cut([salon, dorm_over], "heat") is False  # salón manda
    # A zone merely NEAR its setpoint (old trigger) no longer cuts anything.
    dorm_near = _z("dorm", 22.6, 23.0, margin=0.5)
    assert se.undershoot_cut([dorm_near], "heat") is False
    assert se.undershoot_cut([salon, _z("dorm", 21.0, 23.0)], "heat") is False


def test_reconcile_guards_and_grilles():
    salon = _z("salon", 19.0, 21.0)
    over = _z("dorm", 23.8, 23.0, margin=0.5)        # over-conditioned
    # Without grilles the guard cuts the unit once a zone over-conditions and
    # nobody genuinely lags (REQ-EMI-8, v0.96.0 semantics).
    cut = se.reconcile([over], "heat", grilles=False)
    assert cut["mode"] == "off" and cut["reason"] == "undershoot_cut"
    # A lagging sister keeps the unit alive.
    alive = se.reconcile([salon, over], "heat", grilles=False)
    assert alive["mode"] == "heat"
    # With grilles each zone throttles itself -> unit runs at the most-demanding.
    grilles = se.reconcile([salon, _z("dorm", 22.6, 23.0)], "heat", grilles=True)
    assert grilles["mode"] == "heat" and grilles["target"] == 21.0
    assert grilles["reason"] == "grilles"
    # No demand in this mode -> off.
    assert se.reconcile([], "heat")["mode"] == "off"


def test_reconcile_owner_off_follows_sisters_direction():
    # v0.96.0: the owner being off/idle must not kill the duct for its sisters.
    salon = _z("salon", 19.0, 21.0)
    d = se.reconcile([salon], "off")
    assert d["mode"] == "heat" and d["target"] == 21.0


def test_hub_report_owner_election_and_reconcile():
    hub = SharedEmitterHub()
    hub.report("duct", _z("z2", 19.0, 21.0))
    hub.report("duct", _z("z1", 20.0, 21.0))
    # No declared owner -> the lowest entry_id reconciles.
    assert hub.is_owner("duct", "z1") is True
    assert hub.is_owner("duct", "z2") is False
    # A declared owner wins regardless of id.
    hub.report("duct", _z("z2", 19.0, 21.0, owner=True))
    assert hub.is_owner("duct", "z2") is True
    assert hub.is_owner("duct", "z1") is False
    cmd = hub.reconcile("duct", "heat")
    assert cmd["mode"] == "heat" and cmd["target"] is not None


def test_hub_clear_and_clear_entry():
    hub = SharedEmitterHub()
    hub.report("d1", _z("z1", 19, 21))
    hub.report("d2", _z("z1", 19, 21))
    hub.clear_entry("z1")
    assert hub.is_owner("d1", "z1") is False
    assert hub.reconcile("d1", "heat")["mode"] == "off"
