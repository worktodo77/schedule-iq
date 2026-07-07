"""
V1-D: Destatusing orchestration engine.

DestatusingEngine orchestrates the complete V1-D workflow:
  1. Rule classification (determine_rule per activity)
  2. Anomaly detection and diagnostic generation
  3. Governed transformation with provenance (apply_rule_with_provenance)
  4. Analyst checkpoint generation (policy-driven)
  5. Lag analysis (compute_actual_lag per relationship)
  6. Auto-drive (run_autodrive — driving predecessor selection)
  7. Simulation preparation metadata assembly

Entry point: run_destatusing()

Backward compatibility: existing callers of the raw rule functions
(destatus_rule_a through destatus_rule_f) are unaffected — those functions
remain available via the destatusing package __init__.

Source: ADR-014; CPW-P6 Manual pp. 40-44; ADR-005 (determinism, provenance).

Ported from the LI MIP 3.9 tool (mip39.destatusing.engine) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..models import Activity, Calendar, Relationship
from ..calendar_ops import resolve_activity_workday_resources, is_table_coverage_error
from ..calendar_registry import LagCalendarStrategy
from ..severity import DiagnosticSeverity
from .rules import DestatusingRule, RuleAssignment, determine_rule
from .provenance import TransformationLog
from .diagnostics import (
    V1dDiagnosticAccumulator,
    DSTCode, LAGCode, DRVCode,
)
from .policies import DestatusingPolicy, get_policy_config
from .checkpoints import DSTCheckpoint, DSTCheckpointRegistry
from .transformations import apply_rule_with_provenance
from .lag import run_lag_analysis, LagAnalysisResult, ActualLagResult
from .autodrive import run_autodrive, AutoDriveResult


# ---------------------------------------------------------------------------
# Destatusing input
# ---------------------------------------------------------------------------

@dataclass
class DestatusingInput:
    """
    All inputs required by the destatusing engine.

    Fields:
        activities          — Source activities (will not be mutated).
        relationships       — Source relationships (will not be mutated).
        new_data_date       — The new (earlier) data date for this analysis window.
        old_data_date       — The old (later) data date for this analysis window.
        workday_table       — Prebuilt workday lookup table covering the full
                              window range.
        calendar            — Calendar for workday arithmetic (Rules D and F).
        policy              — DestatusingPolicy governing blocking and checkpoints.
                              Default: STRICT_FORENSIC.
        run_lag_analysis    — If True, compute actual lags after destatusing.
                              Default: True.
        run_autodrive       — If True, apply auto-drive algorithm after lag analysis.
                              Requires run_lag_analysis=True. Default: True.
        context             — Optional run/session context string embedded in
                              all provenance records for audit linkage.
    """
    activities: list[Activity]
    relationships: list[Relationship]
    new_data_date: date
    old_data_date: date
    workday_table: dict[date, int]
    calendar: Calendar
    policy: DestatusingPolicy = DestatusingPolicy.STRICT_FORENSIC
    run_lag_analysis: bool = True
    run_autodrive: bool = True
    context: str = ""
    # F3/F-13 — optional multi-calendar registry. When present, lag analysis
    # measures each relationship's lag in the predecessor's calendar; None keeps
    # the single-calendar behavior.
    calendar_registry: Optional[Any] = None
    # ADR-029 r2 (Codex r2 P2): the lag strategy for run_lag_analysis. The CLI sets
    # it from cfg.lag_calendar_strategy so actual-lag analysis measures in the SAME
    # calendar the import normalized under and CPM schedules under. API paths keep
    # the predecessor default until Slice D exposes a selector.
    lag_strategy: LagCalendarStrategy = LagCalendarStrategy.PREDECESSOR_CALENDAR


# ---------------------------------------------------------------------------
# Simulation preparation metadata
# ---------------------------------------------------------------------------

@dataclass
class SimulationMetadata:
    """
    Metadata produced during destatusing for V1-E simulation schedule generation.

    Contains a summary of what was transformed, what remains unresolved, and
    what the downstream simulation engine needs to be aware of.

    Fields:
        new_data_date       — The new data date for this analysis window.
        old_data_date       — The old data date.
        activity_count      — Total activities in input.
        transformed_count   — Activities with at least one field changed.
        no_change_count     — Activities processed but unchanged (Rules A and C).
        no_match_count      — Activities with NO_MATCH rule (anomalous state).
        not_in_scope_count  — Activities with NOT_IN_SCOPE rule.
        transformation_count — Total individual field transformations.
        unresolved_checkpoints — Count of PENDING blocking checkpoints.
        lag_computed_count  — Relationships with actual lag successfully computed.
        lag_skipped_count   — Relationships with missing dates.
        autodrive_applied   — True if auto-drive was run.
        pc_formula_note     — Disclosure that PC formula is an implementation
                              interpretation (Rules D and F).
        policy_used         — Policy name applied.
    """
    new_data_date: date
    old_data_date: date
    activity_count: int
    transformed_count: int
    no_change_count: int
    no_match_count: int
    not_in_scope_count: int
    transformation_count: int
    unresolved_checkpoints: int
    lag_computed_count: int
    lag_skipped_count: int
    autodrive_applied: bool
    pc_formula_note: str
    policy_used: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "new_data_date": self.new_data_date.isoformat(),
            "old_data_date": self.old_data_date.isoformat(),
            "activity_count": self.activity_count,
            "transformed_count": self.transformed_count,
            "no_change_count": self.no_change_count,
            "no_match_count": self.no_match_count,
            "not_in_scope_count": self.not_in_scope_count,
            "transformation_count": self.transformation_count,
            "unresolved_checkpoints": self.unresolved_checkpoints,
            "lag_computed_count": self.lag_computed_count,
            "lag_skipped_count": self.lag_skipped_count,
            "autodrive_applied": self.autodrive_applied,
            "pc_formula_note": self.pc_formula_note,
            "policy_used": self.policy_used,
        }


# ---------------------------------------------------------------------------
# Destatusing result
# ---------------------------------------------------------------------------

@dataclass
class DestatusingResult:
    """
    Complete output of a governed destatusing run.

    Fields:
        destatused_activities   — Transformed activity set (list, in input order).
        transformed_relationships — Relationships with auto-drive lags applied
                                    (or original relationships if no autodrive).
        rule_assignments        — dict[act_id → RuleAssignment] for all activities.
        transformation_log      — All TransformationRecord objects from this run.
        diagnostics             — V1dDiagnosticAccumulator with all DST/LAG/DRV codes.
        checkpoints             — DSTCheckpointRegistry with policy-driven checkpoints.
        lag_analysis            — LagAnalysisResult (None if run_lag_analysis=False).
        autodrive_result        — AutoDriveResult (None if run_autodrive=False).
        simulation_metadata     — SimulationMetadata for V1-E preparation.
        policy                  — Policy applied during this run.
        new_data_date           — New data date from input.
        old_data_date           — Old data date from input.
        is_blocked              — True if any blocking checkpoint is PENDING.
    """
    destatused_activities: list[Activity]
    transformed_relationships: list[Relationship]
    rule_assignments: dict[str, RuleAssignment]
    transformation_log: TransformationLog
    diagnostics: V1dDiagnosticAccumulator
    checkpoints: DSTCheckpointRegistry
    lag_analysis: Optional[LagAnalysisResult]
    autodrive_result: Optional[AutoDriveResult]
    simulation_metadata: SimulationMetadata
    policy: DestatusingPolicy
    new_data_date: date
    old_data_date: date
    is_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.value,
            "new_data_date": self.new_data_date.isoformat(),
            "old_data_date": self.old_data_date.isoformat(),
            "is_blocked": self.is_blocked,
            "rule_assignments": {
                k: v.to_dict() for k, v in self.rule_assignments.items()
            },
            "transformation_log": self.transformation_log.to_dict_list(),
            "diagnostics": self.diagnostics.to_dict_list(),
            "checkpoints": self.checkpoints.to_dict_list(),
            "lag_analysis": self.lag_analysis.to_dict() if self.lag_analysis else None,
            "autodrive_result": self.autodrive_result.to_dict() if self.autodrive_result else None,
            "simulation_metadata": self.simulation_metadata.to_dict(),
        }


# ---------------------------------------------------------------------------
# Anomaly detection helpers
# ---------------------------------------------------------------------------

def _check_activity_anomalies(
    activity: Activity,
    new_dd: date,
    accum: V1dDiagnosticAccumulator,
) -> None:
    """Detect pre-transformation anomalies and emit DST diagnostics."""
    a = activity
    act_id = a.act_id

    # AF before AS (impossible progress)
    if a.actual_start is not None and a.actual_finish is not None:
        if a.actual_finish < a.actual_start:
            accum.add_dst(
                DSTCode.DST_010,
                f"Activity {act_id!r}: AF={a.actual_finish} is before AS={a.actual_start}. "
                "Impossible progress state.",
                act_id=act_id,
                details={"actual_start": str(a.actual_start), "actual_finish": str(a.actual_finish)},
            )

    # Actual duration > original duration
    if a.actual_duration is not None and a.original_duration is not None:
        if a.actual_duration > a.original_duration:
            accum.add_dst(
                DSTCode.DST_014,
                f"Activity {act_id!r}: AD={a.actual_duration} > OD={a.original_duration}. "
                "Actual duration exceeds original duration.",
                act_id=act_id,
                details={"actual_duration": a.actual_duration, "original_duration": a.original_duration},
            )

    # Percent complete out of range
    if a.percent_complete is not None:
        if a.percent_complete < 0.0 or a.percent_complete > 1.0:
            accum.add_dst(
                DSTCode.DST_012,
                f"Activity {act_id!r}: percent_complete={a.percent_complete:.4f} "
                "is outside [0.0, 1.0].",
                act_id=act_id,
                details={"percent_complete": a.percent_complete},
            )


def _check_post_transform_anomalies(
    act_id: str,
    transformed: Activity,
    rule: DestatusingRule,
    accum: V1dDiagnosticAccumulator,
) -> None:
    """Detect anomalies in the transformed activity."""
    # Negative remaining duration
    if transformed.remaining_duration is not None and transformed.remaining_duration < 0:
        accum.add_dst(
            DSTCode.DST_009,
            f"Activity {act_id!r}: remaining_duration={transformed.remaining_duration} "
            f"is negative after {rule.value} transformation.",
            act_id=act_id,
            details={"remaining_duration": transformed.remaining_duration, "rule": rule.value},
        )

    # Zero or negative original duration after transform
    if transformed.original_duration is not None and transformed.original_duration <= 0:
        if rule in (DestatusingRule.B, DestatusingRule.E):
            accum.add_dst(
                DSTCode.DST_013,
                f"Activity {act_id!r}: original_duration={transformed.original_duration} "
                f"after {rule.value} transformation is zero or negative.",
                act_id=act_id,
                details={"original_duration": transformed.original_duration, "rule": rule.value},
            )


def _emit_rule_assignment_diagnostic(
    assignment: RuleAssignment,
    accum: V1dDiagnosticAccumulator,
) -> None:
    """Emit the informational DST rule-assignment diagnostic."""
    code_map = {
        DestatusingRule.A: DSTCode.DST_001,
        DestatusingRule.B: DSTCode.DST_002,
        DestatusingRule.C: DSTCode.DST_003,
        DestatusingRule.D: DSTCode.DST_004,
        DestatusingRule.E: DSTCode.DST_005,
        DestatusingRule.F: DSTCode.DST_006,
        DestatusingRule.NO_MATCH: DSTCode.DST_007,
        DestatusingRule.NOT_IN_SCOPE: DSTCode.DST_015,
    }
    code = code_map.get(assignment.rule, DSTCode.DST_015)
    accum.add_dst(
        code,
        f"Activity {assignment.act_id!r}: {assignment.reason}",
        act_id=assignment.act_id,
        details={"rule": assignment.rule.value, "missing_fields": list(assignment.missing_fields)},
    )

    # Missing required fields → additional diagnostic
    if assignment.missing_fields:
        for fname in assignment.missing_fields:
            accum.add_dst(
                DSTCode.DST_011,
                f"Activity {assignment.act_id!r}: field '{fname}' is required for "
                f"{assignment.rule.value} but is None.",
                act_id=assignment.act_id,
                details={"field": fname, "rule": assignment.rule.value},
            )


def _generate_checkpoint(
    diag_codes: list[str],
    act_ids: list[str],
    reason: str,
    is_blocking: bool,
    reg: DSTCheckpointRegistry,
) -> DSTCheckpoint:
    """Create and register a checkpoint."""
    cp = DSTCheckpoint(
        checkpoint_id=reg.next_id(),
        reason=reason,
        triggering_codes=sorted(diag_codes),
        act_ids=sorted(act_ids),
        is_blocking=is_blocking,
    )
    reg.add(cp)
    return cp


# ---------------------------------------------------------------------------
# Auto-drive diagnostics emission
# ---------------------------------------------------------------------------

def _emit_autodrive_diagnostics(
    accum: V1dDiagnosticAccumulator,
    autodrive_result: AutoDriveResult,
) -> None:
    """Emit DRV diagnostics from the auto-drive decisions.

    Separated from ``run_destatusing`` so the forensic diagnostic text and counts
    can be unit-tested directly against the ``AutoDriveDecision`` reason strings
    (WF-02/03).
    """
    for dec in autodrive_result.decisions:
        for ld in dec.lag_decisions:
            if ld["is_driving"]:
                accum.add_drv(
                    DRVCode.DRV_001,
                    f"Driving predecessor {ld['pred_id']!r} → {dec.succ_id!r}: "
                    f"actual_lag={ld['actual_lag']}, variance={ld.get('variance')}.",
                    act_id=dec.succ_id,
                    details=ld,
                )
            elif ld.get("reason") == "negative_actual_lag_retained":
                # WF-03: a non-driving predecessor whose ACTUAL lag is negative
                # keeps that lag (CPW p.4) — it is NOT reset to planned.
                accum.add_drv(
                    DRVCode.DRV_007,
                    f"Non-driving predecessor {ld['pred_id']!r} → {dec.succ_id!r}: "
                    f"negative actual lag retained (applied={ld['applied_lag']}, "
                    f"not reset to planned={ld['planned_lag']}; CPW p.4).",
                    act_id=dec.succ_id,
                    details=ld,
                )
            else:
                accum.add_drv(
                    DRVCode.DRV_002,
                    f"Non-driving predecessor {ld['pred_id']!r} → {dec.succ_id!r}: "
                    f"lag reset from actual={ld['actual_lag']} to planned={ld['planned_lag']}.",
                    act_id=dec.succ_id,
                    details=ld,
                )
        if dec.equal_variance_tie:
            # WF-02: the tie is the minimum-variance group ONLY — not the widened
            # driving set (which now also carries negative-variance auto-drivers).
            tied_preds = sorted(
                ld["pred_id"] for ld in dec.lag_decisions
                if ld.get("reason") == "minimum_variance_tie"
            )
            accum.add_drv(
                DRVCode.DRV_003,
                f"Equal variance tie for successor {dec.succ_id!r}: "
                f"{len(tied_preds)} predecessors equally drive at the minimum "
                f"variance ({dec.min_variance}).",
                act_id=dec.succ_id,
                details={"tied_preds": tied_preds},
            )
        if dec.all_negative:
            accum.add_drv(
                DRVCode.DRV_005,
                f"All predecessor lags negative for {dec.succ_id!r}: "
                "all retained per CPW spec.",
                act_id=dec.succ_id,
            )


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def run_destatusing(inp: DestatusingInput) -> DestatusingResult:
    """
    Execute the complete governed destatusing workflow.

    Steps:
      1. Validate inputs.
      2. Classify each activity into a destatusing rule.
      3. Detect pre-transformation anomalies.
      4. Apply transformations with provenance recording.
      5. Detect post-transformation anomalies.
      6. Generate policy-driven analyst checkpoints.
      7. Run lag analysis (if requested).
      8. Run auto-drive (if requested).
      9. Assemble simulation metadata.

    Returns a DestatusingResult. is_blocked=True when unresolved blocking
    checkpoints exist.
    """
    policy_config = get_policy_config(inp.policy)
    # ADR-029 r2 (Codex r2 P2): no silent single-calendar fallback. If a registry is
    # present it MUST cover the run range before the rule loop — exactly like
    # run_analysis / run_lag_analysis — otherwise Rule D/F (and run_lag_analysis=False
    # paths, which skip the later lag guard) would silently compute on the project
    # default. The per-activity resolver's fallback is only for a calendar-less
    # activity or a None registry, never an unready/out-of-range one.
    if inp.calendar_registry is not None and inp.workday_table:
        _cov = getattr(inp.calendar_registry, "tables_cover", None)
        _lo, _hi = min(inp.workday_table), max(inp.workday_table)
        if not (callable(_cov) and _cov(_lo, _hi)):
            raise ValueError(
                "run_destatusing: calendar_registry is present but its per-calendar "
                f"tables do not cover the run range [{_lo} .. {_hi}]. Call "
                "ensure_workday_tables() (via build_calendar_resources) before "
                "run_destatusing — refusing to silently fall back to a single calendar."
            )
    log = TransformationLog(context=inp.context)
    accum = V1dDiagnosticAccumulator()
    checkpoints = DSTCheckpointRegistry()
    rule_assignments: dict[str, RuleAssignment] = {}
    destatused: list[Activity] = []
    transformed_count = 0
    no_change_count = 0
    no_match_count = 0
    not_in_scope_count = 0

    # Sort activities deterministically for consistent output
    sorted_activities = sorted(inp.activities, key=lambda a: a.act_id)

    for activity in sorted_activities:
        # Step 1: pre-transformation anomaly detection
        _check_activity_anomalies(activity, inp.new_data_date, accum)

        # Step 2: rule classification
        assignment = determine_rule(activity, inp.new_data_date, inp.old_data_date)
        rule_assignments[activity.act_id] = assignment

        # Step 3: emit rule assignment diagnostic
        _emit_rule_assignment_diagnostic(assignment, accum)

        # Step 4: apply transformation with provenance
        rule = assignment.rule
        # ADR-029 r2 (#9 P1): Rule D/F remaining-duration workday math must count in
        # the ACTIVITY's own calendar (work-week + holidays), not the project-default
        # table. Resolve per-activity resources; falls back to the default for a
        # calendar-less activity or single-calendar import (byte-identical).
        _act_table, _act_cal = resolve_activity_workday_resources(
            activity, inp.workday_table, inp.calendar, inp.calendar_registry
        )
        if rule in (DestatusingRule.NO_MATCH, DestatusingRule.NOT_IN_SCOPE):
            if rule == DestatusingRule.NO_MATCH:
                no_match_count += 1
            else:
                not_in_scope_count += 1
            # Still record a provenance entry; return copy of original
            transformed = apply_rule_with_provenance(
                assignment, activity, inp.new_data_date, inp.old_data_date,
                log, _act_table, _act_cal, inp.context,
            )
        elif rule in (DestatusingRule.A, DestatusingRule.C):
            no_change_count += 1
            transformed = apply_rule_with_provenance(
                assignment, activity, inp.new_data_date, inp.old_data_date,
                log, None, None, inp.context,
            )
        else:
            try:
                transformed = apply_rule_with_provenance(
                    assignment, activity, inp.new_data_date, inp.old_data_date,
                    log, _act_table, _act_cal, inp.context,
                )
                transformed_count += 1
            except ValueError as exc:
                # ADR-029 4.7b r6: a table-COVERAGE underflow (the workday table is
                # too short for this activity's dates) is NOT a per-activity rule
                # failure — masking it as DST_011 and returning the UNMODIFIED
                # activity would silently feed wrong remaining_duration/% into CPM.
                # Re-raise it so the caller's build_resources_with_growth backstop
                # grows the table and retries. Genuine rule-application failures
                # (anything else) still degrade to DST_011 + original copy.
                if is_table_coverage_error(exc):
                    raise
                accum.add_dst(
                    DSTCode.DST_011,
                    f"Activity {activity.act_id!r}: rule application failed: {exc}",
                    act_id=activity.act_id,
                    details={"rule": rule.value, "error": str(exc)},
                )
                transformed = copy.copy(activity)

        # Step 5: post-transformation anomaly detection
        _check_post_transform_anomalies(activity.act_id, transformed, rule, accum)

        destatused.append(transformed)

    # Step 6: generate checkpoints (policy-driven, after all diagnostics collected)
    for diag in accum.all:
        if policy_config.requires_checkpoint(diag.severity):
            is_blocking = policy_config.is_blocking(diag.severity)
            _generate_checkpoint(
                diag_codes=[diag.code],
                act_ids=[diag.act_id] if diag.act_id else [],
                reason=diag.message,
                is_blocking=is_blocking,
                reg=checkpoints,
            )

    # NO_MATCH activities always get a checkpoint under policies that require it
    if policy_config.require_analyst_review_on_no_match and no_match_count > 0:
        no_match_ids = [
            a.act_id for a in sorted_activities
            if rule_assignments[a.act_id].rule == DestatusingRule.NO_MATCH
        ]
        _generate_checkpoint(
            diag_codes=["DST-007"],
            act_ids=no_match_ids,
            reason=(
                f"{no_match_count} activities could not be classified into any "
                "destatusing rule (DST-007). Analyst review required before "
                "relying on simulation results."
            ),
            is_blocking=True,
            reg=checkpoints,
        )

    # PC formula checkpoint under STRICT_FORENSIC (interpretation not pre-approved)
    if not policy_config.allow_pc_formula_interpretation:
        pc_rules = {DestatusingRule.D, DestatusingRule.F}
        pc_act_ids = [
            a.act_id for a in sorted_activities
            if rule_assignments[a.act_id].rule in pc_rules
        ]
        if pc_act_ids:
            _generate_checkpoint(
                diag_codes=["DST-004", "DST-006"],
                act_ids=pc_act_ids,
                reason=(
                    "Rules D and F use a Percent Complete formula "
                    "(PC = AD_before/(AD_before+RD), AD_before = workdays from AS to the new data date) "
                    "that is an implementation interpretation of CPW Manual p. 40. "
                    "The formula is not explicitly stated in the source. Analyst must "
                    "confirm suitability before forensic reliance."
                ),
                is_blocking=True,
                reg=checkpoints,
            )

    # Step 7: lag analysis
    lag_result: Optional[LagAnalysisResult] = None
    if inp.run_lag_analysis:
        # WF-01 (CPW p. 41): the actual lags are derived from the ORIGINAL actual
        # dates, not the destatused set. Rules B/E strip in-window actuals and
        # Rule D strips the predecessor's Actual Finish, so keying the lag
        # analysis off ``destatused`` returns actual_lag=None for every in-window
        # relationship — auto-drive would then silently apply the PLANNED lag. The
        # lag analysis is defined precisely for each activity "that used to have an
        # actual date but no longer does", so it must read the pre-destatus actuals.
        orig_by_id = {a.act_id: a for a in inp.activities}
        lag_result = run_lag_analysis(
            inp.relationships, orig_by_id, inp.workday_table, inp.calendar,
            calendar_registry=inp.calendar_registry,
            lag_strategy=inp.lag_strategy,
        )
        # Emit LAG diagnostics
        for lr in lag_result.relationship_results:
            if lr.actual_lag is None:
                accum.add_lag(
                    LAGCode.LAG_007,
                    f"Relationship ({lr.pred_id}→{lr.succ_id} {lr.rel_type}): "
                    f"actual lag not computable. Missing: {lr.dates_missing}.",
                    rel_key=lr.rel_key,
                    details={"missing": lr.dates_missing},
                )
            else:
                accum.add_lag(
                    LAGCode.LAG_001,
                    f"Relationship ({lr.pred_id}→{lr.succ_id} {lr.rel_type}): "
                    f"actual_lag={lr.actual_lag} wd (planned={lr.planned_lag}, "
                    f"variance={lr.lag_variance:+.1f}).",
                    rel_key=lr.rel_key,
                    details={"actual_lag": lr.actual_lag, "variance": lr.lag_variance},
                )
                if lr.is_negative:
                    accum.add_lag(
                        LAGCode.LAG_002,
                        f"Relationship ({lr.pred_id}→{lr.succ_id} {lr.rel_type}): "
                        f"negative actual lag ({lr.actual_lag} wd) retained per CPW spec.",
                        rel_key=lr.rel_key,
                        details={"actual_lag": lr.actual_lag},
                    )
                if lr.lag_variance is not None:
                    if lr.lag_variance > 10:
                        accum.add_lag(
                            LAGCode.LAG_003,
                            f"Relationship ({lr.pred_id}→{lr.succ_id} {lr.rel_type}): "
                            f"large positive variance={lr.lag_variance:+.1f} wd.",
                            rel_key=lr.rel_key,
                            details={"variance": lr.lag_variance},
                        )
                    elif lr.lag_variance < -10:
                        accum.add_lag(
                            LAGCode.LAG_004,
                            f"Relationship ({lr.pred_id}→{lr.succ_id} {lr.rel_type}): "
                            f"large negative variance={lr.lag_variance:+.1f} wd.",
                            rel_key=lr.rel_key,
                            details={"variance": lr.lag_variance},
                        )

    # Step 8: auto-drive
    autodrive_result: Optional[AutoDriveResult] = None
    final_relationships = list(inp.relationships)

    if inp.run_autodrive and inp.run_lag_analysis and lag_result is not None:
        autodrive_result = run_autodrive(inp.relationships, lag_result.relationship_results)
        final_relationships = list(autodrive_result.applied_relationships)

        # Update lag_result driving flags
        driving_set: set[tuple[str, str, str]] = set()
        for dec in autodrive_result.decisions:
            for ld in dec.lag_decisions:
                if ld["is_driving"]:
                    driving_set.add((ld["pred_id"], dec.succ_id, ""))

        # Emit DRV diagnostics (WF-02/03: the text/counts must follow the decision
        # reason strings — a retained negative actual lag is NOT "reset to planned",
        # and the tie count is the minimum-variance group only).
        _emit_autodrive_diagnostics(accum, autodrive_result)

    # Step 9: simulation metadata
    sim_meta = SimulationMetadata(
        new_data_date=inp.new_data_date,
        old_data_date=inp.old_data_date,
        activity_count=len(inp.activities),
        transformed_count=transformed_count,
        no_change_count=no_change_count,
        no_match_count=no_match_count,
        not_in_scope_count=not_in_scope_count,
        transformation_count=len(log),
        unresolved_checkpoints=len(checkpoints.unresolved_blocking()),
        lag_computed_count=lag_result.computed_count if lag_result else 0,
        lag_skipped_count=lag_result.skipped_count if lag_result else 0,
        autodrive_applied=autodrive_result is not None,
        pc_formula_note=(
            "Rules D and F Percent Complete formula (PC = AD_before/(AD_before+RD), "
            "where AD_before is the actual duration before the new data date) is an "
            "implementation interpretation of CPW-P6 Manual p. 40. Not explicitly "
            "stated in source. Confirm before forensic reliance."
        ),
        policy_used=inp.policy.value,
    )

    is_blocked = checkpoints.is_analysis_blocked()

    return DestatusingResult(
        destatused_activities=destatused,
        transformed_relationships=final_relationships,
        rule_assignments=rule_assignments,
        transformation_log=log,
        diagnostics=accum,
        checkpoints=checkpoints,
        lag_analysis=lag_result,
        autodrive_result=autodrive_result,
        simulation_metadata=sim_meta,
        policy=inp.policy,
        new_data_date=inp.new_data_date,
        old_data_date=inp.old_data_date,
        is_blocked=is_blocked,
    )
