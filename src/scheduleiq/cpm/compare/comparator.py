"""
V1-G: CPW comparison engine.

compare_schedules() is the primary entry point. It compares a mip39
AnalysisResult against a ReferenceSchedule field by field, applying tolerance
policies and classifying divergences.

Pipeline:
  1. Validate inputs — check that analysis result is valid.
  2. Identify activities — union of mip39 and reference activity IDs (sorted).
  3. Per-activity field comparison — 8 fields compared with tolerance.
  4. Project-level comparison — project_finish and critical_path.
  5. Divergence classification — auto-classify unresolved divergences.
  6. Checkpoint generation — policy-driven analyst checkpoints.
  7. Metrics computation — activity match %, float variance, etc.
  8. Provenance recording — stage-by-stage pipeline trace.
  9. Blocking determination — is_blocked flag.
 10. Summary assembly — ComparisonSummary.

run_lag_strategy_experiment() runs the same schedule under all four
LagCalendarStrategy values and cross-compares results to determine whether
per-relationship lag calendar assignment is necessary for V1 release.

All comparisons are deterministic: activity ordering is sorted by act_id,
field ordering is fixed. Same inputs → same ScheduleComparison output.

Source: ADR-016; ADR-005 (determinism, traceability).

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.comparator) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..calendar_registry import LagCalendarStrategy
from .divergences import DivergenceAccumulator, DivergenceCategory, DivergenceRecord
from .tolerances import TolerancePolicy, within_tolerance
from .policies import ComparisonPolicy, ComparisonPolicyConfig, get_comparison_policy_config
from .checkpoints import ComparisonCheckpoint, ComparisonCheckpointRegistry
from .provenance import (
    ComparisonProvenance,
    ComparisonStageRecord,
    build_comparison_provenance,
)
from .metrics import ComparisonMetrics
from .fixtures import ReferenceSchedule, ReferenceScheduledActivity
from .summaries import ComparisonSummary, LagStrategyExperimentSummary


# Fields compared per-activity. Order is fixed for determinism.
_ACTIVITY_FIELDS: list[str] = [
    "early_start",
    "early_finish",
    "late_start",
    "late_finish",
    "total_float",
    "free_float",
    "is_critical",
    "original_duration",
]

# Date fields for auto-classification
_DATE_FIELDS = frozenset({"early_start", "early_finish", "late_start", "late_finish"})
_FLOAT_FIELDS = frozenset({"total_float", "free_float", "is_critical"})


# ---------------------------------------------------------------------------
# Per-field comparison result
# ---------------------------------------------------------------------------

@dataclass
class FieldComparison:
    """
    Comparison result for a single activity field.

    Fields:
        field:             Field name.
        mip39_value:       Value from the mip39 engine.
        reference_value:   Value from the reference schedule. None = not provided.
        is_exact_match:    True when values are identical (before tolerance).
        is_within_tolerance: True when difference is within policy tolerance.
        delta:             Numeric difference (mip39 - reference), or None.
        divergence:        DivergenceRecord if out of tolerance, else None.
        skipped:           True when reference_value is None (field not compared).
    """

    field: str
    mip39_value: Any
    reference_value: Any
    is_exact_match: bool
    is_within_tolerance: bool
    delta: Optional[float]
    divergence: Optional[DivergenceRecord] = None
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        def _ser(v: Any) -> Any:
            return v.isoformat() if isinstance(v, date) else v

        return {
            "field": self.field,
            "mip39_value": _ser(self.mip39_value),
            "reference_value": _ser(self.reference_value),
            "is_exact_match": self.is_exact_match,
            "is_within_tolerance": self.is_within_tolerance,
            "delta": self.delta,
            "divergence_id": self.divergence.div_id if self.divergence else None,
            "skipped": self.skipped,
        }


# ---------------------------------------------------------------------------
# Per-activity comparison result
# ---------------------------------------------------------------------------

@dataclass
class ActivityComparison:
    """
    Comparison result for all fields of one activity.

    Fields:
        act_id:               Activity identifier.
        field_comparisons:    FieldComparison per field in _ACTIVITY_FIELDS order.
        is_exact_match:       True when all non-skipped fields match exactly.
        is_within_tolerance:  True when all non-skipped fields are within tolerance.
        has_divergences:      True when any field is out of tolerance.
        divergence_count:     Count of out-of-tolerance fields.
    """

    act_id: str
    field_comparisons: list[FieldComparison] = field(default_factory=list)
    is_exact_match: bool = True
    is_within_tolerance: bool = True
    has_divergences: bool = False
    divergence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "act_id": self.act_id,
            "is_exact_match": self.is_exact_match,
            "is_within_tolerance": self.is_within_tolerance,
            "has_divergences": self.has_divergences,
            "divergence_count": self.divergence_count,
            "field_comparisons": [fc.to_dict() for fc in self.field_comparisons],
        }


# ---------------------------------------------------------------------------
# Full schedule comparison result
# ---------------------------------------------------------------------------

@dataclass
class ScheduleComparison:
    """
    Complete comparison result for one mip39 vs reference comparison run.

    Fields:
        policy:               ComparisonPolicy applied.
        tolerance_policy:     TolerancePolicy applied.
        activity_comparisons: Per-activity results in sorted act_id order.
        finish_comparison:    FieldComparison for project_finish, or None.
        critical_path_comparison: dict with cp_mip39, cp_ref, agreement, divergences.
        divergences:          All divergence records for this run.
        checkpoints:          Policy-driven analyst checkpoints.
        metrics:              Quantitative comparison metrics.
        provenance:           Comparison run provenance.
        summary:              High-level comparison summary.
        is_blocked:           True when unresolved blocking checkpoints exist.
    """

    policy: ComparisonPolicy
    tolerance_policy: TolerancePolicy
    activity_comparisons: list[ActivityComparison] = field(default_factory=list)
    finish_comparison: Optional[FieldComparison] = None
    critical_path_comparison: dict[str, Any] = field(default_factory=dict)
    divergences: DivergenceAccumulator = field(default_factory=DivergenceAccumulator)
    checkpoints: ComparisonCheckpointRegistry = field(
        default_factory=ComparisonCheckpointRegistry
    )
    metrics: ComparisonMetrics = field(default_factory=ComparisonMetrics)
    provenance: Optional[ComparisonProvenance] = None
    summary: Optional[ComparisonSummary] = None
    is_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.value,
            "tolerance_policy": self.tolerance_policy.to_dict(),
            "is_blocked": self.is_blocked,
            "metrics": self.metrics.to_dict(),
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "summary": self.summary.to_dict() if self.summary else None,
            "finish_comparison": (
                self.finish_comparison.to_dict() if self.finish_comparison else None
            ),
            "critical_path_comparison": self.critical_path_comparison,
            "divergences": self.divergences.to_dict_list(),
            "checkpoints": self.checkpoints.to_dict_list(),
            "activity_comparisons": [ac.to_dict() for ac in self.activity_comparisons],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_mip39_field(sa: Any, field_name: str) -> Any:
    """Extract a field value from a ScheduledActivity by name."""
    return getattr(sa, field_name, None)


def _get_ref_field(ra: ReferenceScheduledActivity, field_name: str) -> Any:
    """Extract a field value from a ReferenceScheduledActivity by name."""
    return getattr(ra, field_name, None)


def _auto_classify(
    field_name: str,
    delta: Optional[float],
    has_calendar_registry: bool,
) -> DivergenceCategory:
    """
    Auto-classify a divergence category based on field name and context.

    This is a best-effort heuristic. Analysts can override the category
    via DivergenceRecord.reclassify().
    """
    if field_name in _DATE_FIELDS:
        if has_calendar_registry:
            return DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE
        return DivergenceCategory.UNKNOWN_DIFFERENCE
    if field_name in _FLOAT_FIELDS:
        return DivergenceCategory.FLOAT_METHOD_DIFFERENCE
    return DivergenceCategory.UNKNOWN_DIFFERENCE


def _compare_activity_fields(
    act_id: str,
    sa: Any,
    ra: ReferenceScheduledActivity,
    tolerance_policy: TolerancePolicy,
    divergences: DivergenceAccumulator,
    has_calendar_registry: bool,
) -> ActivityComparison:
    """Compare all fields for one activity. Returns an ActivityComparison."""
    ac = ActivityComparison(act_id=act_id)

    for fname in _ACTIVITY_FIELDS:
        mip39_val = _get_mip39_field(sa, fname)
        ref_val = _get_ref_field(ra, fname)

        if ref_val is None:
            fc = FieldComparison(
                field=fname,
                mip39_value=mip39_val,
                reference_value=None,
                is_exact_match=True,
                is_within_tolerance=True,
                delta=None,
                skipped=True,
            )
            ac.field_comparisons.append(fc)
            continue

        exact = mip39_val == ref_val
        in_tol, delta = within_tolerance(fname, mip39_val, ref_val, tolerance_policy)

        divergence_rec = None
        if not in_tol:
            category = _auto_classify(fname, delta, has_calendar_registry)
            explanation = (
                f"Activity {act_id!r} field {fname!r}: "
                f"mip39={mip39_val!r}, reference={ref_val!r}"
                + (f", delta={delta}" if delta is not None else "")
                + f". Auto-classified as {category.value}."
            )
            divergence_rec = divergences.add(
                act_id=act_id,
                field=fname,
                mip39_value=mip39_val,
                reference_value=ref_val,
                category=category,
                explanation=explanation,
                delta=delta,
            )

        fc = FieldComparison(
            field=fname,
            mip39_value=mip39_val,
            reference_value=ref_val,
            is_exact_match=exact,
            is_within_tolerance=in_tol,
            delta=delta,
            divergence=divergence_rec,
        )
        ac.field_comparisons.append(fc)

        if not exact:
            ac.is_exact_match = False
        if not in_tol:
            ac.is_within_tolerance = False
            ac.has_divergences = True
            ac.divergence_count += 1

    return ac


def _compare_project_finish(
    analysis_result: Any,
    reference: ReferenceSchedule,
    tolerance_policy: TolerancePolicy,
    divergences: DivergenceAccumulator,
) -> Optional[FieldComparison]:
    """Compare project finish dates."""
    if reference.project_finish is None:
        return None

    mip39_finish = getattr(analysis_result, "project_finish", None)
    if mip39_finish is None:
        divergence_rec = divergences.add(
            act_id=None,
            field="project_finish",
            mip39_value=None,
            reference_value=reference.project_finish,
            category=DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            explanation=(
                "mip39 analysis result has no project_finish but reference provides one. "
                "This may indicate an invalid analysis result."
            ),
        )
        return FieldComparison(
            field="project_finish",
            mip39_value=None,
            reference_value=reference.project_finish,
            is_exact_match=False,
            is_within_tolerance=False,
            delta=None,
            divergence=divergence_rec,
        )

    exact = mip39_finish == reference.project_finish
    in_tol, delta = within_tolerance(
        "early_finish", mip39_finish, reference.project_finish, tolerance_policy
    )

    divergence_rec = None
    if not in_tol:
        category = DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE
        divergence_rec = divergences.add(
            act_id=None,
            field="project_finish",
            mip39_value=mip39_finish,
            reference_value=reference.project_finish,
            category=category,
            explanation=(
                f"Project finish: mip39={mip39_finish.isoformat()!r}, "
                f"reference={reference.project_finish.isoformat()!r}"
                + (f", delta={delta} calendar days" if delta is not None else "")
                + ". Out of tolerance."
            ),
            delta=delta,
        )

    return FieldComparison(
        field="project_finish",
        mip39_value=mip39_finish,
        reference_value=reference.project_finish,
        is_exact_match=exact,
        is_within_tolerance=in_tol,
        delta=delta,
        divergence=divergence_rec,
    )


def _compare_critical_path(
    analysis_result: Any,
    reference: ReferenceSchedule,
    divergences: DivergenceAccumulator,
) -> dict[str, Any]:
    """Compare critical path activity sets (order-insensitive)."""
    if not reference.critical_path_activity_ids:
        return {
            "cp_mip39": [],
            "cp_reference": [],
            "agreement": True,
            "mip39_only": [],
            "reference_only": [],
            "skipped": True,
        }

    cp_mip39: list[str] = []
    if (
        hasattr(analysis_result, "critical_path")
        and analysis_result.critical_path is not None
    ):
        cp_mip39 = sorted(analysis_result.critical_path.activity_ids or [])

    cp_ref = sorted(reference.critical_path_activity_ids)
    mip39_set = set(cp_mip39)
    ref_set = set(cp_ref)

    mip39_only = sorted(mip39_set - ref_set)
    ref_only = sorted(ref_set - mip39_set)
    agreement = mip39_set == ref_set

    if not agreement:
        explanation = (
            f"Critical path disagreement. mip39-only: {mip39_only}. "
            f"reference-only: {ref_only}. "
            "This may indicate a float method divergence or a material analytical difference."
        )
        divergences.add(
            act_id=None,
            field="critical_path",
            mip39_value=cp_mip39,
            reference_value=cp_ref,
            category=DivergenceCategory.FLOAT_METHOD_DIFFERENCE,
            explanation=explanation,
        )

    return {
        "cp_mip39": cp_mip39,
        "cp_reference": cp_ref,
        "agreement": agreement,
        "mip39_only": mip39_only,
        "reference_only": ref_only,
        "skipped": False,
    }


def _generate_checkpoints(
    divergences: DivergenceAccumulator,
    checkpoints: ComparisonCheckpointRegistry,
    policy_config: ComparisonPolicyConfig,
) -> None:
    """Generate policy-driven analyst checkpoints for divergences."""
    for div in divergences.all:
        if policy_config.requires_checkpoint(div.category):
            is_blocking = policy_config.is_blocking_category(div.category)
            cp = ComparisonCheckpoint(
                checkpoint_id=checkpoints.next_id(),
                reason=div.explanation,
                divergence_ids=[div.div_id],
                act_ids=[div.act_id] if div.act_id else [],
                div_category=div.category,
                is_blocking=is_blocking,
            )
            checkpoints.add(cp)


def _compute_metrics(
    activity_comparisons: list[ActivityComparison],
    mip39_only_ids: list[str],
    ref_only_ids: list[str],
    finish_comparison: Optional[FieldComparison],
    cp_comparison: dict[str, Any],
    divergences: DivergenceAccumulator,
    checkpoints: ComparisonCheckpointRegistry,
) -> ComparisonMetrics:
    """Compute quantitative comparison metrics."""
    total = len(activity_comparisons)
    exact_match = sum(1 for ac in activity_comparisons if ac.is_exact_match)
    within_tol = sum(1 for ac in activity_comparisons if ac.is_within_tolerance)
    divergent = sum(1 for ac in activity_comparisons if ac.has_divergences)

    match_pct = (within_tol / total * 100.0) if total > 0 else 0.0

    finish_delta: Optional[int] = None
    if finish_comparison and finish_comparison.delta is not None:
        finish_delta = int(finish_comparison.delta)

    # Float variance
    tf_deltas: list[float] = []
    ff_deltas: list[float] = []
    for ac in activity_comparisons:
        for fc in ac.field_comparisons:
            if fc.field == "total_float" and fc.delta is not None:
                tf_deltas.append(abs(fc.delta))
            elif fc.field == "free_float" and fc.delta is not None:
                ff_deltas.append(abs(fc.delta))

    tf_max = int(max(tf_deltas)) if tf_deltas else 0
    tf_mean = sum(tf_deltas) / len(tf_deltas) if tf_deltas else 0.0
    ff_max = int(max(ff_deltas)) if ff_deltas else 0

    # CP data
    cp_agree = cp_comparison.get("agreement", True)
    cp_mip39_only = cp_comparison.get("mip39_only", [])
    cp_ref_only = cp_comparison.get("reference_only", [])

    # Divergence counts
    div_counts = divergences.counts_by_category()
    unresolved = len(divergences.unresolved())
    blocking = len(divergences.unresolved_blocking())

    # Checkpoint counts
    cp_total = len(checkpoints)
    cp_unresolved = len(checkpoints.unresolved_blocking())

    return ComparisonMetrics(
        total_activities=total,
        mip39_only_activities=len(mip39_only_ids),
        reference_only_activities=len(ref_only_ids),
        exact_match_activities=exact_match,
        within_tolerance_activities=within_tol,
        divergent_activities=divergent,
        activity_match_pct=match_pct,
        critical_path_agreement=cp_agree,
        critical_path_mip39_only=cp_mip39_only,
        critical_path_ref_only=cp_ref_only,
        finish_date_variance_days=finish_delta,
        total_float_variance_max=tf_max,
        total_float_variance_mean=tf_mean,
        free_float_variance_max=ff_max,
        divergence_count_total=len(divergences),
        divergence_counts=div_counts,
        unresolved_divergence_count=unresolved,
        blocking_divergence_count=blocking,
        checkpoint_count=cp_total,
        unresolved_checkpoint_count=cp_unresolved,
    )


def _build_summary(
    policy: ComparisonPolicy,
    tolerance_policy: TolerancePolicy,
    reference: ReferenceSchedule,
    provenance: ComparisonProvenance,
    metrics: ComparisonMetrics,
    divergences: DivergenceAccumulator,
    checkpoints: ComparisonCheckpointRegistry,
    is_blocked: bool,
    context: str,
) -> ComparisonSummary:
    """Assemble the ComparisonSummary from run components."""
    # Checkpoint status summary
    cp_status: dict[str, int] = {}
    for cp in checkpoints.all():
        key = cp.status.value
        cp_status[key] = cp_status.get(key, 0) + 1

    blocking_divs = [
        f"{d.div_id}: {d.field} on {d.act_id or 'project'} — {d.category.value}"
        for d in divergences.unresolved_blocking()
    ]

    return ComparisonSummary(
        run_id=provenance.run_id,
        timestamp_utc=provenance.timestamp_utc,
        reference_id=reference.schedule_id,
        reference_source=reference.source,
        policy=policy.value,
        tolerance_policy=tolerance_policy.name,
        is_blocked=is_blocked,
        metrics=metrics,
        divergence_summary=metrics.divergence_counts,
        checkpoint_summary=cp_status,
        blocking_divergences=blocking_divs,
        context=context,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compare_schedules(
    analysis_result: Any,
    reference: ReferenceSchedule,
    policy: ComparisonPolicy = ComparisonPolicy.GOVERNED,
    tolerance_policy: TolerancePolicy | None = None,
    calendar_registry: Any = None,
    context: str = "",
) -> ScheduleComparison:
    """
    Compare a mip39 AnalysisResult against a ReferenceSchedule.

    Args:
        analysis_result:   AnalysisResult from run_analysis(). Must be valid
                           (is_valid=True) for per-activity comparison.
        reference:         ReferenceSchedule with expected values.
        policy:            ComparisonPolicy governing blocking behavior.
                           Default: GOVERNED.
        tolerance_policy:  TolerancePolicy for field-level tolerance.
                           Default: TOLERANCE_STRICT (exact match).
        calendar_registry: Optional CalendarRegistry — when provided, date
                           divergences are classified CALENDAR_BEHAVIOR_DIFFERENCE
                           rather than UNKNOWN_DIFFERENCE.
        context:           Optional caller context string for provenance.

    Returns:
        ScheduleComparison with all comparison artifacts.
    """
    from .tolerances import TOLERANCE_STRICT
    if tolerance_policy is None:
        tolerance_policy = TOLERANCE_STRICT

    policy_config = get_comparison_policy_config(policy)
    divergences = DivergenceAccumulator()
    checkpoints = ComparisonCheckpointRegistry()
    has_cr = calendar_registry is not None

    # Build provenance skeleton
    mip39_count = len(getattr(analysis_result, "scheduled", {}) or {})
    ref_count = len(reference.activities)
    provenance = build_comparison_provenance(
        policy=policy.value,
        tolerance_policy=tolerance_policy.name,
        reference_source=reference.source,
        reference_id=reference.schedule_id,
        original_activity_count=mip39_count,
        reference_activity_count=ref_count,
        context=context,
    )

    # Stage 1: Identify activity universe
    mip39_scheduled = getattr(analysis_result, "scheduled", {}) or {}
    mip39_ids = set(mip39_scheduled.keys())
    ref_ids = set(reference.activities.keys())

    # Activities only in one side
    mip39_only = sorted(mip39_ids - ref_ids)
    ref_only = sorted(ref_ids - mip39_ids)

    for act_id in mip39_only:
        divergences.add(
            act_id=act_id,
            field="activity_presence",
            mip39_value="present",
            reference_value="absent",
            category=DivergenceCategory.UNKNOWN_DIFFERENCE,
            explanation=(
                f"Activity {act_id!r} is in mip39 result but not in reference schedule. "
                "This may indicate a schedule version mismatch."
            ),
        )

    for act_id in ref_only:
        divergences.add(
            act_id=act_id,
            field="activity_presence",
            mip39_value="absent",
            reference_value="present",
            category=DivergenceCategory.UNKNOWN_DIFFERENCE,
            explanation=(
                f"Activity {act_id!r} is in reference schedule but not in mip39 result. "
                "This may indicate a schedule version mismatch."
            ),
        )

    provenance.add_stage(ComparisonStageRecord(
        stage_name="activity_universe",
        items_compared=len(mip39_ids | ref_ids),
        divergences_found=len(mip39_only) + len(ref_only),
        notes=[
            f"mip39 activities: {len(mip39_ids)}.",
            f"Reference activities: {len(ref_ids)}.",
            f"In both: {len(mip39_ids & ref_ids)}.",
            f"mip39-only: {mip39_only}.",
            f"reference-only: {ref_only}.",
        ],
    ))

    # Stage 2: Per-activity field comparison (sorted for determinism)
    activity_comparisons: list[ActivityComparison] = []
    common_ids = sorted(mip39_ids & ref_ids)

    is_valid = getattr(analysis_result, "is_valid", False)
    if not is_valid:
        divergences.add(
            act_id=None,
            field="is_valid",
            mip39_value=False,
            reference_value=True,
            category=DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            explanation=(
                "mip39 analysis result is_valid=False. Per-activity comparison "
                "cannot proceed for an invalid analysis result."
            ),
        )

    activity_div_count = 0
    for act_id in common_ids:
        sa = mip39_scheduled[act_id]
        ra = reference.activities[act_id]
        ac = _compare_activity_fields(
            act_id, sa, ra, tolerance_policy, divergences, has_cr
        )
        activity_comparisons.append(ac)
        activity_div_count += ac.divergence_count

    provenance.add_stage(ComparisonStageRecord(
        stage_name="per_activity_comparison",
        items_compared=len(common_ids),
        divergences_found=activity_div_count,
        notes=[
            f"Fields compared per activity: {_ACTIVITY_FIELDS}.",
            f"Tolerance policy: {tolerance_policy.name}.",
        ],
    ))

    # Stage 3: Project-level comparison
    finish_comparison = _compare_project_finish(
        analysis_result, reference, tolerance_policy, divergences
    )
    cp_comparison = _compare_critical_path(analysis_result, reference, divergences)

    project_div_count = (
        (1 if finish_comparison and not finish_comparison.is_within_tolerance else 0)
        + (1 if not cp_comparison.get("agreement", True) else 0)
    )
    provenance.add_stage(ComparisonStageRecord(
        stage_name="project_level_comparison",
        items_compared=2,
        divergences_found=project_div_count,
        notes=["Compared: project_finish, critical_path."],
    ))

    # Stage 4: Policy-driven checkpoints
    _generate_checkpoints(divergences, checkpoints, policy_config)
    provenance.add_stage(ComparisonStageRecord(
        stage_name="checkpoint_generation",
        items_compared=len(divergences),
        divergences_found=0,
        notes=[
            f"Policy: {policy.value}.",
            f"Checkpoints generated: {len(checkpoints)}.",
            f"Blocking checkpoints: {len(checkpoints.unresolved_blocking())}.",
        ],
    ))

    # Stage 5: Metrics
    metrics = _compute_metrics(
        activity_comparisons,
        mip39_only,
        ref_only,
        finish_comparison,
        cp_comparison,
        divergences,
        checkpoints,
    )

    is_blocked = checkpoints.is_comparison_blocked()

    # Stage 6: Summary
    summary = _build_summary(
        policy, tolerance_policy, reference, provenance,
        metrics, divergences, checkpoints, is_blocked, context,
    )

    return ScheduleComparison(
        policy=policy,
        tolerance_policy=tolerance_policy,
        activity_comparisons=activity_comparisons,
        finish_comparison=finish_comparison,
        critical_path_comparison=cp_comparison,
        divergences=divergences,
        checkpoints=checkpoints,
        metrics=metrics,
        provenance=provenance,
        summary=summary,
        is_blocked=is_blocked,
    )


# ---------------------------------------------------------------------------
# Lag calendar strategy experiment
# ---------------------------------------------------------------------------

@dataclass
class LagStrategyResult:
    """Result of running one lag calendar strategy."""
    strategy: str
    analysis_result: Any
    project_finish: Optional[date]


@dataclass
class LagStrategyExperiment:
    """
    Complete result of a lag calendar strategy sensitivity experiment.

    Fields:
        strategy_results:   Results for each strategy tested.
        cross_comparisons:  Pairwise comparisons (key: "PRED_vs_SUCC" etc.).
        summary:            LagStrategyExperimentSummary with findings.
    """

    strategy_results: list[LagStrategyResult] = field(default_factory=list)
    cross_comparisons: dict[str, ScheduleComparison] = field(default_factory=dict)
    summary: LagStrategyExperimentSummary = field(
        default_factory=LagStrategyExperimentSummary
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "strategy_results": [
                {
                    "strategy": r.strategy,
                    "project_finish": (
                        r.project_finish.isoformat() if r.project_finish else None
                    ),
                }
                for r in self.strategy_results
            ],
            "cross_comparison_keys": list(self.cross_comparisons.keys()),
        }


def run_lag_strategy_experiment(
    activities: list,
    relationships: list,
    project_start: date,
    workday_table: dict,
    calendar: Any,
    calendar_registry: Any,
    tolerance_policy: TolerancePolicy | None = None,
    context: str = "",
) -> LagStrategyExperiment:
    """
    Run the same schedule under all four LagCalendarStrategy variants.

    Compares each non-baseline strategy against the PREDECESSOR_CALENDAR
    baseline (the CPW-default strategy). Classifies differences as
    LAG_BEHAVIOR_DIFFERENCE.

    This experiment determines whether per-relationship lag calendar
    assignment is necessary for V1 release:
      - If all strategies produce identical results → run-level strategy
        is sufficient; per-relationship assignment is not required.
      - If any strategy produces different results → lag calendar strategy
        is material; document findings and assess whether per-relationship
        assignment is required.

    Args:
        activities:       Activity list (same as run_analysis() input).
        relationships:    Relationship list.
        project_start:    Project start date.
        workday_table:    Pre-built workday table.
        calendar:         Project-default calendar.
        calendar_registry: CalendarRegistry with all project calendars.
        tolerance_policy: Tolerance for cross-strategy comparison.
                         Default: TOLERANCE_STRICT (detect all differences).
        context:          Optional context string.

    Returns:
        LagStrategyExperiment with per-strategy results and cross-comparisons.
    """
    from ..engine import run_analysis
    from .tolerances import TOLERANCE_STRICT

    if tolerance_policy is None:
        tolerance_policy = TOLERANCE_STRICT

    strategies = list(LagCalendarStrategy)
    baseline_strategy = LagCalendarStrategy.PREDECESSOR_CALENDAR

    strategy_results: list[LagStrategyResult] = []

    for strategy in strategies:
        result = run_analysis(
            activities=activities,
            relationships=relationships,
            project_start=project_start,
            workday_table=workday_table,
            calendar=calendar,
            calendar_registry=calendar_registry,
            lag_strategy=strategy,
        )
        finish = getattr(result, "project_finish", None)
        strategy_results.append(LagStrategyResult(
            strategy=strategy.value,
            analysis_result=result,
            project_finish=finish,
        ))

    # Find the baseline result for cross-comparison reference
    baseline_result = next(
        (r for r in strategy_results if r.strategy == baseline_strategy.value),
        strategy_results[0] if strategy_results else None,
    )

    cross_comparisons: dict[str, ScheduleComparison] = {}
    affected_activities: set[str] = set()
    max_date_delta = 0
    max_float_delta = 0
    finish_deltas: dict[str, Optional[int]] = {}

    if baseline_result is not None:
        # Build a ReferenceSchedule from the baseline analysis result
        baseline_ar = baseline_result.analysis_result
        baseline_scheduled = getattr(baseline_ar, "scheduled", {}) or {}

        # Build ReferenceSchedule from baseline
        from .fixtures import ReferenceSchedule, ReferenceScheduledActivity
        baseline_ref = ReferenceSchedule(
            schedule_id=f"baseline-{baseline_strategy.value}",
            description=f"Lag strategy baseline: {baseline_strategy.value}",
            project_finish=getattr(baseline_ar, "project_finish", None),
            critical_path_activity_ids=(
                list(baseline_ar.critical_path.activity_ids)
                if (hasattr(baseline_ar, "critical_path") and baseline_ar.critical_path)
                else []
            ),
            source="synthetic",
            tool="mip39",
            lag_strategy_assumed=baseline_strategy.value,
        )
        for act_id, sa in sorted(baseline_scheduled.items()):
            baseline_ref.add_activity(ReferenceScheduledActivity(
                act_id=act_id,
                early_start=getattr(sa, "early_start", None),
                early_finish=getattr(sa, "early_finish", None),
                late_start=getattr(sa, "late_start", None),
                late_finish=getattr(sa, "late_finish", None),
                total_float=getattr(sa, "total_float", None),
                free_float=getattr(sa, "free_float", None),
                is_critical=getattr(sa, "is_critical", None),
                original_duration=getattr(sa, "original_duration", None),
            ))

        for strat_result in strategy_results:
            if strat_result.strategy == baseline_strategy.value:
                finish_deltas[strat_result.strategy] = 0
                continue

            comparison = compare_schedules(
                analysis_result=strat_result.analysis_result,
                reference=baseline_ref,
                policy=ComparisonPolicy.ADVISORY,
                tolerance_policy=tolerance_policy,
                calendar_registry=calendar_registry,
                context=f"lag-strategy-experiment:{strat_result.strategy}-vs-{baseline_strategy.value}",
            )

            # Reclassify any divergences as LAG_BEHAVIOR_DIFFERENCE
            for div in comparison.divergences.all:
                if div.category not in (
                    DivergenceCategory.EXPECTED_DIFFERENCE,
                    DivergenceCategory.GOVERNED_DIFFERENCE,
                ):
                    div.category = DivergenceCategory.LAG_BEHAVIOR_DIFFERENCE

            key = f"{strat_result.strategy}_vs_{baseline_strategy.value}"
            cross_comparisons[key] = comparison

            # Track affected activities and max deltas
            for ac in comparison.activity_comparisons:
                if ac.has_divergences:
                    affected_activities.add(ac.act_id)
                    for fc in ac.field_comparisons:
                        if fc.delta is not None and not fc.skipped:
                            abs_delta = abs(fc.delta)
                            if fc.field in _DATE_FIELDS:
                                max_date_delta = max(max_date_delta, int(abs_delta))
                            elif fc.field in {"total_float", "free_float"}:
                                max_float_delta = max(max_float_delta, int(abs_delta))

            # Finish date delta
            if comparison.finish_comparison and comparison.finish_comparison.delta is not None:
                finish_deltas[strat_result.strategy] = int(comparison.finish_comparison.delta)
            elif (
                baseline_result.project_finish is not None
                and strat_result.project_finish is not None
            ):
                finish_deltas[strat_result.strategy] = (
                    (strat_result.project_finish - baseline_result.project_finish).days
                )
            else:
                finish_deltas[strat_result.strategy] = None

    # Formulate finding
    affected_list = sorted(affected_activities)
    if not affected_list:
        finding = (
            "All four LagCalendarStrategy variants produce identical results for "
            "this schedule. Run-level lag calendar strategy is sufficient. "
            "Per-relationship lag calendar assignment is NOT required for this schedule."
        )
        per_rel_mandatory = False
    else:
        finding = (
            f"{len(affected_list)} activity(ies) produce different results under "
            "different lag calendar strategies: "
            + ", ".join(affected_list[:5])
            + ("..." if len(affected_list) > 5 else "")
            + f". Max date delta: {max_date_delta} calendar days. "
            "This schedule is sensitive to lag calendar strategy. "
            "Analyst should assess whether per-relationship lag calendar assignment "
            "is required for V1 forensic reliance."
        )
        per_rel_mandatory = max_date_delta > 0

    summary = LagStrategyExperimentSummary(
        strategies_tested=[s.value for s in strategies],
        baseline_strategy=baseline_strategy.value,
        affected_activities=affected_list,
        max_date_delta_days=max_date_delta,
        max_float_delta=max_float_delta,
        finish_date_deltas=finish_deltas,
        finding=finding,
        per_relationship_mandatory=per_rel_mandatory,
    )

    return LagStrategyExperiment(
        strategy_results=strategy_results,
        cross_comparisons=cross_comparisons,
        summary=summary,
    )
