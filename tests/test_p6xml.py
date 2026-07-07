"""Tests for the P6 XML (PMXML) ingest path (ADR-0002 F3) and the F5 MPXJ
extension routing (.pp / .ppx) in ``scheduleiq.ingest.mpp``.

``demo_p6.xml`` is a synthetic, hand-written PMXML fixture (see the header
comment in that file) — every field the parser maps is asserted here at least
once, spread across the activities/relationships/calendars/settings it covers.
"""
import datetime
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load, SUPPORTED                          # noqa: E402
from scheduleiq.ingest.model import (ActivityStatus, ActivityType,     # noqa: E402
                                    ConstraintType, RelType)
from scheduleiq.ingest.p6xml import parse_p6xml, sniff                 # noqa: E402
from scheduleiq.metrics.engine import evaluate                         # noqa: E402
from scheduleiq.cpm.bridge import build_engine_inputs                  # noqa: E402
from scheduleiq.cpm.handshake import run_handshake                     # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
DEMO_P6 = os.path.join(FIX, "demo_p6.xml")

# A minimal, valid MSPDI document — used only to prove the .xml sniff in
# ingest/__init__.py still routes MSPDI content to parse_mspdi byte-identically
# (no MSPDI fixture exists in this repo yet to regress against, so the smallest
# valid document that exercises parse_mspdi's required elements is built here).
_TINY_MSPDI = """<?xml version="1.0"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Tiny</Name>
  <Title>Tiny MSPDI Regression</Title>
  <StartDate>2026-01-01T08:00:00</StartDate>
  <FinishDate>2026-01-02T17:00:00</FinishDate>
  <CalendarUID>1</CalendarUID>
  <MinutesPerDay>480</MinutesPerDay>
  <MinutesPerWeek>2400</MinutesPerWeek>
  <Calendars>
    <Calendar>
      <UID>1</UID>
      <Name>Standard</Name>
    </Calendar>
  </Calendars>
  <Tasks>
    <Task>
      <UID>1</UID>
      <ID>1</ID>
      <Name>Task A</Name>
      <Start>2026-01-01T08:00:00</Start>
      <Finish>2026-01-02T17:00:00</Finish>
      <Duration>PT8H0M0S</Duration>
    </Task>
  </Tasks>
</Project>
"""


@pytest.fixture(scope="session")
def demo():
    return parse_p6xml(DEMO_P6)[0]


@pytest.fixture(scope="session")
def acts(demo):
    return demo.activities


# --------------------------------------------------------------- project / provenance
def test_project_header(demo):
    assert demo.project_id == "P6-DEMO"
    assert demo.project_name == "Demo Plant Outage - P6 XML"
    assert demo.data_date == datetime.datetime(2026, 1, 19, 8, 0)
    assert demo.start_date == datetime.datetime(2026, 1, 5, 8, 0)
    assert demo.finish_date == datetime.datetime(2026, 1, 23, 17, 0)
    assert demo.must_finish_by == datetime.datetime(2026, 1, 31, 17, 0)
    assert demo.source_format == "P6XML"
    assert demo.source_tool == "P6 (PMXML v23.12)"
    assert demo.export_user == "planner1"
    assert demo.export_date == datetime.datetime(2026, 1, 19, 7, 30)
    assert demo.project_create_user == "planner1"
    assert demo.project_update_user == "scheduler2"
    assert demo.source_sha256 and len(demo.source_sha256) == 64


def test_shape(demo):
    assert len(demo.activities) == 8
    assert len(demo.relationships) == 8
    assert len(demo.calendars) == 2
    assert len(demo.wbs) == 2
    assert demo.parse_warnings == []


# --------------------------------------------------------------------------- WBS
def test_wbs_two_levels(demo):
    root = demo.wbs["WBS_ROOT"]
    assert root.parent_uid is None
    assert root.code == "P6-DEMO"
    assert root.name == "Demo Plant Outage"
    child = demo.wbs["WBS_L2"]
    assert child.parent_uid == "WBS_ROOT"
    assert child.code == "PH1"
    assert child.name == "Phase 1 Outage Work"


# --------------------------------------------------------------------- activities
def test_milestone_start(acts):
    a = acts["A100"]
    assert a.code == "MS-START"
    assert a.atype == ActivityType.START_MILESTONE
    assert a.status == ActivityStatus.COMPLETED
    assert a.is_milestone
    assert a.actual_start == a.actual_finish == datetime.datetime(2026, 1, 5, 8, 0)
    assert a.early_start == a.early_finish == datetime.datetime(2026, 1, 5, 8, 0)
    assert a.late_start == a.late_finish == datetime.datetime(2026, 1, 5, 8, 0)
    assert a.total_float_hours == 0.0
    assert a.free_float_hours == 0.0
    assert a.pct_complete == 100.0
    assert a.is_longest_path is True
    assert a.wbs_uid == "WBS_ROOT"
    assert a.calendar_uid == "CAL_5D"
    assert a.create_user == "planner1"
    assert a.create_date == datetime.datetime(2025, 12, 1, 9, 0)


def test_not_started_task_and_float(acts):
    a = acts["A101"]
    assert a.code == "A1010"
    assert a.atype == ActivityType.TASK
    assert a.status == ActivityStatus.NOT_STARTED
    assert a.original_duration_hours == 40.0
    assert a.remaining_duration_hours == 40.0
    assert a.planned_start == datetime.datetime(2026, 1, 6, 8, 0)
    assert a.planned_finish == datetime.datetime(2026, 1, 8, 17, 0)
    assert a.late_start == datetime.datetime(2026, 1, 12, 8, 0)
    assert a.late_finish == datetime.datetime(2026, 1, 14, 17, 0)
    assert a.total_float_hours == 32.0
    assert a.is_longest_path is False


def test_completed_task_with_actuals(acts):
    a = acts["A102"]
    assert a.code == "A1020"
    assert a.status == ActivityStatus.COMPLETED
    assert a.completed
    assert a.actual_start == datetime.datetime(2026, 1, 6, 8, 0)
    assert a.actual_finish == datetime.datetime(2026, 1, 12, 17, 0)
    assert a.original_duration_hours == 80.0
    assert a.remaining_duration_hours == 0.0
    assert a.at_completion_duration_hours == 80.0
    assert a.pct_complete == 100.0
    assert a.update_user == "fieldeng3"
    assert a.update_date == datetime.datetime(2026, 1, 12, 17, 15)


def test_in_progress_task(acts):
    a = acts["A103"]
    assert a.code == "A1030"
    assert a.status == ActivityStatus.IN_PROGRESS
    assert a.in_progress
    assert a.actual_start == datetime.datetime(2026, 1, 13, 8, 0)
    assert a.actual_finish is None
    assert a.remaining_duration_hours == 40.0
    assert a.pct_complete == 66.7
    assert a.wbs_uid == "WBS_L2"
    # resource assignment fidelity
    assert len(a.resources) == 1
    r = a.resources[0]
    assert r.resource_name == "Piping Crew"
    assert r.resource_type == "Labor"
    assert r.budget_units == 120.0
    assert r.actual_units == 80.0
    assert r.remaining_units == 40.0
    assert a.budget_cost == 9600.0
    assert a.actual_cost == 6400.0
    assert a.remaining_cost == 3200.0


def test_dual_constraint_activity(acts):
    a = acts["A104"]
    assert a.code == "A1040"
    assert a.calendar_uid == "CAL_7D"
    assert a.constraint == ConstraintType.START_ON_OR_AFTER
    assert a.constraint_date == datetime.datetime(2026, 1, 20, 0, 0)
    assert a.constraint2 == ConstraintType.MANDATORY_FINISH
    assert a.constraint2_date == datetime.datetime(2026, 1, 22, 17, 0)
    assert a.constraint.is_hard is False           # SNET is soft
    assert a.constraint2.is_hard is True            # mandatory finish is hard


def test_driving_path_task(acts):
    a = acts["A105"]
    assert a.code == "A1050"
    assert a.is_longest_path is True
    assert a.total_float_hours == 0.0


def test_loe_excluded_from_real_activities(demo, acts):
    a = acts["A106"]
    assert a.code == "A1060"
    assert a.atype == ActivityType.LOE
    assert a.is_loe_or_summary
    assert a.is_longest_path is None                # DrivingPath absent in fixture
    assert a.pct_complete == 40.0
    real_codes = {x.code for x in demo.real_activities}
    assert "A1060" not in real_codes
    assert len(demo.real_activities) == 7


def test_finish_milestone_and_expected_finish(acts):
    a = acts["A107"]
    assert a.code == "MS-FINISH"
    assert a.atype == ActivityType.FINISH_MILESTONE
    assert a.expected_finish == datetime.datetime(2026, 1, 24, 17, 0)
    # no explicit PrimaryConstraintType in the fixture -> ExpectedFinishDate
    # promotes to the EXPECTED_FINISH constraint (mirrors xer.py behavior).
    assert a.constraint == ConstraintType.EXPECTED_FINISH
    assert a.constraint_date == a.expected_finish
    assert a.is_longest_path is True


# ------------------------------------------------------------------- relationships
def test_relationship_types_lag_and_lead(demo):
    by_pair = {(r.pred_uid, r.succ_uid): r for r in demo.relationships}
    assert by_pair[("A100", "A102")].rtype == RelType.FS
    assert by_pair[("A101", "A104")].rtype == RelType.SS
    assert by_pair[("A103", "A105")].rtype == RelType.FF
    assert by_pair[("A104", "A105")].rtype == RelType.SF
    # lag: 1 workday at 8h/day
    assert by_pair[("A102", "A103")].lag_hours == 8.0
    # lead: negative lag
    assert by_pair[("A103", "A105")].lag_hours == -8.0
    assert {r.rtype for r in demo.relationships} == {RelType.FS, RelType.SS,
                                                      RelType.FF, RelType.SF}


# ------------------------------------------------------------------------ calendars
def test_calendar_5day_workweek_and_exceptions(demo):
    c5 = demo.calendars["CAL_5D"]
    assert c5.name == "5 Day Workweek"
    assert c5.ctype == "Project"
    assert c5.hours_per_day == 8.0
    assert c5.hours_per_week == 40.0
    assert c5.workdays_per_week == 5
    assert c5.is_default is True
    assert c5.work_patterns[1].spans == [("08:00", "12:00"), ("13:00", "17:00")]
    assert c5.work_patterns[6].spans == []            # Saturday non-working pattern
    assert datetime.date(2026, 1, 1) in c5.exceptions_nonwork      # holiday
    assert c5.exceptions_work[datetime.date(2026, 1, 17)] == 4.0   # worked Saturday
    assert c5.is_workday(datetime.date(2026, 1, 1)) is False
    assert c5.is_workday(datetime.date(2026, 1, 17)) is True


def test_calendar_7day(demo):
    c7 = demo.calendars["CAL_7D"]
    assert c7.name == "7 Day Vendor Calendar"
    assert c7.ctype == "Global"
    assert c7.hours_per_day == 10.0
    assert c7.hours_per_week == 70.0
    assert c7.workdays_per_week == 7
    assert c7.is_default is False
    assert not c7.exceptions_nonwork
    assert not c7.exceptions_work


# ------------------------------------------------------------------------ settings
def test_schedule_options(demo):
    s = demo.settings
    assert s.retained_logic is True
    assert s.progress_override is False
    assert s.relationship_lag_calendar == "Predecessor Activity Calendar"
    assert s.critical_float_threshold_hours == 0.0
    assert s.critical_definition == "TotalFloat"
    assert s.make_open_ends_critical is False
    assert s.use_expected_finish is False
    assert s.raw["SchedulingProgressedActivities"] == "Retained Logic"


# ----------------------------------------------------------------------- .xml sniff
def test_sniff_detects_pmxml():
    with open(DEMO_P6, "rb") as f:
        assert sniff(f.read(4096)) is True


def test_dispatch_routes_pmxml_by_extension(demo):
    loaded = load(DEMO_P6)[0]
    assert loaded.source_format == "P6XML"
    assert loaded.project_id == demo.project_id


def test_mspdi_still_loads_as_mspdi_regression(tmp_path):
    """.xml sniffing must not regress plain MSPDI files onto the PMXML path."""
    p = tmp_path / "tiny_mspdi.xml"
    p.write_text(_TINY_MSPDI)
    sched = load(str(p))[0]
    assert sched.source_format == "MSPDI"
    assert len(sched.activities) == 1


def test_unrecognized_xml_raises(tmp_path):
    p = tmp_path / "junk.xml"
    p.write_text("<NotASchedule><Foo>bar</Foo></NotASchedule>")
    with pytest.raises(ValueError):
        load(str(p))


# ------------------------------------------------------------------- multi-project
def _two_project_variant() -> str:
    base = open(DEMO_P6, encoding="utf-8").read()
    extra_project = """
  <Project>
    <ObjectId>2</ObjectId>
    <Id>P6-DEMO-2</Id>
    <Name>Demo Second Project</Name>
    <DataDate>2026-01-19T08:00:00</DataDate>
    <PlannedStartDate>2026-01-05T08:00:00</PlannedStartDate>
    <ScheduledFinishDate>2026-01-10T17:00:00</ScheduledFinishDate>
    <DefaultCalendarObjectId>CAL_5D</DefaultCalendarObjectId>
  </Project>"""
    marker = "</Project>"
    idx = base.index(marker) + len(marker)
    out = base[:idx] + extra_project + base[idx:]
    extra_activities = """
  <Activity>
    <ObjectId>B100</ObjectId>
    <ProjectObjectId>2</ProjectObjectId>
    <Id>B1000</Id>
    <Name>Second Project Task</Name>
    <Type>Task Dependent</Type>
    <Status>Not Started</Status>
    <CalendarObjectId>CAL_5D</CalendarObjectId>
    <PlannedDuration>16</PlannedDuration>
    <RemainingDuration>16</RemainingDuration>
    <Start>2026-01-05T08:00:00</Start>
    <Finish>2026-01-06T17:00:00</Finish>
    <TotalFloat>0</TotalFloat>
    <FreeFloat>0</FreeFloat>
    <PercentComplete>0</PercentComplete>
  </Activity>
  <Activity>
    <ObjectId>B101</ObjectId>
    <ProjectObjectId>2</ProjectObjectId>
    <Id>B1010</Id>
    <Name>Second Project Milestone</Name>
    <Type>Finish Milestone</Type>
    <Status>Not Started</Status>
    <CalendarObjectId>CAL_5D</CalendarObjectId>
    <PlannedDuration>0</PlannedDuration>
    <RemainingDuration>0</RemainingDuration>
    <Start>2026-01-06T17:00:00</Start>
    <Finish>2026-01-06T17:00:00</Finish>
    <TotalFloat>0</TotalFloat>
    <FreeFloat>0</FreeFloat>
    <PercentComplete>0</PercentComplete>
  </Activity>
  <ActivityRelationship>
    <PredecessorActivityObjectId>B100</PredecessorActivityObjectId>
    <SuccessorActivityObjectId>B101</SuccessorActivityObjectId>
    <Type>Finish to Start</Type>
    <Lag>0</Lag>
  </ActivityRelationship>
  <ScheduleOptions>
    <ObjectId>SO2</ObjectId>
    <ProjectObjectId>2</ProjectObjectId>
    <SchedulingProgressedActivities>Progress Override</SchedulingProgressedActivities>
    <RelationshipLagCalendar>Successor Activity Calendar</RelationshipLagCalendar>
  </ScheduleOptions>
"""
    close_marker = "</APIBusinessObjects>"
    idx2 = out.index(close_marker)
    return out[:idx2] + extra_activities + out[idx2:]


def test_multi_project_file(tmp_path):
    p = tmp_path / "demo_p6_multi.xml"
    p.write_text(_two_project_variant(), encoding="utf-8")
    schedules = parse_p6xml(str(p))
    assert len(schedules) == 2
    by_id = {s.project_id: s for s in schedules}
    assert "P6-DEMO" in by_id and "P6-DEMO-2" in by_id
    first, second = by_id["P6-DEMO"], by_id["P6-DEMO-2"]
    assert len(first.activities) == 8               # unaffected by the second project
    assert len(second.activities) == 2
    assert len(second.relationships) == 1
    assert second.settings.progress_override is True
    assert second.settings.relationship_lag_calendar == "Successor Activity Calendar"
    # calendars are shared across projects in one export, like xer.py
    assert "CAL_5D" in second.calendars and "CAL_7D" in second.calendars


# --------------------------------------------------------------- parse_warnings path
def test_parse_warnings_non_fatal(tmp_path):
    """A malformed-but-well-formed-XML copy (unrecognized enum values, a
    relationship to a missing activity) must still parse, with warnings
    recorded rather than raised."""
    base = open(DEMO_P6, encoding="utf-8").read()
    malformed = base.replace("<Type>Level of Effort</Type>", "<Type>Bogus Activity Type</Type>")
    malformed = malformed.replace(
        "<Status>Not Started</Status>\n    <CalendarObjectId>CAL_7D</CalendarObjectId>",
        "<Status>Weird Status</Status>\n    <CalendarObjectId>CAL_7D</CalendarObjectId>",
    )
    malformed = malformed.replace(
        "<PredecessorActivityObjectId>A104</PredecessorActivityObjectId>\n"
        "    <SuccessorActivityObjectId>A105</SuccessorActivityObjectId>\n"
        "    <Type>Start to Finish</Type>",
        "<PredecessorActivityObjectId>A999_MISSING</PredecessorActivityObjectId>\n"
        "    <SuccessorActivityObjectId>A105</SuccessorActivityObjectId>\n"
        "    <Type>Start to Finish</Type>",
    )
    p = tmp_path / "demo_p6_malformed.xml"
    p.write_text(malformed, encoding="utf-8")
    schedules = parse_p6xml(str(p))                 # must not raise
    sched = schedules[0]
    assert sched.parse_warnings, "expected non-fatal warnings to be recorded"
    joined = " ".join(sched.parse_warnings)
    assert "Bogus Activity Type" in joined
    assert "Weird Status" in joined
    assert "A999_MISSING" in joined
    # the activity with the bad Type still parsed, defaulted to Task
    assert sched.activities["A106"].atype == ActivityType.TASK
    assert sched.activities["A104"].status == ActivityStatus.NOT_STARTED


# ------------------------------------------------------------------- round-trip smoke
def test_evaluate_runs_without_crash(demo):
    assessment = evaluate(demo)
    dcma_ids = [c for c in ("DCMA-01", "DCMA-02", "DCMA-05", "DCMA-06", "DCMA-08")]
    for cid in dcma_ids:
        r = assessment.result(cid)
        assert r is not None
        assert r.value is not None
        assert isinstance(r.value, (int, float))
    assert assessment.health_score is not None


def test_cpm_bridge_accepts_parsed_schedule(demo):
    ei = build_engine_inputs(demo)
    assert len(ei.activities) == len(demo.real_activities)
    assert len(ei.relationships) > 0


def test_handshake_degrades_not_crashes_on_handwritten_dates(demo):
    """demo_p6.xml's dates are hand-written, not CPM-derived, so the engine
    will not reproduce them exactly — the handshake must degrade gracefully
    (a low/zero match rate, never an exception)."""
    hs = run_handshake(demo)
    assert hs is not None
    assert hs.match_rate_pct is not None
    assert 0.0 <= hs.match_rate_pct <= 100.0
    r = evaluate(demo).result("SET-02")
    assert r is not None
    assert r.status != "NOT EVALUATED"
    assert r.value is not None


# --------------------------------------------------------------------------- F5: MPXJ
def test_pp_ppx_registered_in_dispatch():
    assert ".pp" in SUPPORTED
    assert ".ppx" in SUPPORTED


def test_f5_mpxj_extensions_route_through_bridge(tmp_path):
    """.pp / .ppx must resolve to the shared MPXJ bridge; skip when MPXJ/Java
    is unavailable (mirrors the optional-dependency guard pattern used for
    .mpp — MppSupportMissing / mpxj_available in scheduleiq.ingest.mpp)."""
    from scheduleiq.ingest.mpp import mpxj_available, MppSupportMissing
    if not mpxj_available():
        pytest.skip("MPXJ not installed in this environment (optional dependency)")
    for ext in (".pp", ".ppx"):
        p = tmp_path / f"fake{ext}"
        p.write_bytes(b"not a real project file")
        with pytest.raises((MppSupportMissing, ValueError)):
            load(str(p))


def test_f5_mpxj_missing_gives_actionable_message(tmp_path):
    """Without MPXJ installed (the case in this CI environment), .pp/.ppx must
    fail with the same clear, skip-not-crash guidance as .mpp — never a raw
    ImportError / stack trace."""
    from scheduleiq.ingest.mpp import mpxj_available
    if mpxj_available():
        pytest.skip("MPXJ is installed in this environment; nothing to degrade")
    from scheduleiq.ingest.mpp import MppSupportMissing
    p = tmp_path / "demo.pp"
    p.write_bytes(b"not a real project file")
    with pytest.raises(MppSupportMissing) as ei:
        load(str(p))
    assert "mpxj" in str(ei.value).lower()
