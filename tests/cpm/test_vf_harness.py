"""
Tests for INFRA-016: Phase 7 Validation Harness.

Covers test categories:
  2. Deterministic benchmark execution
  4. Baseline comparison
  5. Divergence detection
  6. Warning comparison
  7. Float comparison
  8. Longest-path comparison
  9. Convention comparison
  12. Stable ordering verification
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    BenchmarkCategory,
    BenchmarkDefinition,
    BenchmarkExpectations,
    BenchmarkMetadata,
    BenchmarkRunResult,
    BenchmarkSuite,
    Divergence,
    ExpectedActivityResult,
    SuiteRunResult,
    ValidationHarness,
    ValidationSeverity,
)
from scheduleiq.cpm.benchmark.fixtures import (  # noqa: E402
    PHASE7_SUITE,
    BM_001, BM_002, BM_003, BM_004, BM_005,
    BM_006, BM_007, BM_008, BM_009, BM_010,
    BM_011, BM_012,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_harness() -> ValidationHarness:
    return ValidationHarness()


def _run(bm: BenchmarkDefinition) -> BenchmarkRunResult:
    return _make_harness().run_benchmark(bm)


# ---------------------------------------------------------------------------
# Category 2: Deterministic benchmark execution — BM-001 through BM-012
# ---------------------------------------------------------------------------

class TestDeterministicExecution:
    """All 12 fixtures must pass when run against the engine."""

    @pytest.mark.parametrize("bm", [
        BM_001, BM_002, BM_003, BM_004, BM_005, BM_006,
        BM_007, BM_008, BM_009, BM_010, BM_011, BM_012,
    ], ids=[f"BM-{i:03d}" for i in range(1, 13)])
    def test_all_benchmarks_pass(self, bm):
        result = _run(bm)
        assert result.passed, (
            f"{bm.metadata.benchmark_id} failed:\n"
            + "\n".join(f"  {d.field}: expected={d.expected!r} actual={d.actual!r}"
                        for d in result.divergences)
        )

    def test_run_returns_benchmark_run_result(self):
        result = _run(BM_001)
        assert isinstance(result, BenchmarkRunResult)

    def test_run_result_has_correct_benchmark_id(self):
        result = _run(BM_001)
        assert result.benchmark_id == "BM-001"

    def test_passing_result_has_empty_divergences(self):
        result = _run(BM_001)
        assert result.divergences == []

    def test_passing_result_severity_informational(self):
        result = _run(BM_001)
        assert result.severity == ValidationSeverity.INFORMATIONAL

    def test_run_result_has_actual_output(self):
        result = _run(BM_001)
        assert isinstance(result.actual_output, dict)
        assert "is_valid" in result.actual_output

    def test_run_result_has_run_timestamp(self):
        result = _run(BM_001)
        assert result.run_timestamp
        assert isinstance(result.run_timestamp, str)

    def test_run_result_has_engine_version(self):
        result = _run(BM_001)
        assert result.engine_version
        assert isinstance(result.engine_version, str)

    def test_run_result_convention_matches_fixture(self):
        result = _run(BM_001)
        assert result.convention == BM_001.convention

    def test_bm011_p6_convention_runs(self):
        result = _run(BM_011)
        assert result.passed, (
            "BM-011 (p6_compatibility) failed:\n"
            + "\n".join(f"  {d.field}: expected={d.expected!r} actual={d.actual!r}"
                        for d in result.divergences)
        )

    def test_bm012_invalid_network_passes(self):
        result = _run(BM_012)
        assert result.passed, (
            "BM-012 (cycle) failed:\n"
            + "\n".join(f"  {d.field}: expected={d.expected!r} actual={d.actual!r}"
                        for d in result.divergences)
        )


# ---------------------------------------------------------------------------
# Category 12: Stable ordering — suite run ordering
# ---------------------------------------------------------------------------

class TestStableOrdering:
    def test_suite_run_result_order_matches_benchmark_ids(self):
        harness = _make_harness()
        suite_result = harness.run_suite(PHASE7_SUITE)
        result_keys = list(suite_result.benchmark_results.keys())
        expected_order = PHASE7_SUITE.benchmark_ids()
        assert result_keys == expected_order

    def test_repeated_suite_run_same_pass_count(self):
        harness = _make_harness()
        r1 = harness.run_suite(PHASE7_SUITE)
        r2 = harness.run_suite(PHASE7_SUITE)
        assert r1.passed_count == r2.passed_count
        assert r1.total == r2.total


# ---------------------------------------------------------------------------
# Suite run result structure
# ---------------------------------------------------------------------------

class TestSuiteRunResult:
    def setup_method(self):
        self.harness = _make_harness()
        self.suite_result = self.harness.run_suite(PHASE7_SUITE)

    def test_suite_run_result_type(self):
        assert isinstance(self.suite_result, SuiteRunResult)

    def test_suite_id_matches(self):
        assert self.suite_result.suite_id == PHASE7_SUITE.suite_id

    def test_total_is_12(self):
        assert self.suite_result.total == 12

    def test_all_passed(self):
        assert self.suite_result.passed
        assert self.suite_result.passed_count == 12
        assert self.suite_result.failed_count == 0

    def test_to_dict_structure(self):
        d = self.suite_result.to_dict()
        assert d["suite_id"] == PHASE7_SUITE.suite_id
        assert d["passed"] is True
        assert d["total"] == 12
        assert "benchmark_results" in d

    def test_benchmark_results_keyed_by_id(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            assert bm_id in self.suite_result.benchmark_results


# ---------------------------------------------------------------------------
# Category 5: Divergence detection
# ---------------------------------------------------------------------------

class TestDivergenceDetection:
    """Verify harness catches incorrect expectations with correct severity."""

    def _bm_with_wrong_finish(self) -> BenchmarkDefinition:
        bm = BM_001
        wrong_exp = BenchmarkExpectations(
            is_valid=True,
            project_finish="2026-01-01",  # wrong
            project_duration=bm.expectations.project_duration,
            critical_path_activity_ids=bm.expectations.critical_path_activity_ids,
            activities=bm.expectations.activities,
            convention=bm.expectations.convention,
            baseline_captured=bm.expectations.baseline_captured,
        )
        return BenchmarkDefinition(
            metadata=bm.metadata,
            activities=bm.activities,
            relationships=bm.relationships,
            project_start=bm.project_start,
            expectations=wrong_exp,
            convention=bm.convention,
        )

    def _bm_with_wrong_validity(self) -> BenchmarkDefinition:
        bm = BM_001
        wrong_exp = BenchmarkExpectations(
            is_valid=False,  # wrong — BM-001 is valid
            project_finish=bm.expectations.project_finish,
            project_duration=bm.expectations.project_duration,
            critical_path_activity_ids=bm.expectations.critical_path_activity_ids,
            activities=bm.expectations.activities,
            convention=bm.expectations.convention,
            baseline_captured=bm.expectations.baseline_captured,
        )
        return BenchmarkDefinition(
            metadata=bm.metadata,
            activities=bm.activities,
            relationships=bm.relationships,
            project_start=bm.project_start,
            expectations=wrong_exp,
            convention=bm.convention,
        )

    def _bm_with_wrong_activity_float(self) -> BenchmarkDefinition:
        bm = BM_001
        wrong_act_a = ExpectedActivityResult(
            activity_id="A",
            early_start=bm.expectations.activities["A"].early_start,
            early_finish=bm.expectations.activities["A"].early_finish,
            late_start=bm.expectations.activities["A"].late_start,
            late_finish=bm.expectations.activities["A"].late_finish,
            total_float=99,  # wrong
            free_float=0,
            is_critical=True,
        )
        wrong_acts = dict(bm.expectations.activities)
        wrong_acts["A"] = wrong_act_a
        wrong_exp = BenchmarkExpectations(
            is_valid=True,
            project_finish=bm.expectations.project_finish,
            project_duration=bm.expectations.project_duration,
            critical_path_activity_ids=bm.expectations.critical_path_activity_ids,
            activities=wrong_acts,
            convention=bm.expectations.convention,
            baseline_captured=bm.expectations.baseline_captured,
        )
        return BenchmarkDefinition(
            metadata=bm.metadata,
            activities=bm.activities,
            relationships=bm.relationships,
            project_start=bm.project_start,
            expectations=wrong_exp,
            convention=bm.convention,
        )

    def test_wrong_finish_fails(self):
        result = _run(self._bm_with_wrong_finish())
        assert not result.passed

    def test_wrong_finish_has_divergence_on_correct_field(self):
        result = _run(self._bm_with_wrong_finish())
        fields = [d.field for d in result.divergences]
        assert "project_finish" in fields

    def test_wrong_finish_severity_analytical(self):
        result = _run(self._bm_with_wrong_finish())
        assert result.severity == ValidationSeverity.ANALYTICAL

    def test_wrong_validity_fails(self):
        result = _run(self._bm_with_wrong_validity())
        assert not result.passed

    def test_wrong_validity_has_is_valid_divergence(self):
        result = _run(self._bm_with_wrong_validity())
        assert any(d.field == "is_valid" for d in result.divergences)

    def test_wrong_validity_severity_critical(self):
        result = _run(self._bm_with_wrong_validity())
        assert result.severity == ValidationSeverity.CRITICAL

    def test_wrong_validity_stops_early(self):
        result = _run(self._bm_with_wrong_validity())
        assert len(result.divergences) == 1

    def test_wrong_activity_float_fails(self):
        result = _run(self._bm_with_wrong_activity_float())
        assert not result.passed

    def test_wrong_activity_float_correct_field_path(self):
        result = _run(self._bm_with_wrong_activity_float())
        fields = [d.field for d in result.divergences]
        assert "scheduled.A.total_float" in fields

    def test_wrong_activity_float_severity_analytical(self):
        result = _run(self._bm_with_wrong_activity_float())
        pf_divs = [d for d in result.divergences if d.field == "scheduled.A.total_float"]
        assert pf_divs[0].severity == ValidationSeverity.ANALYTICAL


# ---------------------------------------------------------------------------
# Category 4: Baseline comparison — BenchmarkRunResult serialization
# ---------------------------------------------------------------------------

class TestBenchmarkRunResultSerialization:
    def setup_method(self):
        self.result = _run(BM_001)

    def test_to_dict_keys(self):
        d = self.result.to_dict()
        expected_keys = {
            "benchmark_id", "passed", "divergences", "actual_output",
            "run_timestamp", "engine_version", "convention", "severity",
            "error_message",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_passed_bool(self):
        assert self.result.to_dict()["passed"] is True

    def test_to_dict_severity_string(self):
        d = self.result.to_dict()
        assert isinstance(d["severity"], str)
        assert d["severity"] == "informational"

    def test_to_dict_divergences_list(self):
        assert self.result.to_dict()["divergences"] == []

    def test_divergence_to_dict_structure(self):
        div = Divergence(
            field="a.b",
            expected="x",
            actual="y",
            severity=ValidationSeverity.ANALYTICAL,
            message="test",
        )
        d = div.to_dict()
        assert set(d.keys()) == {"field", "expected", "actual", "severity", "message"}
        assert d["severity"] == "analytical"


# ---------------------------------------------------------------------------
# Category 7: Float comparison — specific benchmark float checks
# ---------------------------------------------------------------------------

class TestFloatComparison:
    def test_bm003_c_has_float(self):
        result = _run(BM_003)
        assert result.passed
        actual_c = result.actual_output["scheduled"]["C"]
        assert actual_c["total_float"] == 3
        assert actual_c["free_float"] == 3

    def test_bm005_lag_effect_on_floats(self):
        result = _run(BM_005)
        assert result.passed

    def test_bm006_negative_lag_float(self):
        result = _run(BM_006)
        assert result.passed

    def test_bm007_ss_float_values(self):
        result = _run(BM_007)
        assert result.passed
        actual_a = result.actual_output["scheduled"]["A"]
        assert actual_a["total_float"] == 2

    def test_bm009_sf_float_values(self):
        result = _run(BM_009)
        assert result.passed
        actual_a = result.actual_output["scheduled"]["A"]
        assert actual_a["total_float"] == 2


# ---------------------------------------------------------------------------
# Category 8: Longest-path comparison — critical path checks
# ---------------------------------------------------------------------------

class TestLongestPathComparison:
    def test_bm001_critical_path(self):
        result = _run(BM_001)
        actual_cp_ids = sorted(result.actual_output["critical_path"]["activity_ids"])
        assert actual_cp_ids == ["A", "B", "C"]

    def test_bm003_parallel_path_cp(self):
        result = _run(BM_003)
        actual_cp_ids = sorted(result.actual_output["critical_path"]["activity_ids"])
        assert actual_cp_ids == ["A", "B", "D"]

    def test_bm007_ss_empty_critical_path(self):
        result = _run(BM_007)
        actual_cp_ids = result.actual_output["critical_path"]["activity_ids"]
        assert actual_cp_ids == []

    def test_bm009_sf_empty_critical_path(self):
        result = _run(BM_009)
        actual_cp_ids = result.actual_output["critical_path"]["activity_ids"]
        assert actual_cp_ids == []

    def test_bm010_milestone_on_critical_path(self):
        result = _run(BM_010)
        actual_cp_ids = sorted(result.actual_output["critical_path"]["activity_ids"])
        assert actual_cp_ids == ["A", "B", "M"]

    def test_bm004_tied_paths_flag(self):
        result = _run(BM_004)
        assert result.passed
        cp = result.actual_output["critical_path"]
        assert cp["tied_paths"] is True


# ---------------------------------------------------------------------------
# Category 9: Convention comparison — BM-011 P6 vs inclusive_day
# ---------------------------------------------------------------------------

class TestConventionComparison:
    def test_bm001_inclusive_day_convention(self):
        result = _run(BM_001)
        assert result.convention == "inclusive_day"
        # inclusive_day FS offset=0: B starts same day A finishes
        actual_b = result.actual_output["scheduled"]["B"]
        assert actual_b["early_start"] == "2026-01-07"

    def test_bm011_p6_compatibility_convention(self):
        result = _run(BM_011)
        assert result.convention == "p6_compatibility"
        # p6_compatibility FS offset=1: B starts next workday after A finishes
        actual_b = result.actual_output["scheduled"]["B"]
        assert actual_b["early_start"] == "2026-01-08"

    def test_bm011_p6_different_finish_from_inclusive(self):
        r_incl = _run(BM_001)
        r_p6 = _run(BM_011)
        assert r_incl.actual_output["project_finish"] != r_p6.actual_output["project_finish"]


# ---------------------------------------------------------------------------
# Exception handling — CRITICAL divergence on engine error
# ---------------------------------------------------------------------------

class TestExceptionHandling:
    def test_bad_convention_captured_as_critical(self):
        bm = BM_001
        bad_bm = BenchmarkDefinition(
            metadata=bm.metadata,
            activities=bm.activities,
            relationships=bm.relationships,
            project_start=bm.project_start,
            expectations=bm.expectations,
            convention="nonexistent_convention",
        )
        result = _run(bad_bm)
        assert not result.passed
        assert result.severity == ValidationSeverity.CRITICAL
        assert result.error_message != ""
        assert any(d.field == "__execution__" for d in result.divergences)


# ---------------------------------------------------------------------------
# Category 6: Warning comparison — extra (unexpected) codes flagged (G-2)
# ---------------------------------------------------------------------------

class TestWarningComparison:
    """Verify _compare_warnings flags extra codes the engine emits unexpectedly."""

    def test_extra_warning_codes_produce_divergence(self):
        # Engine emits NET-006; benchmark expects no warnings.
        # Governance requirement: unexpected codes must not pass silently.
        actual_output = {"warnings": [{"code": "NET-006", "message": "open end activity"}]}
        divs = ValidationHarness._compare_warnings(actual_output, expected_codes=[])
        assert len(divs) == 1
        assert divs[0].field == "warnings.codes"
        assert divs[0].severity == ValidationSeverity.WARNING
        assert "NET-006" in divs[0].message
