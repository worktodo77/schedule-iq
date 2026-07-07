"""Tests for the intake-accelerator pack (backlog D1-D8).

Uses the existing synthetic fixture series (tests/fixtures/make_fixtures.py,
not edited here): a baseline (DD 2025-01-06, no progress) and two updates
(DD 2025-04-07 and 2025-07-07) at an even ~91-day (~3-month) cadence, with
seeded defects including SET-01 settings drift, CAL-04 calendar changes,
STR-03 WBS re-parenting, added/deleted activities, and float erosion —
exactly the kind of series the accelerators are meant to chew on.  Every
accelerator must degrade gracefully rather than raise, so the empty/None-
input paths are exercised as well as the fixture-driven ones.
"""
import csv
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load_many                            # noqa: E402
from scheduleiq.trend.series import SeriesAnalysis, analyze_series  # noqa: E402
from scheduleiq.intake import run_intake, IntakeResults             # noqa: E402
from scheduleiq.intake.scorecard import build_scorecard, rfi_lines  # noqa: E402
from scheduleiq.intake.variance import build_variance_register      # noqa: E402
from scheduleiq.intake.float_ledger import build_float_ledger       # noqa: E402
from scheduleiq.intake.windows import propose_windows               # noqa: E402
from scheduleiq.intake.concurrency import screen_concurrency        # noqa: E402
from scheduleiq.intake.events import map_events                     # noqa: E402
from scheduleiq.intake.responsibility import run_responsibility     # noqa: E402
from scheduleiq.intake.evergreen import find_evergreen_activities   # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")
EVENTS_CSV = os.path.join(FIX, "events_sample.csv")
RESP_CSV = os.path.join(FIX, "responsibility_sample.csv")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not os.path.exists(BASELINE):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


# --------------------------------------------------------------------- D1
def test_scorecard_cadence_and_files(series):
    sc = build_scorecard(series)
    assert sc.n_files == 3
    assert sc.reason == ""
    # baseline (Jan 6) -> update1 (Apr 7) -> update2 (Jul 7): 91 days each way
    assert sc.intervals_days == [91, 91]
    assert sc.dominant_cadence_days == 91
    assert "month" in sc.cadence_label
    assert "3" in sc.cadence_label
    # baseline carries no progress -> a clean native baseline
    assert sc.baseline_has_progress is False
    assert len(sc.files) == 3
    assert all(f.has_schedoptions for f in sc.files)   # every fixture writes SCHEDOPTIONS


def test_scorecard_rfi_list_generated(series):
    sc = build_scorecard(series)
    lines = rfi_lines(sc)
    assert isinstance(lines, list)
    # not every fixture defect trips every RFI, but resource loading is
    # deliberately sparse in the fixtures (make_fixtures.py TASKRSRC has
    # only 4 rows) so at least one RFI line must be generated
    assert lines, "expected at least one RFI line from the sparsely-resourced fixtures"
    assert all(isinstance(l, str) and l for l in lines)


def test_scorecard_empty_series_never_raises():
    sc = build_scorecard(SeriesAnalysis(schedules=[]))
    assert sc.reason
    assert sc.files == []
    assert rfi_lines(sc) == []


# --------------------------------------------------------------------- D2
def test_variance_register_nonempty_and_sorted(series):
    vr = build_variance_register(series)
    assert vr.reason == ""
    assert vr.rows, "expected a nonempty variance register"
    finish_vars = [abs(r.finish_variance_days) for r in vr.rows
                  if r.finish_variance_days is not None]
    assert finish_vars == sorted(finish_vars, reverse=True)
    # driving-path membership is a real boolean, not always False
    assert any(r.on_driving_path for r in vr.rows)


def test_variance_register_single_file_degrades():
    from scheduleiq.ingest import load
    vr = build_variance_register(SeriesAnalysis(schedules=load(BASELINE)))
    assert vr.rows == []
    assert vr.reason


# --------------------------------------------------------------------- D3
def test_float_ledger_runs(series):
    fl = build_float_ledger(series)
    assert fl.rows, "expected per-activity float-delta rows"
    assert fl.by_wbs
    assert fl.by_band
    assert len(fl.erosion_by_window) == 3
    # bands used are drawn from the documented band vocabulary
    bands = {r.band for r in fl.rows}
    assert bands <= {"critical (<=0d)", "0-5d", "5-10d", "10-20d", ">20d"}


# --------------------------------------------------------------------- D4
def test_windows_proposal_has_boundary_with_reason(series):
    wp = propose_windows(series)
    assert wp.reason == ""
    assert len(wp.boundaries) >= 1
    for b in wp.boundaries:
        assert b.kept_reason
        assert b.labels


def test_windows_proposal_degrades_on_single_file():
    from scheduleiq.ingest import load
    wp = propose_windows(SeriesAnalysis(schedules=load(BASELINE)))
    assert wp.boundaries == []
    assert wp.reason


# --------------------------------------------------------------------- D5
def test_concurrency_screen_never_raises(series):
    cc = screen_concurrency(series)
    assert isinstance(cc.candidates, list)
    assert cc.caption == "concurrency candidates — preliminary, for expert review"
    for c in cc.candidates:
        assert c.path_a_codes and c.path_b_codes
        assert set(c.path_a_codes) != set(c.path_b_codes)


# --------------------------------------------------------------------- D6
def test_event_mapper_matches_foundations(series):
    result = map_events(series, EVENTS_CSV)
    assert result.reason == ""
    assert len(result.events) == 2
    ev1 = next(e for e in result.events if e.event_id == "EV-1")
    ev2 = next(e for e in result.events if e.event_id == "EV-2")
    foundation_matches = [m for m in ev1.matches if "foundations" in m.activity_name.lower()]
    assert len(foundation_matches) >= 1, "EV-1 (Foundations keyword) must map to >= 1 activity"
    assert ev2.matches == [], "EV-2 predates the project and shares no keywords"


def test_event_mapper_no_csv_degrades(series):
    result = map_events(series, None)
    assert result.events == []
    assert result.reason


# --------------------------------------------------------------------- D7
def test_responsibility_tagging_assigns_parties(series):
    result = run_responsibility(series, RESP_CSV)
    assert result.reason == ""
    parties = set(result.tags_by_code.values())
    assert "Contractor" in parties      # CIV wbs
    assert "Owner" in parties           # PROC wbs
    assert result.caption == "responsibility aggregation only — entitlement reserved to the expert"
    assert result.by_activity
    assert result.aggregates


def test_responsibility_no_csv_degrades(series):
    result = run_responsibility(series, None)
    assert result.tags_by_code == {}
    assert result.reason


# --------------------------------------------------------------------- D8
def test_evergreen_returns_list_without_raising(series):
    eg = find_evergreen_activities(series)
    assert isinstance(eg.activities, list)
    for a in eg.activities:
        assert len(a.history) >= 3
        assert a.pct_increase_total > 0


def test_evergreen_degrades_on_short_series():
    from scheduleiq.ingest import load
    eg = find_evergreen_activities(SeriesAnalysis(schedules=load(BASELINE)))
    assert eg.activities == []
    assert eg.reason


# --------------------------------------------------------------- bundling
def test_run_intake_bundles_all_eight(series):
    ir = run_intake(series, events_csv=EVENTS_CSV, responsibility_csv=RESP_CSV)
    assert isinstance(ir, IntakeResults)
    assert ir.scorecard.n_files == 3
    assert ir.variance.rows
    assert ir.float_ledger.rows
    assert ir.windows.boundaries
    assert ir.events.events
    assert ir.responsibility.by_activity
    assert isinstance(ir.evergreen.activities, list)


def test_run_intake_never_raises_on_empty_series():
    ir = run_intake(SeriesAnalysis(schedules=[]))
    assert ir.scorecard.reason
    assert ir.variance.reason
    assert ir.windows.reason


# ------------------------------------------------------------------ outputs
def test_intake_workbook_builds(tmp_path, series):
    from scheduleiq.report.excel_intake import write_intake_workbook
    ir = run_intake(series, events_csv=EVENTS_CSV, responsibility_csv=RESP_CSV)
    xlsx = write_intake_workbook(series, ir, str(tmp_path / "intake_review.xlsx"))
    assert os.path.getsize(xlsx) > 4000
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    assert {"Scorecard", "Variance", "Float Ledger", "Windows", "Concurrency",
            "Events", "Responsibility", "Evergreen"} <= set(wb.sheetnames)


def test_intake_blocks_build(series):
    from scheduleiq.report.intake_report import intake_blocks
    from scheduleiq.intake import run_intake as _run_intake
    ir = _run_intake(series, events_csv=EVENTS_CSV, responsibility_csv=RESP_CSV)
    blocks = intake_blocks(series, ir)
    assert blocks[0] == {"type": "h2", "text": "INTAKE REVIEW"}
    assert any(b["type"] == "table" for b in blocks)


def test_series_report_includes_intake_review(tmp_path, series):
    from scheduleiq.report.report_builder import build_series_report
    import zipfile
    docx = build_series_report(series, str(tmp_path / "report.docx"))
    with zipfile.ZipFile(docx) as z:
        assert z.testzip() is None
        doc = z.read("word/document.xml").decode("utf-8")
    assert "INTAKE REVIEW" in doc


def test_runner_writes_intake_review_xlsx(tmp_path):
    from scheduleiq.runner import run
    out_dir = str(tmp_path / "out")
    rr = run([BASELINE, U1, U2], out_dir, make_pdf=False,
             events_csv=EVENTS_CSV, responsibility_csv=RESP_CSV,
             progress=lambda m: None)
    assert any(os.path.basename(p) == "intake_review.xlsx" for p in rr.outputs)
    assert os.path.exists(os.path.join(out_dir, "intake_review.xlsx"))


# ---------------------------------------------------------------- fixture CSVs
def test_fixture_csvs_are_well_formed():
    with open(EVENTS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {"event_id", "title", "start", "finish", "keywords", "responsibility"} \
        <= set(rows[0].keys())

    with open(RESP_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {"pattern", "scope", "party"} <= set(rows[0].keys())


def test_evergreen_flags_only_rd_lag(series):
    """Healthy progressing activities (RD keeping up with pct) are NOT
    evergreen; a synthetic pct-creep activity with static RD IS."""
    from datetime import datetime
    from scheduleiq.ingest.model import Activity, ActivityStatus, Schedule
    from scheduleiq.trend.series import SeriesAnalysis

    eg = find_evergreen_activities(series)
    assert [e.code for e in eg.activities] == []   # fixtures progress honestly

    def sched(dd, pct):
        s = Schedule(project_id="SYN", data_date=dd)
        a = Activity(uid="1", code="SYN-1", name="Creeper",
                     status=ActivityStatus.IN_PROGRESS,
                     original_duration_hours=200.0,
                     remaining_duration_hours=180.0,   # never moves
                     pct_complete=pct,
                     early_finish=datetime(2025, 12, 1))
        s.activities["1"] = a
        return s

    syn = SeriesAnalysis(schedules=[sched(datetime(2025, 1, 6), 10),
                                    sched(datetime(2025, 2, 3), 30),
                                    sched(datetime(2025, 3, 3), 55)])
    eg = find_evergreen_activities(syn)
    assert [e.code for e in eg.activities] == ["SYN-1"]
    assert eg.activities[0].pct_increase_total == 45
