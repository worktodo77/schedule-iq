"""
Ported from the LI MIP 3.9 tool (mip39.lag_analysis) per ADR-0007 — port-and-validate.
CALC-002: Lag Workday Conversion
CALC-003: Lag Variance

Implements workday-based lag arithmetic and lag variance calculation
as used in MIP 3.9 schedule analysis.

Source: CPW-P6 Manual pp. 41-42 (Lag Analysis subsection).

Phase 2 simplifications (ADR-002):
  - Integer workday lags only (fractional lags require hour-level precision,
    deferred to Phase 3).
  - Single calendar; no exception dates.
  - Non-workday anchor dates are adjusted using the CALC-001 rule before
    lag arithmetic is applied.

Retained Logic assumption (ADR-002):
  All lag calculations assume Retained Logic scheduling. Progress Override
  is excluded from this implementation.
"""

from __future__ import annotations

from datetime import date

from .models import Calendar
from .calendar_ops import _adjust_nonworkday, workday_to_date


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_integer_lag(lag: float, context: str) -> int:
    """
    Validate that lag is a whole number and return it as int.

    Phase 2 uses integer workday lags only. Fractional lags require
    hour-level precision (deferred to Phase 3).

    Raises:
        ValueError: If lag has a non-zero fractional part.
    """
    if lag != int(lag):
        raise ValueError(
            f"{context}: fractional lag {lag} is not supported in Phase 2 "
            "(integer workday lags only; hour-level precision deferred to Phase 3)."
        )
    return int(lag)


# ---------------------------------------------------------------------------
# CALC-002: Lag workday conversion
# ---------------------------------------------------------------------------

def apply_lag(
    anchor: date,
    lag_workdays: float,
    workday_table: dict[date, int],
    calendar: Calendar,
    anchor_is_start: bool = True,
) -> date:
    """
    CALC-002 — Apply a workday lag to an anchor date.

    Computes the date that is lag_workdays workdays from anchor:
      result_workday_number = workday_number(anchor) + lag_workdays

    Non-workday anchors are adjusted before lag application using the
    CALC-001 non-workday adjustment rule (CPW Manual pp. 41-42):
      anchor_is_start=True  → advance to next higher workday
      anchor_is_start=False → retreat to next lower workday

    Typical anchor types by relationship:
      FS / FF → anchor is predecessor Early Finish (anchor_is_start=False)
      SS / SF → anchor is predecessor Early Start  (anchor_is_start=True)

    Source: CPW-P6 Manual pp. 41-42 (Lag Analysis subsection)
    Assumption: Single calendar; no exception dates (ADR-002).
    Assumption: FS lag=0 → constrained_es = pred_ef (same workday, P6 convention).
    Limitation: Integer lags only; fractional lags deferred to Phase 3.

    Args:
        anchor:          The anchor date (predecessor EF for FS/FF, ES for SS/SF).
        lag_workdays:    Lag in workdays. May be negative (lead). Must be whole number.
        workday_table:   Prebuilt workday table covering anchor and result range.
        calendar:        Calendar for non-workday adjustment.
        anchor_is_start: True if anchor is a start-type date; False if finish-type.

    Returns:
        The date that is lag_workdays workdays from the adjusted anchor.

    Raises:
        ValueError: If lag_workdays is fractional, or if the anchor or result
                    date falls outside the workday table range.
    """
    lag_int = _require_integer_lag(lag_workdays, "apply_lag (CALC-002)")

    if not calendar.is_workday(anchor):
        anchor = _adjust_nonworkday(anchor, calendar, is_start=anchor_is_start)

    anchor_num = workday_table.get(anchor)
    if anchor_num is None:
        raise ValueError(
            f"apply_lag (CALC-002): anchor date {anchor} is not in the workday "
            "table after non-workday adjustment. Extend the table range to cover "
            "the full project date span."
        )

    target_num = anchor_num + lag_int
    return workday_to_date(target_num, workday_table)


def compute_lag_between(
    from_date: date,
    to_date: date,
    workday_table: dict[date, int],
    calendar: Calendar,
    from_is_start: bool = False,
    to_is_start: bool = True,
) -> int:
    """
    CALC-002 — Compute the workday lag between two dates.

    Returns: workday_number(to_date) - workday_number(from_date).

    The result is signed:
      Positive — to_date is after from_date (normal sequence).
      Negative — to_date is before from_date (out-of-sequence / lead).
      Zero     — both dates map to the same workday.

    Typical use: compute the as-built lag for a FS relationship:
      as_built_lag = compute_lag_between(pred_af, succ_as,
                                         from_is_start=False, to_is_start=True)

    Non-workday dates are adjusted using the CALC-001 rule before lookup:
      from_is_start=False → retreat from_date to previous workday (finish-type).
      to_is_start=True    → advance to_date to next workday (start-type).

    Source: CPW-P6 Manual pp. 41-42 (Lag Analysis subsection)
    Assumption: Single calendar; no exception dates (ADR-002).
    Limitation: Returns integer workday count only.

    Args:
        from_date:     Start of measurement (typically predecessor Actual Finish).
        to_date:       End of measurement (typically successor Actual Start).
        workday_table: Prebuilt workday table.
        calendar:      Calendar for non-workday adjustment.
        from_is_start: Adjustment direction for from_date (default False = finish-type).
        to_is_start:   Adjustment direction for to_date (default True = start-type).

    Returns:
        Signed integer workday count (to_date workday − from_date workday).

    Raises:
        ValueError: If either date falls outside the workday table range after
                    non-workday adjustment.
    """
    if not calendar.is_workday(from_date):
        from_date = _adjust_nonworkday(from_date, calendar, is_start=from_is_start)
    if not calendar.is_workday(to_date):
        to_date = _adjust_nonworkday(to_date, calendar, is_start=to_is_start)

    from_num = workday_table.get(from_date)
    if from_num is None:
        raise ValueError(
            f"compute_lag_between (CALC-002): from_date {from_date} is not in "
            "the workday table after adjustment. Extend the table range."
        )

    to_num = workday_table.get(to_date)
    if to_num is None:
        raise ValueError(
            f"compute_lag_between (CALC-002): to_date {to_date} is not in "
            "the workday table after adjustment. Extend the table range."
        )

    return to_num - from_num


# ---------------------------------------------------------------------------
# CALC-003: Lag variance
# ---------------------------------------------------------------------------

def lag_variance(as_planned_lag: float, as_built_lag: float) -> float:
    """
    CALC-003 — Compute lag variance between planned and as-built lags.

    lag_variance = as_built_lag − as_planned_lag

    Interpretation:
      Positive → lag grew (successor started or finished later than planned;
                 potential contributor to delay).
      Negative → lag shrank (lead recovered or schedule compressed).
      Zero     → lag unchanged.

    Source: CPW-P6 Manual pp. 41-42 (Lag Analysis subsection)
    Assumption: Both lags expressed in the same units (workdays).
    Limitation: Does not interpret causation; variance magnitude only.

    Args:
        as_planned_lag: The planned lag from the baseline schedule (workdays).
        as_built_lag:   The actual lag measured from as-built dates (workdays).

    Returns:
        Lag variance in workdays (float). Positive = delay, negative = compression.
    """
    return as_built_lag - as_planned_lag
