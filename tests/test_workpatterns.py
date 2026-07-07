"""Tests for N2 — as-built work-pattern reconstruction (ANALYTICS_PROPOSAL.md §8.2).

Driven by the demo_edit.xer / demo_edit_u1.xer fixture pair (two updates of one
project, DD 2025-05-05 -> 2025-07-07), whose seeded mechanisms are documented in
tests/fixtures/make_fixtures.py.  Every count/date/weekday asserted below is
hand-computed against that seed.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load, load_many                          # noqa: E402
from scheduleiq.ingest.model import (                                  # noqa: E402
    Activity, ActivityStatus, Calendar, Schedule, WorkPattern)
from scheduleiq.analytics.workpatterns import (                        # noqa: E402
    reconstruct_work_patterns, WorkPatternAnalysis, LABEL,
    DORMANCY_MIN_WORKING_DAYS)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EDIT0 = os.path.join(FIX, "demo_edit.xer")
EDIT1 = os.path.join(FIX, "demo_edit_u1.xer")
BASELINE = os.path.join(FIX, "demo_baseline.xer")

WINDOW = "DEMO-EDIT (2025-05-05) -> DEMO-EDIT (2025-07-07)"


@pytest.fixture(scope="session", autouse=True)
def _fixtures():
    if not os.path.exists(EDIT1):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def analysis():
    return reconstruct_work_patterns(load_many([EDIT0, EDIT1]))


# ------------------------------------------------------------- de facto calendar
def test_seven_day_calendar_records_five_day_week(analysis):
    """The MECH trade's 7-day calendar carries only Mon-Fri actuals -> the
    headline 'assumed 7 days, record shows 5' divergence."""
    cal = {p.key: p for p in analysis.de_facto_calendars}
    assert "301" in cal                                    # the 7-day calendar
    mech = cal["301"]
    assert mech.observed_working_days == [1, 2, 3, 4, 5]
    assert mech.assigned_working_days == [1, 2, 3, 4, 5, 6, 7]
    assert mech.divergence is True
    assert "7-day" in mech.note and "5-day" in mech.note


def test_five_day_calendar_shows_weekend_working(analysis):
    cal = {p.key: p for p in analysis.de_facto_calendars}
    civ = cal["300"]
    # weekend actuals push Sat(6)/Sun(7) into the observed set on a 5-day calendar
    assert 6 in civ.observed_working_days and 7 in civ.observed_working_days
    assert civ.assigned_working_days == [1, 2, 3, 4, 5]
    assert civ.divergence is True


def test_per_wbs_divergence_present(analysis):
    wbs = {p.key: p for p in analysis.wbs_divergence}
    assert wbs["MECH"].observed_working_days == [1, 2, 3, 4, 5]
    assert wbs["MECH"].assigned_working_days == [1, 2, 3, 4, 5, 6, 7]
    assert wbs["MECH"].divergence is True
    assert analysis.summary["wbs_nodes_divergent"] >= 1


# --------------------------------------------------------------- weekend working
def test_weekend_events_exactly_three(analysis):
    ev = analysis.weekend_events
    assert len(ev) == 3
    got = {(e.activity_code, e.event_type, e.event_date) for e in ev}
    assert got == {("W1", "start", "2025-05-10"),      # Saturday
                   ("W2", "start", "2025-05-11"),      # Sunday
                   ("W3", "finish", "2025-05-17")}     # Saturday
    # all on the 5-day calendar, all in the single update window
    assert all(e.calendar_uid == "300" for e in ev)
    assert all(e.window_key == WINDOW for e in ev)
    assert all(e.weekday in (6, 7) for e in ev)


def test_weekend_by_window_keyed_like_pacing(analysis):
    assert analysis.weekend_by_window == {WINDOW: 3}
    assert " -> " in WINDOW                             # pacing window-label shape


# --------------------------------------------------------------------- dormancy
def test_dormant_critical_activity(analysis):
    assert len(analysis.dormant_spans) == 1
    d = analysis.dormant_spans[0]
    assert d.activity_code == "EDIT-D1"
    assert d.on_driving_path is True
    assert "driving-path flag" in d.basis
    assert d.span_start == "2025-04-01"
    assert d.span_end == "2025-07-07"
    assert d.remaining_hours == 80.0
    # 2025-04-01 (Tue) -> 2025-07-07 (Mon) on the 5-day calendar = 69 working days
    assert d.working_days == 69.0
    assert d.working_days >= DORMANCY_MIN_WORKING_DAYS
    assert d.window_key == WINDOW


# --------------------------------------------------------------------- heatmap
def test_heatmap_totals_match_events(analysis):
    assert analysis.heatmap
    total = sum(c.event_count for c in analysis.heatmap)
    assert total == analysis.summary["actual_events"]
    # MECH work concentrated in June 2025 weeks
    mech_weeks = {c.iso_week for c in analysis.heatmap if c.wbs_code == "MECH"}
    assert mech_weeks and all(w.startswith("2025-W2") for w in mech_weeks)


# ---------------------------------------------------------- disclosures / label
def test_preliminary_label_and_disclosures(analysis):
    assert analysis.label == LABEL
    assert "PRELIMINARY" in analysis.label
    text = " ".join(analysis.disclosures).lower()
    assert "population" in text                         # population sizes disclosed
    assert "threshold" in text or "%" in text           # thresholds disclosed
    assert analysis.thresholds["dormancy_min_working_days"] == DORMANCY_MIN_WORKING_DAYS
    assert analysis.summary["actual_events"] == 20
    assert analysis.summary["activities_with_actuals"] == 11


# --------------------------------------------------------------- determinism/json
def test_determinism_and_json(analysis):
    d1 = analysis.to_dict()
    d2 = reconstruct_work_patterns(load_many([EDIT0, EDIT1])).to_dict()
    assert d1 == d2
    json.dumps(d1)                                       # must not raise


def test_order_independent(analysis):
    # supplying the files out of order still orders by data date internally
    r = reconstruct_work_patterns(load_many([EDIT1, EDIT0]))
    assert r.to_dict() == analysis.to_dict()


# ----------------------------------------------------------------- degradation
def test_single_schedule_skips_dormancy():
    r = reconstruct_work_patterns(load(EDIT1))
    assert r.dormant_spans == []
    assert any("single schedule" in d for d in r.disclosures)
    # de facto and weekend detection still run on one file
    assert r.weekend_events


def test_empty_list_degrades():
    r = reconstruct_work_patterns([])
    assert isinstance(r, WorkPatternAnalysis)
    assert r.reason
    assert r.to_dict()["dormant_spans"] == []


def test_no_actuals_degrades():
    s = Schedule(project_id="EMPTY", data_date=datetime(2025, 1, 6))
    s.activities["1"] = Activity(uid="1", code="X",
                                 status=ActivityStatus.NOT_STARTED)
    r = reconstruct_work_patterns([s])
    assert r.reason
    assert r.weekend_events == []
    assert r.dormant_spans == []
