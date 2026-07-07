"""
Tests for INFRA-017: Phase 7 Regression Governance.

Covers test categories:
  10. Regression detection
  11. Approval workflow governance
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    ApprovalStatus,
    BenchmarkDiff,
    ValidationSeverity,
)
from scheduleiq.cpm.benchmark import (  # noqa: E402
    RegressionChecker,
    RegressionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_dict(
    is_valid=True,
    project_finish="2026-01-13",
    scheduled=None,
    critical_path_ids=None,
):
    """Return a minimal BenchmarkRunResult.to_dict()-compatible payload."""
    if scheduled is None:
        scheduled = {
            "A": {
                "early_start": "2026-01-05", "early_finish": "2026-01-07",
                "late_start": "2026-01-05", "late_finish": "2026-01-07",
                "total_float": 0, "free_float": 0, "is_critical": True,
            },
        }
    if critical_path_ids is None:
        critical_path_ids = ["A"]
    return {
        "actual_output": {
            "is_valid": is_valid,
            "project_finish": project_finish,
            "scheduled": scheduled,
            "critical_path": {"activity_ids": critical_path_ids},
        }
    }


def _baseline() -> dict:
    return _make_run_dict()


def _checker() -> RegressionChecker:
    return RegressionChecker()


# ---------------------------------------------------------------------------
# Category 10: Regression detection
# ---------------------------------------------------------------------------

class TestRegressionDetection:
    def test_identical_runs_no_regression(self):
        baseline = _baseline()
        current = _baseline()
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert not result.has_regression
        assert result.diffs == []

    def test_project_finish_change_detected(self):
        baseline = _baseline()
        current = _make_run_dict(project_finish="2026-01-14")
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert result.has_regression
        assert any(d.field_path == "project_finish" for d in result.diffs)

    def test_is_valid_change_detected(self):
        baseline = _baseline()
        current = _make_run_dict(is_valid=False, project_finish=None, scheduled={})
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert result.has_regression
        assert any(d.field_path == "is_valid" for d in result.diffs)

    def test_is_valid_change_severity_critical(self):
        baseline = _baseline()
        current = _make_run_dict(is_valid=False, project_finish=None, scheduled={})
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        is_valid_diff = next(d for d in result.diffs if d.field_path == "is_valid")
        assert is_valid_diff.severity == ValidationSeverity.CRITICAL

    def test_activity_date_change_detected(self):
        baseline = _baseline()
        current = _make_run_dict(scheduled={
            "A": {
                "early_start": "2026-01-06",  # changed
                "early_finish": "2026-01-07",
                "late_start": "2026-01-05", "late_finish": "2026-01-07",
                "total_float": 0, "free_float": 0, "is_critical": True,
            },
        })
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert result.has_regression
        assert any(d.field_path == "scheduled.A.early_start" for d in result.diffs)

    def test_activity_float_change_detected(self):
        baseline = _baseline()
        current = _make_run_dict(scheduled={
            "A": {
                "early_start": "2026-01-05", "early_finish": "2026-01-07",
                "late_start": "2026-01-05", "late_finish": "2026-01-07",
                "total_float": 2,  # changed
                "free_float": 0, "is_critical": True,
            },
        })
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert any(d.field_path == "scheduled.A.total_float" for d in result.diffs)

    def test_criticality_change_detected(self):
        baseline = _baseline()
        current = _make_run_dict(scheduled={
            "A": {
                "early_start": "2026-01-05", "early_finish": "2026-01-07",
                "late_start": "2026-01-05", "late_finish": "2026-01-07",
                "total_float": 0, "free_float": 0, "is_critical": False,  # changed
            },
        })
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert any(d.field_path == "scheduled.A.is_critical" for d in result.diffs)

    def test_critical_path_change_detected(self):
        baseline = _baseline()
        current = _make_run_dict(critical_path_ids=["A", "B"])
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert any(d.field_path == "critical_path.activity_ids" for d in result.diffs)

    def test_regression_result_has_benchmark_id(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        assert result.benchmark_id == "BM-001"

    def test_regression_result_default_pending(self):
        baseline = _baseline()
        current = _make_run_dict(project_finish="2026-01-14")
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert result.approval_status == ApprovalStatus.PENDING

    def test_no_regression_default_pending_too(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        assert result.approval_status == ApprovalStatus.PENDING

    def test_max_severity_no_diffs(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        assert result.max_severity == ValidationSeverity.INFORMATIONAL

    def test_max_severity_with_analytical_diffs(self):
        baseline = _baseline()
        current = _make_run_dict(project_finish="2026-01-14")
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert result.max_severity == ValidationSeverity.ANALYTICAL

    def test_max_severity_returns_highest(self):
        baseline = _make_run_dict(is_valid=True)
        current = _make_run_dict(is_valid=False, project_finish=None, scheduled={})
        result = _checker().compare_to_baseline(baseline, current, "BM-001")
        assert result.max_severity == ValidationSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Category 11: Approval workflow governance
# ---------------------------------------------------------------------------

class TestApprovalWorkflow:
    def _detected_regression(self) -> RegressionResult:
        baseline = _baseline()
        current = _make_run_dict(project_finish="2026-01-14")
        return _checker().compare_to_baseline(baseline, current, "BM-001")

    def test_approve_sets_approved_status(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="Accepted: engine update")
        assert approved.approval_status == ApprovalStatus.APPROVED

    def test_approve_preserves_diffs(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="Accepted: engine update")
        assert approved.diffs == result.diffs
        assert approved.has_regression is True

    def test_approve_records_note(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="Engine fix confirmed")
        assert approved.approval_note == "Engine fix confirmed"

    def test_approve_records_approver(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="OK", approved_by="A.Smith")
        assert approved.approved_by == "A.Smith"

    def test_approve_records_timestamp(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="OK")
        assert approved.approval_timestamp != ""

    def test_approve_does_not_mutate_original(self):
        result = self._detected_regression()
        _checker().approve_regression(result, note="OK")
        assert result.approval_status == ApprovalStatus.PENDING

    def test_approve_returns_new_object(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="OK")
        assert approved is not result

    def test_reject_sets_rejected_status(self):
        result = self._detected_regression()
        rejected = _checker().reject_regression(result, note="Defect confirmed")
        assert rejected.approval_status == ApprovalStatus.REJECTED

    def test_reject_records_note(self):
        result = self._detected_regression()
        rejected = _checker().reject_regression(result, note="Bug in engine")
        assert rejected.approval_note == "Bug in engine"

    def test_reject_does_not_mutate_original(self):
        result = self._detected_regression()
        _checker().reject_regression(result, note="Bug")
        assert result.approval_status == ApprovalStatus.PENDING

    def test_approve_empty_note_raises(self):
        result = self._detected_regression()
        with pytest.raises(ValueError, match="non-empty"):
            _checker().approve_regression(result, note="")

    def test_approve_whitespace_note_raises(self):
        result = self._detected_regression()
        with pytest.raises(ValueError, match="non-empty"):
            _checker().approve_regression(result, note="   ")

    def test_reject_empty_note_raises(self):
        result = self._detected_regression()
        with pytest.raises(ValueError, match="non-empty"):
            _checker().reject_regression(result, note="")

    def test_approve_no_regression_raises(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        with pytest.raises(ValueError, match="no regression"):
            _checker().approve_regression(result, note="OK")

    def test_reject_no_regression_raises(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        with pytest.raises(ValueError, match="no regression"):
            _checker().reject_regression(result, note="OK")

    def test_note_stripped_of_whitespace(self):
        result = self._detected_regression()
        approved = _checker().approve_regression(result, note="  trimmed  ")
        assert approved.approval_note == "trimmed"


# ---------------------------------------------------------------------------
# ApprovalStatus enum
# ---------------------------------------------------------------------------

class TestApprovalStatus:
    def test_pending_value(self):
        assert ApprovalStatus.PENDING.value == "pending"

    def test_approved_value(self):
        assert ApprovalStatus.APPROVED.value == "approved"

    def test_rejected_value(self):
        assert ApprovalStatus.REJECTED.value == "rejected"


# ---------------------------------------------------------------------------
# BenchmarkDiff serialization
# ---------------------------------------------------------------------------

class TestBenchmarkDiffSerialization:
    def test_to_dict_structure(self):
        diff = BenchmarkDiff(
            benchmark_id="BM-001",
            field_path="project_finish",
            baseline_value="2026-01-13",
            current_value="2026-01-14",
            severity=ValidationSeverity.ANALYTICAL,
            change_description="Project finish date changed.",
        )
        d = diff.to_dict()
        assert set(d.keys()) == {
            "benchmark_id", "field_path", "baseline_value",
            "current_value", "severity", "change_description",
        }

    def test_severity_serialized_as_string(self):
        diff = BenchmarkDiff(
            benchmark_id="BM-001", field_path="x",
            baseline_value=None, current_value=None,
            severity=ValidationSeverity.ANALYTICAL,
            change_description="",
        )
        assert diff.to_dict()["severity"] == "analytical"


# ---------------------------------------------------------------------------
# RegressionResult serialization
# ---------------------------------------------------------------------------

class TestRegressionResultSerialization:
    def test_to_dict_keys(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        d = result.to_dict()
        expected_keys = {
            "benchmark_id", "has_regression", "diffs", "approval_status",
            "approval_note", "approved_by", "approval_timestamp",
            "detected_at", "max_severity",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_approval_status_string(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        assert result.to_dict()["approval_status"] == "pending"

    def test_to_dict_max_severity_string(self):
        result = _checker().compare_to_baseline(_baseline(), _baseline(), "BM-001")
        assert result.to_dict()["max_severity"] == "informational"
