"""
V1-G: Comparison run summary structures.

ComparisonSummary provides a structured, serializable summary of a comparison
run suitable for audit trail generation and future report embedding.

The summary is deliberately separate from ScheduleComparison to allow
lightweight summary-only serialization (e.g., for logging or index records)
without serializing the full per-activity comparison detail.

Source: ADR-016.

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.summaries) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .metrics import ComparisonMetrics


@dataclass
class ComparisonSummary:
    """
    High-level summary of a comparison run.

    Fields:
        run_id:                 UUID from ComparisonProvenance.run_id.
        timestamp_utc:          Run start timestamp.
        reference_id:           ReferenceSchedule.schedule_id.
        reference_source:       ReferenceSchedule.source.
        policy:                 ComparisonPolicy name.
        tolerance_policy:       TolerancePolicy name.
        is_blocked:             True when unresolved blocking checkpoints exist.
        metrics:                ComparisonMetrics for this run.
        divergence_summary:     dict[category_name → count].
        checkpoint_summary:     dict[status → count].
        blocking_divergences:   Summary of unresolved blocking divergences.
        lag_strategy_finding:   Summary of lag calendar strategy investigation.
        analyst_notes:          Free-form notes from analyst review.
        context:                Caller context string.
    """

    run_id: str
    timestamp_utc: str
    reference_id: str
    reference_source: str
    policy: str
    tolerance_policy: str
    is_blocked: bool
    metrics: ComparisonMetrics
    divergence_summary: dict[str, int] = field(default_factory=dict)
    checkpoint_summary: dict[str, int] = field(default_factory=dict)
    blocking_divergences: list[str] = field(default_factory=list)
    lag_strategy_finding: str = ""
    analyst_notes: str = ""
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "reference_id": self.reference_id,
            "reference_source": self.reference_source,
            "policy": self.policy,
            "tolerance_policy": self.tolerance_policy,
            "is_blocked": self.is_blocked,
            "metrics": self.metrics.to_dict(),
            "divergence_summary": dict(self.divergence_summary),
            "checkpoint_summary": dict(self.checkpoint_summary),
            "blocking_divergences": list(self.blocking_divergences),
            "lag_strategy_finding": self.lag_strategy_finding,
            "analyst_notes": self.analyst_notes,
            "context": self.context,
        }


@dataclass
class LagStrategyExperimentSummary:
    """
    Summary of a lag calendar strategy sensitivity experiment.

    Records which activities are affected by lag strategy choice and the
    magnitude of differences. This is the primary V1-G deliverable for the
    per-relationship lag calendar investigation.

    Fields:
        strategies_tested:           List of LagCalendarStrategy names tested.
        baseline_strategy:           Strategy used as the reference baseline.
        affected_activities:         Activity IDs where any strategy produces
                                     a different result from the baseline.
        max_date_delta_days:         Maximum date difference (calendar days)
                                     across all activities and all strategy pairs.
        max_float_delta:             Maximum float difference across all pairs.
        finish_date_deltas:          dict[strategy_name → finish_date_delta_days].
        finding:                     Analytical conclusion string.
        per_relationship_mandatory:  True if evidence suggests per-relationship
                                     lag calendar assignment is required.
    """

    strategies_tested: list[str] = field(default_factory=list)
    baseline_strategy: str = "predecessor_calendar"
    affected_activities: list[str] = field(default_factory=list)
    max_date_delta_days: int = 0
    max_float_delta: int = 0
    finish_date_deltas: dict[str, Optional[int]] = field(default_factory=dict)
    finding: str = ""
    per_relationship_mandatory: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategies_tested": list(self.strategies_tested),
            "baseline_strategy": self.baseline_strategy,
            "affected_activities": list(self.affected_activities),
            "max_date_delta_days": self.max_date_delta_days,
            "max_float_delta": self.max_float_delta,
            "finish_date_deltas": dict(self.finish_date_deltas),
            "finding": self.finding,
            "per_relationship_mandatory": self.per_relationship_mandatory,
        }
