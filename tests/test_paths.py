"""Tests for the path-analytics module (backlog A1, P1-P4).

Assertions map to the fixture's intended critical chain (documented in
tests/fixtures/make_fixtures.py): the driving path must reach the substantial-
completion milestone MS-100, the top-N float paths must lead with the least-
float path, merge ranking and stability must run, and the Excel workbook and
report blocks must build.  Graceful degradation on empty schedules is checked
so path analysis can never raise into a run.
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load, load_many                     # noqa: E402
from scheduleiq.ingest.model import Schedule                      # noqa: E402
from scheduleiq.trend.series import analyze_series                # noqa: E402
from scheduleiq.analytics.paths import (driving_path, float_paths,  # noqa: E402
                                        merge_ranking, path_stability,
                                        proximity_profile,
                                        run_path_analytics)

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
def baseline():
    return load(BASELINE)[0]


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


# ------------------------------------------------------------- A1 driving path
def test_driving_path_reaches_completion(baseline):
    dp = driving_path(baseline)
    assert dp.reason == ""
    assert dp.target is not None and dp.target.code == "MS-100"
    assert dp.steps, "driving path is empty"
    # ordered start -> target, ending at the substantial-completion milestone
    assert dp.codes[-1] == "MS-100"
    assert dp.codes[0] == "MS-000"
    # every non-target step carries the relationship driving the next step
    assert all(s.driving_rel is not None for s in dp.steps[:-1])
    assert dp.steps[-1].driving_rel is None


def test_driving_path_is_zero_float_chain(baseline):
    """Float governs the walk: the zero-float chain through A1110/A1120 must be
    the driving path; the 5d-float A1130 branch must not be claimed as driving."""
    dp = driving_path(baseline)
    assert "A1110" in dp.codes
    assert "A1120" in dp.codes
    assert "A1130" not in dp.codes
    for s in dp.steps:
        assert s.total_float_days is not None and s.total_float_days <= 0, \
            f"{s.code} has float {s.total_float_days}d on the driving path"


def test_driving_path_explicit_target(baseline):
    dp = driving_path(baseline, target_uid="MS-100")
    assert dp.codes[-1] == "MS-100"
    assert len(dp.steps) >= 5


def test_driving_path_carries_calendar_and_float(baseline):
    dp = driving_path(baseline)
    # the odd 7-day calendar activity A1090 is on the driving path
    assert "A1090" in dp.codes
    step = next(s for s in dp.steps if s.code == "A1090")
    assert step.calendar_name
    assert step.total_float_days is not None


# ------------------------------------------------------------- P1 float paths
def test_float_paths_min_first(baseline):
    fps = float_paths(baseline, n=10)
    assert len(fps) >= 2
    assert fps[0].rank == 1
    # the leading path is the least-relative-float path
    assert fps[0].rel_float_days == min(p.rel_float_days for p in fps)
    # paths are distinct
    sigs = {tuple(p.codes) for p in fps}
    assert len(sigs) == len(fps)
    # activities convenience property mirrors steps
    for p in fps:
        assert [a.code for a in p.activities] == p.codes
    # the leading path is the driving path and reaches the target
    assert fps[0].codes[-1] == "MS-100"


def test_float_paths_band(baseline):
    tight = float_paths(baseline, n=10, band_days=1.0)
    wide = float_paths(baseline, n=10, band_days=100.0)
    assert len(tight) <= len(wide)


# ------------------------------------------------------------- P2 proximity
def test_proximity_profile(baseline):
    prof = proximity_profile(baseline, bands=(5, 10, 20))
    assert prof["target"] == "MS-100"
    assert set(prof["bands"]) == {5, 10, 20}
    # wider bands never contain fewer paths than tighter bands
    p5 = prof["bands"][5]["paths"]
    p20 = prof["bands"][20]["paths"]
    assert p20 >= p5 >= 1


# ------------------------------------------------------------- P3 merge ranking
def test_merge_ranking_runs(baseline):
    merges = merge_ranking(baseline, near_days=10)
    assert merges, "expected at least one near-critical merge point"
    # ranked by converging-chain count (desc)
    counts = [m.converging_chains for m in merges]
    assert counts == sorted(counts, reverse=True)
    assert all(m.converging_chains >= 2 for m in merges)
    assert all(m.tightness_days is not None for m in merges)


# ------------------------------------------------------------- P4 stability
def test_path_stability_one_per_pair(series):
    stab = path_stability(series)
    assert len(stab) == len(series.schedules) - 1     # one entry per update pair
    for p in stab:
        assert p.jaccard is None or 0.0 <= p.jaccard <= 1.0
        assert isinstance(p.causes, list)


# ------------------------------------------------------- graceful degradation
def test_empty_schedule_never_raises():
    empty = Schedule(project_id="EMPTY")
    assert driving_path(empty).steps == []
    assert driving_path(empty).reason
    assert float_paths(empty) == []
    assert merge_ranking(empty) == []
    assert proximity_profile(empty)["bands"] == {}
    from scheduleiq.trend.series import SeriesAnalysis
    assert path_stability(SeriesAnalysis(schedules=[empty])) == []


# ------------------------------------------------------------------ outputs
def test_paths_workbook_and_blocks_build(tmp_path, series):
    from scheduleiq.report.excel_paths import write_paths_workbook
    from scheduleiq.report.paths_report import path_blocks
    pr = run_path_analytics(series)
    xlsx = write_paths_workbook(series, pr, str(tmp_path / "path_analysis.xlsx"))
    assert os.path.getsize(xlsx) > 4000
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    assert {"Driving Path", "Float Paths", "Merge Points",
            "Path Stability"} <= set(wb.sheetnames)
    blocks = path_blocks(series, pr)
    assert blocks[0] == {"type": "h2", "text": "MULTI-PATH ANALYSIS"}
    assert any(b["type"] == "table" for b in blocks)


def test_series_report_includes_paths(tmp_path, series):
    from scheduleiq.report.report_builder import build_series_report
    import zipfile
    docx = build_series_report(series, str(tmp_path / "report.docx"))
    with zipfile.ZipFile(docx) as z:
        assert z.testzip() is None
        doc = z.read("word/document.xml").decode("utf-8")
    assert "MULTI-PATH ANALYSIS" in doc
