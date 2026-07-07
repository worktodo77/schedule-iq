"""
Tests for INFRA-017: Phase 7 Validation Artifact Infrastructure.

Covers test categories:
  13. Artifact generation
  14. Registry governance
  15. Provenance fields
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    ApprovalStatus,
    ArtifactRegistry,
    ValidationArtifact,
    ValidationHarness,
    ValidationProvenance,
    ValidationSeverity,
    BENCHMARK_FRAMEWORK_VERSION,
)
from scheduleiq.cpm.benchmark.fixtures import PHASE7_SUITE, BM_001  # noqa: E402
from scheduleiq.cpm.benchmark.regression import RegressionChecker, RegressionResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_bm001() -> "BenchmarkRunResult":
    from scheduleiq.cpm.benchmark import BenchmarkRunResult
    return ValidationHarness().run_benchmark(BM_001)


def _suite_result():
    return ValidationHarness().run_suite(PHASE7_SUITE)


def _no_regression_result() -> RegressionResult:
    harness = ValidationHarness()
    r = harness.run_benchmark(BM_001)
    baseline = r.to_dict()
    current = r.to_dict()
    return RegressionChecker().compare_to_baseline(baseline, current, "BM-001")


def _regression_result() -> RegressionResult:
    harness = ValidationHarness()
    r = harness.run_benchmark(BM_001)
    baseline = r.to_dict()
    current_run = harness.run_benchmark(BM_001)
    # Patch the current output to create an artificial divergence
    current = current_run.to_dict()
    current["actual_output"]["project_finish"] = "2026-01-14"
    return RegressionChecker().compare_to_baseline(baseline, current, "BM-001")


# ---------------------------------------------------------------------------
# Category 15: Provenance fields
# ---------------------------------------------------------------------------

class TestValidationProvenance:
    def test_capture_returns_provenance(self):
        prov = ValidationProvenance.capture()
        assert isinstance(prov, ValidationProvenance)

    def test_capture_engine_version_set(self):
        prov = ValidationProvenance.capture()
        assert prov.engine_version

    def test_capture_benchmark_framework_version(self):
        prov = ValidationProvenance.capture()
        assert prov.benchmark_framework_version == BENCHMARK_FRAMEWORK_VERSION

    def test_capture_default_convention(self):
        prov = ValidationProvenance.capture()
        assert prov.convention == "inclusive_day"

    def test_capture_custom_convention(self):
        prov = ValidationProvenance.capture(convention="p6_compatibility")
        assert prov.convention == "p6_compatibility"

    def test_capture_parser_version_set(self):
        prov = ValidationProvenance.capture()
        assert prov.parser_version

    def test_capture_run_timestamp_set(self):
        prov = ValidationProvenance.capture()
        assert prov.run_timestamp
        assert "T" in prov.run_timestamp  # ISO 8601

    def test_to_dict_keys(self):
        prov = ValidationProvenance.capture()
        d = prov.to_dict()
        assert set(d.keys()) == {
            "engine_version", "benchmark_framework_version",
            "convention", "parser_version", "run_timestamp",
        }


# ---------------------------------------------------------------------------
# Category 13: Artifact generation
# ---------------------------------------------------------------------------

class TestValidationArtifactFromBenchmarkRun:
    def setup_method(self):
        self.run_result = _run_bm001()
        self.artifact = ValidationArtifact.from_benchmark_run(self.run_result)

    def test_artifact_type_benchmark_run(self):
        assert self.artifact.artifact_type == "benchmark_run"

    def test_benchmark_id_matches(self):
        assert self.artifact.benchmark_id == "BM-001"

    def test_suite_id_none(self):
        assert self.artifact.suite_id is None

    def test_passed_matches_run_result(self):
        assert self.artifact.passed == self.run_result.passed

    def test_severity_matches_run_result(self):
        assert self.artifact.severity == self.run_result.severity

    def test_artifact_id_is_uuid(self):
        import uuid
        uuid.UUID(self.artifact.artifact_id)  # raises if invalid

    def test_payload_has_benchmark_id(self):
        assert self.artifact.payload["benchmark_id"] == "BM-001"

    def test_to_dict_structure(self):
        d = self.artifact.to_dict()
        expected_keys = {
            "artifact_id", "artifact_type", "provenance",
            "benchmark_id", "suite_id", "passed", "severity",
            "payload", "created_at",
        }
        assert set(d.keys()) == expected_keys

    def test_severity_in_dict_is_string(self):
        assert isinstance(self.artifact.to_dict()["severity"], str)

    def test_custom_provenance_accepted(self):
        prov = ValidationProvenance.capture(convention="p6_compatibility")
        artifact = ValidationArtifact.from_benchmark_run(self.run_result, provenance=prov)
        assert artifact.provenance.convention == "p6_compatibility"


class TestValidationArtifactFromSuiteRun:
    def setup_method(self):
        self.suite_result = _suite_result()
        self.artifact = ValidationArtifact.from_suite_run(self.suite_result)

    def test_artifact_type_suite_run(self):
        assert self.artifact.artifact_type == "suite_run"

    def test_suite_id_matches(self):
        assert self.artifact.suite_id == PHASE7_SUITE.suite_id

    def test_benchmark_id_none(self):
        assert self.artifact.benchmark_id is None

    def test_passed_reflects_all_passing(self):
        assert self.artifact.passed is True

    def test_severity_informational_when_passing(self):
        assert self.artifact.severity == ValidationSeverity.INFORMATIONAL


class TestValidationArtifactFromReproducibility:
    def setup_method(self):
        from scheduleiq.cpm.benchmark import ReproducibilityChecker
        harness = ValidationHarness()
        checker = ReproducibilityChecker()
        self.repro_result = checker.check(BM_001, harness, n_runs=2)
        self.artifact = ValidationArtifact.from_reproducibility(self.repro_result)

    def test_artifact_type_reproducibility(self):
        assert self.artifact.artifact_type == "reproducibility"

    def test_benchmark_id_matches(self):
        assert self.artifact.benchmark_id == "BM-001"

    def test_passed_true_when_reproducible(self):
        assert self.artifact.passed is True

    def test_severity_informational_when_passing(self):
        assert self.artifact.severity == ValidationSeverity.INFORMATIONAL


class TestValidationArtifactFromRegression:
    def test_from_regression_no_regression_passed(self):
        result = _no_regression_result()
        artifact = ValidationArtifact.from_regression(result)
        assert artifact.artifact_type == "regression"
        assert artifact.passed is True

    def test_from_regression_pending_not_passed(self):
        result = _regression_result()
        artifact = ValidationArtifact.from_regression(result)
        assert artifact.passed is False

    def test_from_regression_approved_is_passed(self):
        result = _regression_result()
        approved = RegressionChecker().approve_regression(result, note="Accepted")
        artifact = ValidationArtifact.from_regression(approved)
        assert artifact.passed is True

    def test_from_regression_benchmark_id(self):
        result = _no_regression_result()
        artifact = ValidationArtifact.from_regression(result)
        assert artifact.benchmark_id == "BM-001"


# ---------------------------------------------------------------------------
# Category 14: Registry governance
# ---------------------------------------------------------------------------

class TestArtifactRegistry:
    def setup_method(self):
        self.registry = ArtifactRegistry()
        self.artifact = ValidationArtifact.from_benchmark_run(_run_bm001())

    def test_record_returns_artifact_id(self):
        returned_id = self.registry.record(self.artifact)
        assert returned_id == self.artifact.artifact_id

    def test_get_returns_recorded_artifact(self):
        self.registry.record(self.artifact)
        retrieved = self.registry.get(self.artifact.artifact_id)
        assert retrieved is self.artifact

    def test_get_missing_returns_none(self):
        assert self.registry.get("nonexistent-id") is None

    def test_record_duplicate_raises(self):
        self.registry.record(self.artifact)
        with pytest.raises(ValueError, match="already exists"):
            self.registry.record(self.artifact)

    def test_all_artifacts_empty_initially(self):
        assert self.registry.all_artifacts() == []

    def test_all_artifacts_returns_in_insertion_order(self):
        a1 = ValidationArtifact.from_benchmark_run(_run_bm001())
        a2 = ValidationArtifact.from_benchmark_run(_run_bm001())
        self.registry.record(a1)
        self.registry.record(a2)
        ordered = self.registry.all_artifacts()
        assert ordered[0].artifact_id == a1.artifact_id
        assert ordered[1].artifact_id == a2.artifact_id

    def test_list_by_type_filters_correctly(self):
        benchmark_artifact = ValidationArtifact.from_benchmark_run(_run_bm001())
        suite_artifact = ValidationArtifact.from_suite_run(_suite_result())
        self.registry.record(benchmark_artifact)
        self.registry.record(suite_artifact)
        bm_arts = self.registry.list_by_type("benchmark_run")
        suite_arts = self.registry.list_by_type("suite_run")
        assert len(bm_arts) == 1
        assert len(suite_arts) == 1
        assert bm_arts[0].artifact_type == "benchmark_run"

    def test_list_by_type_empty_when_none(self):
        assert self.registry.list_by_type("regression") == []

    def test_summary_counts(self):
        self.registry.record(self.artifact)
        s = self.registry.summary()
        assert s["total_artifacts"] == 1
        assert s["passed"] == 1
        assert s["failed"] == 0
        assert s["by_type"]["benchmark_run"] == 1

    def test_to_dict_structure(self):
        self.registry.record(self.artifact)
        d = self.registry.to_dict()
        assert "summary" in d
        assert "artifacts" in d
        assert len(d["artifacts"]) == 1

    def test_registry_is_empty_after_init(self):
        fresh = ArtifactRegistry()
        assert fresh.summary()["total_artifacts"] == 0
