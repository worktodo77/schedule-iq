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
    """Two updates, no logic (so RF = each activity's own total float), with
    hand-picked float moves:
        X: 0d -> -3d  (burn 3d, weight 2^0   = 1.00)
        Y: 5d -> +9d  (recovery 4d, weight 2^-1 = 0.50)
        Z: 10d -> 8d  (burn 2d, weight 2^-2 = 0.25)
    FCBI      = 3*1.00 + 2*0.25            = 3.5
    FCBI_rec  = 4*0.50                     = 2.0
    FCBI%     = 100 * 3.5 / (5*0.5 + 10*0.25) = 70.0   (X's TF=0 excluded)
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
    w = run_li_indices(sa).fcbi.windows[0]
    assert w.fcbi == pytest.approx(3.5)
    assert w.fcbi_recovery == pytest.approx(2.0)
    assert w.fcbi_pct == pytest.approx(70.0)


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
