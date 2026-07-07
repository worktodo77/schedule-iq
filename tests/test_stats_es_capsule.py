"""Tests for the v0.2 wave-2 analytics (BACKLOG S1, S3, N5, C4): statistical
manipulation screens, earned-schedule forecast credibility, the CAL-05
multi-calendar float-distortion check, and the reproducibility capsule.

Uses the existing three-update fixture series (tests/fixtures/make_fixtures.py
is not modified for this wave).
"""
import json
import math
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load, load_many                          # noqa: E402
from scheduleiq.metrics.engine import evaluate                         # noqa: E402
from scheduleiq.trend.series import analyze_series                     # noqa: E402
from scheduleiq.analytics.statistical import (benford_screen,          # noqa: E402
                                              distribution_drift,
                                              ks_distance, progress_physics,
                                              run_stats)
from scheduleiq.analytics.earned_schedule import earned_schedule       # noqa: E402

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


# ------------------------------------------------------------- S1 Benford
def test_benford_distributions_sum_to_100(series):
    results = benford_screen(series.schedules)
    assert len(results) == 3
    for b in results:
        assert b.n_durations > 0
        assert math.isclose(sum(b.first_digit_pct.values()), 100.0, abs_tol=0.5)
        assert math.isclose(sum(b.last_digit_pct.values()), 100.0, abs_tol=0.5)
        assert math.isclose(sum(b.first_digit_expected_pct.values()), 100.0, abs_tol=0.5)
        assert math.isclose(sum(b.last_digit_expected_pct.values()), 100.0, abs_tol=0.5)
        assert b.chi2_first_digit is not None and b.chi2_first_digit >= 0
        assert b.chi2_last_digit is not None and b.chi2_last_digit >= 0
        assert "not proof of manipulation" in b.caution


def test_round_number_concentration_is_high_on_fixtures(baseline):
    b = benford_screen([baseline])[0]
    # the fixture's activity durations are seeded as 5-day multiples
    assert b.round5_pct > 50.0


def test_benford_empty_schedule_never_raises():
    from scheduleiq.ingest.model import Schedule
    results = benford_screen([Schedule(project_id="EMPTY")])
    assert len(results) == 1
    assert results[0].reason


# ------------------------------------------------------- S1 distribution drift
def test_ks_distance_in_unit_interval(series):
    drift = distribution_drift(series)
    assert len(drift) == len(series.schedules) - 1
    for d in drift:
        if d.ks_common is not None:
            assert 0.0 <= d.ks_common <= 1.0
        if d.ks_added is not None:
            assert 0.0 <= d.ks_added <= 1.0
        assert d.narrative


def test_ks_distance_manual_known_values():
    # identical samples -> distance 0
    assert ks_distance([1, 2, 3], [1, 2, 3]) == 0.0
    # fully separated samples -> distance 1
    assert ks_distance([1, 2, 3], [10, 11, 12]) == 1.0
    # empty sample -> undefined
    assert ks_distance([], [1, 2]) is None


# ------------------------------------------------------------ S1 progress physics
def test_progress_physics_runs_and_never_raises(series):
    phys = progress_physics(series)
    assert isinstance(phys.rates, list)
    assert isinstance(phys.findings, list)
    assert phys.narrative
    assert "not proof of manipulation" in phys.caution


def test_run_stats_bundle(series):
    bundle = run_stats(series)
    assert set(bundle) == {"benford", "drift", "physics"}
    assert len(bundle["benford"]) == 3


# ------------------------------------------------------------------ S3 earned schedule
def test_earned_schedule_one_row_per_update(series):
    es = earned_schedule(series)
    assert es.reason == ""
    assert es.basis in ("cost", "count")
    assert len(es.points) == len(series.schedules) - 1
    for p in es.points:
        assert p.spi_t is not None and p.spi_t > 0
        assert p.ieac_days is not None and math.isfinite(p.ieac_days)
        assert p.interpretation


def test_earned_schedule_needs_two_schedules(baseline):
    from scheduleiq.trend.series import SeriesAnalysis
    es = earned_schedule(SeriesAnalysis(schedules=[baseline]))
    assert es.reason
    assert es.points == []


# --------------------------------------------------------------------- C4 CAL-05
def test_cal05_value_on_fixtures(baseline):
    from scheduleiq.metrics.engine import load_matrix
    matrix = load_matrix()
    cd = next(c for c in matrix if c.id == "CAL-05")
    a = evaluate(baseline, matrix)
    res = a.result("CAL-05")
    assert res is not None
    assert res.status != "NOT EVALUATED"
    if res.status != "N/A":
        assert res.value is not None and res.value >= 0.0


def test_cal05_na_gracefully_on_empty_schedule():
    from scheduleiq.ingest.model import Schedule
    from scheduleiq.metrics.engine import load_matrix
    matrix = load_matrix()
    a = evaluate(Schedule(project_id="EMPTY"), matrix)
    res = a.result("CAL-05")
    assert res.status == "N/A"


# -------------------------------------------------------------------- N5 capsule
def test_capsule_built_by_runner(tmp_path):
    from scheduleiq import runner
    out_dir = str(tmp_path / "out")
    rr = runner.run([BASELINE, U1, U2], out_dir, make_pdf=False,
                    progress=lambda m: None)
    assert not any("capsule" in m.lower() and "skipped" in m.lower()
                  for m in rr.messages), rr.messages

    manifest_path = os.path.join(out_dir, "capsule", "manifest.json")
    rerun_path = os.path.join(out_dir, "capsule", "rerun.py")
    readme_path = os.path.join(out_dir, "capsule", "README.txt")
    assert os.path.exists(manifest_path)
    assert os.path.exists(rerun_path)
    assert os.path.exists(readme_path)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["tool"] == "scheduleiq"
    assert manifest["matrix_yaml_sha256"]
    assert manifest["outputs"], "manifest should list at least one output artifact"

    import hashlib

    def sha256_file(path):
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    for entry in manifest["outputs"]:
        full = os.path.join(out_dir, entry["path"])
        assert os.path.exists(full), f"missing manifest-listed output {entry['path']}"
        assert sha256_file(full) == entry["sha256"], \
            f"hash mismatch for {entry['path']}"

    # audit trail is recorded separately, not folded into the verified outputs
    assert manifest["audit_trail"]
    assert all("audit" in e["path"] for e in manifest["audit_trail"])
