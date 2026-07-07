"""
Tests for Phase 7 Integration: End-to-End Validation Workflow.

Covers test categories:
  2.  Deterministic benchmark execution (suite-level)
  3.  Repeated-run reproducibility (full suite)
  13. Artifact generation (end-to-end)
  14. Registry governance (full workflow)
  15. Provenance fields (end-to-end chain)
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    ArtifactRegistry,
    BenchmarkRunResult,
    ReproducibilityChecker,
    SuiteRunResult,
    ValidationArtifact,
    ValidationHarness,
    ValidationProvenance,
    ValidationSeverity,
    BENCHMARK_FRAMEWORK_VERSION,
)
from scheduleiq.cpm.benchmark.fixtures import PHASE7_SUITE, BM_001  # noqa: E402
from scheduleiq.cpm.benchmark.regression import (  # noqa: E402
    ApprovalStatus,
    RegressionChecker,
    RegressionResult,
)


# ---------------------------------------------------------------------------
# End-to-end suite run
# ---------------------------------------------------------------------------

class TestEndToEndSuiteRun:
    def setup_method(self):
        self.harness = ValidationHarness()
        self.suite_result = self.harness.run_suite(PHASE7_SUITE)

    def test_suite_passes_completely(self):
        assert self.suite_result.passed
        assert self.suite_result.failed_count == 0

    def test_suite_total_is_12(self):
        assert self.suite_result.total == 12

    def test_suite_passed_count_is_12(self):
        assert self.suite_result.passed_count == 12

    def test_each_result_is_benchmark_run_result(self):
        for bm_id, result in self.suite_result.benchmark_results.items():
            assert isinstance(result, BenchmarkRunResult), (
                f"{bm_id}: expected BenchmarkRunResult"
            )

    def test_suite_to_dict_serializable(self):
        import json
        d = self.suite_result.to_dict()
        serialized = json.dumps(d, default=str)
        assert len(serialized) > 0


# ---------------------------------------------------------------------------
# Full workflow: run → artifact → registry
# ---------------------------------------------------------------------------

class TestFullWorkflowSingleBenchmark:
    def setup_method(self):
        self.harness = ValidationHarness()
        self.registry = ArtifactRegistry()
        self.run_result = self.harness.run_benchmark(BM_001)
        self.artifact = ValidationArtifact.from_benchmark_run(self.run_result)
        self.registry.record(self.artifact)

    def test_run_passes(self):
        assert self.run_result.passed

    def test_artifact_recorded_in_registry(self):
        assert self.registry.get(self.artifact.artifact_id) is self.artifact

    def test_registry_summary_one_artifact(self):
        s = self.registry.summary()
        assert s["total_artifacts"] == 1
        assert s["passed"] == 1

    def test_provenance_in_artifact(self):
        prov = self.artifact.provenance
        assert isinstance(prov, ValidationProvenance)
        assert prov.benchmark_framework_version == BENCHMARK_FRAMEWORK_VERSION
        assert prov.engine_version != ""

    def test_artifact_to_dict_contains_provenance(self):
        d = self.artifact.to_dict()
        assert "provenance" in d
        assert d["provenance"]["benchmark_framework_version"] == BENCHMARK_FRAMEWORK_VERSION


class TestFullWorkflowSuiteRun:
    def setup_method(self):
        self.harness = ValidationHarness()
        self.registry = ArtifactRegistry()
        self.suite_result = self.harness.run_suite(PHASE7_SUITE)

        # Record a per-benchmark artifact for each run
        for bm_id, run_result in self.suite_result.benchmark_results.items():
            artifact = ValidationArtifact.from_benchmark_run(run_result)
            self.registry.record(artifact)

        # Record one suite-level artifact
        suite_artifact = ValidationArtifact.from_suite_run(self.suite_result)
        self.registry.record(suite_artifact)

    def test_registry_has_13_artifacts(self):
        # 12 benchmark_run + 1 suite_run
        assert self.registry.summary()["total_artifacts"] == 13

    def test_all_benchmark_artifacts_passed(self):
        bm_artifacts = self.registry.list_by_type("benchmark_run")
        for a in bm_artifacts:
            assert a.passed, f"{a.benchmark_id} artifact did not pass"

    def test_suite_artifact_passed(self):
        suite_arts = self.registry.list_by_type("suite_run")
        assert len(suite_arts) == 1
        assert suite_arts[0].passed

    def test_registry_to_dict_serializable(self):
        import json
        d = self.registry.to_dict()
        serialized = json.dumps(d, default=str)
        assert len(serialized) > 0


# ---------------------------------------------------------------------------
# Full workflow: reproducibility → artifact → registry
# ---------------------------------------------------------------------------

class TestFullWorkflowReproducibility:
    def setup_method(self):
        self.harness = ValidationHarness()
        self.checker = ReproducibilityChecker()
        self.registry = ArtifactRegistry()
        self.repro_result = self.checker.check(BM_001, self.harness, n_runs=2)
        self.artifact = ValidationArtifact.from_reproducibility(self.repro_result)
        self.registry.record(self.artifact)

    def test_reproducibility_passes(self):
        assert self.repro_result.passed

    def test_artifact_type_is_reproducibility(self):
        assert self.artifact.artifact_type == "reproducibility"

    def test_artifact_recorded_in_registry(self):
        assert self.registry.get(self.artifact.artifact_id) is self.artifact

    def test_registry_summary_one_reproducibility(self):
        s = self.registry.summary()
        assert s["by_type"].get("reproducibility") == 1


# ---------------------------------------------------------------------------
# Full workflow: regression detection → approval → artifact → registry
# ---------------------------------------------------------------------------

class TestFullWorkflowRegression:
    def setup_method(self):
        self.harness = ValidationHarness()
        self.reg_checker = RegressionChecker()
        self.registry = ArtifactRegistry()

        # Run baseline and current (identical → no regression)
        baseline_run = self.harness.run_benchmark(BM_001)
        current_run = self.harness.run_benchmark(BM_001)
        self.regression_result = self.reg_checker.compare_to_baseline(
            baseline_run.to_dict(),
            current_run.to_dict(),
            "BM-001",
        )

    def test_no_regression_detected(self):
        assert not self.regression_result.has_regression

    def test_regression_artifact_is_passed(self):
        artifact = ValidationArtifact.from_regression(self.regression_result)
        assert artifact.passed

    def test_regression_artifact_type(self):
        artifact = ValidationArtifact.from_regression(self.regression_result)
        assert artifact.artifact_type == "regression"

    def test_regression_artifact_registered(self):
        artifact = ValidationArtifact.from_regression(self.regression_result)
        self.registry.record(artifact)
        assert self.registry.summary()["by_type"]["regression"] == 1


class TestRegressionApprovalEndToEnd:
    def setup_method(self):
        self.harness = ValidationHarness()
        self.reg_checker = RegressionChecker()

        run = self.harness.run_benchmark(BM_001)
        baseline = run.to_dict()

        # Artificially introduce a divergence in the current run dict
        import copy
        current = copy.deepcopy(baseline)
        current["actual_output"]["project_finish"] = "2026-01-14"

        self.regression_result = self.reg_checker.compare_to_baseline(
            baseline, current, "BM-001"
        )

    def test_regression_detected_pending(self):
        assert self.regression_result.has_regression
        assert self.regression_result.approval_status == ApprovalStatus.PENDING

    def test_pending_artifact_not_passed(self):
        artifact = ValidationArtifact.from_regression(self.regression_result)
        assert not artifact.passed

    def test_approve_regression_creates_passed_artifact(self):
        approved = self.reg_checker.approve_regression(
            self.regression_result, note="Engine change confirmed correct."
        )
        artifact = ValidationArtifact.from_regression(approved)
        assert artifact.passed

    def test_reject_regression_creates_failed_artifact(self):
        rejected = self.reg_checker.reject_regression(
            self.regression_result, note="Defect confirmed; baseline stands."
        )
        artifact = ValidationArtifact.from_regression(rejected)
        assert not artifact.passed


# ---------------------------------------------------------------------------
# Context integration — benchmark fields populated by harness
# ---------------------------------------------------------------------------

class TestContextIntegration:
    def test_analysis_context_benchmark_fields_default_none(self):
        from scheduleiq.cpm.context import AnalysisContext
        ctx = AnalysisContext()
        assert ctx.benchmark_id is None
        assert ctx.benchmark_version is None
        assert ctx.validation_provenance is None

    def test_analysis_context_benchmark_fields_settable(self):
        from scheduleiq.cpm.context import AnalysisContext
        ctx = AnalysisContext()
        ctx.benchmark_id = "BM-001"
        ctx.benchmark_version = "1.0-phase7"
        ctx.validation_provenance = {"convention": "inclusive_day"}
        d = ctx.to_dict()
        assert d["benchmark_id"] == "BM-001"
        assert d["benchmark_version"] == "1.0-phase7"
        assert d["validation_provenance"]["convention"] == "inclusive_day"
