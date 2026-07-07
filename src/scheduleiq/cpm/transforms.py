"""
V1-E: Activity preparation transforms for ABCS CPM re-analysis.

prepare_activities_for_cpm() converts destatused activities into CPM-ready
form by substituting durations appropriate for re-scheduling:

  Rule A (complete before new_dd):  original_duration unchanged.
                                    Activity is complete; CPM schedules it
                                    with its original span. Actual dates are
                                    not used by the engine.
  Rule B (complete in window):      original_duration = actual_duration
                                    (already set by the destatusing transform).
                                    No further adjustment needed.
  Rule C (planned after old_dd):    original_duration unchanged.
                                    Activity is fully planned; CPM uses OD.
  Rule D (in-progress spanning new_dd):
                                    original_duration = remaining_duration.
                                    Only remaining work appears in ABCS CPM.
  Rule E (started in window, finishing after):
                                    original_duration unchanged (already reset
                                    by Rule E destatusing transform).
  Rule F (started before window, finishing after):
                                    original_duration = remaining_duration.
                                    Only remaining work appears in ABCS CPM.
  NO_MATCH / NOT_IN_SCOPE:          original_duration unchanged (pass-through).

Source: ADR-015; CPW-P6 Manual pp. 12-20 (ABCS production);
        CPW-P6 Manual p. 40 (Rules D/F remaining duration).

Ported from the LI MIP 3.9 tool (mip39.simulation.transforms) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from .models import Activity, Relationship
from .destatusing.rules import DestatusingRule, RuleAssignment


def prepare_activities_for_cpm(
    destatused_activities: list[Activity],
    rule_assignments: dict[str, RuleAssignment],
) -> list[Activity]:
    """
    Convert destatused activities to CPM-ready form for ABCS scheduling.

    For Rule D and Rule F activities: substitutes original_duration with
    remaining_duration. For all other rules: returns a copy with original_duration
    unchanged.

    Activities whose remaining_duration is None for Rules D/F emit a zero
    duration (milestone equivalent) — the caller receives a SIM-008 diagnostic
    via the generator; this function does not raise.

    Args:
        destatused_activities: Output of run_destatusing().destatused_activities.
        rule_assignments:      dict[act_id → RuleAssignment] from DestatusingResult.

    Returns:
        List of Activity copies ready for CPM forward/backward pass.
    """
    result: list[Activity] = []
    for act in destatused_activities:
        assignment = rule_assignments.get(act.act_id)
        prepared = copy.copy(act)

        if assignment is not None:
            rule = assignment.rule
            if rule in (DestatusingRule.D, DestatusingRule.F):
                if act.remaining_duration is not None:
                    prepared.original_duration = int(act.remaining_duration)
                else:
                    prepared.original_duration = 0

        result.append(prepared)
    return result


def apply_actual_date_pins(
    activities: list[Activity],
) -> tuple[list[Activity], int, int]:
    """
    V2-A actual-date-anchored CPM (ADR-019, brief §4.5): pin completed and
    in-progress activities at their ACTUAL dates so the CPM forward pass fixes
    them there and propagates forward from those anchors, reproducing CPW/P6
    as-built results rather than recomputing completed work from logic.

    Pin assignment (load-bearing — this is the anchoring mode):
      - Completed (actual_finish present): pinned_early_start = actual_start,
        pinned_early_finish = actual_finish. Both pins set → forward pass treats
        the activity as a hard fact and ignores predecessor logic.
      - In-progress (actual_start present, no actual_finish):
        pinned_early_start = actual_start only. ES is anchored; EF is computed
        forward over remaining duration by the engine.
      - Future (no actual_start): no pins; scheduled from predecessors as usual.

    A completed activity with actual_finish but no actual_start is still pinned
    as completed (start defaults to its actual_finish) so it cannot float off
    its actual dates; this is a defensive edge case and is counted as completed.

    Returns:
        (pinned_activities, completed_count, in_progress_count) — a new list of
        Activity copies with pins assigned, plus counts for run provenance.
    """
    result: list[Activity] = []
    completed_count = 0
    in_progress_count = 0
    for act in activities:
        prepared = copy.copy(act)
        if act.actual_finish is not None:
            # Completed: pin both ES and EF at actuals.
            prepared.pinned_early_start = (
                act.actual_start if act.actual_start is not None else act.actual_finish
            )
            prepared.pinned_early_finish = act.actual_finish
            completed_count += 1
        elif act.actual_start is not None:
            # In-progress: pin ES only; EF computed from remaining duration.
            prepared.pinned_early_start = act.actual_start
            prepared.pinned_early_finish = None
            in_progress_count += 1
        # else: future activity — leave pins None.
        result.append(prepared)
    return result, completed_count, in_progress_count


def prepare_relationships_for_variant(
    relationships: list[Relationship],
    lag_results: Optional[list[Any]],  # list[ActualLagResult] from lag analysis
    use_actual_lags: bool,
    use_autodrive: bool,
    autodrive_relationships: Optional[list[Relationship]] = None,
) -> list[Relationship]:
    """
    Select the appropriate relationship set based on simulation variant.

    Decision logic:
      - AUTO_DRIVEN / ANALYST_REVIEWED: use autodrive_relationships (driving
        predecessors have actual lag; non-driving reset to planned lag).
      - LAG_ADJUSTED: apply actual_lag to all relationships where available.
      - BASELINE / NORMALIZED with no destatusing: use original relationships.

    Args:
        relationships:          Original or destatused relationships.
        lag_results:            ActualLagResult objects from lag analysis.
        use_actual_lags:        Apply actual lag to all rels (LAG_ADJUSTED).
        use_autodrive:          Use auto-drive relationship set (AUTO_DRIVEN).
        autodrive_relationships: Pre-built auto-driven relationships from
                                 DestatusingResult.transformed_relationships.

    Returns:
        List of Relationship copies with appropriate lag values.
    """
    if use_autodrive and autodrive_relationships is not None:
        return list(autodrive_relationships)

    if use_actual_lags and lag_results is not None:
        # Build lookup: (pred_id, succ_id, rel_type) → actual_lag
        lag_lookup: dict[tuple[str, str, str], Optional[float]] = {}
        for lr in lag_results:
            if lr.actual_lag is not None:
                lag_lookup[(lr.pred_id, lr.succ_id, lr.rel_type)] = lr.actual_lag

        result: list[Relationship] = []
        for rel in relationships:
            key = (rel.pred_id, rel.succ_id, rel.rel_type)
            actual = lag_lookup.get(key)
            if actual is not None:
                new_rel = copy.copy(rel)
                new_rel.lag = actual
                result.append(new_rel)
            else:
                result.append(copy.copy(rel))
        return result

    return [copy.copy(r) for r in relationships]
