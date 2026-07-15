"""
V1-D: Destatusing rule classification and application (CALC-005 through CALC-010).

Converts a statused (progress-recorded) schedule back into a CPM-driven
schedule by removing actual dates and resetting durations/percent complete
according to where each activity sits relative to the new and old data dates.

Source: CPW-P6 Manual p. 40, Figure 1 ("Activity Destatus Procedure").
ADR-014 — V1-D destatusing and auto-drive governance.

Six rules (A–F) cover every positional case from Figure 1:
  A — AS and AF both before new data date       → Do nothing   (CALC-005)
  B — AS and AF both in analysis window         → Remove AS/AF, reset   (CALC-006)
  C — ES and EF both after old data date        → Do nothing   (CALC-007)
  D — AS before new DD, AF after new DD         → Remove AF, compute RD/PC (CALC-008)
  E — AS in window, EF after old DD             → Remove AS, reset OD/PC (CALC-009)
  F — AS before new DD, EF after old DD         → Compute RD/PC from new DD (CALC-010)

determine_rule() classifies any Activity into one of the six rules (or NO_MATCH).

Ported from the LI MIP 3.9 tool (mip39.destatusing.rules) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from ..models import Activity, Calendar
from ..calendar_ops import _adjust_nonworkday


# ---------------------------------------------------------------------------
# Rule classification enum
# ---------------------------------------------------------------------------

class DestatusingRule(str, Enum):
    """
    The six CPW-P6 destatusing rules (Figure 1, p. 40) plus two sentinel values.

    String mixin enables use as dict keys and in diagnostic messages.
    """
    A = "RULE_A"   # Complete before new_dd — do nothing
    B = "RULE_B"   # Complete in analysis window — remove actuals, OD=AD
    C = "RULE_C"   # Future / planned — do nothing
    D = "RULE_D"   # In-progress spanning new_dd — remove AF, compute RD/PC
    E = "RULE_E"   # Started in window — remove AS, OD=AD+RD, PC=0
    F = "RULE_F"   # Started before new_dd, finishing after old_dd
    NO_MATCH = "NO_MATCH"       # State is anomalous; analyst review required
    NOT_IN_SCOPE = "NOT_IN_SCOPE"  # Activity excluded from destatusing scope


# ---------------------------------------------------------------------------
# Rule assignment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleAssignment:
    """
    Classification result for a single activity.

    Fields:
        act_id          — Activity identifier.
        rule            — Assigned DestatusingRule.
        reason          — Human-readable explanation of why this rule was assigned.
        missing_fields  — Fields required for the rule that were None.
                          Non-empty means the rule can be determined but not applied.
        condition_notes — Additional notes about ambiguous or boundary conditions.
    """
    act_id: str
    rule: DestatusingRule
    reason: str
    missing_fields: tuple[str, ...] = ()
    condition_notes: str = ""

    def is_applicable(self) -> bool:
        """True when the rule can be applied without missing required fields."""
        return len(self.missing_fields) == 0

    def to_dict(self) -> dict:
        return {
            "act_id": self.act_id,
            "rule": self.rule.value,
            "reason": self.reason,
            "missing_fields": list(self.missing_fields),
            "condition_notes": self.condition_notes,
        }


# ---------------------------------------------------------------------------
# Rule classifier
# ---------------------------------------------------------------------------

def determine_rule(
    activity: Activity,
    new_dd: date,
    old_dd: date,
) -> RuleAssignment:
    """
    Classify an activity into one of the six destatusing rules.

    Priority follows CPW manual Figure 1. Activities with Actual Start AND
    Actual Finish are checked for Rules A, B, D first. Activities with only
    Actual Start are checked for Rules E and F. Activities with no actuals
    are checked for Rule C.

    Returns NO_MATCH when the activity state does not match any rule cleanly.
    This is a legitimate diagnostic condition requiring analyst review.

    Source: CPW-P6 Manual p. 40.
    """
    a = activity
    as_ = a.actual_start
    af_ = a.actual_finish
    es_ = a.early_start
    ef_ = a.early_finish

    # --- Activities with both Actual Start and Actual Finish ---
    if as_ is not None and af_ is not None:
        # Rule A: AS and AF both before new_dd (complete before analysis window)
        if as_ < new_dd and af_ < new_dd:
            return RuleAssignment(
                act_id=a.act_id,
                rule=DestatusingRule.A,
                reason=(
                    f"AS={as_} and AF={af_} both before new_dd={new_dd}. "
                    "Activity complete before analysis window. No change required."
                ),
            )
        # Rule B: AS and AF both in analysis window (new_dd < both < old_dd)
        if as_ > new_dd and af_ > new_dd and as_ < old_dd and af_ < old_dd:
            missing = []
            if a.actual_duration is None:
                missing.append("actual_duration")
            return RuleAssignment(
                act_id=a.act_id,
                rule=DestatusingRule.B,
                reason=(
                    f"AS={as_} and AF={af_} both after new_dd={new_dd} and "
                    f"before old_dd={old_dd}. Remove actuals; OD=AD; PC=0."
                ),
                missing_fields=tuple(missing),
            )
        # Rule D: AS before new_dd, AF after new_dd (in-progress spanning new_dd)
        if as_ < new_dd and af_ > new_dd:
            missing = []
            if a.actual_duration is None:
                missing.append("actual_duration")
            return RuleAssignment(
                act_id=a.act_id,
                rule=DestatusingRule.D,
                reason=(
                    f"AS={as_} before new_dd={new_dd} and AF={af_} after new_dd. "
                    "In-progress spanning new data date. Remove AF; compute RD/PC."
                ),
                missing_fields=tuple(missing),
            )

    # --- Activities with Actual Start only (no Actual Finish) ---
    if as_ is not None and af_ is None:
        # Rule E: AS in window (new_dd < AS < old_dd), EF after old_dd
        if as_ > new_dd and as_ < old_dd:
            if ef_ is not None and ef_ > old_dd:
                missing = []
                if a.actual_duration is None:
                    missing.append("actual_duration")
                if a.remaining_duration is None:
                    missing.append("remaining_duration")
                return RuleAssignment(
                    act_id=a.act_id,
                    rule=DestatusingRule.E,
                    reason=(
                        f"AS={as_} in window (new_dd={new_dd}, old_dd={old_dd}); "
                        f"EF={ef_} after old_dd. Remove AS; OD=AD+RD; PC=0."
                    ),
                    missing_fields=tuple(missing),
                )
            elif ef_ is None:
                return RuleAssignment(
                    act_id=a.act_id,
                    rule=DestatusingRule.NO_MATCH,
                    reason=(
                        f"AS={as_} in window but EF is None. Cannot classify. "
                        "Analyst review required."
                    ),
                    missing_fields=("early_finish",),
                )
        # Rule F: AS before new_dd, EF after old_dd
        if as_ < new_dd:
            if ef_ is not None and ef_ > old_dd:
                missing = []
                if a.actual_duration is None:
                    missing.append("actual_duration")
                return RuleAssignment(
                    act_id=a.act_id,
                    rule=DestatusingRule.F,
                    reason=(
                        f"AS={as_} before new_dd={new_dd}; "
                        f"EF={ef_} after old_dd={old_dd}. "
                        "Compute RD/PC from new_dd to old EF."
                    ),
                    missing_fields=tuple(missing),
                )
            elif ef_ is None:
                return RuleAssignment(
                    act_id=a.act_id,
                    rule=DestatusingRule.NO_MATCH,
                    reason=(
                        f"AS={as_} before new_dd={new_dd} but EF is None. "
                        "Cannot determine Rule F applicability."
                    ),
                    missing_fields=("early_finish",),
                )

    # --- Activities with no actuals ---
    if as_ is None and af_ is None:
        if es_ is not None and ef_ is not None and es_ > old_dd and ef_ > old_dd:
            return RuleAssignment(
                act_id=a.act_id,
                rule=DestatusingRule.C,
                reason=(
                    f"No actuals. ES={es_} and EF={ef_} both after old_dd={old_dd}. "
                    "Future activity. No change required."
                ),
            )
        if es_ is not None and ef_ is not None:
            return RuleAssignment(
                act_id=a.act_id,
                rule=DestatusingRule.NOT_IN_SCOPE,
                reason=(
                    f"No actuals. ES={es_}, EF={ef_}. Activity dates do not "
                    "clearly place it in window or as future planned. "
                    "May be partially in-scope or before analysis window start."
                ),
            )
        return RuleAssignment(
            act_id=a.act_id,
            rule=DestatusingRule.NOT_IN_SCOPE,
            reason=(
                "No actuals and ES/EF not available. Activity has no progress "
                "and cannot be classified."
            ),
            missing_fields=("early_start", "early_finish") if (es_ is None or ef_ is None) else (),
        )

    # --- Catch-all: anomalous state ---
    return RuleAssignment(
        act_id=a.act_id,
        rule=DestatusingRule.NO_MATCH,
        reason=(
            f"Activity state does not match any destatusing rule. "
            f"AS={as_}, AF={af_}, ES={es_}, EF={ef_}. "
            "Analyst review required."
        ),
    )


# ---------------------------------------------------------------------------
# Internal helpers (preserved from original destatusing.py)
# ---------------------------------------------------------------------------

def _require_field(activity: Activity, fld: str, rule: str) -> None:
    """Raise ValueError if a required field is None."""
    if getattr(activity, fld, None) is None:
        raise ValueError(
            f"Destatusing {rule}: activity {activity.act_id!r} is missing "
            f"required field '{fld}'."
        )


def _workdays_between(
    start: date,
    end: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> float:
    """Count workdays from start (exclusive) to end (inclusive). Returns 0.0 if start >= end."""
    if not calendar.is_workday(start):
        start = _adjust_nonworkday(
            start, calendar, is_start=True, workday_table=workday_table
        )
    if not calendar.is_workday(end):
        end = _adjust_nonworkday(
            end, calendar, is_start=False, workday_table=workday_table
        )
    if start >= end:
        return 0.0
    start_num = workday_table.get(start)
    end_num = workday_table.get(end)
    if start_num is None or end_num is None:
        raise ValueError(
            f"_workdays_between: dates not found in workday table after adjustment: "
            f"start={start} (wd={start_num}), end={end} (wd={end_num})."
        )
    return max(float(end_num - start_num), 0.0)


# ---------------------------------------------------------------------------
# Remaining-duration method (AACE 29R-03 §3.9 "Reconstructed Updates", pp.30-32)
# ---------------------------------------------------------------------------

class RDMethod(str, Enum):
    """How an in-progress activity's remaining duration is reconstructed.

    Per AACE 29R-03 §3.9, the two schools of thought for re-creating a partially
    statused schedule:

    * **HINDSIGHT** — the forensic scheduler performs the analysis after the job
      is complete, so the *actual* performance dates/durations are used. The
      governed destatus Rules D/F already do this (RD measured from the new data
      date to the activity's actual/forecast finish).

    * **BLINDSIGHT** ("blinders") — stand in the scheduler's shoes at the data
      date; assume a straight line and do NOT use after-the-fact knowledge:
          IF (DD - AS) < OD:  RD = OD - (DD - AS)
          ELSE:               RD = 1

    29R-03 §3.9.F.5 expects *both* models to be run per window and compared.
    """

    HINDSIGHT = "hindsight"
    BLINDSIGHT = "blindsight"


def blindsight_remaining_duration(
    activity: Activity,
    new_dd: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> int:
    """29R-03 §3.9 "Blindsight" remaining duration for an in-progress activity.

    Straight-line from the *original* duration, ignoring after-the-fact knowledge:
    ``RD = OD - (new_dd - AS)`` when that is positive, else ``1``. Requires
    ``actual_start`` and ``original_duration``.
    """
    od = int(activity.original_duration or 0)
    if activity.actual_start is None or od <= 0:
        return 1
    elapsed = int(
        _workdays_between(activity.actual_start, new_dd, workday_table, calendar)
    )
    rd = od - elapsed
    return rd if rd >= 1 else 1


# ---------------------------------------------------------------------------
# CALC-005: Destatusing Rule A — do nothing
# ---------------------------------------------------------------------------

def destatus_rule_a(activity: Activity, new_dd: date, old_dd: date) -> Activity:
    """CALC-005 — Rule A: AS and AF both before new_dd. Do nothing."""
    _require_field(activity, "actual_start", "Rule A (CALC-005)")
    _require_field(activity, "actual_finish", "Rule A (CALC-005)")
    if not (activity.actual_start < new_dd and activity.actual_finish < new_dd):  # type: ignore[operator]
        raise ValueError(
            f"Rule A (CALC-005): condition not met for {activity.act_id!r}. "
            f"AS={activity.actual_start}, AF={activity.actual_finish}, new_dd={new_dd}."
        )
    return copy.copy(activity)


# ---------------------------------------------------------------------------
# CALC-006: Destatusing Rule B — remove actuals, OD=AD, PC=0
# ---------------------------------------------------------------------------

def destatus_rule_b(activity: Activity, new_dd: date, old_dd: date) -> Activity:
    """CALC-006 — Rule B: AS and AF both in analysis window. Remove actuals; OD=AD; PC=0."""
    _require_field(activity, "actual_start", "Rule B (CALC-006)")
    _require_field(activity, "actual_finish", "Rule B (CALC-006)")
    _require_field(activity, "actual_duration", "Rule B (CALC-006)")
    if not (
        activity.actual_start > new_dd  # type: ignore[operator]
        and activity.actual_finish > new_dd  # type: ignore[operator]
        and activity.actual_start < old_dd  # type: ignore[operator]
        and activity.actual_finish < old_dd  # type: ignore[operator]
    ):
        raise ValueError(
            f"Rule B (CALC-006): condition not met for {activity.act_id!r}. "
            f"AS={activity.actual_start}, AF={activity.actual_finish}, "
            f"new_dd={new_dd}, old_dd={old_dd}."
        )
    result = copy.copy(activity)
    result.actual_start = None
    result.actual_finish = None
    result.original_duration = activity.actual_duration
    result.percent_complete = 0.0
    return result


# ---------------------------------------------------------------------------
# CALC-007: Destatusing Rule C — future activity, do nothing
# ---------------------------------------------------------------------------

def destatus_rule_c(activity: Activity, new_dd: date, old_dd: date) -> Activity:
    """CALC-007 — Rule C: ES and EF both after old_dd. Do nothing."""
    _require_field(activity, "early_start", "Rule C (CALC-007)")
    _require_field(activity, "early_finish", "Rule C (CALC-007)")
    if not (activity.early_start > old_dd and activity.early_finish > old_dd):  # type: ignore[operator]
        raise ValueError(
            f"Rule C (CALC-007): condition not met for {activity.act_id!r}. "
            f"ES={activity.early_start}, EF={activity.early_finish}, old_dd={old_dd}."
        )
    return copy.copy(activity)


# ---------------------------------------------------------------------------
# CALC-008: Destatusing Rule D — remove AF, compute RD/PC
# ---------------------------------------------------------------------------

def destatus_rule_d(
    activity: Activity,
    new_dd: date,
    old_dd: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> Activity:
    """
    CALC-008 — Rule D: AS before new_dd, AF after new_dd.
    Remove AF; compute RD = workdays from new_dd to old AF; compute
    PC = AD_before/(AD_before+RD) where AD_before = workdays(AS→new_dd) (WF-06).
    The caller-supplied ``actual_duration`` (the full as-built span in the analyst
    API) is NOT the PC basis; it is retained only for the AD+RD>0 guard.
    PC formula is an implementation interpretation — confirm before production use.
    """
    _require_field(activity, "actual_start", "Rule D (CALC-008)")
    _require_field(activity, "actual_finish", "Rule D (CALC-008)")
    _require_field(activity, "actual_duration", "Rule D (CALC-008)")
    if not (activity.actual_start < new_dd and activity.actual_finish > new_dd):  # type: ignore[operator]
        raise ValueError(
            f"Rule D (CALC-008): condition not met for {activity.act_id!r}. "
            f"AS={activity.actual_start}, AF={activity.actual_finish}, new_dd={new_dd}."
        )
    rd = _workdays_between(new_dd, activity.actual_finish, workday_table, calendar)  # type: ignore[arg-type]
    ad = activity.actual_duration  # type: ignore[assignment]
    total = ad + rd
    if total <= 0:
        raise ValueError(
            f"Rule D (CALC-008): AD+RD <= 0 for {activity.act_id!r}. AD={ad}, RD={rd}."
        )
    # WF-06 (CALC-008): percent-complete is measured on the AD accrued BEFORE the
    # new data date — AD_before/(AD_before+RD) — NOT the full as-built AD. The
    # analyst API derives actual_duration = wd(AS→AF), so using the caller's AD
    # double-counts the post-new_dd segment already inside RD and overstates PC.
    # AS is required for Rule D, so AD_before = wd(AS→new_dd) in the same workday
    # convention RD uses.
    ad_before = _workdays_between(
        activity.actual_start, new_dd, workday_table, calendar  # type: ignore[arg-type]
    )
    pc_total = ad_before + rd
    result = copy.copy(activity)
    result.actual_finish = None
    result.remaining_duration = rd
    result.percent_complete = (ad_before / pc_total) if pc_total > 0 else 0.0
    return result


# ---------------------------------------------------------------------------
# CALC-009: Destatusing Rule E — remove AS, OD=AD+RD, PC=0
# ---------------------------------------------------------------------------

def destatus_rule_e(activity: Activity, new_dd: date, old_dd: date) -> Activity:
    """CALC-009 — Rule E: AS in window, EF after old_dd. Remove AS; OD=AD+RD; PC=0."""
    _require_field(activity, "actual_start", "Rule E (CALC-009)")
    _require_field(activity, "early_finish", "Rule E (CALC-009)")
    _require_field(activity, "actual_duration", "Rule E (CALC-009)")
    _require_field(activity, "remaining_duration", "Rule E (CALC-009)")
    if not (
        activity.actual_start > new_dd  # type: ignore[operator]
        and activity.actual_start < old_dd  # type: ignore[operator]
        and activity.early_finish > old_dd  # type: ignore[operator]
    ):
        raise ValueError(
            f"Rule E (CALC-009): condition not met for {activity.act_id!r}. "
            f"AS={activity.actual_start}, EF={activity.early_finish}, "
            f"new_dd={new_dd}, old_dd={old_dd}."
        )
    result = copy.copy(activity)
    result.actual_start = None
    result.original_duration = activity.actual_duration + activity.remaining_duration  # type: ignore[operator]
    result.percent_complete = 0.0
    return result


# ---------------------------------------------------------------------------
# CALC-010: Destatusing Rule F — compute RD/PC from new_dd to old EF
# ---------------------------------------------------------------------------

def destatus_rule_f(
    activity: Activity,
    new_dd: date,
    old_dd: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> Activity:
    """
    CALC-010 — Rule F: AS before new_dd, EF after old_dd.
    Compute RD = workdays from new_dd to old EF; compute
    PC = AD_before/(AD_before+RD) where AD_before = workdays(AS→new_dd) (WF-06).
    The caller-supplied ``actual_duration`` (the full as-built span in the analyst
    API) is NOT the PC basis; it is retained only for the AD+RD>0 guard.
    PC formula is an implementation interpretation — confirm before production use.
    """
    _require_field(activity, "actual_start", "Rule F (CALC-010)")
    _require_field(activity, "early_finish", "Rule F (CALC-010)")
    _require_field(activity, "actual_duration", "Rule F (CALC-010)")
    if not (activity.actual_start < new_dd and activity.early_finish > old_dd):  # type: ignore[operator]
        raise ValueError(
            f"Rule F (CALC-010): condition not met for {activity.act_id!r}. "
            f"AS={activity.actual_start}, EF={activity.early_finish}, "
            f"new_dd={new_dd}, old_dd={old_dd}."
        )
    rd = _workdays_between(new_dd, activity.early_finish, workday_table, calendar)  # type: ignore[arg-type]
    ad = activity.actual_duration  # type: ignore[assignment]
    total = ad + rd
    if total <= 0:
        raise ValueError(
            f"Rule F (CALC-010): AD+RD <= 0 for {activity.act_id!r}. AD={ad}, RD={rd}."
        )
    # WF-06 (CALC-008/010): PC uses the AD accrued BEFORE the new data date —
    # AD_before/(AD_before+RD), AD_before = wd(AS→new_dd) — not the full as-built
    # AD the analyst API supplies (which double-counts the post-new_dd segment in
    # RD). actual_duration is retained only for the AD+RD>0 guard.
    ad_before = _workdays_between(
        activity.actual_start, new_dd, workday_table, calendar  # type: ignore[arg-type]
    )
    pc_total = ad_before + rd
    result = copy.copy(activity)
    result.remaining_duration = rd
    result.percent_complete = (ad_before / pc_total) if pc_total > 0 else 0.0
    return result
