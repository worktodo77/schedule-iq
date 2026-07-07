"""Tests for the ADR-0007 validation handshake and check SET-02.

demo_cpm.xer is a CPM-consistent fixture whose stored tool-of-record values were
produced by the ported engine (see tests/fixtures/make_fixtures.py), so it
handshakes at 100%.  demo_cpm_divergent.xer shifts exactly three activities'
stored dates, so it lands at a deterministic 75%.  The old demo_baseline.xer is
known CPM-inconsistent and must degrade gracefully (not error).
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load                                    # noqa: E402
from scheduleiq.metrics.engine import evaluate, load_matrix           # noqa: E402
from scheduleiq.cpm.handshake import (HandshakeRefusal, build_reference,  # noqa: E402
                                     require_valid_handshake, run_handshake)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
CPM = os.path.join(FIX, "demo_cpm.xer")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")
BASELINE = os.path.join(FIX, "demo_baseline.xer")

# The three activities whose stored dates are corrupted in the divergent file.
SEEDED = {"A60", "A90", "A100"}


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(CPM) and os.path.exists(CPM_DIV)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def cpm_sched():
    return load(CPM)[0]


@pytest.fixture(scope="session")
def div_sched():
    return load(CPM_DIV)[0]


# ------------------------------------------------------------- handshake core
def test_handshake_clean_is_100_and_passes(cpm_sched):
    hs = run_handshake(cpm_sched)
    assert hs.match_rate_pct == 100.0
    assert hs.passed is True
    assert hs.engine_is_valid is True
    assert hs.total_activities == 12
    assert hs.within_tolerance == 12
    assert hs.divergent == 0
    assert hs.constraint_applications == 2          # one SNET + one FNLT
    assert hs.lag_strategy == "predecessor_calendar"
    assert hs.statusing_mode == "retained_logic"
    assert hs.convention == "p6_compatibility"
    assert hs.tolerance_policy == "CALENDAR_AWARE"  # LIM-044: calendar-day tolerance
    assert hs.disclosures                           # disclosures are populated


def test_handshake_divergent_is_exactly_75_and_names_seeded(div_sched):
    hs = run_handshake(div_sched)
    assert hs.match_rate_pct == 75.0                # (12 - 3) / 12 * 100, exact
    assert hs.passed is False
    assert hs.divergent == 3
    codes = {m["code"] for m in hs.mismatches}
    assert SEEDED <= codes
    # every seeded mismatch is a date field out by the +5-workday shift
    fields = {m["field"] for m in hs.mismatches if m["code"] in SEEDED}
    assert fields <= {"early_start", "early_finish", "late_start", "late_finish"}


def test_handshake_result_serializable(cpm_sched):
    d = run_handshake(cpm_sched).to_dict()
    assert d["match_rate_pct"] == 100.0 and d["passed"] is True
    assert set(d) >= {"match_rate_pct", "threshold_pct", "passed", "mismatches",
                     "disclosures", "constraint_applications", "engine_is_valid"}


# --------------------------------------------------------------- caching
def test_run_handshake_is_cached(cpm_sched):
    a = run_handshake(cpm_sched)
    b = run_handshake(cpm_sched)
    assert a is b                                    # cached object, engine ran once


# ------------------------------------------------------ require_valid gate
def test_require_valid_returns_on_clean(cpm_sched):
    hs = require_valid_handshake(cpm_sched)
    assert hs.passed is True


def test_require_valid_raises_on_divergent(div_sched):
    with pytest.raises(HandshakeRefusal):
        require_valid_handshake(div_sched)


# ------------------------------------------------------ build_reference
def test_build_reference_provenance_and_population(cpm_sched):
    ref = build_reference(cpm_sched)
    assert len(ref.activities) == 12                 # real activities only
    assert ref.source == "schedule of record (XER)"
    assert ref.tool == cpm_sched.source_tool


# --------------------------------------------------------------- SET-02 check
def test_set02_pass_on_clean(cpm_sched):
    r = evaluate(cpm_sched).result("SET-02")
    assert r is not None
    assert r.status == "PASS"
    assert r.value == 100.0


def test_set02_warns_on_divergent_naming_seeded(div_sched):
    r = evaluate(div_sched).result("SET-02")
    # severity is info, direction min: below-threshold -> WARNING (not FAIL)
    assert r.status == "WARNING"
    assert r.value == 75.0
    assert SEEDED <= {f.object_id for f in r.findings}


def test_set02_degrades_gracefully_on_legacy_baseline():
    """The old fixtures are known CPM-inconsistent; SET-02 must not crash — it
    returns a graded MetricResult with a numeric value (the invalid-network
    handshake fails at 0.0 with the blocking issues listed)."""
    r = evaluate(load(BASELINE)[0]).result("SET-02")
    assert r is not None
    assert r.status != "NOT EVALUATED"
    assert r.value is not None
    assert r.status in ("PASS", "WARNING", "FAIL")


# --------------------------------------------------------------- matrix wiring
def test_set02_in_matrix_and_implemented(cpm_sched):
    assert "SET-02" in {c.id for c in load_matrix()}
    # spirit of test_all_non_series_checks_still_implemented, asserted here so
    # the shared test file is not edited: SET-02 is implemented, not skipped.
    unimplemented = [res.check.id for res in evaluate(cpm_sched).results
                    if res.status == "NOT EVALUATED"]
    assert "SET-02" not in unimplemented
