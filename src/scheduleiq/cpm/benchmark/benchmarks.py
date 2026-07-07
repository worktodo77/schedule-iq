"""
INFRA-015: Phase 7 Benchmark Definition Structures.

Defines the core data structures for the MIP 3.9 validation framework:
  ValidationSeverity    — severity levels for divergence classification
  BenchmarkCategory     — controlled categories for benchmark organization
  BenchmarkMetadata     — provenance and traceability metadata per benchmark
  ExpectedActivityResult — expected per-activity CPM output
  BenchmarkExpectations — complete expected output specification
  BenchmarkDefinition   — full benchmark: inputs + expectations + metadata
  BenchmarkSuite        — ordered collection of related benchmarks

Governance requirements (ADR-009):
  - All benchmarks are versioned and immutable once committed.
  - Expected outputs are explicitly distinguished from actual outputs.
  - Baseline-captured flag distinguishes hand-verified from engine-captured baselines.
  - No silent updates. Baseline changes require explicit approval records.
  - All structures serializable via to_dict() for provenance and artifact storage.

Source: ADR-009 — Benchmark Governance.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.benchmarks) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


BENCHMARK_FRAMEWORK_VERSION: str = "1.0-phase7"


# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

class ValidationSeverity(Enum):
    """
    Severity classification for a divergence detected during benchmark validation.

    Members:
        INFORMATIONAL: Minor difference; does not affect analytical conclusions.
                       Example: warning message wording differs but code matches.
        WARNING:       Difference requires analyst attention; may affect secondary
                       outputs. Example: free-float value differs by 1 workday.
        ANALYTICAL:    Difference affects primary analytical outputs (critical
                       path, total float). High forensic risk. Analyst must review.
        CRITICAL:      Fundamental benchmark failure. Engine produced an invalid
                       result or raised an unexpected exception. Blocks reliance.

    Ordering: INFORMATIONAL < WARNING < ANALYTICAL < CRITICAL.
    """
    INFORMATIONAL = "informational"
    WARNING = "warning"
    ANALYTICAL = "analytical"
    CRITICAL = "critical"

    def is_at_least(self, other: "ValidationSeverity") -> bool:
        """Return True if this severity is >= other in risk ordering."""
        order = [
            ValidationSeverity.INFORMATIONAL,
            ValidationSeverity.WARNING,
            ValidationSeverity.ANALYTICAL,
            ValidationSeverity.CRITICAL,
        ]
        return order.index(self) >= order.index(other)


# ---------------------------------------------------------------------------
# Benchmark categories
# ---------------------------------------------------------------------------

class BenchmarkCategory(Enum):
    """
    Controlled category taxonomy for benchmark organization.

    All Phase 7 benchmarks are synthetic (no proprietary schedules).
    Categories correspond to the Phase 7 authorized fixture types.
    """
    SIMPLE_FS = "simple_fs"
    SS_FF_SF = "ss_ff_sf"
    LAG_HEAVY = "lag_heavy"
    BRANCHING = "branching"
    MERGE = "merge"
    TIED_LONGEST_PATH = "tied_longest_path"
    TF_DIVERGENCE = "tf_divergence"
    CONVENTION_DIVERGENCE = "convention_divergence"
    EDGE_CASE = "edge_case"
    INVALID_NETWORK = "invalid_network"
    NORMALIZATION_WARNING = "normalization_warning"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    # V1-B.1 multi-calendar categories
    MULTI_CALENDAR_REGISTRY = "multi_calendar_registry"
    MULTI_CALENDAR_EXCEPTION_DATES = "multi_calendar_exception_dates"
    MULTI_CALENDAR_LAG_STRATEGY = "multi_calendar_lag_strategy"
    MULTI_CALENDAR_BINDING = "multi_calendar_binding"
    MULTI_CALENDAR_ENGINE = "multi_calendar_engine"
    # V1-C normalization category
    NORMALIZATION = "normalization"
    # V1-D destatusing category
    DESTATUSING = "destatusing"
    # V1-E simulation schedule generation category
    SIMULATION = "simulation"
    # V1-G CPW comparison validation category
    COMPARISON = "comparison"


# ---------------------------------------------------------------------------
# Benchmark metadata
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkMetadata:
    """
    Provenance and traceability metadata for a single benchmark definition.

    Fields:
        benchmark_id:      Unique identifier (e.g. "BM-001").
        benchmark_version: Version string for this benchmark definition.
        description:       Human-readable description of the scenario tested.
        category:          BenchmarkCategory classifying the benchmark type.
        source:            Data source. Always "synthetic" in Phase 7.
        assumptions:       Documented analytical assumptions for this benchmark.
        tags:              Optional classification tags for filtering.
    """
    benchmark_id: str
    benchmark_version: str
    description: str
    category: BenchmarkCategory
    source: str = "synthetic"
    assumptions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_version": self.benchmark_version,
            "description": self.description,
            "category": self.category.value,
            "source": self.source,
            "assumptions": list(self.assumptions),
            "tags": list(self.tags),
        }


# ---------------------------------------------------------------------------
# Expected per-activity result
# ---------------------------------------------------------------------------

@dataclass
class ExpectedActivityResult:
    """
    Expected CPM output for a single activity.

    All date fields are ISO 8601 strings (YYYY-MM-DD).

    Fields:
        activity_id:    Activity identifier matching the benchmark input.
        early_start:    Expected Early Start date.
        early_finish:   Expected Early Finish date.
        late_start:     Expected Late Start date.
        late_finish:    Expected Late Finish date.
        total_float:    Expected Total Float in workdays.
        free_float:     Expected Free Float in workdays.
        is_critical:    Expected longest-path criticality.
    """
    activity_id: str
    early_start: str
    early_finish: str
    late_start: str
    late_finish: str
    total_float: int
    free_float: int
    is_critical: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "early_start": self.early_start,
            "early_finish": self.early_finish,
            "late_start": self.late_start,
            "late_finish": self.late_finish,
            "total_float": self.total_float,
            "free_float": self.free_float,
            "is_critical": self.is_critical,
        }


# ---------------------------------------------------------------------------
# Benchmark expectations
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkExpectations:
    """
    Complete expected output specification for a benchmark.

    Explicitly distinguishes:
        - What the benchmark expects (this object).
        - What the engine actually produces (BenchmarkRunResult.actual_output).
        - Whether any difference has been approved (RegressionResult.approval_status).

    Fields:
        is_valid:                  Expected is_valid flag from AnalysisResult.
        project_finish:            Expected project finish date (ISO 8601), or None.
        project_duration:          Expected project duration in workdays.
        critical_path_activity_ids: Expected activity IDs on the critical path.
        activities:                 Expected results per activity (act_id → expected).
        warning_codes_present:     Warning codes expected to appear in the result.
        divergence_flags:          Expected CP-001..CP-004 or CV-001..CV-004 flags.
        tied_paths:                Expected tied_paths flag on CriticalPathInfo.
        convention:                EFConvention value used when producing expectations.
        baseline_captured:         True = expected values captured from engine output.
                                   False = hand-verified by analyst.
    """
    is_valid: bool
    project_finish: Optional[str]
    project_duration: int
    critical_path_activity_ids: list[str]
    activities: dict[str, ExpectedActivityResult]
    warning_codes_present: list[str] = field(default_factory=list)
    divergence_flags: list[str] = field(default_factory=list)
    tied_paths: bool = False
    convention: str = "inclusive_day"
    baseline_captured: bool = False
    expected_diagnostic_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "project_finish": self.project_finish,
            "project_duration": self.project_duration,
            "critical_path_activity_ids": list(self.critical_path_activity_ids),
            "activities": {k: v.to_dict() for k, v in self.activities.items()},
            "warning_codes_present": list(self.warning_codes_present),
            "divergence_flags": list(self.divergence_flags),
            "tied_paths": self.tied_paths,
            "convention": self.convention,
            "baseline_captured": self.baseline_captured,
            "expected_diagnostic_codes": list(self.expected_diagnostic_codes),
        }


# ---------------------------------------------------------------------------
# Benchmark definition
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkDefinition:
    """
    Full benchmark definition: analytical inputs + expected outputs + metadata.

    Inputs are stored as serializable dicts so the definition is self-contained
    and does not depend on live engine objects. The harness reconstructs
    Activity, Relationship, and Calendar objects from these dicts at run time.

    Activity dicts: {"act_id": str, "original_duration": int, ...optional fields}
    Relationship dicts: {"pred_id": str, "succ_id": str, "rel_type": str, "lag": float}

    Fields:
        metadata:           Benchmark provenance and classification.
        activities:         List of activity constructor-kwarg dicts.
        relationships:      List of relationship constructor-kwarg dicts.
        project_start:      ISO 8601 date string for project start.
        calendar_work_days: ISO weekday numbers for workdays (default [1,2,3,4,5]).
        hours_per_day:      Working hours per day (default 8.0).
        convention:         EFConvention value string ("inclusive_day" or "p6_compatibility").
        expectations:       Expected output specification.
    """
    metadata: BenchmarkMetadata
    activities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    project_start: str
    calendar_work_days: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    hours_per_day: float = 8.0
    convention: str = "inclusive_day"
    expectations: BenchmarkExpectations = field(
        default_factory=lambda: BenchmarkExpectations(
            is_valid=True,
            project_finish=None,
            project_duration=0,
            critical_path_activity_ids=[],
            activities={},
        )
    )
    extra_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "metadata": self.metadata.to_dict(),
            "activities": list(self.activities),
            "relationships": list(self.relationships),
            "project_start": self.project_start,
            "calendar_work_days": list(self.calendar_work_days),
            "hours_per_day": self.hours_per_day,
            "convention": self.convention,
            "expectations": self.expectations.to_dict(),
        }
        if self.extra_data:
            d["extra_data"] = dict(self.extra_data)
        return d


# ---------------------------------------------------------------------------
# Benchmark suite
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkSuite:
    """
    Ordered collection of benchmark definitions.

    A suite groups related benchmarks and provides a single execution target
    for the ValidationHarness. Suite identity is versioned independently of
    individual benchmark versions.

    Fields:
        suite_id:          Unique suite identifier (e.g. "SUITE-001").
        suite_version:     Version of this suite definition.
        description:       Human-readable description of what this suite covers.
        benchmarks:        Ordered dict of benchmark_id → BenchmarkDefinition.
        framework_version: Version of the benchmark framework (auto-set).
    """
    suite_id: str
    suite_version: str
    description: str
    benchmarks: dict[str, BenchmarkDefinition] = field(default_factory=dict)
    framework_version: str = BENCHMARK_FRAMEWORK_VERSION

    def add(self, bm: BenchmarkDefinition) -> None:
        """Add a benchmark definition to the suite."""
        self.benchmarks[bm.metadata.benchmark_id] = bm

    def __iter__(self):
        """Iterate over BenchmarkDefinition objects in insertion order."""
        return iter(self.benchmarks.values())

    def get(self, benchmark_id: str) -> Optional[BenchmarkDefinition]:
        """Return the named benchmark or None."""
        return self.benchmarks.get(benchmark_id)

    def benchmark_ids(self) -> list[str]:
        """Return benchmark IDs in insertion order."""
        return list(self.benchmarks.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "description": self.description,
            "framework_version": self.framework_version,
            "benchmark_ids": self.benchmark_ids(),
            "benchmarks": {k: v.to_dict() for k, v in self.benchmarks.items()},
        }
