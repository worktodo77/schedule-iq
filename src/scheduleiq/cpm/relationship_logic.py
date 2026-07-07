"""
Ported from the LI MIP 3.9 tool (mip39.relationship_logic) per ADR-0007 — port-and-validate.
CALC-004: Retained Logic Driving Relationship

Computes the date constraints imposed by predecessor relationships on a
successor activity under Retained Logic scheduling, and identifies which
relationship(s) are driving.

Source: CPW-P6 Manual [relationship logic section].
ADR-002: Retained Logic only. Progress Override is explicitly excluded.

Relationship types and constrained date:
  FS (Finish-to-Start): constrains successor Early Start (ES)
    constrained_es = pred_ef + lag
  SS (Start-to-Start):  constrains successor Early Start (ES)
    constrained_es = pred_es + lag
  FF (Finish-to-Finish): constrains successor Early Finish (EF)
    constrained_ef = pred_ef + lag
  SF (Start-to-Finish):  constrains successor Early Finish (EF)
    constrained_ef = pred_es + lag

Driving relationship: the relationship that imposes the latest constraint
date on the successor. A relationship is driving if its constrained date
equals the successor's actual early date (ES or EF as appropriate).
Co-driving is possible when multiple relationships produce the same
latest constraint.

Phase 2 simplifications (ADR-002):
  - Integer workday lags only.
  - Single calendar; no exception dates.
  - No full CPM forward pass — single-relationship and multi-predecessor
    constraint evaluation only.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .conventions import EFConvention, fs_forward_offset
from .models import Activity, Relationship, Calendar
from .lag_analysis import apply_lag


# ---------------------------------------------------------------------------
# CALC-004: Relationship constraint computation
# ---------------------------------------------------------------------------

def compute_relationship_constraint(
    rel_type: str,
    pred_es: date,
    pred_ef: date,
    lag_workdays: float,
    workday_table: dict[date, int],
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
) -> tuple[str, date]:
    """
    CALC-004 — Compute the date constraint a relationship imposes on its successor.

    Under Retained Logic, each relationship type constrains a specific early
    date of the successor:
      FS → ("ES", pred_ef + lag)   — successor Early Start
      SS → ("ES", pred_es + lag)   — successor Early Start
      FF → ("EF", pred_ef + lag)   — successor Early Finish
      SF → ("EF", pred_es + lag)   — successor Early Finish

    Non-workday predecessor dates are adjusted using the CALC-001 rule before
    lag arithmetic (CPW Manual pp. 41-42):
      pred_ef (finish-type) → retreat to previous workday if non-workday.
      pred_es (start-type)  → advance to next workday if non-workday.

    Source: CPW-P6 Manual [relationship logic section]; ADR-002
    Assumption: Retained Logic; single calendar; integer lags (ADR-002).
    Assumption: FS lag=0 convention — constrained_es = pred_ef (same workday).
    Limitation: Single-relationship evaluation only; not a full CPM forward pass.

    Args:
        rel_type:      Relationship type: "FS", "SS", "FF", or "SF".
        pred_es:       Predecessor Early Start.
        pred_ef:       Predecessor Early Finish.
        lag_workdays:  Lag in workdays (may be negative for lead).
        workday_table: Prebuilt workday table covering all relevant dates.
        calendar:      Calendar for non-workday adjustment.

    Returns:
        Tuple (constraint_type, constrained_date) where:
          constraint_type — "ES" for FS/SS relationships, "EF" for FF/SF.
          constrained_date — the computed constraint date.

    Raises:
        ValueError: If rel_type is not one of {"FS", "SS", "FF", "SF"}, or if
                    workday arithmetic fails (dates outside table range).
    """
    valid_types = {"FS", "SS", "FF", "SF"}
    if rel_type not in valid_types:
        raise ValueError(
            f"compute_relationship_constraint (CALC-004): invalid rel_type "
            f"{rel_type!r}. Must be one of {sorted(valid_types)}."
        )

    if rel_type == "FS":
        effective_lag = lag_workdays + fs_forward_offset(convention)
        constrained = apply_lag(
            pred_ef, effective_lag, workday_table, calendar, anchor_is_start=False
        )
        return ("ES", constrained)

    if rel_type == "SS":
        constrained = apply_lag(
            pred_es, lag_workdays, workday_table, calendar, anchor_is_start=True
        )
        return ("ES", constrained)

    if rel_type == "FF":
        constrained = apply_lag(
            pred_ef, lag_workdays, workday_table, calendar, anchor_is_start=False
        )
        return ("EF", constrained)

    # rel_type == "SF"
    constrained = apply_lag(
        pred_es, lag_workdays, workday_table, calendar, anchor_is_start=True
    )
    return ("EF", constrained)


# ---------------------------------------------------------------------------
# CALC-004: Driving relationship identification
# ---------------------------------------------------------------------------

def is_driving_relationship(
    rel_type: str,
    pred_es: date,
    pred_ef: date,
    succ_es: date,
    succ_ef: date,
    lag_workdays: float,
    workday_table: dict[date, int],
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
) -> bool:
    """
    CALC-004 — Determine whether a single relationship is driving for its successor.

    A relationship is driving if the date constraint it imposes equals the
    successor's actual early date:
      FS/SS: driving if constrained_es == succ_es
      FF/SF: driving if constrained_ef == succ_ef

    This checks a single relationship in isolation. In a multi-predecessor
    network, a relationship is truly driving only if its constrained date is
    also the latest among all incoming constraints (i.e., the forward-pass
    winner). For multi-predecessor analysis, use find_driving_relationship().

    Source: CPW-P6 Manual [relationship logic section]; ADR-002
    Assumption: Retained Logic. Successor early dates come from a completed
                CPM forward pass (Phase 3 — not computed here).
    Limitation: Does not re-compute successor dates; takes them as given.

    Args:
        rel_type:      Relationship type: "FS", "SS", "FF", or "SF".
        pred_es:       Predecessor Early Start.
        pred_ef:       Predecessor Early Finish.
        succ_es:       Successor Early Start (from CPM forward pass).
        succ_ef:       Successor Early Finish (from CPM forward pass).
        lag_workdays:  Lag in workdays.
        workday_table: Prebuilt workday table.
        calendar:      Calendar for non-workday adjustment.

    Returns:
        True if this relationship is driving; False otherwise.

    Raises:
        ValueError: If rel_type is invalid or workday arithmetic fails.
    """
    constraint_type, constrained_date = compute_relationship_constraint(
        rel_type, pred_es, pred_ef, lag_workdays, workday_table, calendar, convention
    )

    if constraint_type == "ES":
        return constrained_date == succ_es
    else:  # "EF"
        return constrained_date == succ_ef


def find_driving_relationship(
    predecessors: list[tuple[Activity, Relationship]],
    succ_es: date,
    succ_ef: date,
    workday_table: dict[date, int],
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
) -> list[tuple[Activity, Relationship]]:
    """
    CALC-004 — Find all driving relationships for a successor among its predecessors.

    Evaluates each (predecessor Activity, Relationship) pair and returns those
    whose constrained date matches the successor's early date. Multiple pairs
    may be returned when co-driving relationships produce the same latest constraint.

    Each predecessor Activity must have early_start and early_finish set.
    Each Relationship must use rel_type in {"FS", "SS", "FF", "SF"}.

    Source: CPW-P6 Manual [relationship logic section]; ADR-002
    Assumption: Retained Logic. succ_es and succ_ef are taken from a completed
                CPM forward pass; this function does not recompute them.
    Limitation: Phase 2 single-calendar, integer-lag implementation only.

    Args:
        predecessors:  List of (Activity, Relationship) pairs. Each Activity is
                       a predecessor with early_start and early_finish set.
                       Each Relationship connects that predecessor to the successor.
        succ_es:       Successor Early Start (from CPM forward pass).
        succ_ef:       Successor Early Finish (from CPM forward pass).
        workday_table: Prebuilt workday table.
        calendar:      Calendar for non-workday adjustment.

    Returns:
        List of (Activity, Relationship) pairs that are driving. Empty list if
        none match (which may indicate the successor is start-constrained by
        something other than a predecessor relationship, e.g., a date constraint).

    Raises:
        ValueError: If any Activity is missing early_start or early_finish,
                    or if workday arithmetic fails.
    """
    driving: list[tuple[Activity, Relationship]] = []

    for pred, rel in predecessors:
        if pred.early_start is None:
            raise ValueError(
                f"find_driving_relationship (CALC-004): predecessor {pred.act_id!r} "
                "has early_start=None. A completed CPM forward pass is required."
            )
        if pred.early_finish is None:
            raise ValueError(
                f"find_driving_relationship (CALC-004): predecessor {pred.act_id!r} "
                "has early_finish=None. A completed CPM forward pass is required."
            )

        if is_driving_relationship(
            rel.rel_type,
            pred.early_start,
            pred.early_finish,
            succ_es,
            succ_ef,
            rel.lag,
            workday_table,
            calendar,
            convention,
        ):
            driving.append((pred, rel))

    return driving
