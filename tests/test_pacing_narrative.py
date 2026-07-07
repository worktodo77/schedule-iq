"""Tests for the pacing/constructive-acceleration screens (S2) and the
narrative-reconciliation module (S4) — ANALYTICS_PROPOSAL.md §6.3/§6.8.

Uses the existing synthetic fixture series (tests/fixtures/make_fixtures.py,
not edited here) for the narrative-reconciliation classifications, since
those depend on the seeded retroactive change to A1010's actual dates
between update1 and update2 (documented in make_fixtures.py's update2
comment block).  Pacing/acceleration are exercised against the same fixture
series to confirm the screens run and degrade gracefully, plus two hand-built
synthetic two-update series that exhibit textbook patterns, since the
fixture series is not guaranteed to contain either pattern.
"""
import os
import subprocess
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load_many                             # noqa: E402
from scheduleiq.ingest.model import (Activity, ActivityStatus,       # noqa: E402
                                     Relationship, RelType,
                                     ResourceAssignment, Schedule)
from scheduleiq.compare.diff import compare                          # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis, analyze_series   # noqa: E402
from scheduleiq.analytics.pacing import (AccelerationCandidate,      # noqa: E402
                                         PacingCandidate, PacingResult,
                                         acceleration_candidates,
                                         pacing_candidates, run_pacing)
from scheduleiq.analytics.narrative import (ReconciliationResult,    # noqa: E402
                                            load_claims_csv, reconcile,
                                            run_narrative)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")
EVENTS_CSV = os.path.join(FIX, "events_sample.csv")
CLAIMS_CSV = os.path.join(FIX, "narrative_claims_sample.csv")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not os.path.exists(BASELINE):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


# =========================================================================
# S4 — narrative reconciliation
# =========================================================================
def test_claims_csv_is_well_formed():
    claims = load_claims_csv(CLAIMS_CSV)
    assert len(claims) == 4
    assert claims[0].activity_code is None
    assert claims[1].activity_code == "A1030"
    assert claims[2].activity_code == "A1010"
    assert claims[3].period_end == datetime(2024, 1, 15)


def test_reconcile_four_claim_classifications(series):
    rr = reconcile(series, CLAIMS_CSV)
    assert rr.reason == ""
    assert len(rr.rows) == 4
    classes = [r.classification for r in rr.rows]

    # (1) project-level claim matching update1's finish -> CONSISTENT
    assert classes[0] == "CONSISTENT"
    assert rr.rows[0].matched_update.startswith("DEMO-PLANT (2025-04-07")

    # (2) A1030 pct overstated by >10 points at update1 -> DISCREPANT
    assert classes[1] == "DISCREPANT"
    assert "75" in rr.rows[1].reason and "60" in rr.rows[1].reason

    # (3) A1010 finish consistent with update1 but contradicted by update2's
    #     rewritten actual -> RECORD-REWRITTEN
    assert classes[2] == "RECORD-REWRITTEN"
    assert "2025-03-26" in rr.rows[2].reason
    assert "2025-02-03" in rr.rows[2].reason

    # (4) dated outside any update window -> UNMATCHED
    assert classes[3] == "UNMATCHED"

    assert rr.caption == ("narrative reconciliation — each discrepancy is a "
                          "matter for explanation, not, without more, "
                          "evidence of impropriety.")
    assert rr.summary == {"CONSISTENT": 1, "DISCREPANT": 1,
                          "RECORD-REWRITTEN": 1, "UNMATCHED": 1, "total": 4}


def test_run_narrative_bundles_and_never_raises(series):
    rr = run_narrative(series, CLAIMS_CSV)
    assert isinstance(rr, ReconciliationResult)
    assert rr.summary["total"] == 4


def test_narrative_degrades_on_missing_csv(series):
    rr = run_narrative(series, None)
    assert rr.rows == []
    assert rr.reason


def test_narrative_degrades_on_empty_series():
    rr = reconcile(SeriesAnalysis(schedules=[]), CLAIMS_CSV)
    assert rr.rows == []
    assert rr.reason


# =========================================================================
# S2 — pacing / constructive-acceleration screens
# =========================================================================
def test_pacing_runs_on_fixture_series_typed_results(series):
    pr = run_pacing(series, events_csv=EVENTS_CSV)
    assert isinstance(pr, PacingResult)
    assert isinstance(pr.pacing, list)
    assert isinstance(pr.acceleration, list)
    assert pr.caption == ("pacing candidates — preliminary screening; the "
                          "pacing defense requires contemporaneous intent "
                          "evidence — reserved to the expert.")
    for c in pr.pacing:
        assert isinstance(c, PacingCandidate)
        assert c.chain_codes
        assert c.deceleration_measure
        assert c.concurrent_critical_slip
    for c in pr.acceleration:
        assert isinstance(c, AccelerationCandidate)
        assert len(c.signals) >= 2


def test_pacing_candidates_direct_api_never_raises(series):
    cands = pacing_candidates(series)
    assert isinstance(cands, list)
    acands = acceleration_candidates(series)
    assert isinstance(acands, list)


def test_pacing_degrades_on_empty_series():
    pr = run_pacing(SeriesAnalysis(schedules=[]))
    assert pr.pacing == []
    assert pr.acceleration == []
    assert pr.reason == ""     # empty series is not an error, just no windows


def test_pacing_degrades_on_single_file():
    from scheduleiq.ingest import load
    sa = SeriesAnalysis(schedules=load(BASELINE))
    pr = run_pacing(sa)
    assert pr.pacing == []
    assert pr.acceleration == []


# ------------------------------------------------------------- synthetic pacing
def _synthetic_pacing_series():
    """Textbook pacing pattern: a non-critical two-activity chain (float > 5d
    in the earlier update, linked by an FS relationship) whose remaining
    duration GROWS across the window, while the project forecast finish
    slips (the parallel critical delay)."""
    s1 = Schedule(project_id="SYN-PACE", data_date=datetime(2025, 1, 1),
                 finish_date=datetime(2025, 6, 1))
    nc1 = Activity(uid="NC1", code="NC-1", name="Non-critical Chain Start",
                  status=ActivityStatus.IN_PROGRESS,
                  remaining_duration_hours=80.0, total_float_hours=80.0,   # 10 wd
                  early_finish=datetime(2025, 2, 1))
    nc2 = Activity(uid="NC2", code="NC-2", name="Non-critical Chain End",
                  status=ActivityStatus.NOT_STARTED,
                  remaining_duration_hours=40.0, total_float_hours=60.0,   # 7.5 wd
                  early_finish=datetime(2025, 2, 15))
    s1.activities = {"NC1": nc1, "NC2": nc2}
    s1.relationships = [Relationship(pred_uid="NC1", succ_uid="NC2", rtype=RelType.FS)]

    s2 = Schedule(project_id="SYN-PACE", data_date=datetime(2025, 2, 1),
                 finish_date=datetime(2025, 6, 20))                       # slipped 19d
    nc1b = Activity(uid="NC1", code="NC-1", name="Non-critical Chain Start",
                   status=ActivityStatus.IN_PROGRESS,
                   remaining_duration_hours=120.0,                        # RD grew
                   total_float_hours=80.0, early_finish=datetime(2025, 2, 20))
    nc2b = Activity(uid="NC2", code="NC-2", name="Non-critical Chain End",
                   status=ActivityStatus.NOT_STARTED,
                   remaining_duration_hours=60.0,                         # RD grew
                   total_float_hours=60.0, early_finish=datetime(2025, 3, 5))
    s2.activities = {"NC1": nc1b, "NC2": nc2b}
    s2.relationships = [Relationship(pred_uid="NC1", succ_uid="NC2", rtype=RelType.FS)]
    return s1, s2


def test_synthetic_pacing_pattern_is_caught_with_float_evidence():
    s1, s2 = _synthetic_pacing_series()
    sa = SeriesAnalysis(schedules=[s1, s2], changesets=[compare(s1, s2)])
    cands = pacing_candidates(sa)
    assert cands, "expected the textbook pacing pattern to be caught"
    c = cands[0]
    assert set(c.chain_codes) == {"NC-1", "NC-2"}
    assert c.float_at_start_days is not None
    assert c.float_at_start_days > 5.0     # the chain qualified as non-critical
    assert "grew" in c.deceleration_measure or "pushed right" in c.deceleration_measure
    assert "slip" in c.concurrent_critical_slip.lower()


def test_synthetic_pacing_run_pacing_wraps_cleanly():
    s1, s2 = _synthetic_pacing_series()
    sa = SeriesAnalysis(schedules=[s1, s2], changesets=[compare(s1, s2)])
    pr = run_pacing(sa)
    assert pr.pacing
    assert pr.reason == ""


# ------------------------------------------------------ synthetic acceleration
def _synthetic_acceleration_series():
    """Textbook constructive-acceleration window: an incomplete activity
    whose duration is compressed on paper while its resource loading is
    increased in the same window (two independent signals)."""
    s1 = Schedule(project_id="SYN-ACC", data_date=datetime(2025, 1, 1))
    a1 = Activity(uid="A1", code="ACC-1", name="Accelerated Activity",
                 status=ActivityStatus.IN_PROGRESS,
                 original_duration_hours=200.0, remaining_duration_hours=150.0)
    a1.resources = [ResourceAssignment(activity_uid="A1", resource_uid="R1",
                                       budget_units=100.0)]
    s1.activities = {"A1": a1}

    s2 = Schedule(project_id="SYN-ACC", data_date=datetime(2025, 2, 1))
    a1b = Activity(uid="A1", code="ACC-1", name="Accelerated Activity",
                  status=ActivityStatus.IN_PROGRESS,
                  original_duration_hours=120.0,                          # compressed
                  remaining_duration_hours=80.0)
    a1b.resources = [ResourceAssignment(activity_uid="A1", resource_uid="R1",
                                        budget_units=200.0)]               # increased
    s2.activities = {"A1": a1b}
    return s1, s2


def test_synthetic_acceleration_window_is_caught():
    s1, s2 = _synthetic_acceleration_series()
    sa = SeriesAnalysis(schedules=[s1, s2], changesets=[compare(s1, s2)])
    cands = acceleration_candidates(sa)
    assert cands, "expected the synthetic acceleration window to be caught"
    c = cands[0]
    assert len(c.signals) >= 2
    assert any("duration compression" in s for s in c.signals)
    assert any("resource increase" in s for s in c.signals)
    assert "ACC-1" in c.evidence


def test_synthetic_acceleration_run_pacing_wraps_cleanly():
    s1, s2 = _synthetic_acceleration_series()
    sa = SeriesAnalysis(schedules=[s1, s2], changesets=[compare(s1, s2)])
    pr = run_pacing(sa)
    assert pr.acceleration
    assert pr.reason == ""


def test_acceleration_single_signal_does_not_qualify():
    """A lone duration compression (no other signal) must NOT be flagged —
    the threshold is >= 2 independent signals."""
    s1 = Schedule(project_id="SYN-ACC2", data_date=datetime(2025, 1, 1))
    a1 = Activity(uid="A1", code="ACC-2", name="Lone Compression",
                 status=ActivityStatus.IN_PROGRESS,
                 original_duration_hours=200.0, remaining_duration_hours=150.0)
    s1.activities = {"A1": a1}
    s2 = Schedule(project_id="SYN-ACC2", data_date=datetime(2025, 2, 1))
    a1b = Activity(uid="A1", code="ACC-2", name="Lone Compression",
                  status=ActivityStatus.IN_PROGRESS,
                  original_duration_hours=120.0, remaining_duration_hours=80.0)
    s2.activities = {"A1": a1b}
    sa = SeriesAnalysis(schedules=[s1, s2], changesets=[compare(s1, s2)])
    assert acceleration_candidates(sa) == []
