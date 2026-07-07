"""Tests for the Fuse-parity analytics: F1 Ribbon Analyzer, F2 Phase
Analyzer, F4 per-period start/finish compliance (docs/FUSE_PARITY.md).

Ribbon and phase tests build a ``ScheduleAssessment`` BY HAND (real
``CheckDef`` rows pulled from ``load_matrix()``, hand-picked findings) rather
than running the full ~80-check engine, so every offender count, density,
and score below is independently hand-computable and does not drift if an
unrelated check's population changes.  One smoke test per module additionally
runs the aggregator against a real ``evaluate()``-produced assessment from
the synthetic fixture series to prove end-to-end interop.

Compliance tests build in-memory ``Schedule``/``Activity`` objects directly
(test_asbuilt.py pattern) since F4 needs no metrics assessment at all.
"""
import os
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest.model import (                                    # noqa: E402
    Activity, ActivityStatus, ActivityType, ConstraintType, Schedule,
    WbsNode)
from scheduleiq.metrics.engine import (                                  # noqa: E402
    Finding, MetricResult, ScheduleAssessment, load_matrix)
from scheduleiq.analytics.ribbon import (                                # noqa: E402
    ribbon_analysis, RibbonAnalysis, LABEL as RIBBON_LABEL)
from scheduleiq.analytics.phase import (                                 # noqa: E402
    phase_analysis, PhaseAnalysis, LABEL as PHASE_LABEL)
from scheduleiq.analytics.compliance import (                            # noqa: E402
    period_compliance, ComplianceAnalysis, LABEL as COMPLIANCE_LABEL)

MATRIX = load_matrix()


def _cd(check_id):
    return next(c for c in MATRIX if c.id == check_id)


def _mr(check_id, findings):
    return MetricResult(check=_cd(check_id), findings=findings,
                        value=float(len(findings)), status="INFO")


def _dt(y, m, d, h=8):
    return datetime(y, m, d, h, 0)


# ===========================================================================
# F1 — Ribbon Analyzer
# ===========================================================================
def _wbs_schedule():
    """2-level WBS: two branches (AREA-1, AREA-2), each with one child WBS
    node under which activities actually sit — AREA-1.1 (3 activities, 2
    seeded DUR-01 offenders + 1 seeded CON-01 offender) and AREA-2.1 (2
    clean activities)."""
    s = Schedule(project_id="RIB", data_date=_dt(2025, 1, 6))
    s.wbs["W1"] = WbsNode(uid="W1", parent_uid=None, code="AREA-1", name="Area 1")
    s.wbs["W1a"] = WbsNode(uid="W1a", parent_uid="W1", code="AREA-1.1", name="Area 1 Sub")
    s.wbs["W2"] = WbsNode(uid="W2", parent_uid=None, code="AREA-2", name="Area 2")
    s.wbs["W2a"] = WbsNode(uid="W2a", parent_uid="W2", code="AREA-2.1", name="Area 2 Sub")

    def act(code, wbs_uid):
        return Activity(uid=code, code=code, name=code, atype=ActivityType.TASK,
                        status=ActivityStatus.NOT_STARTED, wbs_uid=wbs_uid)

    for code in ("A1", "A2", "A3"):
        s.activities[code] = act(code, "W1a")
    for code in ("B1", "B2"):
        s.activities[code] = act(code, "W2a")
    return s


def _wbs_assessment(s):
    return ScheduleAssessment(schedule=s, results=[
        _mr("DUR-01", [Finding("A1", "A1"), Finding("A2", "A2")]),
        _mr("CON-01", [Finding("A2", "A2")]),
        _mr("DCMA-07", []),                                    # live nowhere -> 0 everywhere
        _mr("DCMA-02", [Finding("A1 -> A2", "A1 -> A2")]),     # relationship-keyed -> excluded
        _mr("TRD-01", [Finding("A1", "A1")]),                  # series -> skipped entirely
    ])


def test_ribbon_wbs_leaf_level_exact_densities_and_score():
    s = _wbs_schedule()
    ra = ribbon_analysis(s, _wbs_assessment(s), group_by="wbs", level=2)
    assert ra.reason == ""
    assert ra.label == RIBBON_LABEL
    assert ra.unassigned_activities == 0
    assert ra.clamped_activities == 0
    assert ra.excluded_checks == ["DCMA-02"]
    assert "resolve" in ra.excluded_reason["DCMA-02"]
    assert "TRD-01" not in ra.excluded_checks
    for row in ra.rows:
        assert "TRD-01" not in row.check_offenders
        assert "DCMA-02" not in row.check_offenders

    by_group = {r.group: r for r in ra.rows}
    a = by_group["AREA-1.1"]
    assert a.activity_count == 3
    assert a.check_offenders == {"DUR-01": 2, "CON-01": 1, "DCMA-07": 0}
    assert a.category_density["Duration & Estimating"] == pytest.approx(2 / 3)
    assert a.category_density["Constraints"] == pytest.approx(1 / 3)
    assert a.category_density["DCMA 14-Point Assessment"] == pytest.approx(0.0)
    assert a.worst_checks == [("DUR-01", 2), ("CON-01", 1)]
    # eligible checks: DUR-01 (info, w=1) and CON-01 (info, w=1); DCMA-07 dormant
    # everywhere so excluded from the denominator.
    # num = 1*(1-2/3) + 1*(1-1/3) = 1/3 + 2/3 = 1.0; den = 2.0 -> score 50.0
    assert a.score == pytest.approx(50.0)

    b = by_group["AREA-2.1"]
    assert b.activity_count == 2
    assert b.check_offenders == {"DUR-01": 0, "CON-01": 0, "DCMA-07": 0}
    assert b.category_density["Duration & Estimating"] == 0.0
    assert b.worst_checks == []
    assert b.score == pytest.approx(100.0)

    # sorted worst-group-first (ascending score), tie-broken by group code
    assert [r.group for r in ra.rows] == ["AREA-1.1", "AREA-2.1"]


def test_ribbon_root_level_matches_leaf_level_here():
    """Each root has exactly one child in this fixture, so level=1 (root)
    reproduces the same per-branch numbers as level=2 (leaf) under different
    group labels — a 1:1 remap, not a coincidence of the data."""
    s = _wbs_schedule()
    assessment = _wbs_assessment(s)
    root_ra = ribbon_analysis(s, assessment, level=1)
    leaf_ra = ribbon_analysis(s, assessment, level=2)
    root_by_count = sorted(r.activity_count for r in root_ra.rows)
    leaf_by_count = sorted(r.activity_count for r in leaf_ra.rows)
    assert root_by_count == leaf_by_count == [2, 3]
    root_scores = sorted(r.score for r in root_ra.rows)
    leaf_scores = sorted(r.score for r in leaf_ra.rows)
    assert root_scores == leaf_scores
    assert {r.group for r in root_ra.rows} == {"AREA-1", "AREA-2"}


def test_ribbon_level_deeper_than_wbs_clamps_and_discloses():
    s = _wbs_schedule()
    ra = ribbon_analysis(s, _wbs_assessment(s), level=5)
    assert ra.clamped_activities == 5      # every activity's 2-node chain is shorter than 5
    assert {r.group for r in ra.rows} == {"AREA-1.1", "AREA-2.1"}


def test_ribbon_unassigned_activities_disclosed():
    s = Schedule(project_id="UNAS")
    s.wbs["W1"] = WbsNode(uid="W1", parent_uid=None, code="AREA-1")
    s.activities["A1"] = Activity(uid="A1", code="A1", atype=ActivityType.TASK,
                                  status=ActivityStatus.NOT_STARTED, wbs_uid="W1")
    s.activities["A2"] = Activity(uid="A2", code="A2", atype=ActivityType.TASK,
                                  status=ActivityStatus.NOT_STARTED, wbs_uid=None)
    ra = ribbon_analysis(s, ScheduleAssessment(schedule=s, results=[]), level=1)
    assert ra.unassigned_activities == 1
    by_group = {r.group: r for r in ra.rows}
    assert by_group["(unassigned)"].activity_count == 1
    assert by_group["AREA-1"].activity_count == 1


def test_ribbon_custom_groups_map():
    s = _wbs_schedule()
    ra = ribbon_analysis(s, _wbs_assessment(s), groups={"A1": "TeamX", "A2": "TeamX"})
    assert ra.group_by == "custom"
    by_group = {r.group: r for r in ra.rows}
    assert by_group["TeamX"].activity_count == 2
    assert by_group["(unassigned)"].activity_count == 3   # A3, B1, B2 unmapped


def test_ribbon_empty_schedule_degrades():
    s = Schedule(project_id="EMPTY")
    ra = ribbon_analysis(s, ScheduleAssessment(schedule=s, results=[]))
    assert ra.reason
    assert ra.rows == []


def test_ribbon_unsupported_group_by_degrades():
    s = _wbs_schedule()
    ra = ribbon_analysis(s, _wbs_assessment(s), group_by="area")
    assert ra.reason
    assert ra.rows == []


def test_ribbon_determinism():
    s = _wbs_schedule()
    assessment = _wbs_assessment(s)
    d1 = ribbon_analysis(s, assessment, level=1).to_dict()
    d2 = ribbon_analysis(s, assessment, level=1).to_dict()
    assert d1 == d2


def test_ribbon_smoke_against_real_assessment(baseline_schedule_and_assessment):
    sched, assessment = baseline_schedule_and_assessment
    ra = ribbon_analysis(sched, assessment, level=1)
    assert ra.reason == ""
    assert ra.rows
    assert sum(r.activity_count for r in ra.rows) == len(sched.real_activities)
    assert all(0.0 <= r.score <= 100.0 for r in ra.rows)
    d1 = ribbon_analysis(sched, assessment, level=1).to_dict()
    d2 = ribbon_analysis(sched, assessment, level=1).to_dict()
    assert d1 == d2


# ===========================================================================
# F2 — Phase Analyzer
# ===========================================================================
def _phase_schedule():
    """P1 sits entirely in January; P2 spans January into February and
    carries a soft constraint; P3 sits entirely in February; P4 carries no
    dates at all (unbucketed)."""
    s = Schedule(project_id="PHASE")
    p1 = Activity(uid="P1", code="P1", name="P1", atype=ActivityType.TASK,
                 status=ActivityStatus.IN_PROGRESS,
                 actual_start=_dt(2025, 1, 10), early_finish=_dt(2025, 1, 15),
                 total_float_hours=88.0, remaining_duration_hours=16.0)
    p2 = Activity(uid="P2", code="P2", name="P2", atype=ActivityType.TASK,
                 status=ActivityStatus.NOT_STARTED,
                 planned_start=_dt(2025, 1, 25), planned_finish=_dt(2025, 2, 5),
                 total_float_hours=40.0, remaining_duration_hours=88.0,
                 constraint=ConstraintType.START_ON_OR_AFTER)
    p3 = Activity(uid="P3", code="P3", name="P3", atype=ActivityType.TASK,
                 status=ActivityStatus.NOT_STARTED,
                 planned_start=_dt(2025, 2, 10), planned_finish=_dt(2025, 2, 20),
                 total_float_hours=8.0, remaining_duration_hours=80.0)
    p4 = Activity(uid="P4", code="P4", name="P4", atype=ActivityType.TASK,
                 status=ActivityStatus.NOT_STARTED)
    for a in (p1, p2, p3, p4):
        s.activities[a.code] = a
    return s


def _phase_assessment(s):
    return ScheduleAssessment(schedule=s, results=[
        _mr("DUR-03", [Finding("P2", "P2")]),
        _mr("FLT-02", []),
        _mr("DCMA-04", [Finding("P1 -> P2", "P1 -> P2")]),
    ])


def test_phase_bucket_membership_and_density_exact():
    s = _phase_schedule()
    pa = phase_analysis(s, _phase_assessment(s), bucket="month")
    assert pa.reason == ""
    assert pa.label == PHASE_LABEL
    assert pa.unbucketed_activities == 1
    assert pa.excluded_checks == ["DCMA-04"]
    assert [r.bucket_label for r in pa.rows] == ["2025-01", "2025-02"]

    jan, feb = pa.rows
    assert jan.bucket_start == _dt(2025, 1, 1, 0)
    assert jan.bucket_end == _dt(2025, 2, 1, 0)
    assert jan.active_count == 2            # P1, P2
    assert jan.starting_count == 2          # P1 (Jan10), P2 (Jan25)
    assert jan.finishing_count == 1         # P1 (Jan15)
    assert jan.remaining_hours == pytest.approx(16.0 + 88.0)
    assert jan.check_offenders == {"DUR-03": 1, "FLT-02": 0}
    assert jan.density == pytest.approx(1 / 2)
    assert jan.near_critical_count == 1     # P2 (5d) ; P1 (11d) is not
    assert jan.near_critical_share == pytest.approx(0.5)
    assert jan.constraint_count == 1        # P2

    assert feb.active_count == 2            # P2, P3
    assert feb.starting_count == 1          # P3 (Feb10)
    assert feb.finishing_count == 2         # P2 (Feb5), P3 (Feb20)
    assert feb.remaining_hours == pytest.approx(88.0 + 80.0)
    assert feb.check_offenders == {"DUR-03": 1, "FLT-02": 0}   # P2 occupies both buckets
    assert feb.density == pytest.approx(1 / 2)
    assert feb.near_critical_count == 2     # P2 (5d), P3 (1d)
    assert feb.near_critical_share == pytest.approx(1.0)
    assert feb.constraint_count == 1        # P2


def test_phase_week_bucket_boundaries():
    s = _phase_schedule()
    pa = phase_analysis(s, _phase_assessment(s), bucket="week",
                        start=_dt(2025, 1, 1), end=_dt(2025, 1, 21))
    assert pa.reason == ""
    assert len(pa.rows) == 3
    assert pa.rows[0].bucket_start == _dt(2025, 1, 1)
    assert pa.rows[1].bucket_start == _dt(2025, 1, 8)
    assert pa.rows[2].bucket_start == _dt(2025, 1, 15)


def test_phase_unsupported_bucket_degrades():
    s = _phase_schedule()
    pa = phase_analysis(s, _phase_assessment(s), bucket="year")
    assert pa.reason
    assert pa.rows == []


def test_phase_empty_schedule_degrades():
    s = Schedule(project_id="EMPTY")
    pa = phase_analysis(s, ScheduleAssessment(schedule=s, results=[]))
    assert pa.reason
    assert pa.rows == []


def test_phase_no_resolvable_date_range_degrades():
    s = Schedule(project_id="NODATES")
    s.activities["X1"] = Activity(uid="X1", code="X1", atype=ActivityType.TASK,
                                  status=ActivityStatus.NOT_STARTED)
    pa = phase_analysis(s, ScheduleAssessment(schedule=s, results=[]))
    assert pa.reason
    assert pa.rows == []
    assert pa.unbucketed_activities == 1


def test_phase_determinism():
    s = _phase_schedule()
    assessment = _phase_assessment(s)
    d1 = phase_analysis(s, assessment).to_dict()
    d2 = phase_analysis(s, assessment).to_dict()
    assert d1 == d2


def test_phase_smoke_against_real_assessment(baseline_schedule_and_assessment):
    sched, assessment = baseline_schedule_and_assessment
    pa = phase_analysis(sched, assessment)
    assert pa.reason == ""
    assert pa.rows
    d1 = phase_analysis(sched, assessment).to_dict()
    d2 = phase_analysis(sched, assessment).to_dict()
    assert d1 == d2


# ===========================================================================
# F4 — per-period start/finish compliance
# ===========================================================================
def _compliance_schedules():
    """Window Jan 6 -> Feb 3 2025.  Start side: S1/S2 on time, S3 late by 5
    calendar days (the acceptance scenario: 3 started, 2 on time, 1 late 5d),
    S4 started with no basis date, S5 planned to start but never started
    (drags commitment reliability below 100%).  Finish side: F1 on time, F2
    late by 8 calendar days (misses both the 0d and 7d tolerance), F3
    finished with no basis date."""
    earlier = Schedule(project_id="CMP", data_date=_dt(2025, 1, 6))
    later = Schedule(project_id="CMP", data_date=_dt(2025, 2, 3))

    defs = [
        dict(code="S1", planned_start=_dt(2025, 1, 10), actual_start=_dt(2025, 1, 10),
            status=ActivityStatus.IN_PROGRESS),
        dict(code="S2", planned_start=_dt(2025, 1, 13), actual_start=_dt(2025, 1, 13),
            status=ActivityStatus.IN_PROGRESS),
        dict(code="S3", planned_start=_dt(2025, 1, 15), actual_start=_dt(2025, 1, 20),
            status=ActivityStatus.IN_PROGRESS),
        dict(code="S4", actual_start=_dt(2025, 1, 25), status=ActivityStatus.IN_PROGRESS),
        dict(code="S5", planned_start=_dt(2025, 1, 27), status=ActivityStatus.NOT_STARTED),
        dict(code="F1", planned_finish=_dt(2025, 1, 20), actual_finish=_dt(2025, 1, 19),
            actual_start=_dt(2025, 1, 5), status=ActivityStatus.COMPLETED),
        dict(code="F2", planned_finish=_dt(2025, 1, 22), actual_finish=_dt(2025, 1, 30),
            actual_start=_dt(2025, 1, 5), status=ActivityStatus.COMPLETED),
        dict(code="F3", actual_finish=_dt(2025, 1, 28), actual_start=_dt(2025, 1, 5),
            status=ActivityStatus.COMPLETED),
    ]
    for d in defs:
        code = d.pop("code")
        a = Activity(uid=code, code=code, name=code, atype=ActivityType.TASK, **d)
        later.activities[code] = a
    return earlier, later


def test_compliance_single_schedule_degrades():
    earlier, _later = _compliance_schedules()
    ca = period_compliance([earlier])
    assert ca.reason
    assert ca.windows == []


def test_compliance_window_rates_exact():
    earlier, later = _compliance_schedules()
    ca = period_compliance([earlier, later])
    assert ca.label == COMPLIANCE_LABEL
    assert len(ca.windows) == 1
    w = ca.windows[0]
    assert w.reason == ""

    # start side: 3 with a basis date (S1,S2,S3); S4 has no basis
    assert w.started_population == 4          # S1,S2,S3,S4
    assert w.actually_started_count == 4
    assert w.no_basis_start_count == 1         # S4
    assert w.start_compliance_pct_0d == pytest.approx(100.0 * 2 / 3)
    assert w.start_compliance_pct_7d == pytest.approx(100.0)
    assert len(w.late_starts) == 1
    late = w.late_starts[0]
    assert late.code == "S3"
    assert late.days_late == pytest.approx(5.0)
    assert late.basis_date == _dt(2025, 1, 15)
    assert late.actual_date == _dt(2025, 1, 20)

    # finish side: F1 on time, F2 late by 8d (misses 0d AND 7d tolerance), F3 no basis
    assert w.finished_population == 3          # F1,F2,F3
    assert w.no_basis_finish_count == 1        # F3
    assert w.finish_compliance_pct_0d == pytest.approx(50.0)
    assert w.finish_compliance_pct_7d == pytest.approx(50.0)
    assert len(w.late_finishes) == 1
    lf = w.late_finishes[0]
    assert lf.code == "F2"
    assert lf.days_late == pytest.approx(8.0)

    # commitment reliability: planned to start = {S1,S2,S3,S5}; actually
    # started = {S1,S2,S3,S4}; intersection = {S1,S2,S3} -> 3/4
    assert w.planned_to_start_count == 4
    assert w.commitment_reliability_pct == pytest.approx(75.0)

    assert ca.trend["start_compliance_0d"] == [w.start_compliance_pct_0d]
    assert ca.trend["commitment_reliability"] == [w.commitment_reliability_pct]


def test_compliance_window_missing_data_date_degrades():
    earlier, later = _compliance_schedules()
    earlier.data_date = None
    ca = period_compliance([earlier, later])
    assert len(ca.windows) == 1
    w = ca.windows[0]
    assert w.reason
    assert w.started_population == 0
    assert ca.trend["start_compliance_0d"] == [None]


def test_compliance_no_activities_all_no_basis():
    earlier = Schedule(project_id="NB", data_date=_dt(2025, 1, 6))
    later = Schedule(project_id="NB", data_date=_dt(2025, 2, 3))
    later.activities["Z1"] = Activity(uid="Z1", code="Z1", name="Z1",
                                      atype=ActivityType.TASK,
                                      actual_start=_dt(2025, 1, 15),
                                      status=ActivityStatus.IN_PROGRESS)
    ca = period_compliance([earlier, later])
    w = ca.windows[0]
    assert w.started_population == 1
    assert w.no_basis_start_count == 1
    assert w.start_compliance_pct_0d is None
    assert w.start_compliance_pct_7d is None


def test_compliance_determinism():
    earlier, later = _compliance_schedules()
    d1 = period_compliance([earlier, later]).to_dict()
    d2 = period_compliance([earlier, later]).to_dict()
    assert d1 == d2


def test_compliance_smoke_against_real_series(demo_schedules):
    ca = period_compliance(demo_schedules)
    assert ca.reason == ""
    assert len(ca.windows) == len(demo_schedules) - 1
    d1 = period_compliance(demo_schedules).to_dict()
    d2 = period_compliance(demo_schedules).to_dict()
    assert d1 == d2


# ===========================================================================
# shared fixtures against the synthetic fixture series
# ===========================================================================
FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")


@pytest.fixture(scope="session", autouse=True)
def _fixtures():
    if not os.path.exists(BASELINE):
        import subprocess
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def demo_schedules():
    from scheduleiq.ingest import load_many
    return load_many([BASELINE, U1, U2])


@pytest.fixture(scope="session")
def baseline_schedule_and_assessment(demo_schedules):
    from scheduleiq.metrics.engine import evaluate
    sched = demo_schedules[0]
    return sched, evaluate(sched)
