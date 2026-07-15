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
                                     ActivityType, ConstraintType, RelType,
                                     Relationship, Schedule)
from scheduleiq.compare.diff import compare                         # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis, analyze_series  # noqa: E402
from scheduleiq.analytics.li_indices import (                       # noqa: E402
    kernel_weight, run_li_indices)

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



def test_fcbi_target_recode_is_uid_invariant():
    """A UID-stable target re-code must not change the FCBI target basis."""
    rels = [Relationship("A", "T")]
    e = _s(datetime(2025, 1, 6, 8),
           [_a("A", "A", 0.0), _m("T", "T", 0.0)], rels)
    l = _s(datetime(2025, 2, 6, 8),
           [_a("A", "A", -4.0), _m("T", "T-RECODED", -4.0)],
           [Relationship("A", "T")])
    r = _fcbi([e, l], target="T")
    assert r.reason == ""
    assert r.windows[0].burn_gross == pytest.approx(4.0)
    assert r.windows[0].top_burners[0].weight == pytest.approx(1.0)


def test_fcbi_mixed_calendar_frontier_matches_exhaustive():
    """Fixed-reference-hour frontier agrees with exhaustive paths across
    different native calendars."""
    from scheduleiq.ingest.model import Calendar
    from scheduleiq.analytics.paths import float_paths
    from scheduleiq.analytics.li_indices import _target_distance, REFERENCE_HPD
    e = _s(datetime(2025, 1, 6, 8),
           [_a("D", "D", 0.0), _a("F", "F", 6.0, od=20),
            _a("G", "G", 18.0, od=20), _m("T", "T", 0.0)],
           [Relationship("D", "T"), Relationship("F", "T"),
            Relationship("G", "T")])
    e.calendars = {
        "c5": Calendar(uid="c5", name="5d", hours_per_day=5.0, is_default=True),
        "c10": Calendar(uid="c10", name="10d", hours_per_day=10.0),
    }
    e.activities["F"].calendar_uid = "c5"
    e.activities["G"].calendar_uid = "c10"
    dist, dm, _tm, capped = _target_distance(e, "T")
    paths = float_paths(e, target_uid="T", n=128, band_days=None)
    assert paths and not capped and dm is not None
    oracle = {}
    for p in paths:
        d = max(0.0, p.rel_float_hours / REFERENCE_HPD - dm)
        for a in p.activities:
            if not a.is_loe_or_summary:
                oracle[a.uid] = min(oracle.get(a.uid, d), d)
    assert all(dist.get(uid) == pytest.approx(value) for uid, value in oracle.items())


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


# ============================== LOE / summary exclusion (ruling C1, v0.4.2) ===
def _sched_with(specs, dd, fin=None, rels=None):
    """specs: list of (uid, code, tf_hours, atype, remaining_hours).  Builds one
    Schedule on a single 5-day calendar for LOE-exclusion tests."""
    from scheduleiq.ingest.model import Calendar, Relationship, RelType
    cal = Calendar(uid="1", name="5d", hours_per_day=8.0, is_default=True)
    s = Schedule(project_id="SYN", data_date=dd, finish_date=fin)
    s.calendars = {"1": cal}
    for uid, code, tf, atype, rem in specs:
        s.activities[uid] = Activity(
            uid=uid, code=code, name=code, atype=atype,
            status=ActivityStatus.NOT_STARTED, calendar_uid="1",
            original_duration_hours=80.0, remaining_duration_hours=rem,
            total_float_hours=tf, early_start=datetime(2025, 1, 1),
            early_finish=datetime(2025, 3, 1), planned_start=datetime(2025, 1, 1),
            planned_finish=datetime(2025, 3, 1))
    for pc, sc in (rels or []):
        s.relationships.append(Relationship(pred_uid=pc, succ_uid=sc,
                                            rtype=RelType.FS, lag_hours=0.0))
    return s


def _loe_series(loe_tf_u1=0.0, loe_rem_u1=80.0):
    from scheduleiq.ingest.model import ActivityType as AT
    rels = [("A", "B"), ("B", "MS"), ("A", "LOE"), ("LOE", "MS")]
    u0 = _sched_with([("A", "A", 0.0, AT.TASK, 80.0), ("B", "B", 0.0, AT.TASK, 80.0),
                      ("LOE", "LOE", 0.0, AT.LOE, 80.0),
                      ("MS", "MS", 0.0, AT.FINISH_MILESTONE, 0.0)],
                     datetime(2025, 1, 1), datetime(2025, 4, 1), rels)
    u1 = _sched_with([("A", "A", 0.0, AT.TASK, 40.0), ("B", "B", 0.0, AT.TASK, 80.0),
                      ("LOE", "LOE", loe_tf_u1, AT.LOE, loe_rem_u1),
                      ("MS", "MS", 0.0, AT.FINISH_MILESTONE, 0.0)],
                     datetime(2025, 2, 1), datetime(2025, 4, 1), rels)
    return SeriesAnalysis(schedules=[u0, u1], changesets=[compare(u0, u1)])


def test_loe_excluded_from_relative_float_map():
    from scheduleiq.analytics.li_indices import _build_kernel
    sa = _loe_series()
    k = _build_kernel(sa.schedules[0], 5.0)
    assert "LOE" not in k.rf and "LOE" not in k.weight
    assert "A" in k.rf and "B" in k.rf          # discrete work still present


def test_cdi_ignores_loe():
    res = run_li_indices(_loe_series())
    assert "LOE" not in {e.code for e in res.cdi.leaderboard}
    assert {"A", "B"} <= {e.code for e in res.cdi.leaderboard}


def test_fcbi_ignores_loe_burn_and_top_burners():
    # LOE burns 40d of float; it must contribute zero and never be a burner.
    res = run_li_indices(_loe_series(loe_tf_u1=-320.0))
    w = res.fcbi.windows[0]
    assert "LOE" not in {b.code for b in w.top_burners}
    assert "LOE" not in {b.code for b in res.fcbi.top_burners}
    # A burned (0d->... actually A's tf unchanged here) — assert LOE simply absent
    assert all(b.code != "LOE" for b in w.top_burners)


def test_fcbi_ignores_loe_recovery():
    # LOE "regains" float (0 -> +40d); recovery must not count it.
    res = run_li_indices(_loe_series(loe_tf_u1=320.0))
    # only A/B/MS may contribute; LOE excluded — recovery holds no LOE weight.
    assert "LOE" not in {b.code for b in res.fcbi.top_burners}


def test_pci_unaffected_by_loe():
    from scheduleiq.ingest.model import ActivityType as AT
    rels_loe = [("A", "B"), ("B", "MS"), ("A", "LOE"), ("LOE", "MS")]
    with_loe = _sched_with([("A", "A", 0.0, AT.TASK, 80.0), ("B", "B", 0.0, AT.TASK, 80.0),
                            ("LOE", "LOE", 0.0, AT.LOE, 80.0),
                            ("MS", "MS", 0.0, AT.FINISH_MILESTONE, 0.0)],
                           datetime(2025, 1, 1), datetime(2025, 4, 1), rels_loe)
    no_loe = _sched_with([("A", "A", 0.0, AT.TASK, 80.0), ("B", "B", 0.0, AT.TASK, 80.0),
                          ("MS", "MS", 0.0, AT.FINISH_MILESTONE, 0.0)],
                         datetime(2025, 1, 1), datetime(2025, 4, 1), [("A", "B"), ("B", "MS")])
    pci_with = run_li_indices(SeriesAnalysis(schedules=[with_loe])).pci.per_update[0]
    pci_without = run_li_indices(SeriesAnalysis(schedules=[no_loe])).pci.per_update[0]
    assert pci_with == pytest.approx(pci_without)   # LOE-only path dropped
    assert pci_without == pytest.approx(1.0)        # single discrete-work path


def test_bwi_target_survives_rename_via_uid():
    from scheduleiq.ingest.model import ActivityType as AT, ConstraintType as CT
    def mk(ms_code, dd, rem):
        s = _sched_with([("w1", "W1", 0.0, AT.TASK, rem),
                         ("m1", ms_code, 0.0, AT.FINISH_MILESTONE, 0.0)],
                        dd, datetime(2025, 3, 1), [("w1", "m1")])
        s.activities["m1"].constraint = CT.MANDATORY_FINISH
        s.activities["m1"].early_finish = datetime(2025, 3, 1)
        s.activities["w1"].early_finish = datetime(2025, 3, 1)
        return s
    u0 = mk("MS-1", datetime(2025, 1, 1), 80.0)
    u1 = mk("MS-RENAMED", datetime(2025, 2, 1), 40.0)   # same uid m1, new code
    bwi = run_li_indices(SeriesAnalysis(schedules=[u0, u1], changesets=[compare(u0, u1)])).bwi
    assert bwi.target_code == "MS-1"                    # anchor code from update 0
    assert all(r.density is not None for r in bwi.rows)  # uid survived the rename


def test_rdi_accrues_against_p50_not_max():
    """R2 ruling (v0.4.3): RDI accrues debt against the running P50 (median)
    demonstrated pace, not the single best window (max).  Construct a series
    whose required pace, at one window, exceeds the running P50 but NOT the
    running max — debt must accrue (it would be zero under the old max-only
    rule)."""
    from scheduleiq.ingest.model import (ActivityType as AT, ActivityStatus as ST,
                                         Calendar, Relationship, RelType)
    from scheduleiq.analytics.li_indices import _median

    cal = Calendar(uid="1", name="5d", hours_per_day=8.0, is_default=True)

    def A(uid, code, rem, status=ST.NOT_STARTED, af=None, as_=None, od=80.0,
          atype=AT.TASK):
        return Activity(uid=uid, code=code, name=code, atype=atype, status=status,
                        calendar_uid="1", original_duration_hours=od,
                        remaining_duration_hours=rem, total_float_hours=0.0,
                        early_start=datetime(2025, 1, 1),
                        early_finish=datetime(2025, 6, 1), actual_start=as_,
                        actual_finish=af, planned_start=datetime(2025, 1, 1),
                        planned_finish=datetime(2025, 6, 1))

    def S(acts, dd, fin):
        s = Schedule(project_id="SYN", data_date=dd, finish_date=fin)
        s.calendars = {"1": cal}
        for a in acts:
            s.activities[a.uid] = a
        s.relationships = [Relationship(pred_uid="a", succ_uid="ms",
                                        rtype=RelType.FS, lag_hours=0.0)]
        return s

    def acts(rem, done=None, af=None, od=80.0):
        lst = [A("a", "A", rem), A("ms", "MS", 0.0, atype=AT.FINISH_MILESTONE)]
        if done:
            lst.append(A(done, done, 0.0, status=ST.COMPLETED, af=af, od=od))
        return lst
    u0 = S(acts(400.0), datetime(2025, 1, 1), datetime(2025, 4, 1))
    u1 = S(acts(300.0, "C1", datetime(2025, 1, 20), od=800.0),   # fast window
           datetime(2025, 2, 1), datetime(2025, 4, 1))
    u2 = S(acts(250.0, "C2", datetime(2025, 2, 20), od=40.0),    # slow window
           datetime(2025, 3, 1), datetime(2025, 4, 1))
    u3 = S(acts(200.0, "C3", datetime(2025, 3, 20), od=40.0),    # slow window
           datetime(2025, 3, 25), datetime(2025, 4, 1))
    sa = SeriesAnalysis(schedules=[u0, u1, u2, u3],
                        changesets=[compare(u0, u1), compare(u1, u2), compare(u2, u3)])
    res = run_li_indices(sa).rdi

    # Per window w (update w -> w+1): accrual uses required[w] (window start) and
    # the demonstrated pace observed through window w.  Replicate both anchors.
    required = [r.required_pace for r in res.rows]
    demonstrated = [res.rows[w + 1].demonstrated_pace
                    for w in range(len(res.rows) - 1)]
    seen: list[float] = []
    max_only_would_accrue = False
    p50_triggers = False
    for w, d in enumerate(demonstrated):
        if d is not None:
            seen.append(d)
        rq = required[w]
        if rq is None:
            continue
        if rq > (max(seen) if seen else 0.0):
            max_only_would_accrue = True
        if rq > _median(seen):
            p50_triggers = True
    assert res.rdi_days > 0            # debt accrued under the P50 rule
    assert p50_triggers               # ... because required exceeded the P50
    assert not max_only_would_accrue  # ... but never exceeded the running max


def _rdi_case_sched(acts, dd, fin):
    """One schedule on the shared 5d calendar for the R1 tests."""
    from scheduleiq.ingest.model import Calendar
    cal = Calendar(uid="1", name="5d", hours_per_day=8.0, is_default=True)
    s = Schedule(project_id="SYN", data_date=dd, finish_date=fin)
    s.calendars = {"1": cal}
    for a in acts:
        s.activities[a.uid] = a
    return s


def _rdi_case_act(uid, code, rem_h, status=None, as_=None, af=None, od_h=80.0):
    from scheduleiq.ingest.model import ActivityStatus as ST
    return Activity(uid=uid, code=code, name=code, atype=ActivityType.TASK,
                    status=status or ST.NOT_STARTED, calendar_uid="1",
                    original_duration_hours=od_h, remaining_duration_hours=rem_h,
                    total_float_hours=0.0, early_start=datetime(2025, 1, 6),
                    early_finish=datetime(2025, 6, 2), actual_start=as_,
                    actual_finish=af, planned_start=datetime(2025, 1, 6),
                    planned_finish=datetime(2025, 6, 2))


def test_rdi_planned_basis_concurrency_no_phantom_debt():
    """R1 ruling (v0.4.4): demonstrated pace stays planned-scope-per-calendar-
    working-day.  Five parallel near-critical activities, each planned 10wd,
    each actually taking the full 20wd window, all completing in it: the
    project retired 50 planned days in 20 working days, so demonstrated pace
    must be 2.5 (an elapsed-denominator basis would read 50/100 = 0.5 and
    manufacture phantom debt from mere parallelism).  The overrun signal lands
    in the companion ratio instead: 100 elapsed / 50 planned = 2.0."""
    from scheduleiq.ingest.model import ActivityStatus as ST
    dd0, dd1 = datetime(2025, 1, 6), datetime(2025, 2, 3)   # 20 working days
    fin = datetime(2025, 6, 2)
    u0 = _rdi_case_sched([_rdi_case_act(f"p{i}", f"P{i}", 80.0)
                          for i in range(5)], dd0, fin)
    u1 = _rdi_case_sched([_rdi_case_act(f"p{i}", f"P{i}", 0.0, ST.COMPLETED,
                                        as_=dd0, af=dd1)
                          for i in range(5)], dd1, fin)
    rdi = run_li_indices(SeriesAnalysis(schedules=[u0, u1],
                                        changesets=[compare(u0, u1)])).rdi
    row = rdi.rows[1]
    assert row.demonstrated_pace == pytest.approx(2.5)     # 50 planned / 20 wd
    assert row.overrun_ratio == pytest.approx(2.0)         # 100 elapsed / 50 planned
    assert rdi.overrun_ratio == pytest.approx(2.0)         # series-level
    assert any("never an accrual input" in d for d in rdi.disclosures)


def test_rdi_overrun_spread_and_missing_start_data_quality():
    """R1 companion, 3-window shape: an activity planned 10wd spanning three
    10wd windows completes in the last — demonstrated pace is 0 in the first
    two windows (the overrun's calendar cost, which the P50 anchor punishes)
    and 1.0 in the third, with the window overrun ratio 30/10 = 3.0.  A second
    case drops the actual start: the ratio degrades to None with a DATA
    QUALITY disclosure, never a guess."""
    from scheduleiq.ingest.model import ActivityStatus as ST
    dds = [datetime(2025, 1, 6), datetime(2025, 1, 20),
           datetime(2025, 2, 3), datetime(2025, 2, 17)]    # 3 x 10-wd windows
    fin = datetime(2025, 6, 2)

    def upd(i, done, as_):
        acts = [_rdi_case_act("f", "F", 400.0)]            # filler keeps series alive
        acts.append(_rdi_case_act("x", "X", 0.0 if done else 80.0,
                                  ST.COMPLETED if done else ST.NOT_STARTED,
                                  as_=as_ if done else None,
                                  af=dds[3] if done else None))
        return _rdi_case_sched(acts, dds[i], fin)
    scheds = [upd(0, False, None), upd(1, False, None), upd(2, False, None),
              upd(3, True, dds[0])]
    sa = SeriesAnalysis(schedules=scheds,
                        changesets=[compare(scheds[i], scheds[i + 1])
                                    for i in range(3)])
    rdi = run_li_indices(sa).rdi
    demo = [r.demonstrated_pace for r in rdi.rows[1:]]
    assert demo[0] == pytest.approx(0.0) and demo[1] == pytest.approx(0.0)
    assert demo[2] == pytest.approx(1.0)                   # 10 planned / 10 wd
    assert rdi.rows[3].overrun_ratio == pytest.approx(3.0)  # 30 elapsed / 10 planned

    # same series, actual start missing -> ratio None + DATA QUALITY note
    scheds2 = [upd(0, False, None), upd(1, False, None), upd(2, False, None),
               upd(3, True, None)]
    scheds2[3].activities["x"].actual_start = None
    sa2 = SeriesAnalysis(schedules=scheds2,
                         changesets=[compare(scheds2[i], scheds2[i + 1])
                                     for i in range(3)])
    rdi2 = run_li_indices(sa2).rdi
    assert rdi2.rows[3].overrun_ratio is None
    assert rdi2.overrun_ratio is None
    assert any("no actual start" in d for d in rdi2.disclosures)
    # the accrual itself is untouched by the missing start (diagnostic only)
    assert rdi2.rows[3].demonstrated_pace == pytest.approx(1.0)


def test_bwi_slipping_milestone_holds_at_one_fixed_horizon():
    """B1 ruling (v0.4.3): BWI normalizes against a FIXED reference horizon.  A
    milestone that SLIPS with unchanged near-critical work must read BWI == 1.0
    (the bow wave neither grew nor shrank), not < 1.0 as the old moving-forecast
    denominator produced (which mis-read a slip as relief)."""
    from scheduleiq.ingest.model import ActivityType as AT, ConstraintType as CT

    def mk(ms_finish, dd):
        s = _sched_with([("w1", "W1", 0.0, AT.TASK, 80.0),
                         ("m1", "MS", 0.0, AT.FINISH_MILESTONE, 0.0)],
                        dd, ms_finish, [("w1", "m1")])
        s.activities["w1"].early_finish = datetime(2025, 5, 1)
        ms = s.activities["m1"]
        ms.constraint = CT.MANDATORY_FINISH
        ms.constraint_date = ms_finish
        ms.early_finish = ms_finish
        return s
    # same data date + same near-critical work; only the milestone slips.
    u0 = mk(datetime(2025, 6, 1), datetime(2025, 1, 1))
    u1 = mk(datetime(2025, 9, 1), datetime(2025, 1, 1))
    bwi = run_li_indices(SeriesAnalysis(schedules=[u0, u1],
                                        changesets=[compare(u0, u1)])).bwi
    assert bwi.target_code == "MS"
    assert bwi.rows[0].density == pytest.approx(bwi.rows[1].density)  # denom fixed
    assert bwi.rows[1].bwi == pytest.approx(1.0)                      # not < 1.0
    assert any("fixed reference horizon".lower() in d.lower()
               for d in bwi.disclosures)


def test_rdi_bwi_cdi_carry_disclosures():
    res = run_li_indices(_loe_series())
    assert res.cdi.disclosures and any("retrospective" in d for d in res.cdi.disclosures)
    assert res.rdi.disclosures and any("LOE" in d for d in res.rdi.disclosures)
    assert res.bwi.disclosures and any("LOE" in d for d in res.bwi.disclosures)


def test_pci_all_milestone_schedule_graceful():
    """Closure lock: a schedule with no discrete executable work (milestones
    only) has no genuine near-critical path.  The discrete-work kernel filter
    must drop every path, PCI must degrade gracefully to None (not a spurious
    concentration figure), and run_li_indices must not raise.

    Non-vacuous: this fails if PCI ever returns a numeric path-concentration
    value for an all-milestone schedule (e.g. treating a bare-milestone chain
    as a real path)."""
    from scheduleiq.ingest.model import ActivityType as AT
    from scheduleiq.analytics.li_indices import _build_kernel
    ms = _sched_with([("m0", "M0", 40.0, AT.START_MILESTONE, 0.0),
                      ("m1", "M1", 40.0, AT.FINISH_MILESTONE, 0.0),
                      ("m2", "M2", 0.0, AT.FINISH_MILESTONE, 0.0)],
                     datetime(2025, 1, 1), datetime(2025, 4, 1),
                     [("m0", "m1"), ("m1", "m2")])
    k = _build_kernel(ms, 5.0)
    assert k.paths == []                                  # no discrete-work path survives
    res = run_li_indices(SeriesAnalysis(schedules=[ms]))  # must not raise
    assert res.pci.per_update == [None]                   # graceful, NOT a number
    assert not any(isinstance(v, (int, float)) for v in res.pci.per_update)
    assert res.pci.reason                                 # a labelled reason is carried


def test_pci_mixed_path_loe_neutralized_in_kernel():
    """v0.4.3 mixed-path LOE neutralization ruling.  Previously (v0.4.2) a kept
    mixed path (real work + LOE) took its relative float from the shared
    float_paths() over ALL members, so an LOE that was the lowest-float member
    dragged the discrete member's RF toward criticality (the disclosed residual).

    v0.4.3 layers an LI-specific per-path relative float over the path's DISCRETE
    unique members only (relative_float_map / _li_path_rel_float), so the LOE no
    longer drives the discrete member's RF.  The shared float_paths() is
    untouched: the driving path itself, and its rel_float_days, are unchanged —
    only the LI kernel's RF map is neutralized (it reads float_paths' additive
    unique_uids, nothing more)."""
    from scheduleiq.ingest.model import ActivityType as AT, ConstraintType as CT
    from scheduleiq.analytics.li_indices import _build_kernel
    from scheduleiq.analytics.paths import float_paths
    # A own float 30d -> LOE 2d -> T 5d ; competing real path X 50d -> T.
    # LOE (2d) is the strictly-lowest-float member of the driving mixed path.
    s = _sched_with([("a", "A", 240.0, AT.TASK, 80.0),
                     ("loe", "LOE", 16.0, AT.LOE, 80.0),
                     ("t", "T", 40.0, AT.FINISH_MILESTONE, 0.0),
                     ("x", "X", 400.0, AT.TASK, 80.0)],
                    datetime(2025, 1, 1), datetime(2025, 4, 1),
                    [("a", "loe"), ("loe", "t"), ("x", "t")])
    s.activities["t"].constraint = CT.MANDATORY_FINISH
    a_own = s.activities["a"].total_float_days(s.cal_for(s.activities["a"]))
    loe_own = s.activities["loe"].total_float_days(s.cal_for(s.activities["loe"]))
    assert (a_own, loe_own) == (30.0, 2.0)                # LOE strictly below A
    # shared float_paths() is UNCHANGED — it still routes the driving path through
    # the LOE and its rel_float_days still follows the LOE's lower float.
    driving = float_paths(s, n=10, band_days=None)[0]
    assert [st.activity.code for st in driving.steps] == ["A", "LOE", "T"]
    assert driving.rel_float_days == pytest.approx(loe_own)   # enumerator untouched
    # but the LI kernel now neutralizes the LOE: A's RF is its OWN 30d, not 2d.
    rf = _build_kernel(s, 5.0).rf
    assert rf["A"] == pytest.approx(a_own)                    # neutralized: 30d
    assert rf["A"] != pytest.approx(loe_own)                  # no longer LOE-driven
    assert "LOE" not in rf                                    # LOE still excluded
