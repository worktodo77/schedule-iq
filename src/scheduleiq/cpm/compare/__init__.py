"""
V1-G: CPW Comparison Validation package.

Public API for comparing mip39 AnalysisResult outputs against historical
CPW reference schedules under governed tolerance and policy rules.

CPW is an operational comparison reference, NOT the mathematical authority.
AACE RPs and Long International methodology remain authoritative. Divergence
from CPW is acceptable when analytically justified, deterministic, reproducible,
documented, and disclosed. Exact P6 emulation is NOT the objective.

Entry point: compare_schedules(analysis_result, reference) → ScheduleComparison

Source: ADR-016.

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.__init__) per ADR-0007 — port-and-validate.
"""

from .comparator import (
    compare_schedules,
    run_lag_strategy_experiment,
    ActivityComparison,
    FieldComparison,
    LagStrategyExperiment,
    LagStrategyResult,
    ScheduleComparison,
)
from .divergences import (
    DivergenceAccumulator,
    DivergenceCategory,
    DivergenceRecord,
)
from .tolerances import (
    NAMED_TOLERANCE_POLICIES,
    TOLERANCE_ADVISORY,
    TOLERANCE_CALENDAR_AWARE,
    TOLERANCE_STRICT,
    TolerancePolicy,
    ToleranceType,
    within_tolerance,
)
from .policies import (
    ComparisonPolicy,
    ComparisonPolicyConfig,
    get_comparison_policy_config,
)
from .checkpoints import (
    ComparisonCheckpoint,
    ComparisonCheckpointRegistry,
    ComparisonCheckpointStatus,
)
from .provenance import (
    ComparisonProvenance,
    ComparisonStageRecord,
    build_comparison_provenance,
)
from .metrics import ComparisonMetrics
from .fixtures import (
    COMPARISON_FIXTURES,
    ComparisonFixture,
    ReferenceSchedule,
    ReferenceScheduledActivity,
    get_comparison_fixture,
)
from .summaries import ComparisonSummary, LagStrategyExperimentSummary

__all__ = [
    # Entry points
    "compare_schedules",
    "run_lag_strategy_experiment",
    # Comparison results
    "ScheduleComparison",
    "ActivityComparison",
    "FieldComparison",
    "LagStrategyExperiment",
    "LagStrategyResult",
    # Divergence framework
    "DivergenceCategory",
    "DivergenceRecord",
    "DivergenceAccumulator",
    # Tolerance governance
    "ToleranceType",
    "TolerancePolicy",
    "within_tolerance",
    "TOLERANCE_STRICT",
    "TOLERANCE_CALENDAR_AWARE",
    "TOLERANCE_ADVISORY",
    "NAMED_TOLERANCE_POLICIES",
    # Comparison policy
    "ComparisonPolicy",
    "ComparisonPolicyConfig",
    "get_comparison_policy_config",
    # Analyst checkpoints
    "ComparisonCheckpointStatus",
    "ComparisonCheckpoint",
    "ComparisonCheckpointRegistry",
    # Provenance
    "ComparisonStageRecord",
    "ComparisonProvenance",
    "build_comparison_provenance",
    # Metrics
    "ComparisonMetrics",
    # Reference fixtures
    "ReferenceScheduledActivity",
    "ReferenceSchedule",
    "ComparisonFixture",
    "COMPARISON_FIXTURES",
    "get_comparison_fixture",
    # Summaries
    "ComparisonSummary",
    "LagStrategyExperimentSummary",
]
