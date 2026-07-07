"""
V1-D: Governed transformation layer.

apply_rule_with_provenance() wraps each CALC-005 through CALC-010 rule
function with provenance record generation. Every field change produces a
TransformationRecord before the Activity is returned.

No transformation is silent. All changes are captured in the log before
the transformed Activity is added to the output set.

Source: ADR-014 §3 (transformation provenance); CPW-P6 Manual p. 40.

Ported from the LI MIP 3.9 tool (mip39.destatusing.transformations) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from ..models import Activity, Calendar
from .rules import (
    DestatusingRule,
    RuleAssignment,
    destatus_rule_a,
    destatus_rule_b,
    destatus_rule_c,
    destatus_rule_d,
    destatus_rule_e,
    destatus_rule_f,
)
from .provenance import (
    TransformationLog,
    make_removal_record,
    make_set_record,
    make_compute_record,
)


def apply_rule_with_provenance(
    assignment: RuleAssignment,
    activity: Activity,
    new_dd: date,
    old_dd: date,
    log: TransformationLog,
    workday_table: dict[date, int] | None = None,
    calendar: Calendar | None = None,
    context: str = "",
) -> Activity:
    """
    Apply the assigned destatusing rule to an Activity and record all field changes.

    For Rules A and C (no-change rules), a copy is returned and an informational
    record is created confirming no transformation was applied.

    For Rules B, D, E, F (transformation rules), one record is created per field
    changed, before the transformed Activity is returned.

    Args:
        assignment:    RuleAssignment from determine_rule().
        activity:      Source activity (never mutated).
        new_dd:        New (earlier) data date.
        old_dd:        Old (later) data date.
        log:           TransformationLog to append records to.
        workday_table: Required for Rules D and F (workday arithmetic).
        calendar:      Required for Rules D and F.
        context:       Optional run/session context string.

    Returns:
        Transformed Activity (new object; source is not mutated).

    Raises:
        ValueError: If rule application fails (missing fields, conditions not met).
        ValueError: If workday_table or calendar is None for Rules D or F.
    """
    rule = assignment.rule
    act_id = activity.act_id
    rule_str = rule.value

    if rule == DestatusingRule.A:
        transformed = destatus_rule_a(activity, new_dd, old_dd)
        make_set_record(
            log, act_id, rule_str, "CALC-005", "_rule_applied",
            source_value=None, target_value="RULE_A_NO_CHANGE",
            reversible=True, analyst_review_required=False,
            analytical_implication="Activity complete before analysis window. No fields modified.",
            context=context,
        )
        return transformed

    if rule == DestatusingRule.C:
        transformed = destatus_rule_c(activity, new_dd, old_dd)
        make_set_record(
            log, act_id, rule_str, "CALC-007", "_rule_applied",
            source_value=None, target_value="RULE_C_NO_CHANGE",
            reversible=True, analyst_review_required=False,
            analytical_implication="Future/planned activity. No fields modified.",
            context=context,
        )
        return transformed

    if rule == DestatusingRule.B:
        transformed = destatus_rule_b(activity, new_dd, old_dd)
        make_removal_record(
            log, act_id, rule_str, "CALC-006", "actual_start",
            source_value=activity.actual_start,
            analyst_review_required=False,
            analytical_implication=(
                "Actual Start removed. Activity completed in analysis window; "
                "will be CPM-scheduled from project logic."
            ),
            context=context,
        )
        make_removal_record(
            log, act_id, rule_str, "CALC-006", "actual_finish",
            source_value=activity.actual_finish,
            analyst_review_required=False,
            analytical_implication=(
                "Actual Finish removed. Activity completed in analysis window; "
                "duration converted to OD."
            ),
            context=context,
        )
        make_set_record(
            log, act_id, rule_str, "CALC-006", "original_duration",
            source_value=activity.original_duration,
            target_value=transformed.original_duration,
            reversible=True,
            analyst_review_required=False,
            analytical_implication=(
                f"Original Duration set to Actual Duration ({transformed.original_duration} wd). "
                "Activity will schedule based on its actual elapsed duration."
            ),
            context=context,
        )
        make_set_record(
            log, act_id, rule_str, "CALC-006", "percent_complete",
            source_value=activity.percent_complete,
            target_value=0.0,
            reversible=True,
            analyst_review_required=False,
            analytical_implication="Percent Complete reset to 0. Activity treated as not-started.",
            context=context,
        )
        return transformed

    if rule == DestatusingRule.D:
        if workday_table is None or calendar is None:
            raise ValueError(
                f"Rule D (CALC-008) for {act_id!r} requires workday_table and calendar."
            )
        transformed = destatus_rule_d(activity, new_dd, old_dd, workday_table, calendar)
        make_removal_record(
            log, act_id, rule_str, "CALC-008", "actual_finish",
            source_value=activity.actual_finish,
            analyst_review_required=False,
            analytical_implication=(
                "Actual Finish removed. In-progress activity spanning new data date; "
                "RD computed from new_dd to old AF."
            ),
            context=context,
        )
        make_compute_record(
            log, act_id, rule_str, "CALC-008", "remaining_duration",
            source_value=activity.remaining_duration,
            target_value=transformed.remaining_duration,
            analyst_review_required=False,
            analytical_implication=(
                f"Remaining Duration computed as {transformed.remaining_duration} wd "
                f"(workdays from new_dd={new_dd} to old AF={activity.actual_finish})."
            ),
            context=context,
        )
        make_compute_record(
            log, act_id, rule_str, "CALC-008", "percent_complete",
            source_value=activity.percent_complete,
            target_value=transformed.percent_complete,
            analyst_review_required=True,
            analytical_implication=(
                f"PC={transformed.percent_complete:.4f} computed as AD_before/(AD_before+RD) "
                "(AD_before = workdays from AS to the new data date; WF-06). "
                "Formula is an implementation interpretation of CPW Manual p. 40. "
                "Confirm before forensic reliance."
            ),
            context=context,
        )
        return transformed

    if rule == DestatusingRule.E:
        transformed = destatus_rule_e(activity, new_dd, old_dd)
        make_removal_record(
            log, act_id, rule_str, "CALC-009", "actual_start",
            source_value=activity.actual_start,
            analyst_review_required=False,
            analytical_implication=(
                "Actual Start removed. Activity started in window; "
                "will be CPM-scheduled from project logic."
            ),
            context=context,
        )
        make_set_record(
            log, act_id, rule_str, "CALC-009", "original_duration",
            source_value=activity.original_duration,
            target_value=transformed.original_duration,
            reversible=True,
            analyst_review_required=False,
            analytical_implication=(
                f"OD set to AD+RD = {transformed.original_duration} wd. "
                "Activity will span full actual + remaining duration in CPM."
            ),
            context=context,
        )
        make_set_record(
            log, act_id, rule_str, "CALC-009", "percent_complete",
            source_value=activity.percent_complete,
            target_value=0.0,
            reversible=True,
            analyst_review_required=False,
            analytical_implication="Percent Complete reset to 0. Activity treated as not-started.",
            context=context,
        )
        return transformed

    if rule == DestatusingRule.F:
        if workday_table is None or calendar is None:
            raise ValueError(
                f"Rule F (CALC-010) for {act_id!r} requires workday_table and calendar."
            )
        transformed = destatus_rule_f(activity, new_dd, old_dd, workday_table, calendar)
        make_compute_record(
            log, act_id, rule_str, "CALC-010", "remaining_duration",
            source_value=activity.remaining_duration,
            target_value=transformed.remaining_duration,
            analyst_review_required=False,
            analytical_implication=(
                f"RD computed as {transformed.remaining_duration} wd "
                f"(workdays from new_dd={new_dd} to old EF={activity.early_finish})."
            ),
            context=context,
        )
        make_compute_record(
            log, act_id, rule_str, "CALC-010", "percent_complete",
            source_value=activity.percent_complete,
            target_value=transformed.percent_complete,
            analyst_review_required=True,
            analytical_implication=(
                f"PC={transformed.percent_complete:.4f} computed as AD_before/(AD_before+RD) "
                "(AD_before = workdays from AS to the new data date; WF-06). "
                "Formula is an implementation interpretation of CPW Manual p. 40. "
                "Confirm before forensic reliance."
            ),
            context=context,
        )
        return transformed

    # NO_MATCH and NOT_IN_SCOPE — no transformation applied, record the skip
    if rule in (DestatusingRule.NO_MATCH, DestatusingRule.NOT_IN_SCOPE):
        make_set_record(
            log, act_id, rule_str, "N/A", "_rule_applied",
            source_value=None, target_value=rule.value,
            reversible=True,
            analyst_review_required=(rule == DestatusingRule.NO_MATCH),
            analytical_implication=(
                "Activity not transformed. "
                + ("State is anomalous — analyst review required." if rule == DestatusingRule.NO_MATCH
                   else "Activity not in destatusing scope.")
            ),
            context=context,
        )
        return copy.copy(activity)

    raise ValueError(f"apply_rule_with_provenance: unknown rule {rule!r}.")
