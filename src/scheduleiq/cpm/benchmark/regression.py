"""
INFRA-013: Phase 7 Regression Governance.

Implements the formal regression detection and approval workflow required
by ADR-009. Regression governance enforces that:
  - changed benchmark outputs are never silently accepted;
  - every detected regression requires explicit analyst approval;
  - approval records include the approver identity, timestamp, and rationale;
  - approval records are persisted in the artifact trail.

Types:
  ApprovalStatus    — approval state machine: PENDING → APPROVED or REJECTED
  BenchmarkDiff     — single field-level divergence between baseline and current
  RegressionResult  — complete regression analysis for one benchmark

Class:
  RegressionChecker — compare two benchmark run results; manage approvals

Governance (ADR-009):
  - Regressions are detected by comparing two BenchmarkRunResult.to_dict() payloads.
  - Approval requires an explicit note; empty notes are rejected.
  - Once APPROVED or REJECTED, a result is immutable (returns a new object).
  - PENDING results must not be used as new baselines.

Source: ADR-009 — Benchmark Governance.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.regression) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from .benchmarks import ValidationSeverity


# ---------------------------------------------------------------------------
# Approval state
# ---------------------------------------------------------------------------

class ApprovalStatus(Enum):
    """
    Approval state for a detected regression.

    Members:
        PENDING:  Regression detected; no analyst decision yet. Default state.
        APPROVED: Analyst has reviewed and approved the changed output.
                  The current output may be promoted to the new baseline.
        REJECTED: Analyst has reviewed and rejected the changed output.
                  The baseline stands; the current output is a defect.
    """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Benchmark field-level diff
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkDiff:
    """
    A single field-level difference between a baseline and a current run.

    Fields:
        benchmark_id:       Benchmark that produced this diff.
        field_path:         Dot-path to the differing field
                            (e.g. "activities.A100.total_float").
        baseline_value:     Value in the baseline (reference) run.
        current_value:      Value in the current (tested) run.
        severity:           Severity classification of this difference.
        change_description: Human-readable description of the change.
    """
    benchmark_id: str
    field_path: str
    baseline_value: Any
    current_value: Any
    severity: ValidationSeverity
    change_description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "field_path": self.field_path,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "severity": self.severity.value,
            "change_description": self.change_description,
        }


# ---------------------------------------------------------------------------
# Regression result
# ---------------------------------------------------------------------------

@dataclass
class RegressionResult:
    """
    Complete regression analysis for a single benchmark.

    A RegressionResult records whether a benchmark's current output matches
    its baseline, and tracks the analyst approval workflow for any differences.

    Fields:
        benchmark_id:    Benchmark identifier.
        has_regression:  True when at least one BenchmarkDiff was detected.
        diffs:           All detected field-level differences.
        approval_status: Current approval state (PENDING by default).
        approval_note:   Analyst rationale for APPROVED/REJECTED decisions.
        approved_by:     Identifier for the approving analyst.
        approval_timestamp: ISO 8601 UTC timestamp of the approval decision.
        detected_at:     ISO 8601 UTC timestamp when the regression was detected.
        max_severity:    Highest severity among all diffs; INFORMATIONAL when empty.
    """
    benchmark_id: str
    has_regression: bool
    diffs: list[BenchmarkDiff] = field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approval_note: str = ""
    approved_by: str = ""
    approval_timestamp: str = ""
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def max_severity(self) -> ValidationSeverity:
        if not self.diffs:
            return ValidationSeverity.INFORMATIONAL
        order = [
            ValidationSeverity.INFORMATIONAL,
            ValidationSeverity.WARNING,
            ValidationSeverity.ANALYTICAL,
            ValidationSeverity.CRITICAL,
        ]
        return max(self.diffs, key=lambda d: order.index(d.severity)).severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "has_regression": self.has_regression,
            "diffs": [d.to_dict() for d in self.diffs],
            "approval_status": self.approval_status.value,
            "approval_note": self.approval_note,
            "approved_by": self.approved_by,
            "approval_timestamp": self.approval_timestamp,
            "detected_at": self.detected_at,
            "max_severity": self.max_severity.value,
        }


# ---------------------------------------------------------------------------
# Regression checker
# ---------------------------------------------------------------------------

class RegressionChecker:
    """
    Compares benchmark run results against a baseline and manages approvals.

    Governance contract (ADR-009):
      1. compare_to_baseline() detects field-level differences between a
         previously captured baseline run and a new current run.
      2. Regressions always start as PENDING; they require explicit approval.
      3. approve_regression() / reject_regression() return NEW immutable objects.
         They do NOT mutate the original result.
      4. Only APPROVED regressions may be used to update baselines.
      5. PENDING results must never be silently promoted to baselines.
    """

    # Fields compared in the activity schedule dict
    _ACTIVITY_DATE_FIELDS = (
        "early_start", "early_finish", "late_start", "late_finish"
    )
    _ACTIVITY_FLOAT_FIELDS = ("total_float", "free_float")
    _ACTIVITY_BOOL_FIELDS = ("is_critical",)

    def compare_to_baseline(
        self,
        baseline: dict[str, Any],
        current: dict[str, Any],
        benchmark_id: str,
    ) -> RegressionResult:
        """
        Compare current run results against a baseline.

        Both arguments are serialized BenchmarkRunResult dicts
        (from BenchmarkRunResult.to_dict()).

        Returns a RegressionResult with all detected diffs. When no
        differences exist, has_regression=False and diffs=[].

        Args:
            baseline:     Previously committed BenchmarkRunResult dict.
            current:      Newly computed BenchmarkRunResult dict.
            benchmark_id: Benchmark identifier (for error messages).

        Returns:
            RegressionResult with PENDING status if any diffs found.
        """
        diffs: list[BenchmarkDiff] = []

        baseline_output = baseline.get("actual_output", {})
        current_output = current.get("actual_output", {})

        # Top-level validity flag
        if baseline_output.get("is_valid") != current_output.get("is_valid"):
            diffs.append(BenchmarkDiff(
                benchmark_id=benchmark_id,
                field_path="is_valid",
                baseline_value=baseline_output.get("is_valid"),
                current_value=current_output.get("is_valid"),
                severity=ValidationSeverity.CRITICAL,
                change_description="is_valid flag changed — result validity changed.",
            ))

        # Project finish date
        b_pf = baseline_output.get("project_finish")
        c_pf = current_output.get("project_finish")
        if b_pf != c_pf:
            diffs.append(BenchmarkDiff(
                benchmark_id=benchmark_id,
                field_path="project_finish",
                baseline_value=b_pf,
                current_value=c_pf,
                severity=ValidationSeverity.ANALYTICAL,
                change_description="Project finish date changed.",
            ))

        # Activity-level diffs
        b_sched = baseline_output.get("scheduled", {})
        c_sched = current_output.get("scheduled", {})
        all_act_ids = sorted(set(b_sched) | set(c_sched))
        for act_id in all_act_ids:
            b_act = b_sched.get(act_id)
            c_act = c_sched.get(act_id)
            if b_act is None or c_act is None:
                diffs.append(BenchmarkDiff(
                    benchmark_id=benchmark_id,
                    field_path=f"scheduled.{act_id}",
                    baseline_value="present" if b_act else "absent",
                    current_value="present" if c_act else "absent",
                    severity=ValidationSeverity.CRITICAL,
                    change_description=f"Activity {act_id!r} presence changed.",
                ))
                continue
            for f in self._ACTIVITY_DATE_FIELDS:
                if b_act.get(f) != c_act.get(f):
                    diffs.append(BenchmarkDiff(
                        benchmark_id=benchmark_id,
                        field_path=f"scheduled.{act_id}.{f}",
                        baseline_value=b_act.get(f),
                        current_value=c_act.get(f),
                        severity=ValidationSeverity.ANALYTICAL,
                        change_description=f"Date field {f} changed for {act_id!r}.",
                    ))
            for f in self._ACTIVITY_FLOAT_FIELDS:
                if b_act.get(f) != c_act.get(f):
                    diffs.append(BenchmarkDiff(
                        benchmark_id=benchmark_id,
                        field_path=f"scheduled.{act_id}.{f}",
                        baseline_value=b_act.get(f),
                        current_value=c_act.get(f),
                        severity=ValidationSeverity.ANALYTICAL,
                        change_description=f"Float field {f} changed for {act_id!r}.",
                    ))
            for f in self._ACTIVITY_BOOL_FIELDS:
                if b_act.get(f) != c_act.get(f):
                    diffs.append(BenchmarkDiff(
                        benchmark_id=benchmark_id,
                        field_path=f"scheduled.{act_id}.{f}",
                        baseline_value=b_act.get(f),
                        current_value=c_act.get(f),
                        severity=ValidationSeverity.ANALYTICAL,
                        change_description=f"Criticality changed for {act_id!r}.",
                    ))

        # Critical path composition
        b_cp = (baseline_output.get("critical_path") or {})
        c_cp = (current_output.get("critical_path") or {})
        b_cp_ids = b_cp.get("activity_ids", [])
        c_cp_ids = c_cp.get("activity_ids", [])
        if sorted(b_cp_ids) != sorted(c_cp_ids):
            diffs.append(BenchmarkDiff(
                benchmark_id=benchmark_id,
                field_path="critical_path.activity_ids",
                baseline_value=b_cp_ids,
                current_value=c_cp_ids,
                severity=ValidationSeverity.ANALYTICAL,
                change_description="Critical path composition changed.",
            ))

        return RegressionResult(
            benchmark_id=benchmark_id,
            has_regression=bool(diffs),
            diffs=diffs,
            approval_status=ApprovalStatus.PENDING,
        )

    def approve_regression(
        self,
        result: RegressionResult,
        note: str,
        approved_by: str = "analyst",
    ) -> RegressionResult:
        """
        Approve a detected regression. Returns a new immutable RegressionResult.

        Governance requirement: approval note must be non-empty. The approver
        identity and timestamp are recorded in the returned result.

        Args:
            result:      The RegressionResult to approve.
            note:        Non-empty rationale for approving the changed output.
            approved_by: Identifier for the approving analyst.

        Returns:
            New RegressionResult with APPROVED status, note, and timestamp.

        Raises:
            ValueError: If note is empty or result has no regression.
        """
        if not note or not note.strip():
            raise ValueError(
                "approve_regression: approval_note must be non-empty. "
                "Document the rationale for accepting this changed output."
            )
        if not result.has_regression:
            raise ValueError(
                f"approve_regression: benchmark {result.benchmark_id!r} has no "
                "regression to approve. Only use approve_regression when "
                "has_regression=True."
            )
        return RegressionResult(
            benchmark_id=result.benchmark_id,
            has_regression=result.has_regression,
            diffs=result.diffs,
            approval_status=ApprovalStatus.APPROVED,
            approval_note=note.strip(),
            approved_by=approved_by,
            approval_timestamp=datetime.now(timezone.utc).isoformat(),
            detected_at=result.detected_at,
        )

    def reject_regression(
        self,
        result: RegressionResult,
        note: str,
        rejected_by: str = "analyst",
    ) -> RegressionResult:
        """
        Reject a detected regression. Returns a new immutable RegressionResult.

        A rejected regression means the current output is a defect; the
        baseline stands as the correct expected behavior.

        Args:
            result:      The RegressionResult to reject.
            note:        Non-empty rationale for rejecting the changed output.
            rejected_by: Identifier for the rejecting analyst.

        Returns:
            New RegressionResult with REJECTED status, note, and timestamp.

        Raises:
            ValueError: If note is empty or result has no regression.
        """
        if not note or not note.strip():
            raise ValueError(
                "reject_regression: rejection note must be non-empty. "
                "Document the rationale for rejecting this changed output."
            )
        if not result.has_regression:
            raise ValueError(
                f"reject_regression: benchmark {result.benchmark_id!r} has no "
                "regression to reject."
            )
        return RegressionResult(
            benchmark_id=result.benchmark_id,
            has_regression=result.has_regression,
            diffs=result.diffs,
            approval_status=ApprovalStatus.REJECTED,
            approval_note=note.strip(),
            approved_by=rejected_by,
            approval_timestamp=datetime.now(timezone.utc).isoformat(),
            detected_at=result.detected_at,
        )
