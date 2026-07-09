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
                                     Schedule)
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


# ==================================================================== FCBI
def test_fcbi_burns_across_series(indices):
    fcbi = indices.fcbi
    assert fcbi.reason == ""
    # seeded float erosion => strictly positive burn in every window
    assert fcbi.windows and all(w.fcbi > 0 for w in fcbi.windows)
    # cumulative curve is non-decreasing (burn is never netted down)
    cum = fcbi.cumulative
    assert cum == sorted(cum)
    assert cum[-1] > 0
    # recovery tracked separately and never negative
    assert all(w.fcbi_recovery >= 0 for w in fcbi.windows)
    # a non-empty, contribution-ranked top-burner decomposition
    assert fcbi.top_burners
    contribs = [b.contribution for b in fcbi.top_burners]
    assert contribs == sorted(contribs, reverse=True)


def test_fcbi_exact_two_update_pair():
    """Two updates, no logic (so RF = each activity's own total float).  Weight
    uses min(RF_(u-1), RF_u) per the audit item-3 ruling; expected values are
    expressed through kernel_weight so the arithmetic is self-documenting:
        X: 0d -> -3d  burn 3d, w = 2^-(min(0,-3)/5)  = 2^(3/5)
        Y: 5d -> +9d  recovery 4d, w = 2^-(min(5,9)/5) = 2^-1 = 0.50
        Z: 10d -> 8d  burn 2d, w = 2^-(min(10,8)/5)  = 2^-(8/5)
        FCBI+  = 3*w_X + 2*w_Z
        FCBI-  = 4*w_Y
        FCBI%  = 100 * FCBI+ / (5*w_Y + 10*w_Z)   (X's TF=0 excluded from stock)
    """
    def act(uid, code, tf_hours):
        return Activity(uid=uid, code=code, atype=ActivityType.TASK,
                        total_float_hours=tf_hours)

    earlier = Schedule(project_id="SYN", data_date=datetime(2025, 1, 6, 8),
                       activities={a.uid: a for a in
                                   [act("X", "X", 0.0), act("Y", "Y", 40.0),
                                    act("Z", "Z", 80.0)]})
    later = Schedule(project_id="SYN", data_date=datetime(2025, 2, 6, 8),
                     activities={a.uid: a for a in
                                 [act("X", "X", -24.0), act("Y", "Y", 72.0),
                                  act("Z", "Z", 64.0)]})
    sa = SeriesAnalysis(schedules=[earlier, later],
                        changesets=[compare(earlier, later)])
    w_X, w_Y, w_Z = kernel_weight(-3, 5), kernel_weight(5, 5), kernel_weight(8, 5)
    exp_fcbi = 3 * w_X + 2 * w_Z
    exp_rec = 4 * w_Y
    exp_pct = 100.0 * exp_fcbi / (5 * w_Y + 10 * w_Z)
    w = run_li_indices(sa).fcbi.windows[0]
    assert w.fcbi == pytest.approx(exp_fcbi)          # ~5.2069
    assert w.fcbi_recovery == pytest.approx(exp_rec)  # 2.0
    assert w.fcbi_pct == pytest.approx(exp_pct)       # ~89.793


# ---- audit governance-quartet tests (FCBI_audit_2026-07-08.md) --------------
def _syn(uid_tf, status=None, rels=None):
    """Build a one-schedule Schedule from {code: tf_hours}; optional per-code
    status dict and relationship list (pred_code, succ_code)."""
    from scheduleiq.ingest.model import Calendar, Relationship, RelType
    cal = Calendar(uid="1", name="5d", hours_per_day=8.0, is_default=True)
    s = Schedule(project_id="SYN", data_date=datetime(2025, 1, 6, 8))
    s.calendars = {"1": cal}
    for code, tf in uid_tf.items():
        st = (status or {}).get(code, ActivityStatus.NOT_STARTED)
        a = Activity(uid=code, code=code, name=code, atype=ActivityType.TASK,
                     status=st, calendar_uid="1", total_float_hours=tf,
                     original_duration_hours=80.0, remaining_duration_hours=80.0,
                     early_start=datetime(2025, 1, 1), early_finish=datetime(2025, 2, 1),
                     planned_start=datetime(2025, 1, 1), planned_finish=datetime(2025, 2, 1))
        if st == ActivityStatus.COMPLETED:
            a.actual_start, a.actual_finish = datetime(2025, 1, 2), datetime(2025, 1, 20)
        s.activities[code] = a
    for pc, sc in (rels or []):
        s.relationships.append(Relationship(pred_uid=pc, succ_uid=sc,
                                            rtype=RelType.FS, lag_hours=0.0))
    return s


def _fcbi_of(*scheds):
    sa = SeriesAnalysis(schedules=list(scheds),
                        changesets=[compare(scheds[i], scheds[i + 1])
                                    for i in range(len(scheds) - 1)])
    return run_li_indices(sa).fcbi


def test_fcbi_item1_completed_excluded_and_exporter_invariant():
    """Item 1 — an activity that burns then completes must contribute ZERO to
    both burn and recovery, and must score identically whether the exporter
    wrote TF=0 or TF=null for the completed activity (no phantom burn)."""
    e = _syn({"A": 120.0, "B": 0.0}, rels=[("A", "B")])
    comp0 = _syn({"A": 0.0, "B": 0.0},
                 status={"A": ActivityStatus.COMPLETED}, rels=[("A", "B")])
    compN = _syn({"A": None, "B": 0.0},
                 status={"A": ActivityStatus.COMPLETED}, rels=[("A", "B")])
    w0 = _fcbi_of(e, comp0).windows[0]
    wN = _fcbi_of(e, compN).windows[0]
    assert w0.fcbi == pytest.approx(0.0) and w0.fcbi_recovery == pytest.approx(0.0)
    assert wN.fcbi == pytest.approx(w0.fcbi)
    assert wN.fcbi_recovery == pytest.approx(w0.fcbi_recovery)
    # recovery side too: a completed activity that "regained" float is excluded
    e2 = _syn({"A": 40.0, "B": 0.0}, rels=[("A", "B")])
    l2 = _syn({"A": 200.0, "B": 0.0},
              status={"A": ActivityStatus.COMPLETED}, rels=[("A", "B")])
    assert _fcbi_of(e2, l2).windows[0].fcbi_recovery == pytest.approx(0.0)


def test_fcbi_item3_weight_uses_min_over_window():
    """Item 3 — A (its path's min-float member via a floaty target Z) goes
    RF 20d -> 0d while burning 20d.  min(20,0)=0 -> weight 1.0 -> contribution
    20.0 (start-of-window weighting would give 2^-4 = 0.0625 -> 1.25)."""
    from scheduleiq.ingest.model import Relationship, RelType
    def s(tf_a):
        sc = _syn({"A": tf_a, "Z": 200.0})
        sc.activities["A"].early_finish = datetime(2025, 2, 1)
        sc.activities["Z"].early_finish = datetime(2025, 3, 1)   # Z resolves as target
        sc.activities["Z"].planned_finish = datetime(2025, 3, 1)
        sc.relationships.append(Relationship(pred_uid="A", succ_uid="Z",
                                            rtype=RelType.FS, lag_hours=0.0))
        return sc
    b = _fcbi_of(s(160.0), s(0.0)).windows[0].top_burners[0]
    assert b.code == "A"
    assert b.weight == pytest.approx(1.0)
    assert b.contribution == pytest.approx(20.0)


def test_fcbi_item4_rf_basis_falls_back_to_own_float_when_no_path():
    """Item 4 (reproducibility lock) — a tied target-finish yields a <2-step
    walk, float_paths()==[] , and RF falls back to each activity's OWN total
    float rather than a shared path minimum."""
    from scheduleiq.analytics.li_indices import _build_kernel
    from scheduleiq.ingest.model import Relationship, RelType
    sc = _syn({"A": 160.0, "Z": 200.0})           # both finish 2025-02-01 (tie)
    sc.relationships.append(Relationship(pred_uid="A", succ_uid="Z",
                                        rtype=RelType.FS, lag_hours=0.0))
    k = _build_kernel(sc, 5.0)
    assert k.rf["A"] == pytest.approx(20.0)        # own float, not a path min
    assert k.rf["Z"] == pytest.approx(25.0)


def test_fcbi_item5_windowing_not_additive():
    """Item 5 — TF 10 -> 0 -> 10 : per-window FCBI+ total is 10 (burn then
    regain), endpoint-only is 0 (net dTF zero).  Locks the intended
    non-additive semantics."""
    u0 = _syn({"A": 80.0, "Z": 0.0}, rels=[("A", "Z")])
    u1 = _syn({"A": 0.0, "Z": 0.0}, rels=[("A", "Z")])
    u2 = _syn({"A": 80.0, "Z": 0.0}, rels=[("A", "Z")])
    per_window = sum(w.fcbi for w in _fcbi_of(u0, u1, u2).windows)
    endpoint = sum(w.fcbi for w in _fcbi_of(u0, u2).windows)
    assert per_window == pytest.approx(10.0)
    assert endpoint == pytest.approx(0.0)


def test_fcbi_item2_pct_undefined_is_labelled_not_bare_none():
    """Item 2 — all-negative float stock: FCBI% is None but carries the
    labelled reason, and absolute FCBI+ is still reported."""
    e = _syn({"A": -40.0, "B": -80.0}, rels=[("A", "B")])
    l = _syn({"A": -80.0, "B": -120.0}, rels=[("A", "B")])
    w = _fcbi_of(e, l).windows[0]
    assert w.fcbi_pct is None
    assert w.pct_undefined_reason and "undefined" in w.pct_undefined_reason
    assert w.fcbi > 0


def test_fcbi_crossindex_completed_excluded_by_fcbi_kept_by_cdi():
    """Item 1b lock — a near-critical activity completing in-window is excluded
    from FCBI burn but still earns CDI dwell (retrospective vs live-work)."""
    e = _syn({"A": 40.0, "B": 0.0}, rels=[("A", "B")])
    l = _syn({"A": 0.0, "B": 0.0},
             status={"A": ActivityStatus.COMPLETED}, rels=[("A", "B")])
    sa = SeriesAnalysis(schedules=[e, l], changesets=[compare(e, l)])
    res = run_li_indices(sa)
    assert all("A" not in {b.code for b in w.top_burners} for w in res.fcbi.windows)
    assert "A" in {row.code for row in res.cdi.leaderboard}


def test_fcbi_disclosures_present():
    e = _syn({"A": 80.0, "B": 0.0}, rels=[("A", "B")])
    l = _syn({"A": 0.0, "B": 0.0}, rels=[("A", "B")])
    res = _fcbi_of(e, l)
    assert len(res.disclosures) == 5
    joined = " ".join(res.disclosures)
    assert "Completed activities are excluded" in joined
    assert "min(RF_(u-1), RF_u)" in joined


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
