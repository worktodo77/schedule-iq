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
                                     RelType, Relationship, Schedule)
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


# ---- wave-3 review (GPT-5.6 Pro W3-01..10) regressions -------------------
def test_fcbi_w3_01_hidden_low_margin_branch_resolved():
    """W3-01 (disputed, guarded): a low-margin branch reachable only through a
    higher-margin parent (R->Q->X, with P->X at the merge) is RESOLVED, not
    omitted — float_paths enumerates it early, so the convergence bound holds."""
    acts = ([_m("T", "T", 0.0), _a("D", "D", 0.0), _a("X", "X", 50.0),
             _a("P", "P", 40.0), _a("Q", "Q", 41.0), _a("R", "R", 5.0)]
            + [_a(f"F{i}", f"F{i}", 60.0 + i) for i in range(24)])
    rels = ([Relationship("D", "T"), Relationship("X", "D"), Relationship("P", "X"),
             Relationship("Q", "X"), Relationship("R", "Q")]
            + [Relationship(f"F{i}", "D") for i in range(24)])
    from scheduleiq.analytics.li_indices import _target_distance
    dist, _dm, _tm, capped = _target_distance(
        _s(datetime(2025, 1, 6, 8), acts, rels), "T")
    assert dist.get("R") == pytest.approx(5.0)          # resolved, not omitted
    assert not capped


def test_fcbi_w3_02_b_lambda_invariant():
    """W3-02: the distance basis is λ-independent, so B and coverage are identical
    at every λ (the sensitivity set reports one invariant B)."""
    n = 40
    def bld(dd, u_tf):
        acts = ([_m("T", "T", 0.0), _a("D", "D", 0.0)]
                + [_a(f"F{i}", f"F{i}", 10.0 + i * 0.5) for i in range(n)]
                + [_a("U", "U", u_tf)])
        rels = ([Relationship("D", "T")]
                + [Relationship(f"F{i}", "T") for i in range(n)] + [Relationship("U", "T")])
        return _s(dd, acts, rels)
    sa = SeriesAnalysis(schedules=[bld(datetime(2025, 1, 6, 8), 30.0),
                                   bld(datetime(2025, 2, 6, 8), 25.0)],
                        changesets=[compare(bld(datetime(2025, 1, 6, 8), 30.0),
                                            bld(datetime(2025, 2, 6, 8), 25.0))])
    bs = {run_li_indices(sa, fcbi_target="T", lam=lam).fcbi.cumulative_burn[-1]
          for lam in (3.0, 5.0, 10.0)}
    assert len(bs) == 1                                 # B invariant across λ
    ls = fcbi_lambda_sensitivity(sa, target="T")
    assert ls.cumulative_b is not None and ls.coverage is not None


def test_fcbi_w3_03_cumulative_c_identity():
    """W3-03: cumulative C = W_cum / B_cum, so W_cum = B_cum · C_cum is exact
    (the headline no longer prints a false equality)."""
    def w(dd, af):
        return _s(dd, [_a("DR", "DR", 0.0, od=30), _a("A", "A", af, od=30), _m("T", "T", 0.0)],
                  [Relationship("DR", "T"), Relationship("A", "T")])
    res = _fcbi([w(datetime(2025, 1, 6, 8), 80.0), w(datetime(2025, 1, 20, 8), 40.0),
                 w(datetime(2025, 2, 6, 8), 0.0)], target="T")
    cb, cw, cc = (res.cumulative_burn[-1], res.cumulative_weighted[-1],
                  res.cumulative_proximity[-1])
    assert cw == pytest.approx(cb * cc)
    assert "cumulative C" in res.interpretation


def test_fcbi_w3_04_explicit_target_validated():
    """W3-04: an explicit target is validated (terminal finish milestone); a task
    or intermediate is NOT EVALUATED, not silently accepted."""
    r = [Relationship("A", "Q"), Relationship("Q", "C")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _a("Q", "Q", 0.0), _m("C", "C", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _a("Q", "Q", 0.0), _m("C", "C", 0.0)], r)
    assert "NOT EVALUATED" in _fcbi([e, l], target="Q").reason      # task
    assert _fcbi([e, l], target="C").reason == ""                   # valid terminal


def test_fcbi_w3_06_and_09_depth_cap(monkeypatch):
    """W3-06: a cap at the LATER endpoint propagates to depth_capped.  W3-09: a
    network with exactly MAX paths is NOT falsely capped (one-path lookahead)."""
    import scheduleiq.analytics.li_indices as li
    monkeypatch.setattr(li, "FCBI_PATHS_MAX", 5)
    # W3-06: later endpoint has many equal feeders -> caps
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], [Relationship("A", "T")])
    lacts = [_a("A", "A", -2.0)] + [_a(f"G{i}", f"G{i}", 3.0 + i * 0.1) for i in range(8)] + [_m("T", "T", 0.0)]
    l = _s(datetime(2025, 2, 6, 8), lacts, [Relationship("A", "T")] + [Relationship(f"G{i}", "T") for i in range(8)])
    assert _fcbi([e, l], target="T").depth_capped
    # W3-09: exactly 5 paths -> not capped
    acts = [_m("T", "T", 0.0), _a("D", "D", 0.0)] + [_a(f"F{i}", f"F{i}", 5.0 + i) for i in range(4)]
    rels = [Relationship("D", "T")] + [Relationship(f"F{i}", "T") for i in range(4)]
    _dist, _dm, _tm, capped = li._target_distance(_s(datetime(2025, 1, 6, 8), acts, rels), "T")
    assert not capped


def test_fcbi_w3_07_sensitivity_status():
    """W3-07: the sensitivity set fails as a whole on an invalid target and fails
    only the offending point on an invalid λ (status/reason retained)."""
    r = [Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], r)
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    assert fcbi_lambda_sensitivity(sa, target="NOPE").reason        # whole set fails
    ls = fcbi_lambda_sensitivity(sa, target="T", lams=(3.0, 0.0, 5.0))
    bad = [p for p in ls.points if p.lam == 0.0][0]
    assert bad.status == "failed" and bad.reason


def test_fcbi_w3_08_endpoint_type_change_excluded():
    """W3-08: a task that becomes LOE/milestone at the later endpoint is excluded
    from B and disclosed as a type-change exclusion."""
    r = [Relationship("A", "T"), Relationship("D", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 0.0), _a("D", "D", 0.0), _m("T", "T", 0.0)], r)
    la = _a("A", "A", -5.0)
    la.atype = ActivityType.LOE
    l = _s(datetime(2025, 2, 6, 8), [la, _a("D", "D", -1.0), _m("T", "T", 0.0)], r)
    w = _fcbi([e, l], target="T").windows[0]
    assert "A" not in {b.code for b in w.top_burners}
    assert "activity type changed at endpoint" in w.pop_exclusions


def test_fcbi_w3_10_milestone_margin_signed():
    """W3-10: a non-target milestone's margin change keeps its sign (recovery vs
    erosion distinguishable)."""
    r = [Relationship("MM", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_m("MM", "MM", 5.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_m("MM", "MM", 10.0), _m("T", "T", 0.0)], r)   # +5 recovery
    mm = _fcbi([e, l], target="T").windows[0].milestone_margin_changes[0]
    assert mm.signed_delta_days == pytest.approx(5.0)


# ---- wave-4 review (W4-01..07): EXACT float_paths equivalence ------------
import random as _random                                             # noqa: E402
from scheduleiq.analytics.paths import (float_paths as _float_paths,  # noqa: E402
                                        iter_float_paths as _iter_fp)
from scheduleiq.analytics.li_indices import (                        # noqa: E402
    _target_distance as _tdist, kernel_weight as _kw,
    FCBI_CONV_LAMBDA as _CL, FCBI_CONV_TOL as _CT, REFERENCE_HPD as _HPD)


def _ah(uid, tf_hours, atype=ActivityType.TASK):
    """Activity keyed by RAW total-float HOURS (the wave-4 counterexamples give
    floats in hours, not whole days)."""
    return _a(uid, uid, None, tf_hours=tf_hours, atype=atype, od=10, rem=10)


def _oracle_distance(schedule, target, big_n=256):
    """Per-activity distance built DIRECTLY from the reference float_paths (NEVER
    the iterator) — the non-circular oracle for the O1 definition."""
    paths = _float_paths(schedule, target_uid=target, n=big_n, band_days=None)
    if not paths or paths[0].rel_float_hours is None:
        return {}, paths
    dm = paths[0].rel_float_hours / _HPD
    dist = {}
    for fp in paths:
        if fp.rel_float_hours is None:
            continue
        d = max(0.0, fp.rel_float_hours / _HPD - dm)
        for a in fp.activities:
            if not a.is_loe_or_summary:
                dist[a.code] = min(dist.get(a.code, 1e18), d)
    return dist, paths


def _random_dag(rng, n_acts):
    """A seeded random single-sink DAG: tasks A0..A{n-1} in topological order with
    FS edges only to a later task or the terminal milestone T (so every task
    reaches T), random working-day floats spanning negative to large.  Relationship
    creation order is deterministic (sorted targets) so the fixture is stable across
    PYTHONHASHSEED (Item 4)."""
    acts = [_m("T", "T", 0.0)]
    codes = [f"A{i}" for i in range(n_acts)]
    for c in codes:
        acts.append(_a(c, c, round(rng.uniform(-15.0, 110.0), 2)))
    rels = []
    for i, c in enumerate(codes):
        later = codes[i + 1:] + ["T"]
        tgts = {rng.choice(later)}                       # >=1 successor -> reaches T
        for _ in range(rng.randint(0, 2)):
            tgts.add(rng.choice(later))
        rels += [Relationship(c, t) for t in sorted(tgts)]   # stable order (Item 4)
    return _s(datetime(2025, 1, 6, 8), acts, rels)


def _random_mixed_dag(rng, n_acts):
    """A seeded random single-sink DAG exercising the FULL topology surface (Item 4):
    FS/SS/FF/SF relationships, positive and negative lags, negative / None / large
    floats, LOE nodes (excluded from margins), parallel non-terminal finish
    milestones, deep feeder chains, and shared merges — every task still reaches the
    terminal milestone T.  Deterministic given ``rng`` (sorted edge order)."""
    acts = [_m("T", "T", 0.0)]
    codes = [f"A{i}" for i in range(n_acts)]
    reltypes = [RelType.FS, RelType.SS, RelType.FF, RelType.SF]
    for i, c in enumerate(codes):
        r = rng.random()
        if r < 0.12:                                     # LOE node (excluded from margin)
            acts.append(_a(c, c, round(rng.uniform(-10.0, 90.0), 2),
                           atype=ActivityType.LOE))
        elif r < 0.24:                                   # parallel NON-terminal finish mile
            acts.append(_m(c, c, round(rng.uniform(-5.0, 60.0), 2)))
        elif r < 0.32:                                   # unmeasurable float
            acts.append(_a(c, c, None, tf_hours=None))
        else:
            acts.append(_a(c, c, round(rng.uniform(-15.0, 110.0), 2)))
    rels = []
    for i, c in enumerate(codes):
        later = codes[i + 1:] + ["T"]
        tgts = {rng.choice(later)}
        for _ in range(rng.randint(0, 3)):               # richer fan-out / shared merges
            tgts.add(rng.choice(later))
        for t in sorted(tgts):
            rt = reltypes[rng.randrange(len(reltypes))]
            lag = rng.choice([0.0, 8.0, -8.0, 16.0, -16.0])
            rels.append(Relationship(c, t, rt, lag))
    return _s(datetime(2025, 1, 6, 8), acts, rels)


def _path_signature(paths):
    return [tuple(p.codes) for p in paths]


def _assert_iter_equals_float_paths(schedule, target, big_n=128):
    """iter_float_paths yields EXACTLY float_paths's paths, in the same order — same
    path COUNT, node sequence, rel_float_days AND rel_float_hours — and never emits a
    duplicate path signature (the core wave-4 fix, W4-01; Item-4 comparison set)."""
    ref = _float_paths(schedule, target_uid=target, n=big_n, band_days=None)
    got = []
    for _rel, fp, _used in _iter_fp(schedule, target_uid=target):
        got.append(fp)
        if len(got) >= big_n:
            break
    assert len(got) == len(ref)                                   # path count
    assert [p.codes for p in got] == [p.codes for p in ref]       # code sequence
    assert [p.rel_float_days for p in got] == [p.rel_float_days for p in ref]
    assert [p.rel_float_hours for p in got] == [p.rel_float_hours for p in ref]
    sigs = _path_signature(got)
    assert len(sigs) == len(set(sigs))                            # no duplicate paths


def test_w4_01_counterexample_regression():
    """W4-01 (BLOCKER, permanent regression): the all-8h FS-only network on which
    the withdrawn best-first iterator spliced A18 onto the wrong tail (iter path 3
    = A04,A13,A14,A18,A20,T vs reference A04,A13,A14,T), giving A18 a spurious
    d=0.  The reference-equivalent iterator restores d(A18)=29.625."""
    acts = [_ah("A04", -72.0), _ah("A05", 254.0), _ah("A11", 183.0), _ah("A13", 640.0),
            _ah("A14", 320.0), _ah("A18", 237.0), _ah("A20", 8.0),
            _ah("T", 0.0, atype=ActivityType.FINISH_MILESTONE)]
    rels = [Relationship("A14", "T"), Relationship("A13", "A14"),
            Relationship("A18", "A20"), Relationship("A14", "A18"),
            Relationship("A04", "A13"), Relationship("A05", "A18"),
            Relationship("A20", "T"), Relationship("A11", "A20"),
            Relationship("A05", "A14")]
    s = _s(datetime(2025, 1, 6, 8), acts, rels)
    _assert_iter_equals_float_paths(s, "T")
    dist, _dm, _tm, capped = _tdist(s, "T")
    oracle, _p = _oracle_distance(s, "T")
    assert dist.get("A18") == pytest.approx(29.625)      # was a spurious 0.0
    for code, d in dist.items():
        assert oracle[code] == pytest.approx(d, abs=1e-9)


def test_w4_02_counterexample_regression():
    """W4-02 (BLOCKER, permanent regression): mixed relationship types + lags on
    which the withdrawn iterator split float_paths's A01,A06,A08,A16,T into two
    wrong paths, OMITTED A06/A08 entirely, and the frontier (read off the corrupted
    used set) falsely declared convergence while dropping material weight
    (0.354).  A06/A08 must now resolve at d=15 days (weight 0.354)."""
    acts = [_ah("A01", -40.0), _ah("A02", 344.0), _ah("A03", 598.0), _ah("A05", 619.0),
            _ah("A06", 600.0), _ah("A08", 495.0), _ah("A16", -160.0), _ah("A17", 665.0),
            _ah("A18", -80.0), _ah("A19", 631.0),
            _ah("T", 0.0, atype=ActivityType.FINISH_MILESTONE)]
    rels = [Relationship("A01", "A06", RelType.SF, -8.0),
            Relationship("A16", "T", RelType.FF),
            Relationship("A18", "T", RelType.SF),
            Relationship("A03", "A17", RelType.FS, -8.0),
            Relationship("A19", "T", RelType.FS, -8.0),
            Relationship("A06", "A08", RelType.SF),
            Relationship("A08", "A16", RelType.SF, -8.0),
            Relationship("A05", "A19", RelType.SS),
            Relationship("A01", "A05", RelType.FS, -8.0),
            Relationship("A17", "A18", RelType.SS),
            Relationship("A03", "A08", RelType.FF, -8.0),
            Relationship("A02", "A16", RelType.SF)]
    s = _s(datetime(2025, 1, 6, 8), acts, rels)
    _assert_iter_equals_float_paths(s, "T")
    dist, _dm, _tm, capped = _tdist(s, "T")
    oracle, _p = _oracle_distance(s, "T")
    assert dist.get("A06") == pytest.approx(15.0)        # was OMITTED (None)
    assert dist.get("A08") == pytest.approx(15.0)        # was OMITTED (None)
    assert _kw(15.0, _CL) == pytest.approx(0.353553, abs=1e-6)   # material weight
    for code, d in dist.items():
        assert oracle[code] == pytest.approx(d, abs=1e-9)


def test_w4_03_iter_exactly_matches_float_paths_corpus():
    """W4-03: on a 500-DAG seeded corpus the streaming iterator is byte-for-byte
    the reference float_paths enumeration (same paths, same order, same margins),
    and _target_distance agrees with the float_paths-built oracle on every RESOLVED
    activity — the equivalence check no longer reads the reference from the iterator
    itself (the wave-4 circularity, W4-03)."""
    rng = _random.Random(20260711)
    for _ in range(500):
        s = _random_dag(rng, rng.randint(4, 10))
        _assert_iter_equals_float_paths(s, "T")
        oracle, _paths = _oracle_distance(s, "T")
        dist, _dm, _tm, _capped = _tdist(s, "T")
        for code, d in dist.items():                     # resolved == oracle exactly
            assert oracle.get(code) == pytest.approx(d, abs=1e-9), (code, d)


def test_w4_03_frontier_no_material_omission_corpus():
    """W4-03/W4-02: across the seeded corpus, whenever a run is NOT depth-capped,
    every activity the frontier OMITTED is provably immaterial (reference weight at
    the convergence λ is below tolerance) — zero material-weight omissions, the
    property the wave-4 W4-02 counterexample violated."""
    rng = _random.Random(770077)
    material_omissions = 0
    for _ in range(500):
        s = _random_dag(rng, rng.randint(4, 11))
        oracle, _paths = _oracle_distance(s, "T")
        dist, _dm, _tm, capped = _tdist(s, "T")
        if capped:
            continue
        for code, d_ref in oracle.items():
            if code not in dist and _kw(d_ref, _CL) >= _CT:
                material_omissions += 1
    assert material_omissions == 0


def test_w4_03_determinism():
    """W4-03: the enumerator and the distance map are deterministic — identical
    across repeated calls on the same network (no set-iteration nondeterminism in
    the yielded order or the resolved distances)."""
    rng = _random.Random(4242)
    for _ in range(40):
        s = _random_dag(rng, rng.randint(5, 10))
        seq1 = [fp.codes for _r, fp, _u in _iter_fp(s, target_uid="T")]
        seq2 = [fp.codes for _r, fp, _u in _iter_fp(s, target_uid="T")]
        assert seq1 == seq2
        assert _tdist(s, "T")[0] == _tdist(s, "T")[0]


# ============================================ v0.5.6 hardening (wave-5 items)
# ---- Item 4: mixed-topology corpus + hash-seed reproducibility -----------
def test_v056_mixed_topology_corpus():
    """Item 4: a 250-DAG mixed-topology corpus (FS/SS/FF/SF relationships, +/- lags,
    LOE nodes, parallel non-terminal finish milestones, None/negative float, shared
    merges, deep chains) — the iterator stays byte-for-byte float_paths (count,
    sequence, rel_float_days/hours, no duplicate signatures) and the frontier makes
    ZERO material omissions on uncapped runs."""
    rng = _random.Random(31337)
    material_omissions = 0
    for _ in range(250):
        s = _random_mixed_dag(rng, rng.randint(4, 11))
        _assert_iter_equals_float_paths(s, "T")
        oracle, _p = _oracle_distance(s, "T")
        dist, _dm, _tm, capped = _tdist(s, "T")
        for code, d in dist.items():
            assert oracle.get(code) == pytest.approx(d, abs=1e-9), (code, d)
        if not capped:
            for code, d_ref in oracle.items():
                if code not in dist and _kw(d_ref, _CL) >= _CT:
                    material_omissions += 1
    assert material_omissions == 0


def test_v056_corpus_stable_across_hashseed():
    """Item 4: the randomized corpus is reproducible across PYTHONHASHSEED.  The
    fixture builds relationships in sorted order, so set-iteration hash randomization
    cannot change the network, the enumerated path sequence, or the distance map.
    Proven by building the SAME seeded mixed corpus in subprocesses under different
    PYTHONHASHSEED values and comparing float_paths output + distance maps."""
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    prog = (
        "import sys; sys.path.insert(0, %r)\n" % tests_dir +
        "import random, test_li_indices as t\n"
        "rng = random.Random(2026)\n"
        "lines = []\n"
        "for _ in range(30):\n"
        "    s = t._random_mixed_dag(rng, rng.randint(5, 10))\n"
        "    paths = t._float_paths(s, target_uid='T', n=128, band_days=None)\n"
        "    dist = t._tdist(s, 'T')[0]\n"
        "    lines.append('|'.join(','.join(p.codes) for p in paths))\n"
        "    lines.append(repr(sorted((k, round(v, 6)) for k, v in dist.items())))\n"
        "print('\\n'.join(lines))\n")

    def run(seed):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0, r.stderr
        return r.stdout

    a, b, c = run(0), run(1), run(524287)
    assert a.strip() and a == b == c


# ---- Item 1: SeriesAnalysis integrity validator --------------------------
def _two_update_series(pid="P"):
    r = [Relationship("D", "T"), Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("D", "D", 0.0), _a("A", "A", 3.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("D", "D", 0.0), _a("A", "A", -2.0), _m("T", "T", 0.0)], r)
    e.project_id = l.project_id = pid
    return e, l


def test_v056_series_integrity_canonical_accepted():
    """Item 1: a canonical SeriesAnalysis (changesets built from the same schedule
    objects) passes the integrity guard unchanged."""
    from scheduleiq.analytics.li_indices import _validate_fcbi_series_integrity
    e, l = _two_update_series()
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    assert _validate_fcbi_series_integrity(sa, "T") == ""
    assert run_li_indices(sa, fcbi_target="T").fcbi.reason == ""


def test_v056_series_integrity_clones_accepted_and_identical():
    """Item 1: semantically identical DEEP-COPIED changeset endpoints (the wave-5
    object-identity mismatch) are accepted, and the numbers are identical to the
    canonical run — object identity is NOT required, only structural coherence."""
    import copy
    e, l = _two_update_series()
    canon = run_li_indices(SeriesAnalysis(schedules=[e, l],
                                          changesets=[compare(e, l)]),
                           fcbi_target="T").fcbi
    e2, l2 = copy.deepcopy(e), copy.deepcopy(l)
    cloned = run_li_indices(SeriesAnalysis(schedules=[e, l],
                                           changesets=[compare(e2, l2)]),
                            fcbi_target="T").fcbi
    assert cloned.reason == ""
    assert cloned.cumulative_burn == canon.cumulative_burn
    assert cloned.cumulative_weighted == canon.cumulative_weighted
    assert [b.contribution for b in cloned.top_burners] == \
           [b.contribution for b in canon.top_burners]


def test_v056_series_integrity_mismatched_project_rejected():
    """Item 1: a changeset endpoint whose project_id differs from the corresponding
    schedule is rejected as an internal-series-integrity failure (NOT EVALUATED)."""
    e, l = _two_update_series()
    e_wrong, _l2 = _two_update_series(pid="OTHER")            # different project id
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e_wrong, l)])
    res = _fcbi_via_sa(sa, "T")
    assert "internal series integrity" in res.reason and "NOT EVALUATED" in res.reason


def test_v056_series_integrity_bad_date_order_rejected():
    """Item 1: a window whose endpoints run backward in data date is rejected."""
    e, l = _two_update_series()
    # schedules in order [l(Feb), e(Jan)] with a Feb->Jan window: correspondence
    # holds but the window moves backward in time -> rejected
    sa = SeriesAnalysis(schedules=[l, e], changesets=[compare(l, e)])
    res = _fcbi_via_sa(sa, "T")
    assert "internal series integrity" in res.reason and "NOT EVALUATED" in res.reason


def test_v056_series_integrity_window_count_rejected():
    """Item 1: a missing (or duplicated) changeset window is rejected by the count
    check — the windows must correspond one-to-one to consecutive schedule pairs."""
    e, l = _two_update_series()
    m = _s(datetime(2025, 3, 6, 8),
           [_a("D", "D", 0.0), _a("A", "A", -5.0), _m("T", "T", 0.0)],
           [Relationship("D", "T"), Relationship("A", "T")])
    # 3 schedules but only 1 window (should be 2) -> missing window
    sa = SeriesAnalysis(schedules=[e, l, m], changesets=[compare(e, l)])
    res = _fcbi_via_sa(sa, "T")
    assert "internal series integrity" in res.reason and "NOT EVALUATED" in res.reason
    # duplicated window (2 windows for 2 schedules) -> rejected
    sa2 = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l), compare(e, l)])
    assert "internal series integrity" in _fcbi_via_sa(sa2, "T").reason


def _fcbi_via_sa(sa, target):
    return run_li_indices(sa, fcbi_target=target).fcbi


# ---- Item 2: target UID continuity warning -------------------------------
def _uid_series(uid_e, uid_l):
    """Two updates whose target CODE 'T' is a terminal finish milestone in both, but
    whose internal UID is uid_e then uid_l (relationships wire to the milestone's
    UID)."""
    e = _s(datetime(2025, 1, 6, 8),
           [_a("A", "A", 5.0), _m(uid_e, "T", 0.0)], [Relationship("A", uid_e)])
    l = _s(datetime(2025, 2, 6, 8),
           [_a("A", "A", 0.0), _m(uid_l, "T", 0.0)], [Relationship("A", uid_l)])
    return SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])


def test_v056_target_uid_stable_no_warning():
    """Item 2: same target code AND same UID across updates -> no continuity flag."""
    fcbi = _fcbi_via_sa(_uid_series("T", "T"), "T")
    assert fcbi.reason == ""
    assert fcbi.target_uid_changed is False
    assert fcbi.target_continuity_note == ""
    assert "internal activity identifier changed" not in fcbi.interpretation


def test_v056_target_uid_changed_is_provisional():
    """Item 2: same stable+terminal target code but a CHANGED internal UID does NOT
    reject the run — it is evaluated, flagged provisional, and carries a
    continuity warning requiring analyst confirmation."""
    fcbi = _fcbi_via_sa(_uid_series("T1", "T2"), "T")
    assert fcbi.reason == ""                              # still evaluated
    assert fcbi.target_uid_changed is True
    assert fcbi.target_uid_history == ["T1", "T2"]
    assert fcbi.target_continuity_note
    assert "PROVISIONAL" in fcbi.interpretation
    assert "internal activity identifier changed" in fcbi.interpretation


def test_v056_target_uid_change_not_treated_as_target_change():
    """Item 2: a UID change is NOT proof the target changed — the numbers match the
    same-UID run exactly (only the provisional continuity flag differs)."""
    same = _fcbi_via_sa(_uid_series("T", "T"), "T")
    moved = _fcbi_via_sa(_uid_series("T1", "T2"), "T")
    assert moved.cumulative_burn == same.cumulative_burn
    assert moved.cumulative_weighted == same.cumulative_weighted


def test_v056_target_code_change_still_governed():
    """Item 2: existing target-stability governance still applies — a target that
    becomes intermediate or disappears in an update is NOT EVALUATED (the UID
    disclosure never softens the code-level W4-06 rules)."""
    # target 'T' becomes non-terminal in update 2 (reaches another finish milestone)
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _m("T", "T", 0.0)],
           [Relationship("A", "T")])
    l = _s(datetime(2025, 2, 6, 8),
           [_a("A", "A", 0.0), _m("T", "T", 0.0), _m("C", "C", 0.0)],
           [Relationship("A", "T"), Relationship("T", "C")])   # T -> C: T not terminal
    assert "NOT EVALUATED" in _fcbi([e, l], target="T").reason
    # target disappears in update 2
    l2 = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0)], [])
    assert "NOT EVALUATED" in _fcbi([e, l2], target="T").reason


# ---- Item 3: lambda input type hardening ---------------------------------
def test_v056_lambda_input_type_hardening():
    """Item 3: run_li_indices never raises on ANY lambda input type (None, str,
    bool, complex, containers, non-finite, out-of-range); 3/5/10 are valid, every
    other listed value is invalid-with-a-reason."""
    from scheduleiq.analytics.li_indices import _invalid_lambda_reason
    r = [Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], r)
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    valid = [3, 5, 10, 3.0, 5.0, 10.0]
    invalid = [None, "5", True, False, 2 + 3j, [5], {"l": 5}, float("nan"),
               float("inf"), float("-inf"), 0, 0.0, -5.0, 10.000001, 20.0]
    for lam in valid:
        assert _invalid_lambda_reason(lam) == ""
        assert run_li_indices(sa, fcbi_target="T", lam=lam).fcbi.reason == ""   # no raise
    for lam in invalid:
        assert _invalid_lambda_reason(lam) != ""
        res = run_li_indices(sa, fcbi_target="T", lam=lam).fcbi                 # no raise
        assert "invalid lambda" in res.reason


# ---- Item 5: optional enumeration instrumentation ------------------------
def test_v056_target_distance_stats_instrumentation():
    """Item 5: the optional stats hook records audit counters without changing the
    result (paths_enumerated / convergence_stopped / depth_capped / stop_reason)."""
    # far-off-critical fan: frontier stops after the driver
    acts = [_m("T", "T", 0.0), _a("D", "D", 0.0)] + \
           [_a(f"F{i}", f"F{i}", 80.0 + i) for i in range(30)]
    rels = [Relationship("D", "T")] + [Relationship(f"F{i}", "T") for i in range(30)]
    s = _s(datetime(2025, 1, 6, 8), acts, rels)
    stats = {}
    dist_a, _dm, _tm, cap_a = _tdist(s, "T", stats)
    dist_b, _dm2, _tm2, cap_b = _tdist(s, "T")           # without stats: same result
    assert dist_a == dist_b and cap_a == cap_b
    assert stats["convergence_stopped"] is True and stats["depth_capped"] is False
    assert stats["stop_reason"] == "frontier" and stats["paths_enumerated"] >= 1


def test_w4_04_sensitivity_reuses_one_basis(monkeypatch):
    """W4-04: fcbi_lambda_sensitivity enumerates the λ-independent distance basis
    ONCE per schedule and reuses it across every λ — a 2-schedule set does 2
    enumerations, not 2·(len(lams)+1).  Counts _target_distance invocations."""
    import scheduleiq.analytics.li_indices as li
    calls = {"n": 0}
    orig = li._target_distance
    monkeypatch.setattr(li, "_target_distance",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or orig(*a, **k)))
    r = [Relationship("D", "T"), Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("D", "D", 0.0), _a("A", "A", 3.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("D", "D", 0.0), _a("A", "A", -2.0), _m("T", "T", 0.0)], r)
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    calls["n"] = 0
    ls = fcbi_lambda_sensitivity(sa, target="T", lams=(3.0, 5.0, 10.0))
    assert calls["n"] == 2                               # one per schedule, reused across λ
    assert [p.status for p in ls.points] == ["ok", "ok", "ok"]


def test_w4_05_lambda_range_enforced():
    """W4-05: the FCBI weighting λ must be finite and in (0, FCBI_CONV_LAMBDA].
    λ ≤ 10 is evaluated; λ > 10 (or non-finite/≤0) is NOT EVALUATED / a failed
    sensitivity point, because the convergence basis is proven only for λ ≤ the
    reference λ."""
    r = [Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 5.0), _m("T", "T", 0.0)], r)
    l = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], r)
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])

    def evaluated(lam):
        return run_li_indices(sa, fcbi_target="T", lam=lam).fcbi.reason == ""
    # <= reference λ (10): evaluated
    assert evaluated(3.0) and evaluated(5.0) and evaluated(10.0)
    # > reference λ: NOT EVALUATED (basis proven only for λ <= reference)
    assert not evaluated(10.000001) and not evaluated(20.0)
    # non-positive / non-finite: invalid (never raises — REV-12)
    assert not evaluated(-1.0) and not evaluated(0.0)
    assert not evaluated(float("nan")) and not evaluated(float("inf"))
    # sensitivity: only the out-of-range points fail
    ls = fcbi_lambda_sensitivity(sa, target="T", lams=(3.0, 10.0, 10.000001, 20.0))
    st = {p.lam: p.status for p in ls.points}
    assert st[3.0] == "ok" and st[10.0] == "ok"
    assert st[10.000001] == "failed" and st[20.0] == "failed"


def test_w4_06_target_terminal_in_every_update():
    """W4-06: an explicit target must be a terminal finish milestone in EVERY
    update (all, not any); a target present/terminal in only one update is a
    target-basis discontinuity — NOT EVALUATED."""
    from scheduleiq.analytics.li_indices import _resolve_fcbi_target
    r = [Relationship("A", "T")]
    with_t = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 3.0), _m("T", "T", 0.0)], r)
    # T is a terminal finish milestone in BOTH updates -> resolves
    both = [with_t, _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], r)]
    assert _resolve_fcbi_target(both, "T") == ("T", False)
    # T present in only ONE update -> all() fails -> NOT EVALUATED
    no_t = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0)], [])
    assert _resolve_fcbi_target([with_t, no_t], "T") == (None, False)
    assert "NOT EVALUATED" in _fcbi([with_t, no_t], target="T").reason


def test_w4_06_auto_resolution_intersects_series():
    """W4-06: auto-resolution takes the INTERSECTION of terminal finish-milestone
    codes across updates; a milestone terminal in only some updates is excluded,
    and a series with no common terminal milestone is NOT EVALUATED."""
    from scheduleiq.analytics.li_indices import _resolve_fcbi_target
    rA = [Relationship("A", "M1")]
    rB = [Relationship("A", "M2")]
    # update 1 terminal = {M1}, update 2 terminal = {M2}: empty intersection
    s1 = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 3.0), _m("M1", "M1", 0.0)], rA)
    s2 = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("M2", "M2", 0.0)], rB)
    assert _resolve_fcbi_target([s1, s2], None) == (None, True)   # discontinuity
    # both updates share terminal T -> auto-resolves T (provisional)
    rT = [Relationship("A", "T")]
    t1 = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 3.0), _m("T", "T", 0.0)], rT)
    t2 = _s(datetime(2025, 2, 6, 8), [_a("A", "A", 0.0), _m("T", "T", 0.0)], rT)
    assert _resolve_fcbi_target([t1, t2], None) == ("T", True)


def test_w4_07_exact_cap_boundary(monkeypatch):
    """W4-07: depth_capped fires EXACTLY when a (MAX+1)-th path exists — MAX-1 and
    MAX paths are not capped, MAX+1 and MAX+2 are (one-path generator lookahead,
    cap before the exhaustion shortcut)."""
    import scheduleiq.analytics.li_indices as li
    monkeypatch.setattr(li, "FCBI_PATHS_MAX", 4)

    def fan(k):
        # D (driver) + k near-critical feeders => exactly (k+1) float paths to T,
        # none immaterial (so the frontier never short-circuits the cap test)
        acts = [_m("T", "T", 0.0), _a("D", "D", 0.0)] + \
               [_a(f"F{i}", f"F{i}", 0.5 + i * 0.01) for i in range(k)]
        rels = [Relationship("D", "T")] + [Relationship(f"F{i}", "T") for i in range(k)]
        return _s(datetime(2025, 1, 6, 8), acts, rels)

    # total paths = k+1; MAX=4
    assert not li._target_distance(fan(2), "T")[3]       # 3 paths  (MAX-1) -> not capped
    assert not li._target_distance(fan(3), "T")[3]       # 4 paths  (MAX)   -> not capped
    assert li._target_distance(fan(4), "T")[3]           # 5 paths  (MAX+1) -> capped
    assert li._target_distance(fan(5), "T")[3]           # 6 paths  (MAX+2) -> capped


def test_w4_reachability_edge_cases():
    """Reachability edge cases for the frontier: a target with no predecessors
    yields an empty basis (no paths); an activity that cannot reach m is excluded
    from the frontier's reachable set (never bounds enumeration or gets resolved),
    while the reachable burners still resolve; a self-referential/cyclic predecessor
    graph terminates (the reachability walk is a visited-guarded BFS)."""
    # (1) target with no predecessors -> no float path -> empty, unresolved basis
    lone = _s(datetime(2025, 1, 6, 8), [_a("A", "A", 3.0), _m("T", "T", 0.0)],
              [Relationship("A", "B")])            # nothing feeds T
    assert _tdist(lone, "T") == ({}, None, None, False)
    # (2) an activity with no directed path to m is not in `reachable`: it neither
    #     bounds the frontier nor is resolved, but the reachable driver still is
    r = [Relationship("D", "T"), Relationship("N", "T"), Relationship("ISLE", "X")]
    s = _s(datetime(2025, 1, 6, 8),
           [_a("D", "D", 0.0), _a("N", "N", 4.0), _a("ISLE", "ISLE", -50.0),
            _a("X", "X", 9.0), _m("T", "T", 0.0)], r)
    dist, dm, _tm, capped = _tdist(s, "T")
    assert dist.get("D") == pytest.approx(0.0) and dist.get("N") == pytest.approx(4.0)
    assert "ISLE" not in dist                    # cannot reach m -> never resolved
    # ISLE's large negative float must NOT have dragged the frontier (it is unreachable)
    oracle, _p = _oracle_distance(s, "T")
    assert "ISLE" not in oracle
    # (3) a cycle among predecessors of m terminates (visited-guarded reachability)
    rc = [Relationship("P", "Q"), Relationship("Q", "P"), Relationship("Q", "T")]
    cyc = _s(datetime(2025, 1, 6, 8),
             [_a("P", "P", 1.0), _a("Q", "Q", 0.0), _m("T", "T", 0.0)], rc)
    d2, _dm2, _tm2, _c2 = _tdist(cyc, "T")       # must return, not hang
    assert d2.get("Q") == pytest.approx(0.0)


def test_fcbi_proven_frontier_bound():
    """v0.5.4: the sound frontier (min unused reachable float) stops enumeration
    once every omitted path is immaterial — a far-off-critical fan resolves only
    the driver (frontier weight < tol), and every omitted activity's weight is
    provably below tolerance."""
    from scheduleiq.analytics.li_indices import (_target_distance, kernel_weight,
                                                 FCBI_CONV_LAMBDA, FCBI_CONV_TOL,
                                                 REFERENCE_HPD)
    acts = [_m("T", "T", 0.0), _a("D", "D", 0.0)] + \
           [_a(f"F{i}", f"F{i}", 80.0 + i) for i in range(200)]     # far off critical
    rels = [Relationship("D", "T")] + [Relationship(f"F{i}", "T") for i in range(200)]
    s = _s(datetime(2025, 1, 6, 8), acts, rels)
    dist, dmarg, _tm, capped = _target_distance(s, "T")
    assert not capped and len(dist) < 10                 # frontier stopped early
    omitted = [f"F{i}" for i in range(200) if f"F{i}" not in dist]
    assert omitted
    worst = min(s.activities[c].total_float_hours for c in omitted)  # least-float omitted
    wd = max(0.0, worst / REFERENCE_HPD - dmarg)
    assert kernel_weight(wd, FCBI_CONV_LAMBDA) < FCBI_CONV_TOL       # bound HOLDS


def test_fcbi_wide_fan_completes_and_caps(monkeypatch):
    """v0.5.4: a genuinely wide near-critical fan completes (no O(n^2) restart
    hang) and, beyond the cap, is disclosed provisional."""
    import scheduleiq.analytics.li_indices as li
    monkeypatch.setattr(li, "FCBI_PATHS_MAX", 20)
    acts = [_m("T", "T", 0.0), _a("D", "D", 0.0)] + \
           [_a(f"F{i}", f"F{i}", 1.0 + i * 0.01) for i in range(40)]   # all near-critical
    rels = [Relationship("D", "T")] + [Relationship(f"F{i}", "T") for i in range(40)]
    dist, _dm, _tm, capped = li._target_distance(_s(datetime(2025, 1, 6, 8), acts, rels), "T")
    assert capped and len(dist) > 15                     # completed + provisional


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
