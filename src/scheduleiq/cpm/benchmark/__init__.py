"""
Phase 7 Validation Framework — INFRA-015 through INFRA-018.

Provides the formal validation infrastructure for the MIP 3.9 analytical engine:
  - Benchmark definitions and suites (INFRA-011)
  - Machine-readable comparison artifacts (INFRA-012)
  - Regression governance and approval workflow (INFRA-013)
  - Validation artifact infrastructure (INFRA-014)
  - Reproducibility verification (INFRA-015)
  - Validation execution harness (INFRA-016)

Public API:

    from mip39.validation_framework import (
        # Benchmark structures
        BenchmarkDefinition, BenchmarkSuite, BenchmarkExpectations,
        ExpectedActivityResult, BenchmarkMetadata, BenchmarkCategory,
        ValidationSeverity, BENCHMARK_FRAMEWORK_VERSION,

        # Harness and results
        ValidationHarness, BenchmarkRunResult, SuiteRunResult, Divergence,

        # Comparison
        compare_float_results, compare_date_results,
        compare_paths, compare_warning_codes,
        FloatDiff, DateDiff, PathDiff, WarningDiff, ConventionDiff,

        # Regression governance
        RegressionChecker, RegressionResult, BenchmarkDiff, ApprovalStatus,

        # Reproducibility
        ReproducibilityChecker, ReproducibilityResult,

        # Artifacts
        ValidationArtifact, ValidationProvenance, ArtifactRegistry,

        # Canonical fixtures
        PHASE7_SUITE, build_phase7_suite,
    )

Governance: ADR-009, ADR-010.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.__init__) per ADR-0007 — port-and-validate.
"""

from .benchmarks import (
    BENCHMARK_FRAMEWORK_VERSION,
    BenchmarkCategory,
    BenchmarkDefinition,
    BenchmarkExpectations,
    BenchmarkMetadata,
    BenchmarkSuite,
    ExpectedActivityResult,
    ValidationSeverity,
)
from .comparison import (
    ConventionDiff,
    DateDiff,
    FloatDiff,
    NormalizationDiff,
    PathDiff,
    WarningDiff,
    compare_date_results,
    compare_float_results,
    compare_paths,
    compare_warning_codes,
)
from .regression import (
    ApprovalStatus,
    BenchmarkDiff,
    RegressionChecker,
    RegressionResult,
)
from .artifacts import (
    ArtifactRegistry,
    ValidationArtifact,
    ValidationProvenance,
)
from .reproducibility import (
    ReproducibilityChecker,
    ReproducibilityResult,
)
from .harness import (
    BenchmarkRunResult,
    Divergence,
    SuiteRunResult,
    ValidationHarness,
)
from .fixtures import (
    MULTI_CALENDAR_SUITE,
    NORMALIZATION_SUITE,
    PHASE7_SUITE,
    build_multi_calendar_suite,
    build_normalization_suite,
    build_phase7_suite,
)

__all__ = [
    # benchmarks
    "BENCHMARK_FRAMEWORK_VERSION",
    "BenchmarkCategory",
    "BenchmarkDefinition",
    "BenchmarkExpectations",
    "BenchmarkMetadata",
    "BenchmarkSuite",
    "ExpectedActivityResult",
    "ValidationSeverity",
    # comparison
    "ConventionDiff",
    "DateDiff",
    "FloatDiff",
    "NormalizationDiff",
    "PathDiff",
    "WarningDiff",
    "compare_date_results",
    "compare_float_results",
    "compare_paths",
    "compare_warning_codes",
    # regression
    "ApprovalStatus",
    "BenchmarkDiff",
    "RegressionChecker",
    "RegressionResult",
    # artifacts
    "ArtifactRegistry",
    "ValidationArtifact",
    "ValidationProvenance",
    # reproducibility
    "ReproducibilityChecker",
    "ReproducibilityResult",
    # harness
    "BenchmarkRunResult",
    "Divergence",
    "SuiteRunResult",
    "ValidationHarness",
    # fixtures
    "MULTI_CALENDAR_SUITE",
    "NORMALIZATION_SUITE",
    "PHASE7_SUITE",
    "build_multi_calendar_suite",
    "build_normalization_suite",
    "build_phase7_suite",
]
