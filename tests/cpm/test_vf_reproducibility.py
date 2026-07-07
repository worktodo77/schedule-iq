"""
Tests for INFRA-015: Phase 7 Reproducibility Verification.

Covers test categories:
  3. Repeated-run reproducibility
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    ReproducibilityChecker,
    ReproducibilityResult,
    ValidationHarness,
)
from scheduleiq.cpm.benchmark.fixtures import (  # noqa: E402
    PHASE7_SUITE,
    BM_001, BM_002, BM_003, BM_011, BM_012,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _checker() -> ReproducibilityChecker:
    return ReproducibilityChecker()


def _harness() -> ValidationHarness:
    return ValidationHarness()


# ---------------------------------------------------------------------------
# Category 3: Repeated-run reproducibility
# ---------------------------------------------------------------------------

class TestReproducibilityBasic:
    def test_check_returns_result(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        assert isinstance(result, ReproducibilityResult)

    def test_bm001_passes_2_runs(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        assert result.passed

    def test_bm001_passes_3_runs(self):
        result = _checker().check(BM_001, _harness(), n_runs=3)
        assert result.passed

    def test_n_runs_recorded(self):
        result = _checker().check(BM_001, _harness(), n_runs=3)
        assert result.n_runs == 3

    def test_run_hashes_count_matches_n_runs(self):
        result = _checker().check(BM_001, _harness(), n_runs=4)
        assert len(result.run_hashes) == 4

    def test_run_hashes_are_sha256_strings(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        for h in result.run_hashes:
            assert isinstance(h, str)
            assert len(h) == 64  # SHA-256 hex digest length

    def test_all_hashes_identical_when_passing(self):
        result = _checker().check(BM_001, _harness(), n_runs=3)
        assert result.passed
        assert len(set(result.run_hashes)) == 1

    def test_no_discrepancies_when_passing(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        assert result.discrepancies == []

    def test_benchmark_id_recorded(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        assert result.benchmark_id == "BM-001"

    def test_run_timestamp_set(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        assert result.run_timestamp
        assert "T" in result.run_timestamp


class TestReproducibilityAcrossBenchmarks:
    @pytest.mark.parametrize("bm,bm_id", [
        (BM_001, "BM-001"),
        (BM_002, "BM-002"),
        (BM_003, "BM-003"),
        (BM_011, "BM-011"),
        (BM_012, "BM-012"),
    ])
    def test_benchmark_passes_reproducibility(self, bm, bm_id):
        result = _checker().check(bm, _harness(), n_runs=2)
        assert result.passed, (
            f"{bm_id} failed reproducibility: {result.discrepancies}"
        )


class TestReproducibilityGovernance:
    def test_n_runs_less_than_2_raises(self):
        with pytest.raises(ValueError, match="n_runs must be >= 2"):
            _checker().check(BM_001, _harness(), n_runs=1)

    def test_n_runs_zero_raises(self):
        with pytest.raises(ValueError, match="n_runs must be >= 2"):
            _checker().check(BM_001, _harness(), n_runs=0)

    def test_n_runs_exactly_2_valid(self):
        result = _checker().check(BM_001, _harness(), n_runs=2)
        assert result.n_runs == 2


class TestReproducibilityResultSerialization:
    def setup_method(self):
        self.result = _checker().check(BM_001, _harness(), n_runs=2)

    def test_to_dict_keys(self):
        d = self.result.to_dict()
        expected_keys = {
            "benchmark_id", "n_runs", "passed",
            "run_hashes", "discrepancies", "run_timestamp",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_passed_bool(self):
        assert self.result.to_dict()["passed"] is True

    def test_to_dict_run_hashes_list(self):
        d = self.result.to_dict()
        assert isinstance(d["run_hashes"], list)
        assert len(d["run_hashes"]) == 2

    def test_to_dict_discrepancies_empty_when_passing(self):
        assert self.result.to_dict()["discrepancies"] == []
