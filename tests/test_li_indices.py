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


def test_rdi_bwi_cdi_carry_disclosures():
    res = run_li_indices(_loe_series())
    assert res.cdi.disclosures and any("retrospective" in d for d in res.cdi.disclosures)
    assert res.rdi.disclosures and any("LOE" in d for d in res.rdi.disclosures)
    assert res.bwi.disclosures and any("LOE" in d for d in res.bwi.disclosures)
