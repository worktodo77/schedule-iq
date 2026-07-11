"""Tests for the LI-proprietary indices (backlog N6/N9/N10/N12/N14).

Fixture-based assertions run against the seeded three-update series
(tests/fixtures/make_fixtures.py), whose float erosion (float_shift 0 -> -2 ->
-12 working days on the critical chain) guarantees non-zero float burn.
Synthetic in-memory schedules pin the shared criticality kernel, an exact
hand-computed FCBI, and a BWI projected-break date to closed-form values.
"""
import os
import subprocess
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load_many                             # noqa: E402
from scheduleiq.ingest.model import (Activity, ActivityStatus,      # noqa: E402
                                     ActivityType, ConstraintType,
                                     Relationship, Schedule)
from scheduleiq.compare.diff import compare                         # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis, analyze_series  # noqa: E402
from scheduleiq.analytics.li_indices import (                       # noqa: E402
    kernel_weight, run_li_indices, fcbi_lambda_sensitivity)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not os.path.exists(BASELINE):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


@pytest.fixture(scope="session")
def indices(series):
    return run_li_indices(series)


# ============================================================ shared kernel
def test_kernel_weights_closed_form():
    # driving-path float weighs full; each half-weight constant halves it
    assert kernel_weight(0.0, 5.0) == pytest.approx(1.0)
    assert kernel_weight(5.0, 5.0) == pytest.approx(0.5)
    assert kernel_weight(10.0, 5.0) == pytest.approx(0.25)
    # negative float (over-critical) weighs above 1.0
    assert kernel_weight(-5.0, 5.0) == pytest.approx(2.0)


# ============================================ FCBI v0.5 (LI-01 governed O1-O7)
# Probe set §P of the LI-01 v0.5 revision, built as hand-built in-memory series.
# Every activity carries a finish date so float_paths enumerates a real path to
# the target milestone m (the v0.5 distance basis, ruling O1).
from datetime import timedelta                                      # noqa: E402

_H = 8.0
_DFIN = datetime(2025, 6, 30, 17)


def _a(uid, code, tf_days, *, atype=ActivityType.TASK,
       status=ActivityStatus.NOT_STARTED, constraint=ConstraintType.NONE,
       cdate=None, od=10, rem=10, ef=_DFIN, af=None, tf_hours=None, xf=None):
    return Activity(uid=uid, code=code, atype=atype, status=status,
                    total_float_hours=(tf_hours if tf_hours is not None
                                       else (None if tf_days is None else tf_days * _H)),
                    original_duration_hours=od * _H, remaining_duration_hours=rem * _H,
                    early_start=(ef - timedelta(days=od)) if ef else None,
                    early_finish=ef, actual_finish=af, constraint=constraint,
                    constraint_date=cdate, expected_finish=xf)


def _m(uid, code, tf_days=0.0, constraint=ConstraintType.NONE, cdate=None, ef=_DFIN):
    return _a(uid, code, tf_days, atype=ActivityType.FINISH_MILESTONE, od=0, rem=0,
              constraint=constraint, cdate=cdate, ef=ef)


def _s(dd, acts, rels):
    sc = Schedule(project_id="P", data_date=dd, activities={a.uid: a for a in acts})
    sc.relationships = list(rels)
    return sc


def _fcbi(scheds, target="T"):
    css = [compare(scheds[i], scheds[i + 1]) for i in range(len(scheds) - 1)]
    sa = SeriesAnalysis(schedules=scheds, changesets=css)
    return run_li_indices(sa, fcbi_target=target).fcbi


def test_fcbi_demo_series_v05(series):
    """v0.5 on the seeded three-update demo (target = A1200, the constrained
    completion deadline).  Window 1 is operational with positive gross burn and
    a computed coverage; window 2 correctly fires the basis-change gate (the
    fixture flips retained-logic and edits a calendar in update 2) and is
    segmented out of the operational trend (ruling O7.9)."""
    fcbi = run_li_indices(series, fcbi_target="A1200").fcbi
    assert fcbi.reason == ""
    assert fcbi.target_code == "A1200"
    w0 = fcbi.windows[0]
    assert not w0.basis_change and w0.burn_gross > 0
    assert w0.coverage is not None and 0.0 < w0.coverage <= 1.0
    assert w0.burn_rate is not None and w0.working_days is not None
    # B is unweighted gross; W = B*C is the weighted diagnostic
    assert w0.burn_weighted == pytest.approx(w0.burn_gross * w0.burn_proximity)
    # update 2 changed the scheduling basis -> basis-change window, segmented
    w1 = fcbi.windows[1]
    assert w1.basis_change and w1.basis_change_reasons
    assert fcbi.cumulative_burn[1] is None
    # decomposition ranked by weighted contribution; no weight exceeds 1 (O1)
    assert fcbi.top_burners
    assert all(0.0 < b.weight <= 1.0 and b.distance_days >= 0.0
               for b in fcbi.top_burners)


def test_fcbi_p1_worked_example():
    """P1 — X(0->-3 driver), Y(5->9 recovery), Z(10->8).  v0.5 must give
    X d=0, Z d=10, no weight above 1.0; B=5, C=0.7, W=B*C=3.5."""
    rels = [Relationship("X", "T"), Relationship("Y", "T"), Relationship("Z", "T")]
    e = _s(datetime(2025, 1, 6, 8),
           [_a("X", "X", 0.0), _a("Y", "Y", 5.0), _a("Z", "Z", 10.0), _m("T", "T", 0.0)], rels)
    l = _s(datetime(2025, 2, 6, 8),
           [_a("X", "X", -3.0), _a("Y", "Y", 9.0), _a("Z", "Z", 8.0), _m("T", "T", -3.0)], rels)
    w = _fcbi([e, l]).windows[0]
    byc = {b.code: b for b in w.top_burners}
    assert byc["X"].distance_days == pytest.approx(0.0)      # driver
    assert byc["Z"].distance_days == pytest.approx(10.0)     # 10 - 0
    assert all(b.weight <= 1.0 for b in w.top_burners)       # no over-critical premium
    assert w.burn_gross == pytest.approx(5.0)                # B = c_X(3) + c_Z(2)
    assert w.burn_proximity == pytest.approx(0.7)            # C = (3*1 + 2*0.25)/5
    assert w.burn_weighted == pytest.approx(3.5)             # W = B*C = old weighted sum
    assert w.recov_gross == pytest.approx(4.0)               # Y regained 4d
    assert w.recov_proximity == pytest.approx(0.5)           # C- = w(d_Y=5)


def _p2(dd, qtf):
    r = [Relationship("D", "T"), Relationship("Q", "T")]
    return _s(dd, [_a("D", "D", 0.0), _a("Q", "Q", qtf, od=30, rem=30), _m("T", "T", 0.0)], r)


def test_fcbi_p2_monotonic_cadence():
    """P2 — d 10->0, c=10, one window vs two.  The min-endpoint timing is
    cadence-dependent (10 as one window, 7.5 as two): the counterexample that
    supersedes the v0.4.2 min-RF ruling (O3)."""
    one = _fcbi([_p2(datetime(2025, 1, 6, 8), 10.0),
                 _p2(datetime(2025, 2, 6, 8), 0.0)]).windows[0]
    assert one.timing.start == pytest.approx(2.5)
    assert one.timing.end == pytest.approx(10.0)
    assert one.timing.min_endpoint == pytest.approx(10.0)
    two = _fcbi([_p2(datetime(2025, 1, 6, 8), 10.0), _p2(datetime(2025, 1, 20, 8), 5.0),
                 _p2(datetime(2025, 2, 6, 8), 0.0)])
    assert sum(x.timing.start for x in two.windows) == pytest.approx(3.75)
    assert sum(x.timing.end for x in two.windows) == pytest.approx(7.5)
    assert sum(x.timing.min_endpoint for x in two.windows) == pytest.approx(7.5)


def test_fcbi_p3_identity_w_equals_b_times_c():
    """P3 — W = B*C on any fixture window with positive burn."""
    w = _fcbi([_p2(datetime(2025, 1, 6, 8), 10.0),
               _p2(datetime(2025, 2, 6, 8), 4.0)]).windows[0]
    assert w.burn_gross > 0
    assert w.burn_weighted == pytest.approx(w.burn_gross * w.burn_proximity)


def test_fcbi_p4_sensitivity_set_not_bounds():
    """P4 — opposite-direction burners (moving driver): the min-endpoint
    aggregate strictly EXCEEDS both endpoint aggregates, proving the
    endpoint-timing set is a sensitivity set, not a band/bounds (O3)."""
    def p4(dd, dr, a_tf, b_tf):
        r = [Relationship("DR", "T"), Relationship("A", "T"), Relationship("B", "T")]
        return _s(dd, [_a("DR", "DR", dr, od=40, rem=40), _a("A", "A", a_tf, od=40, rem=40),
                       _a("B", "B", b_tf, od=40, rem=40), _m("T", "T", 0.0)], r)
    w = _fcbi([p4(datetime(2025, 1, 6, 8), 0.0, 8.0, 12.0),
               p4(datetime(2025, 2, 6, 8), -20.0, 2.0, -19.0)]).windows[0]
    assert w.timing.min_endpoint > w.timing.start + 1e-6
    assert w.timing.min_endpoint > w.timing.end + 1e-6


def test_fcbi_p5_zero_burn_c_not_applicable():
    """P5 — zero-burn window: C reported NOT APPLICABLE with a labelled
    reason, never 0 (O2)."""
    w = _fcbi([_p2(datetime(2025, 1, 6, 8), 0.0),
               _p2(datetime(2025, 2, 6, 8), 0.0)]).windows[0]
    assert w.burn_gross == pytest.approx(0.0)
    assert w.burn_proximity is None
    assert "NOT APPLICABLE" in w.burn_proximity_reason


def test_fcbi_p6_target_shift_basis_change():
    """P6 — target completion date pulled 10d earlier on an otherwise unchanged
    network: basis-change window fires, zero operational burn, requirement-
    induced margin change reported separately (O7.9)."""
    def p6(dd, cdate, ttf):
        r = [Relationship("A", "T")]
        return _s(dd, [_a("A", "A", 0.0),
                       _m("T", "T", ttf, constraint=ConstraintType.MANDATORY_FINISH,
                          cdate=cdate)], r)
    res = _fcbi([p6(datetime(2025, 1, 6, 8), _DFIN, 0.0),
                 p6(datetime(2025, 2, 6, 8), _DFIN - timedelta(days=10), -10.0)])
    w = res.windows[0]
    assert w.basis_change and w.basis_change_reasons
    assert w.burn_gross == pytest.approx(0.0)               # zero execution erosion
    assert res.cumulative_burn[0] is None                    # segmented out of trend
    assert w.requirement_margin_change == pytest.approx(10.0)
    assert w.n_severity == pytest.approx(10.0)               # target 10d negative


def test_fcbi_p7_propagated_governance_quarantine():
    """P7 — A -> M(constrained) -> completion.  A carries no constraint of its
    own, but its late dates are governed by M; predicate (3) routes A's burn to
    quarantine and coverage reflects it (O6)."""
    def p7(dd, atf):
        r = [Relationship("A", "M"), Relationship("M", "C")]
        return _s(dd, [_a("A", "A", atf, od=10, rem=10),
                       _m("M", "M", 0.0, constraint=ConstraintType.MANDATORY_FINISH,
                          ef=_DFIN - timedelta(days=5)),
                       _m("C", "C", 5.0, ef=_DFIN)], r)
    w = _fcbi([p7(datetime(2025, 1, 6, 8), 2.0),
               p7(datetime(2025, 2, 6, 8), -1.0)], target="C").windows[0]
    assert "A" in {q.code for q in w.quarantine}
    assert "A" not in {b.code for b in w.top_burners}
    assert w.coverage is not None and w.coverage < 1.0
    assert w.quarantine_burn > 0


def test_fcbi_p8_split_changes_b():
    """P8 — subdividing a burning activity changes B: the disclosed granularity
    property (B is a gross activity-day aggregate, not a stock, O2)."""
    def whole(dd, tf):
        r = [Relationship("D", "T"), Relationship("W", "T")]
        return _s(dd, [_a("D", "D", 0.0), _a("W", "W", tf, od=20, rem=20), _m("T", "T", 0.0)], r)
    def split(dd, tf):
        r = [Relationship("D", "T"), Relationship("W1", "T"), Relationship("W2", "T")]
        return _s(dd, [_a("D", "D", 0.0), _a("W1", "W1", tf, od=10, rem=10),
                       _a("W2", "W2", tf, od=10, rem=10), _m("T", "T", 0.0)], r)
    bw = _fcbi([whole(datetime(2025, 1, 6, 8), 4.0), whole(datetime(2025, 2, 6, 8), 0.0)]).windows[0]
    bs = _fcbi([split(datetime(2025, 1, 6, 8), 4.0), split(datetime(2025, 2, 6, 8), 0.0)]).windows[0]
    assert bw.burn_gross != pytest.approx(bs.burn_gross)


def test_fcbi_p9_unequal_windows_burn_rate():
    """P9 — unequal windows (21d, ~90d): burn-rate normalization present in
    every window's output (O7.10)."""
    r9 = _fcbi([_p2(datetime(2025, 1, 6, 8), 10.0), _p2(datetime(2025, 2, 4, 8), 6.0),
                _p2(datetime(2025, 6, 9, 8), 0.0)])
    assert all(x.burn_rate is not None and x.working_days is not None for x in r9.windows)
    assert r9.windows[0].working_days != pytest.approx(r9.windows[1].working_days)


def test_fcbi_p10_tier1_tolerance():
    """P10 — sub-precision hour jitter (< Tier-1 hour tolerance) produces zero
    burn; tolerance applied in HOURS before the hour->day conversion (O4)."""
    def p10(dd, tf_hours):
        r = [Relationship("D", "T"), Relationship("J", "T")]
        return _s(dd, [_a("D", "D", 0.0), _a("J", "J", None, tf_hours=tf_hours),
                       _m("T", "T", 0.0)], r)
    w = _fcbi([p10(datetime(2025, 1, 6, 8), 40.0),
               p10(datetime(2025, 2, 6, 8), 40.0 - 0.25)]).windows[0]   # 0.25h < 0.5h tol
    assert w.burn_gross == pytest.approx(0.0)


def test_fcbi_p11_completion_omission():
    """P11 — an activity burning 15d then completing in-window appears in the
    completion-omission diagnostic with prior float and weight, and NOT in B
    (O5)."""
    def p11(dd, btf, done):
        r = [Relationship("B", "T"), Relationship("L", "T")]
        b = _a("B", "B", btf, od=20, rem=(0 if done else 20),
               status=ActivityStatus.COMPLETED if done else ActivityStatus.NOT_STARTED,
               af=datetime(2025, 1, 20, 17) if done else None)
        return _s(dd, [b, _a("L", "L", 2.0, od=10, rem=10), _m("T", "T", 0.0)], r)
    w = _fcbi([p11(datetime(2025, 1, 6, 8), 5.0, False),
               p11(datetime(2025, 2, 6, 8), -10.0, True)]).windows[0]
    co = {c.code: c for c in w.completion_omission}
    assert "B" in co
    assert co["B"].prior_pos_float_days == pytest.approx(5.0)
    assert co["B"].prior_weight is not None
    assert "B" not in {b.code for b in w.top_burners}       # excluded from B
    assert w.completed_in_window == 1


def test_fcbi_worked_example_anchor_v05():
    """The v0.5 worked-example regression anchor (supersedes X/Y/Z; the briefing
    exhibit).  Exercises a d=0 driver, a governed->quarantined activity,
    coverage < 100%, and the N/dN+ negative-float severity output.

        DRV : TF 0 -> -4  driver, d=0, w=1        (eligible burn 4)
        NEAR: TF 5 -> 2   near-critical, d=5, w=0.5 (eligible burn 3)
        GOV : TF 1 -> -2  governed by GATE(MANDFIN) -> quarantined (burn 3)
        COMP: TF 0 -> -4  target terminal -> N=4, dN+=4
    B = 4+3 = 7 ; W = 4*1 + 3*0.5 = 5.5 ; C = 5.5/7 ; coverage = 7/(7+3) = 0.7
    """
    rels = [Relationship("DRV", "COMP"), Relationship("NEAR", "COMP"),
            Relationship("GOV", "GATE"), Relationship("GATE", "COMP")]

    def build(dd, drv, near, gov, comp):
        return _s(dd, [_a("DRV", "DRV", drv), _a("NEAR", "NEAR", near),
                       _a("GOV", "GOV", gov),
                       _m("GATE", "GATE", 0.0, constraint=ConstraintType.MANDATORY_FINISH,
                          ef=_DFIN - timedelta(days=2)),
                       _m("COMP", "COMP", comp, ef=_DFIN)], rels)
    w = _fcbi([build(datetime(2025, 3, 3, 8), 0.0, 5.0, 1.0, 0.0),
               build(datetime(2025, 4, 7, 8), -4.0, 2.0, -2.0, -4.0)], target="COMP").windows[0]
    byc = {b.code: b for b in w.top_burners}
    assert byc["DRV"].distance_days == pytest.approx(0.0) and byc["DRV"].weight == pytest.approx(1.0)
    assert byc["NEAR"].distance_days == pytest.approx(5.0)
    assert w.burn_gross == pytest.approx(7.0)
    assert w.burn_weighted == pytest.approx(5.5)
    assert w.burn_proximity == pytest.approx(5.5 / 7.0)
    assert w.coverage == pytest.approx(0.7)
    assert w.quarantine_burn == pytest.approx(3.0)
    assert "GOV" in {q.code for q in w.quarantine}
    assert w.n_severity == pytest.approx(4.0) and w.n_deepening == pytest.approx(4.0)


def test_fcbi_forecast_slip_is_not_a_basis_change():
    """Post-review regression (finding F1).  A moving *forecast* on an
    unconstrained completion milestone is ordinary execution erosion and must
    stay in the operational trend; only a moving *requirement* basis (constraint
    date / rebaseline) is a basis-change window (O7.9).  A false trip would also
    restart the cumulative and discard previously accumulated burn."""
    def bld(dd, atf, ef):
        r = [Relationship("A", "T"), Relationship("B2", "T")]
        return _s(dd, [_a("A", "A", atf), _a("B2", "B2", 0.0), _m("T", "T", atf, ef=ef)], r)
    # unconstrained target whose forecast slips 6d then 10d across two windows
    res = _fcbi([bld(datetime(2025, 1, 6, 8), 0.0, _DFIN),
                 bld(datetime(2025, 2, 6, 8), -6.0, _DFIN + timedelta(days=6)),
                 bld(datetime(2025, 3, 6, 8), -10.0, _DFIN + timedelta(days=10))], target="T")
    assert not any(w.basis_change for w in res.windows)      # pure erosion
    assert all(c is not None for c in res.cumulative_burn)   # nothing segmented out
    assert res.cumulative_burn[-1] > res.cumulative_burn[0]  # burn accumulates
    # control: a genuine constraint-date move still fires the basis-change gate
    def con(dd, cdate):
        return _s(dd, [_a("A", "A", 0.0),
                       _m("T", "T", 0.0 if cdate == _DFIN else -10.0,
                          constraint=ConstraintType.MANDATORY_FINISH, cdate=cdate)],
                  [Relationship("A", "T")])
    cw = _fcbi([con(datetime(2025, 1, 6, 8), _DFIN),
                con(datetime(2025, 2, 6, 8), _DFIN - timedelta(days=10))], target="T").windows[0]
    assert cw.basis_change and cw.requirement_margin_change == pytest.approx(10.0)


def test_fcbi_offpath_negative_feeder_preserves_driver():
    """Post-review regression (finding F2).  An off-driving-path feeder pushed
    negative by a non-target constraint must NOT become the distance reference:
    the true rank-1 driver keeps d=0 / w=1 (O1's mandatory 'driving-path d=0'),
    so C is not silently biased down by a quarantined activity."""
    rels = [Relationship("A", "T"), Relationship("B", "C"), Relationship("C", "T")]
    def bld(dd, atf, btf):
        return _s(dd, [_a("A", "A", atf),
                       _a("B", "B", btf, constraint=ConstraintType.FINISH_ON_OR_BEFORE),
                       _a("C", "C", 10.0), _m("T", "T", 0.0)], rels)
    w = _fcbi([bld(datetime(2025, 1, 6, 8), 0.0, -5.0),
               bld(datetime(2025, 2, 6, 8), -2.0, -5.0)], target="T").windows[0]
    byc = {b.code: b for b in w.top_burners}
    assert byc["A"].distance_days == pytest.approx(0.0)      # driver stays the driver
    assert byc["A"].weight == pytest.approx(1.0)
    assert w.burn_proximity == pytest.approx(1.0)            # C not biased by feeder


def test_fcbi_completer_with_unknown_prior_still_disclosed():
    """Post-review regression (finding F3).  A completer whose prior float is
    unknown is still counted and disclosed in the omission diagnostic (O5's
    purpose: a heavy-completion month must never look benign), with prior fields
    left None rather than the completer dropped entirely."""
    r = [Relationship("B", "T"), Relationship("L", "T")]
    e = _s(datetime(2025, 1, 6, 8),
           [_a("B", "B", None, tf_hours=None), _a("L", "L", 2.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8),
           [_a("B", "B", None, tf_hours=None, status=ActivityStatus.COMPLETED, rem=0,
               af=datetime(2025, 1, 20, 17)), _a("L", "L", 2.0), _m("T", "T", 0.0)], r)
    w = _fcbi([e, l], target="T").windows[0]
    assert w.completed_in_window == 1
    co = {c.code: c for c in w.completion_omission}
    assert "B" in co and co["B"].prior_pos_float_days is None   # prior unknown, still shown


# ---- peer-review wave 2 (Codex REV-01..17): regressions ------------------
def test_fcbi_target_resolves_terminal_not_intermediate():
    """REV-01: the auto-resolved target is a TERMINAL finish milestone, never a
    constrained intermediate milestone or a task."""
    from scheduleiq.analytics.li_indices import _resolve_fcbi_target
    r = [Relationship("A", "M"), Relationship("M", "C")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0),
           _m("M", "M", 0.0, constraint=ConstraintType.MANDATORY_FINISH,
              ef=_DFIN - timedelta(days=30)), _m("C", "C", 0.0, ef=_DFIN)], r)
    code, auto = _resolve_fcbi_target([e], None)
    assert code == "C" and auto is True


def test_fcbi_invalid_lambda_never_raises():
    """REV-12: a non-positive / non-finite lambda returns a reason, never raises."""
    r = [Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", -3.0), _m("T", "T", 0.0)], r)
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    for lam in (0.0, -5.0, float("nan"), float("inf")):
        res = run_li_indices(sa, fcbi_target="T", lam=lam).fcbi
        assert "invalid lambda" in res.reason


def test_fcbi_stable_series_no_false_unresolved_reason():
    """REV-13: a fully resolvable but zero-movement window is NOT reported as a
    distance-resolution failure."""
    r = [Relationship("D", "T"), Relationship("A2", "T")]
    def bld(dd):
        return _s(dd, [_a("D", "D", 0.0), _a("A2", "A2", 5.0), _m("T", "T", 0.0)], r)
    res = _fcbi([bld(datetime(2025, 1, 6, 8)), bld(datetime(2025, 2, 6, 8))], target="T")
    assert res.reason == "" and res.windows[0].burn_gross == pytest.approx(0.0)


def test_fcbi_distance_on_fixed_reference_calendar():
    """REV-02: the distance is on the fixed 8h reference basis, not each
    activity's native calendar (A: 40h float => d=5, not 40/10=4)."""
    from scheduleiq.ingest.model import Calendar
    c10 = Calendar(uid="C10", hours_per_day=10.0)
    c8 = Calendar(uid="C8", hours_per_day=8.0, is_default=True)
    rels = [Relationship("A", "T"), Relationship("B", "T")]
    def bld(dd, a_h):
        s = _s(dd, [_a("A", "A", None, tf_hours=a_h), _a("B", "B", 0.0),
                    _m("T", "T", 0.0)], rels)
        s.activities["A"].calendar_uid = "C10"
        s.calendars = {"C10": c10, "C8": c8}
        return s
    w = _fcbi([bld(datetime(2025, 1, 6, 8), 40.0),
               bld(datetime(2025, 2, 6, 8), 32.0)], target="T").windows[0]
    assert {b.code: b for b in w.top_burners}["A"].distance_days == pytest.approx(5.0)


def test_fcbi_loe_excluded_from_path_margin():
    """REV-07: a level-of-effort node on a feeder cannot set the branch margin
    (discrete members only) — A keeps d=10, not the LOE's 1."""
    rels = [Relationship("D", "T"), Relationship("A", "L"), Relationship("L", "T")]
    def bld(dd, a_tf):
        return _s(dd, [_a("D", "D", 0.0), _a("A", "A", a_tf),
                       _a("L", "L", 1.0, atype=ActivityType.LOE), _m("T", "T", 0.0)], rels)
    w = _fcbi([bld(datetime(2025, 1, 6, 8), 10.0),
               bld(datetime(2025, 2, 6, 8), 8.0)], target="T").windows[0]
    assert {b.code: b for b in w.top_burners}["A"].distance_days == pytest.approx(10.0)


def test_fcbi_basis_change_not_presented_as_operational():
    """REV-03: a basis-change window does not populate the operational aggregate
    and its cumulative restarts; the wiring reports it as basis-change, and a
    prior segment is not revived as the headline."""
    def con(dd, cdate, atf, ttf):
        return _s(dd, [_a("A", "A", atf),
                       _m("T", "T", ttf, constraint=ConstraintType.MANDATORY_FINISH,
                          cdate=cdate)], [Relationship("A", "T")])
    res = _fcbi([con(datetime(2025, 1, 6, 8), _DFIN, 0.0, 0.0),
                 con(datetime(2025, 1, 20, 8), _DFIN, -5.0, 0.0),
                 con(datetime(2025, 2, 6, 8), _DFIN - timedelta(days=10), -10.0, -10.0)],
                target="T")
    assert res.cumulative_burn[-1] is None          # latest is a basis-change restart
    assert res.windows[-1].basis_change


def test_fcbi_aggregate_burner_coherent_across_windows():
    """REV-09: an activity burning across windows at different distances has an
    aggregate row whose consumption * effective-weight == contribution."""
    def bld(dd, atf):
        return _s(dd, [_a("DR", "DR", 0.0, od=30), _a("A", "A", atf, od=30),
                       _m("T", "T", 0.0)], [Relationship("DR", "T"), Relationship("A", "T")])
    res = _fcbi([bld(datetime(2025, 1, 6, 8), 10.0), bld(datetime(2025, 1, 20, 8), 5.0),
                 bld(datetime(2025, 2, 6, 8), 0.0)], target="T")
    A = {b.code: b for b in res.top_burners}["A"]
    assert A.consumption_days * A.weight == pytest.approx(A.contribution)


def test_fcbi_governance_union_and_expected_finish():
    """REV-04: a non-target constraint ADDED mid-window, and a downstream
    expected finish, both quarantine the upstream burner (union of endpoints +
    propagation)."""
    r = [Relationship("A", "M"), Relationship("M", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _m("M", "M", 0.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0),
           _m("M", "M", 0.0, constraint=ConstraintType.MANDATORY_FINISH, cdate=_DFIN),
           _m("T", "T", 0.0)], r)
    w = _fcbi([e, l], target="T").windows[0]
    assert "A" in {q.code for q in w.quarantine} and w.burn_gross == pytest.approx(0.0)
    # downstream expected finish
    rk = [Relationship("A", "K"), Relationship("K", "T")]
    ek = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _a("K", "K", 0.0),
            _m("T", "T", 0.0)], rk)
    lk = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0),
            _a("K", "K", 0.0, xf=_DFIN), _m("T", "T", 0.0)], rk)
    wk = _fcbi([ek, lk], target="T").windows[0]
    assert "A" in {q.code for q in wk.quarantine}


def test_fcbi_basis_signature_ignores_stale_none_constraint():
    """REV-06: a stale constraint_date whose type is NONE is not a basis change;
    a project must-finish-by move is."""
    def stale(dd, cd):
        return _s(dd, [_a("A", "A", 0.0),
                       _m("T", "T", 0.0, constraint=ConstraintType.NONE, cdate=cd)],
                  [Relationship("A", "T")])
    w = _fcbi([stale(datetime(2025, 1, 6, 8), _DFIN),
               stale(datetime(2025, 2, 6, 8), _DFIN + timedelta(days=1))], target="T").windows[0]
    assert not w.basis_change
    def mfb(dd, m):
        s = _s(dd, [_a("A", "A", 0.0), _m("T", "T", 0.0)], [Relationship("A", "T")])
        s.must_finish_by = m
        return s
    w2 = _fcbi([mfb(datetime(2025, 1, 6, 8), _DFIN),
                mfb(datetime(2025, 2, 6, 8), _DFIN - timedelta(days=10))], target="T").windows[0]
    assert w2.basis_change


def test_fcbi_unmeasurable_and_milestone_and_recovery_quarantine():
    """REV-11/15/17: unmeasurable float is counted (coverage not misread), a
    non-target milestone is excluded from B and disclosed separately, and
    quarantined recovery is tracked."""
    # REV-11 unmeasurable
    r = [Relationship("D", "T"), Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("D", "D", 0.0), _a("A", "A", 5.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("D", "D", -1.0),
           _a("A", "A", None, tf_hours=None), _m("T", "T", 0.0)], r)
    w = _fcbi([e, l], target="T").windows[0]
    assert w.unmeasurable_count >= 1
    # REV-17 milestone excluded from B, disclosed
    rm = [Relationship("MM", "T")]
    em = _s(datetime(2025, 1, 6, 8), [_m("MM", "MM", 5.0), _m("T", "T", 0.0)], rm)
    lm = _s(datetime(2025, 2, 6, 8), [_m("MM", "MM", 0.0), _m("T", "T", 0.0)], rm)
    wm = _fcbi([em, lm], target="T").windows[0]
    assert wm.burn_gross == pytest.approx(0.0) and len(wm.milestone_margin_changes) >= 1
    # REV-15 quarantined recovery
    rr = [Relationship("A", "M"), Relationship("M", "T")]
    er = _s(datetime(2025, 1, 6, 8), [_a("A", "A", -5.0),
            _m("M", "M", 0.0, constraint=ConstraintType.MANDATORY_FINISH), _m("T", "T", 0.0)], rr)
    lr = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0),
            _m("M", "M", 0.0, constraint=ConstraintType.MANDATORY_FINISH), _m("T", "T", 0.0)], rr)
    wr = _fcbi([er, lr], target="T").windows[0]
    assert wr.recov_quarantine > 0


# ---- settled open questions (principal decisions Q1-Q7) ------------------
def test_fcbi_population_coverage_block():
    """Q3/Q6 settled: population coverage reported over the whole candidate
    population (not just movers), distinct from eligible-burn coverage."""
    r = [Relationship("D", "T"), Relationship("A", "T"), Relationship("G", "M"),
         Relationship("M", "T"), Relationship("U", "T")]
    def bld(dd, a_tf, u_tf):
        return _s(dd, [_a("D", "D", 0.0), _a("A", "A", a_tf), _a("G", "G", 2.0),
                       _m("M", "M", 0.0, constraint=ConstraintType.MANDATORY_FINISH),
                       _a("U", "U", u_tf), _m("T", "T", 0.0)], r)
    w = _fcbi([bld(datetime(2025, 1, 6, 8), 5.0, 3.0),
               bld(datetime(2025, 2, 6, 8), 0.0, None)], target="T").windows[0]
    assert w.candidate_pop == 4                          # D, A, G, U (tasks)
    assert w.tf_evaluability == pytest.approx(0.75)      # U unmeasurable at end
    assert w.population_eligibility == pytest.approx(0.5)  # G governed, U unmeasurable
    assert w.pop_exclusions                              # reasons recorded


def test_fcbi_adaptive_convergence():
    """Q6/REV-08 settled: enumeration converges (not depth_capped) when the
    omitted-weight bound falls below tolerance, even with many off-critical
    feeders; and the depth ceiling is disclosed rather than implied converged."""
    n = 60
    rels = [Relationship("D", "T")] + [Relationship(f"F{i}", "T") for i in range(n)]
    def bld(dd, d_tf):
        acts = ([_a("D", "D", d_tf)]
                + [_a(f"F{i}", f"F{i}", 50.0 + i) for i in range(n)]
                + [_m("T", "T", 0.0)])
        return _s(dd, acts, rels)
    res = _fcbi([bld(datetime(2025, 1, 6, 8), 0.0),
                 bld(datetime(2025, 2, 6, 8), -2.0)], target="T")
    assert not res.depth_capped                          # converged early
    assert res.windows[0].burn_gross == pytest.approx(2.0)


def test_fcbi_target_auto_resolved_is_provisional():
    """Q1/O7.1 settled: an auto-resolved target flags the run PROVISIONAL (m must
    be analyst-confirmed for work product)."""
    r = [Relationship("A", "C")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _m("C", "C", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("C", "C", 0.0)], r)
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    res = run_li_indices(sa).fcbi                        # no explicit target
    assert res.target_auto_resolved
    assert "PROVISIONAL" in res.interpretation


def test_fcbi_lambda_sensitivity_set():
    """Q2/Q4 settled: a λ∈{3,5,10} sensitivity set; B is λ-invariant, C/W move."""
    r = [Relationship("D", "T"), Relationship("A", "T")]
    def bld(dd, a_tf):
        return _s(dd, [_a("D", "D", 0.0), _a("A", "A", a_tf), _m("T", "T", 0.0)], r)
    sa = SeriesAnalysis(schedules=[bld(datetime(2025, 1, 6, 8), 5.0),
                                   bld(datetime(2025, 2, 6, 8), 0.0)],
                        changesets=[compare(bld(datetime(2025, 1, 6, 8), 5.0),
                                            bld(datetime(2025, 2, 6, 8), 0.0))])
    ls = fcbi_lambda_sensitivity(sa, target="T")
    assert [p.lam for p in ls.points] == [3.0, 5.0, 10.0]
    assert ls.cumulative_b is not None                  # single λ-invariant B
    cs = [p.cumulative_c for p in ls.points]
    assert cs[0] < cs[1] < cs[2]                         # C rises with λ (A at d=5)


def test_fcbi_headline_is_b_and_c_pair():
    """Q1 settled: the headline framing is the (B, C) pair with W derived."""
    r = [Relationship("D", "T"), Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("D", "D", 0.0), _a("A", "A", 5.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("D", "D", -3.0), _a("A", "A", 2.0), _m("T", "T", 0.0)], r)
    res = _fcbi([e, l], target="T")
    assert "(B, C) pair" in res.interpretation


def test_fcbi_retired_surfaces_absent():
    """The retired FCBI% (old Eq. 3) and its D=0 sentinel are gone (O2)."""
    w = _fcbi([_p2(datetime(2025, 1, 6, 8), 10.0),
               _p2(datetime(2025, 2, 6, 8), 4.0)]).windows[0]
    assert not hasattr(w, "fcbi_pct")
    assert not hasattr(w, "fcbi")               # replaced by burn_gross / burn_weighted


# ===================================================================== PCI
def test_pci_in_unit_interval(indices):
    pci = indices.pci
    assert pci.reason == ""
    assert len(pci.per_update) == 3
    # a Herfindahl over normalized weights sits in (0, 1] for every update
    for v in pci.per_update:
        assert v is not None and 0.0 < v <= 1.0


# ===================================================================== CDI
def test_cdi_shares_sum_to_one(indices):
    cdi = indices.cdi
    assert cdi.reason == ""
    assert cdi.leaderboard, "expected a non-empty dwell leaderboard"
    # each update allocates exactly one unit; shares are that unit's split
    total = sum(e.dwell_share for e in cdi.leaderboard)
    assert total == pytest.approx(1.0, abs=1e-6)
    assert cdi.top_decile_share is not None
    # leaderboard is ranked by dwell share
    shares = [e.dwell_share for e in cdi.leaderboard]
    assert shares == sorted(shares, reverse=True)


# ===================================================================== RDI
def test_rdi_nonnegative_one_row_per_update(indices, series):
    rdi = indices.rdi
    assert rdi.reason == ""
    assert rdi.rdi_days >= 0.0
    assert len(rdi.rows) == len(series.schedules)     # one row per update
    # cumulative column is a running total of the accruals
    running = 0.0
    for row in rdi.rows:
        running += row.accrual_days
        assert row.cumulative_days == pytest.approx(running)
        assert row.accrual_days >= 0.0


# ===================================================================== BWI
def test_bwi_first_update_is_baseline(indices):
    bwi = indices.bwi
    assert bwi.reason == ""
    # default target is the sole late-type-constrained finish milestone (A1200)
    assert bwi.target_code == "A1200"
    # BWI is normalized to the first update, so BWI_0 == 1.0 by construction;
    # the fixture's baseline near-critical density ahead of A1200 is non-zero,
    # so the first row is 1.0 (not None).
    assert bwi.rows[0].bwi == pytest.approx(1.0)


def test_bwi_projected_break_date():
    """Three updates, no logic (RF = own float; all near-critical at TF=0),
    target milestone T fixed at 2025-06-30.  Window 1 completes 20 activity-days
    of near-critical work (demonstrated pace ~1.0/day); update 2 then loads 500
    activity-days of remaining near-critical work ahead of T, whose required
    density (~6/day) outruns anything demonstrated -> projected break at U2."""
    def mk(uid, code, *, status=ActivityStatus.NOT_STARTED, od_h=0.0, rem_h=0.0,
           tf_h=0.0, ef=None, af=None,
           atype=ActivityType.TASK, constraint=ConstraintType.NONE):
        return Activity(uid=uid, code=code, atype=atype, status=status,
                        original_duration_hours=od_h, remaining_duration_hours=rem_h,
                        total_float_hours=tf_h, early_finish=ef, actual_finish=af,
                        constraint=constraint)

    TFIN = datetime(2025, 6, 30, 17)

    def sched(dd, acts):
        return Schedule(project_id="SYN", data_date=dd,
                        activities={a.uid: a for a in acts})

    T = lambda: mk("T", "T", atype=ActivityType.FINISH_MILESTONE, ef=TFIN,
                   constraint=ConstraintType.MANDATORY_FINISH)

    u0 = sched(datetime(2025, 1, 6, 8), [
        T(),
        mk("W1", "W1", od_h=160, rem_h=160, ef=datetime(2025, 3, 1, 17)),
    ])
    u1 = sched(datetime(2025, 2, 3, 8), [
        T(),
        mk("W1", "W1", status=ActivityStatus.COMPLETED, od_h=160, rem_h=0,
           af=datetime(2025, 1, 20, 17)),
        mk("W2", "W2", od_h=80, rem_h=80, ef=datetime(2025, 4, 1, 17)),
    ])
    u2 = sched(datetime(2025, 3, 3, 8), [
        T(),
        mk("W1", "W1", status=ActivityStatus.COMPLETED, od_h=160, rem_h=0,
           af=datetime(2025, 1, 20, 17)),
        mk("W2", "W2", status=ActivityStatus.COMPLETED, od_h=80, rem_h=0,
           af=datetime(2025, 2, 20, 17)),
        mk("W3", "W3", od_h=4000, rem_h=4000, ef=datetime(2025, 5, 1, 17)),
    ])
    sa = SeriesAnalysis(schedules=[u0, u1, u2])
    bwi = run_li_indices(sa, bwi_target="T").bwi
    assert bwi.reason == ""
    assert bwi.rows[0].bwi == pytest.approx(1.0)
    assert bwi.projected_break_label == u2.label()


# ==================================================== graceful degradation
def test_empty_series_never_raises():
    empty = Schedule(project_id="EMPTY")
    r = run_li_indices(SeriesAnalysis(schedules=[empty]))
    # single schedule -> the pair-based indices report a reason, none raise
    assert r.fcbi.reason
    assert r.rdi.reason
    # no float paths -> PCI/CDI carry reasons and empty payloads
    assert r.pci.reason or all(v is None for v in r.pci.per_update)
    assert r.cdi.reason or not r.cdi.leaderboard
    assert r.bwi.reason or r.bwi.rows is not None


def test_run_li_indices_empty_schedule_list_never_raises():
    r = run_li_indices(SeriesAnalysis(schedules=[]))
    assert r.fcbi.reason and r.pci.reason and r.cdi.reason
    assert r.rdi.reason and r.bwi.reason
