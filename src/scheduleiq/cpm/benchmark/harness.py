"""
INFRA-016: Phase 7 Validation Harness.

Provides deterministic benchmark execution, expected-vs-actual comparison,
and structured divergence reporting. The harness is the primary entry point
for running the benchmark suite against the analytical engine.

Types:
  Divergence         — single field-level divergence between expected and actual
  BenchmarkRunResult — structured result of one benchmark execution
  SuiteRunResult     — structured result of executing a BenchmarkSuite

Class:
  ValidationHarness  — executes benchmarks and compares against expectations

Governance (ADR-009):
  - All benchmark runs are deterministic: same inputs → same outputs.
  - Every divergence is explicitly recorded with expected and actual values.
  - No silent suppression of differences.
  - Results are fully serializable via to_dict() for artifact storage.
  - The harness never modifies expectations. It only reads them.

Source: ADR-009 — Benchmark Governance.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.harness) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .benchmarks import (
    BenchmarkDefinition,
    BenchmarkSuite,
    ValidationSeverity,
)
from .comparison import compare_warning_codes
from ..calendar_ops import build_workday_table
from ..conventions import EFConvention
from ..engine import run_analysis
from ..models import Activity, Calendar, Relationship
from ..context import ENGINE_VERSION


# ---------------------------------------------------------------------------
# Divergence record
# ---------------------------------------------------------------------------

@dataclass
class Divergence:
    """
    A single field-level difference between expected and actual benchmark output.

    Fields:
        field:    Dot-path to the diverging field (e.g. "activities.A100.total_float").
        expected: Expected value (from BenchmarkExpectations).
        actual:   Actual value produced by the engine.
        severity: Risk classification of this divergence.
        message:  Human-readable description.
    """
    field: str
    expected: Any
    actual: Any
    severity: ValidationSeverity
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity.value,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Benchmark run result
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkRunResult:
    """
    Structured result of executing a single benchmark.

    Fields:
        benchmark_id:   Benchmark identifier.
        passed:         True when no divergences were detected.
        divergences:    All detected divergences.
        actual_output:  Serialized AnalysisResult (from to_dict()).
        run_timestamp:  ISO 8601 UTC timestamp.
        engine_version: mip39 version string at run time.
        convention:     EFConvention value used.
        severity:       Maximum severity across all divergences.
        error_message:  Set when an unexpected exception occurred.
    """
    benchmark_id: str
    passed: bool
    divergences: list[Divergence] = field(default_factory=list)
    actual_output: dict[str, Any] = field(default_factory=dict)
    run_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    engine_version: str = field(default_factory=lambda: ENGINE_VERSION)
    convention: str = "inclusive_day"
    severity: ValidationSeverity = ValidationSeverity.INFORMATIONAL
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "passed": self.passed,
            "divergences": [d.to_dict() for d in self.divergences],
            "actual_output": self.actual_output,
            "run_timestamp": self.run_timestamp,
            "engine_version": self.engine_version,
            "convention": self.convention,
            "severity": self.severity.value,
            "error_message": self.error_message,
        }


# ---------------------------------------------------------------------------
# Suite run result
# ---------------------------------------------------------------------------

@dataclass
class SuiteRunResult:
    """
    Structured result of executing a BenchmarkSuite.

    Fields:
        suite_id:           Suite identifier.
        suite_version:      Suite version.
        benchmark_results:  Dict of benchmark_id → BenchmarkRunResult.
        passed:             True when ALL benchmarks passed.
        total:              Total number of benchmarks run.
        passed_count:       Count of passing benchmarks.
        failed_count:       Count of failing benchmarks.
        run_timestamp:      ISO 8601 UTC timestamp.
    """
    suite_id: str
    suite_version: str
    benchmark_results: dict[str, BenchmarkRunResult] = field(default_factory=dict)
    run_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.benchmark_results.values())

    @property
    def total(self) -> int:
        return len(self.benchmark_results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.benchmark_results.values() if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.benchmark_results.values() if not r.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "passed": self.passed,
            "total": self.total,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "run_timestamp": self.run_timestamp,
            "benchmark_results": {
                k: v.to_dict() for k, v in self.benchmark_results.items()
            },
        }


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class ValidationHarness:
    """
    Deterministic benchmark execution and comparison engine.

    The harness:
      1. Reconstructs Activity, Relationship, and Calendar objects from the
         serialized BenchmarkDefinition inputs.
      2. Builds a workday table covering the project range.
      3. Calls run_analysis() with the specified convention.
      4. Compares the actual result against BenchmarkExpectations.
      5. Returns a BenchmarkRunResult with all divergences listed.

    The harness never modifies expectations. It is a read-only consumer
    of BenchmarkDefinition and a read-only producer of BenchmarkRunResult.

    Workday table coverage: project_start − 30 days to project_start + 1000 days,
    sufficient for all Phase 7 synthetic benchmarks.
    """

    _TABLE_PRE_DAYS = 30
    _TABLE_POST_DAYS = 1000

    def run_benchmark(self, bm: BenchmarkDefinition) -> BenchmarkRunResult:
        """
        Execute a single benchmark and compare against its expectations.

        Args:
            bm: The BenchmarkDefinition to execute.

        Returns:
            BenchmarkRunResult with passed/failed status and all divergences.
        """
        try:
            activities = self._build_activities(bm.activities)
            relationships = self._build_relationships(bm.relationships)
            calendar = self._build_calendar(bm.calendar_work_days, bm.hours_per_day)
            project_start = date.fromisoformat(bm.project_start)
            convention = self._resolve_convention(bm.convention)
            workday_table = self._build_workday_table(calendar, project_start)

            result = run_analysis(
                activities=activities,
                relationships=relationships,
                project_start=project_start,
                workday_table=workday_table,
                calendar=calendar,
                convention=convention,
            )

            actual_output = result.to_dict()
            divergences = self._compare(actual_output, bm)
            severity = self._max_severity(divergences)
            passed = len(divergences) == 0

            return BenchmarkRunResult(
                benchmark_id=bm.metadata.benchmark_id,
                passed=passed,
                divergences=divergences,
                actual_output=actual_output,
                convention=bm.convention,
                severity=severity,
            )

        except Exception as exc:  # noqa: BLE001
            return BenchmarkRunResult(
                benchmark_id=bm.metadata.benchmark_id,
                passed=False,
                divergences=[Divergence(
                    field="__execution__",
                    expected="no exception",
                    actual=str(exc),
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Unexpected exception during benchmark execution: {exc}",
                )],
                actual_output={},
                convention=bm.convention,
                severity=ValidationSeverity.CRITICAL,
                error_message=str(exc),
            )

    def run_suite(self, suite: BenchmarkSuite) -> SuiteRunResult:
        """
        Execute all benchmarks in a suite in definition order.

        Args:
            suite: The BenchmarkSuite to execute.

        Returns:
            SuiteRunResult with per-benchmark results and aggregate pass/fail.
        """
        suite_result = SuiteRunResult(
            suite_id=suite.suite_id,
            suite_version=suite.suite_version,
        )
        for bm_id in suite.benchmark_ids():
            bm = suite.get(bm_id)
            if bm is not None:
                suite_result.benchmark_results[bm_id] = self.run_benchmark(bm)
        return suite_result

    # ------------------------------------------------------------------
    # Input reconstruction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_activities(act_dicts: list[dict[str, Any]]) -> list[Activity]:
        return [
            Activity(
                act_id=d["act_id"],
                original_duration=d.get("original_duration"),
                actual_start=_parse_optional_date(d.get("actual_start")),
                actual_finish=_parse_optional_date(d.get("actual_finish")),
                constraint_type=d.get("constraint_type"),
                constraint_date=_parse_optional_date(d.get("constraint_date")),
                calendar_id=d.get("calendar_id"),
            )
            for d in act_dicts
        ]

    @staticmethod
    def _build_relationships(rel_dicts: list[dict[str, Any]]) -> list[Relationship]:
        return [
            Relationship(
                pred_id=d["pred_id"],
                succ_id=d["succ_id"],
                rel_type=d["rel_type"],
                lag=float(d.get("lag", 0.0)),
            )
            for d in rel_dicts
        ]

    @staticmethod
    def _build_calendar(work_days: list[int], hours_per_day: float) -> Calendar:
        return Calendar(
            name="benchmark_calendar",
            work_days=set(work_days),
            hours_per_day=hours_per_day,
        )

    @classmethod
    def _build_workday_table(
        cls,
        calendar: Calendar,
        project_start: date,
    ) -> dict[date, int]:
        table_start = project_start - timedelta(days=cls._TABLE_PRE_DAYS)
        table_end = project_start + timedelta(days=cls._TABLE_POST_DAYS)
        return build_workday_table(calendar, table_start, table_end)

    @staticmethod
    def _resolve_convention(convention_str: str) -> EFConvention:
        for c in EFConvention:
            if c.value == convention_str:
                return c
        raise ValueError(
            f"ValidationHarness: unknown convention {convention_str!r}. "
            f"Valid values: {[c.value for c in EFConvention]}."
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def _compare(
        self,
        actual_output: dict[str, Any],
        bm: BenchmarkDefinition,
    ) -> list[Divergence]:
        exp = bm.expectations
        divs: list[Divergence] = []

        # is_valid
        actual_valid = actual_output.get("is_valid")
        if actual_valid != exp.is_valid:
            divs.append(Divergence(
                field="is_valid",
                expected=exp.is_valid,
                actual=actual_valid,
                severity=ValidationSeverity.CRITICAL,
                message=f"is_valid: expected {exp.is_valid}, got {actual_valid}.",
            ))
            # If validity differs, remaining comparisons may not be meaningful
            return divs

        # project_finish
        if exp.project_finish is not None:
            actual_pf = actual_output.get("project_finish")
            if actual_pf != exp.project_finish:
                divs.append(Divergence(
                    field="project_finish",
                    expected=exp.project_finish,
                    actual=actual_pf,
                    severity=ValidationSeverity.ANALYTICAL,
                    message=(
                        f"project_finish: expected {exp.project_finish!r}, "
                        f"got {actual_pf!r}."
                    ),
                ))

        # Activity-level fields
        actual_sched = actual_output.get("scheduled", {})
        for act_id, exp_act in exp.activities.items():
            actual_act = actual_sched.get(act_id)
            if actual_act is None:
                divs.append(Divergence(
                    field=f"scheduled.{act_id}",
                    expected="present",
                    actual="absent",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Activity {act_id!r} absent from scheduled output.",
                ))
                continue
            divs.extend(self._compare_activity(act_id, exp_act.to_dict(), actual_act))

        # Critical path
        actual_cp = actual_output.get("critical_path")
        if actual_cp is not None and exp.is_valid:
            divs.extend(self._compare_critical_path(actual_cp, exp))

        # Warnings
        divs.extend(self._compare_warnings(actual_output, exp.warning_codes_present))

        return divs

    @staticmethod
    def _compare_activity(
        act_id: str,
        expected: dict[str, Any],
        actual: dict[str, Any],
    ) -> list[Divergence]:
        divs: list[Divergence] = []
        date_fields = ("early_start", "early_finish", "late_start", "late_finish")
        float_fields = ("total_float", "free_float")

        for f in date_fields:
            if expected[f] != actual.get(f):
                divs.append(Divergence(
                    field=f"scheduled.{act_id}.{f}",
                    expected=expected[f],
                    actual=actual.get(f),
                    severity=ValidationSeverity.ANALYTICAL,
                    message=(
                        f"{act_id}.{f}: expected {expected[f]!r}, "
                        f"got {actual.get(f)!r}."
                    ),
                ))
        for f in float_fields:
            if expected[f] != actual.get(f):
                divs.append(Divergence(
                    field=f"scheduled.{act_id}.{f}",
                    expected=expected[f],
                    actual=actual.get(f),
                    severity=ValidationSeverity.ANALYTICAL,
                    message=(
                        f"{act_id}.{f}: expected {expected[f]}, "
                        f"got {actual.get(f)}."
                    ),
                ))
        if expected["is_critical"] != actual.get("is_critical"):
            divs.append(Divergence(
                field=f"scheduled.{act_id}.is_critical",
                expected=expected["is_critical"],
                actual=actual.get("is_critical"),
                severity=ValidationSeverity.ANALYTICAL,
                message=(
                    f"{act_id}.is_critical: expected {expected['is_critical']}, "
                    f"got {actual.get('is_critical')}."
                ),
            ))
        return divs

    @staticmethod
    def _compare_critical_path(
        actual_cp: dict[str, Any],
        exp: Any,  # BenchmarkExpectations
    ) -> list[Divergence]:
        divs: list[Divergence] = []
        actual_ids = actual_cp.get("activity_ids", [])
        exp_ids = exp.critical_path_activity_ids

        if sorted(actual_ids) != sorted(exp_ids):
            divs.append(Divergence(
                field="critical_path.activity_ids",
                expected=exp_ids,
                actual=actual_ids,
                severity=ValidationSeverity.ANALYTICAL,
                message=(
                    f"Critical path composition differs: "
                    f"expected {exp_ids}, got {actual_ids}."
                ),
            ))

        # project_duration
        actual_dur = actual_cp.get("project_duration")
        if actual_dur != exp.project_duration:
            divs.append(Divergence(
                field="critical_path.project_duration",
                expected=exp.project_duration,
                actual=actual_dur,
                severity=ValidationSeverity.ANALYTICAL,
                message=(
                    f"project_duration: expected {exp.project_duration}, "
                    f"got {actual_dur}."
                ),
            ))

        # tied_paths
        actual_tied = actual_cp.get("tied_paths", False)
        if actual_tied != exp.tied_paths:
            divs.append(Divergence(
                field="critical_path.tied_paths",
                expected=exp.tied_paths,
                actual=actual_tied,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"tied_paths: expected {exp.tied_paths}, got {actual_tied}."
                ),
            ))

        # divergence_flags
        actual_flags = sorted(actual_cp.get("divergence_flags", []))
        exp_flags = sorted(exp.divergence_flags)
        if actual_flags != exp_flags:
            divs.append(Divergence(
                field="critical_path.divergence_flags",
                expected=exp_flags,
                actual=actual_flags,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"divergence_flags: expected {exp_flags}, got {actual_flags}."
                ),
            ))
        return divs

    @staticmethod
    def _compare_warnings(
        actual_output: dict[str, Any],
        expected_codes: list[str],
    ) -> list[Divergence]:
        actual_warnings = actual_output.get("warnings", [])
        actual_codes = [w.get("code", "") for w in actual_warnings]
        warn_diff = compare_warning_codes(expected_codes, actual_codes)
        divs: list[Divergence] = []
        if warn_diff.missing:
            divs.append(Divergence(
                field="warnings.codes",
                expected=warn_diff.expected_codes,
                actual=warn_diff.actual_codes,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Missing warning codes: {sorted(warn_diff.missing)}."
                ),
            ))
        # Extra codes: engine emitted warning codes not listed in the benchmark
        # expectations. WARNING severity — symmetric to missing codes: both
        # indicate the engine's warning behavior has deviated from specification.
        if warn_diff.extra:
            divs.append(Divergence(
                field="warnings.codes",
                expected=warn_diff.expected_codes,
                actual=warn_diff.actual_codes,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Unexpected warning codes: {sorted(warn_diff.extra)}."
                ),
            ))
        return divs

    @staticmethod
    def _max_severity(divergences: list[Divergence]) -> ValidationSeverity:
        if not divergences:
            return ValidationSeverity.INFORMATIONAL
        order = [
            ValidationSeverity.INFORMATIONAL,
            ValidationSeverity.WARNING,
            ValidationSeverity.ANALYTICAL,
            ValidationSeverity.CRITICAL,
        ]
        return max(divergences, key=lambda d: order.index(d.severity)).severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_optional_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    return date.fromisoformat(value)
