"""End-to-end and per-check tests against the seeded-defect fixtures.

Fixture defects are documented in tests/fixtures/make_fixtures.py; every
assertion here maps to a seeded defect, so a failing test means either a
check regression or an (intentional) fixture change.
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load, load_many                     # noqa: E402
from scheduleiq.metrics.engine import evaluate, load_matrix       # noqa: E402
from scheduleiq.trend.series import analyze_series                # noqa: E402

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
def assessment(baseline):
    return evaluate(baseline)


def res(assessment, cid):
    r = assessment.result(cid)
    assert r is not None, f"{cid} missing from results"
    return r


# ------------------------------------------------------------------ parsing
def test_parse_shape(baseline):
    assert baseline.project_id == "DEMO-PLANT"
    assert len(baseline.activities) == 21
    assert len(baseline.real_activities) == 20          # LOE excluded
    assert len(baseline.relationships) == 23
    assert baseline.data_date is not None


def test_calendar_parsing(baseline):
    c5 = baseline.calendars["100"]
    assert c5.workdays_per_week == 5
    assert c5.hours_per_day == 8.0
    assert len(c5.exceptions_nonwork) == 1              # New Year holiday
    c7 = baseline.calendars["101"]
    assert c7.workdays_per_week == 7
    assert c7.hours_per_day == 10.0


def test_matrix_integrity():
    matrix = load_matrix()
    assert len(matrix) >= 50
    ids = [c.id for c in matrix]
    assert len(ids) == len(set(ids)), "duplicate check IDs"
    for c in matrix:
        assert c.references, f"{c.id} has no literature reference"
        assert c.direction in ("max", "min", "info")
    assert sum(1 for c in matrix
               if c.category == "DCMA 14-Point Assessment") == 14


def test_all_non_series_checks_implemented(assessment):
    unimplemented = [r.check.id for r in assessment.results
                     if r.status == "NOT EVALUATED"]
    assert unimplemented == [], f"unimplemented checks: {unimplemented}"


# --------------------------------------------------------------- DCMA checks
def test_dcma01_open_ends(assessment):
    r = res(assessment, "DCMA-01")
    finds = {f.object_id for f in r.findings}
    assert "A1190" in finds                    # orphan both ways
    assert "A1180" in finds                    # no successor


def test_dcma02_leads(assessment):
    r = res(assessment, "DCMA-02")
    assert r.numerator == 1                    # 1050->1070 lead
    assert r.status == "FAIL"


def test_dcma05_hard_constraints(assessment):
    r = res(assessment, "DCMA-05")
    finds = {f.object_id for f in r.findings}
    assert "A1200" in finds                    # Mandatory Finish
    assert "A1080" not in finds                # SNET is soft


def test_dcma06_high_float(assessment):
    finds = {f.object_id for f in res(assessment, "DCMA-06").findings}
    assert {"A1190", "A1080"} <= finds         # 90d and 55d float


def test_dcma08_high_duration(assessment):
    finds = {f.object_id for f in res(assessment, "DCMA-08").findings}
    assert "A1080" in finds                    # 60d procurement


def test_dcma09_baseline_clean(assessment):
    assert res(assessment, "DCMA-09").value == 0   # baseline has no progress


# ------------------------------------------------------- logic and integrity
def test_log03_sf(assessment):
    assert res(assessment, "LOG-03").value == 1


def test_log04_duplicates(assessment):
    r = res(assessment, "LOG-04")
    assert r.value >= 1                        # 1150->1160 FS+FF (and SF pair)


def test_res01_milestone_resources(assessment):
    finds = {f.object_id for f in res(assessment, "RES-01").findings}
    assert "MS-100" in finds


def test_update1_seeded_defects():
    a = evaluate(load(U1)[0])
    inv = {f.object_id for f in res(a, "DCMA-09").findings}
    assert "A1020" in inv                      # actual finish after DD
    dat = {f.object_id for f in res(a, "DAT-01").findings}
    assert "A1050" in dat                      # in progress, no actual start
    assert res(a, "DCMA-07").numerator >= 1    # negative float seeded
    oos = res(a, "LOG-07")
    assert oos.value >= 1                      # out-of-sequence progress


# -------------------------------------------------------------- series/trend
@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


def test_series_order_and_health(series):
    dds = [s.data_date for s in series.schedules]
    assert dds == sorted(dds)
    scores = [a.health_score for a in series.assessments]
    assert scores[0] > scores[-1]              # quality degrades as seeded


def test_series_retroactive_actuals(series):
    r = next(x for x in series.series_results if x.check.id == "TRD-05")
    assert r.status == "FAIL"
    assert any(f.object_id == "A1010" for f in r.findings)  # seeded rewrite


def test_series_scope_churn(series):
    r = next(x for x in series.series_results if x.check.id == "TRD-07")
    ids = " ".join(f.detail for f in r.findings)
    assert "A1210" in ids and "MS-200" in ids  # added
    assert r.value >= 3                        # 2 added + 1 deleted


def test_series_duration_change(series):
    r = next(x for x in series.series_results if x.check.id == "TRD-06")
    assert any(f.object_id == "A1020" for f in r.findings)  # 15d -> 12d


def test_changeset_logic_adds(series):
    cs = series.changesets[1]
    added = {(c.pred_code, c.succ_code) for c in cs.logic_changes
             if c.kind == "added"}
    assert ("A1210", "A1060") in added


# ------------------------------------------------------------------ outputs
def test_outputs(tmp_path, series):
    from scheduleiq.report.excel import (write_assessment_workbook,
                                         write_trend_workbook)
    from scheduleiq.report.report_builder import build_series_report
    xlsx = write_assessment_workbook(series.assessments[-1],
                                     str(tmp_path / "results.xlsx"))
    assert os.path.getsize(xlsx) > 5000
    trend = write_trend_workbook(series, str(tmp_path / "trend.xlsx"))
    assert os.path.getsize(trend) > 5000
    docx = build_series_report(series, str(tmp_path / "report.docx"))
    assert os.path.getsize(docx) > 100000      # includes template + figures
    import xml.dom.minidom
    import zipfile
    with zipfile.ZipFile(docx) as z:
        assert z.testzip() is None
        xml.dom.minidom.parseString(z.read("word/document.xml"))
        xml.dom.minidom.parseString(z.read("word/footnotes.xml"))
        assert len([n for n in z.namelist()
                    if n.startswith("word/media/zfig")]) == 4


def test_cli_end_to_end(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "scheduleiq.cli", "analyze",
         BASELINE, U1, U2, "-o", str(tmp_path / "out"), "--no-pdf"],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": SRC})
    assert out.returncode == 0, out.stderr
    assert (tmp_path / "out" / "schedule_assessment.docx").exists()
    assert (tmp_path / "out" / "trend_analysis.xlsx").exists()
    assert (tmp_path / "out" / "audit" / "audit_log.jsonl").exists()


def test_audit_log(tmp_path):
    from scheduleiq.runner import run
    rr = run([BASELINE], str(tmp_path), make_pdf=False)
    import json
    log = tmp_path / "audit" / "audit_log.jsonl"
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["tool"] == "scheduleiq"
    assert rec["inputs"][0]["sha256"]
    assert rec["summary"]["schedules"] == 1
    assert rr.outputs
