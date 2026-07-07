"""Tests for the v0.2 wave-1 checks (BACKLOG C1, C3, C5-C10): DAT-05, REL-01,
FLT-03 (single-file) and SET-01, CAL-04, LOG-10, DUR-04, STR-03 (series).

Seeded defects are documented in tests/fixtures/make_fixtures.py.  Each test
below asserts the check fires on its seeded defect, and that it is clean
(PASS/absent) on files where the defect was not seeded.
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load, load_many                     # noqa: E402
from scheduleiq.metrics.engine import evaluate                    # noqa: E402
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
def baseline_a():
    return evaluate(load(BASELINE)[0])


@pytest.fixture(scope="session")
def u1_a():
    return evaluate(load(U1)[0])


@pytest.fixture(scope="session")
def u2_a():
    return evaluate(load(U2)[0])


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


def res(assessment, cid):
    r = assessment.result(cid)
    assert r is not None, f"{cid} missing from results"
    return r


def series_res(series, cid):
    r = next((x for x in series.series_results if x.check.id == cid), None)
    assert r is not None, f"{cid} missing from series results"
    return r


# --------------------------------------------------------------- DAT-05 -----
def test_dat05_fires_on_update1(u1_a):
    r = res(u1_a, "DAT-05")
    assert r.status == "FAIL"
    finds = {f.object_id for f in r.findings}
    assert "A1010" in finds                    # seeded AF < AS


def test_dat05_clean_on_baseline_and_update2(baseline_a, u2_a):
    assert res(baseline_a, "DAT-05").value == 0
    assert res(baseline_a, "DAT-05").status == "PASS"
    assert res(u2_a, "DAT-05").value == 0


# --------------------------------------------------------------- REL-01 -----
def test_rel01_fires_on_update1(u1_a):
    r = res(u1_a, "REL-01")
    assert r.status == "WARNING"
    assert r.value == 1
    detail = " ".join(f.object_id for f in r.findings)
    assert "9999" in detail                    # seeded zombie predecessor


def test_rel01_clean_on_baseline_and_update2(baseline_a, u2_a):
    assert res(baseline_a, "REL-01").value == 0
    assert res(baseline_a, "REL-01").status == "PASS"
    assert res(u2_a, "REL-01").value == 0


# --------------------------------------------------------------- FLT-03 -----
def test_flt03_fires_on_update2(u2_a):
    r = res(u2_a, "FLT-03")
    assert r.status == "WARNING"
    finds = {f.object_id for f in r.findings}
    assert "A1180" in finds                    # seeded 400d float


def test_flt03_clean_on_baseline_and_update1(baseline_a, u1_a):
    assert res(baseline_a, "FLT-03").value == 0
    assert res(baseline_a, "FLT-03").status == "PASS"
    assert res(u1_a, "FLT-03").value == 0


# --------------------------------------------------------------- SET-01 -----
def test_set01_fires_on_settings_flip(series):
    r = series_res(series, "SET-01")
    assert r.status == "FAIL"
    assert r.value == 1
    detail = " ".join(f.detail for f in r.findings)
    assert "retained_logic" in detail
    assert "True -> False" in detail


# --------------------------------------------------------------- CAL-04 -----
def test_cal04_fires_on_holiday_added(series):
    r = series_res(series, "CAL-04")
    assert r.status == "INFO"
    assert r.value == 1
    detail = " ".join(f.detail for f in r.findings)
    assert "2025-07-04" in detail
    assert "holidays added" in detail


# --------------------------------------------------------------- LOG-10 -----
def test_log10_fires_on_inserted_stub(series):
    r = series_res(series, "LOG-10")
    assert r.status == "WARNING"
    assert r.value == 1
    finds = {f.object_id for f in r.findings}
    assert "A1215" in finds
    # the longer-duration added activity (A1210, 12d) must not qualify
    assert "A1210" not in finds


# --------------------------------------------------------------- DUR-04 -----
def test_dur04_branch2_fires_on_rd_compression(series):
    """Branch 2: RD collapsed without percent movement, Physical-% activity."""
    r = series_res(series, "DUR-04")
    assert r.status == "WARNING"
    finds = {f.object_id for f in r.findings}
    assert "A1070" in finds                    # seeded: 20% -> 20%, RD 192h -> 40h
    detail = next(f.detail for f in r.findings if f.object_id == "A1070")
    assert "branch 2" in detail


def test_dur04_duration_pct_activities_not_false_positives(series):
    """Duration-% activities making normal progress must NOT trip: their
    percent is derived from RD/OD, so branch 2 excludes them, and their RD
    consumption is within the working time elapsed, so branch 1 is silent."""
    r = series_res(series, "DUR-04")
    finds = {f.object_id for f in r.findings}
    assert "A1050" not in finds                # 30% -> 70%, Duration % (was a FP)
    assert "A1080" not in finds                # 40% -> 85%, Duration % (was a FP)


def test_dur04_branch1_impossible_consumption():
    """Branch 1 on synthetic in-memory schedules: RD dropping faster than
    working time passes between data dates trips regardless of percent type
    (both synthetic activities are Duration-%, which branch 2 ignores)."""
    from datetime import datetime

    from scheduleiq.ingest.model import (Activity, ActivityStatus, Calendar,
                                         PercentCompleteType, Schedule)

    def mk(dd, rd_map):
        s = Schedule(project_id="SYN", project_name="SYN", data_date=dd,
                     start_date=datetime(2025, 1, 6, 8, 0),
                     finish_date=datetime(2025, 12, 1, 17, 0))
        s.calendars["C1"] = Calendar(uid="C1", name="Std 5-Day",
                                     hours_per_day=8.0, is_default=True)
        for code, rd in rd_map.items():
            s.activities[code] = Activity(
                uid=code, code=code, name=f"Synthetic {code}",
                status=ActivityStatus.IN_PROGRESS, calendar_uid="C1",
                original_duration_hours=400.0, remaining_duration_hours=rd,
                pct_type=PercentCompleteType.DURATION,
                actual_start=datetime(2025, 5, 1, 8, 0))
        return s

    # one week between data dates (Mon 2025-06-02 -> Mon 2025-06-09):
    # 5 workdays x 8h = 40h available (+8h tolerance = 48h)
    earlier = mk(datetime(2025, 6, 2, 8, 0), {"S1": 200.0, "S2": 200.0})
    later = mk(datetime(2025, 6, 9, 8, 0), {"S1": 100.0, "S2": 170.0})
    sa = analyze_series([earlier, later])
    r = series_res(sa, "DUR-04")
    finds = {f.object_id for f in r.findings}
    assert "S1" in finds                       # 100h consumed > 48h -> impossible
    assert "S2" not in finds                   # 30h consumed <= 48h -> legitimate
    detail = next(f.detail for f in r.findings if f.object_id == "S1")
    assert "branch 1" in detail
    assert r.status == "WARNING"


# --------------------------------------------------------------- STR-03 -----
def test_str03_fires_on_wbs_move(series):
    r = series_res(series, "STR-03")
    assert r.status == "INFO"
    assert r.value == 1
    finds = {f.object_id for f in r.findings}
    assert "A1130" in finds
    detail = " ".join(f.detail for f in r.findings)
    assert "MECH" in detail and "CIV" in detail


# ------------------------------------------------------------ matrix rows ---
def test_new_checks_registered_in_matrix():
    from scheduleiq.metrics.engine import load_matrix
    ids = {c.id for c in load_matrix()}
    for cid in ("DAT-05", "REL-01", "FLT-03", "SET-01", "CAL-04", "LOG-10",
                "DUR-04", "STR-03"):
        assert cid in ids


def test_all_non_series_checks_still_implemented(baseline_a):
    unimplemented = [r.check.id for r in baseline_a.results
                     if r.status == "NOT EVALUATED"]
    assert unimplemented == []
