"""
V1-G: Comparison tolerance governance.

Tolerance policies govern when a numerical difference between mip39 output
and a CPW reference output is considered "within tolerance" vs. a divergence.

All tolerance policies are:
  - named and documented (no hidden tolerance rules);
  - frozen once constructed;
  - reproducible across runs.

Three named tolerance policies cover the common validation scenarios:

  STRICT:         All fields must match exactly. No tolerance.
  CALENDAR_AWARE: Date fields may differ by up to 1 calendar day. Float fields
                  may differ by up to 1 workday. Covers common weekend-boundary
                  artifacts in workday arithmetic.
  ADVISORY:       Wider tolerances for preliminary review. Date fields: 2 days.
                  Float: 2 workdays. Lag: 0.5 workdays.

Note on calendar-day vs workday tolerance: this framework uses calendar days
for date field tolerance because the comparator does not receive the workday
table. A 1-calendar-day tolerance on a weekday boundary corresponds to
1 workday; on a Friday→Monday boundary, 1 workday = 3 calendar days. Analysts
working with Monday/Friday start/finish activities should use CALENDAR_AWARE
or ADVISORY tolerance accordingly. This limitation is documented as LIM-043.

Source: ADR-016; ADR-005 (no hidden defaults).

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.tolerances) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Tolerance type enumeration
# ---------------------------------------------------------------------------

class ToleranceType(str, Enum):
    """
    Classification of tolerance types applied per field.

    Members:
        EXACT:            Values must be identical.
        CALENDAR_DAY:     Date values may differ by up to max_calendar_days.
        WORKDAY:          Integer workday values may differ by up to max_workdays.
        FLOAT_WORKDAY:    Float (TF/FF) values may differ by up to max_workdays.
        LAG:              Lag float values may differ by up to max_lag.
    """
    EXACT = "EXACT"
    CALENDAR_DAY = "CALENDAR_DAY"
    WORKDAY = "WORKDAY"
    FLOAT_WORKDAY = "FLOAT_WORKDAY"
    LAG = "LAG"


# ---------------------------------------------------------------------------
# Tolerance policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TolerancePolicy:
    """
    Named tolerance configuration for comparison runs.

    Fields:
        name:                  Unique policy name for provenance.
        date_tolerance_days:   Max calendar-day difference for date fields
                               (early_start, early_finish, late_start, late_finish).
                               0 = exact match required.
        float_tolerance_wdays: Max workday difference for float fields
                               (total_float, free_float). 0 = exact match.
        lag_tolerance:         Max lag difference in workdays (float). 0.0 = exact.
        duration_tolerance:    Max workday difference for original_duration. 0 = exact.
        description:           Human-readable description of when to use this policy.
    """

    name: str
    date_tolerance_days: int = 0
    float_tolerance_wdays: int = 0
    lag_tolerance: float = 0.0
    duration_tolerance: int = 0
    description: str = ""

    def date_field_type(self) -> ToleranceType:
        return ToleranceType.EXACT if self.date_tolerance_days == 0 else ToleranceType.CALENDAR_DAY

    def float_field_type(self) -> ToleranceType:
        return ToleranceType.EXACT if self.float_tolerance_wdays == 0 else ToleranceType.FLOAT_WORKDAY

    def lag_field_type(self) -> ToleranceType:
        return ToleranceType.EXACT if self.lag_tolerance == 0.0 else ToleranceType.LAG

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "date_tolerance_days": self.date_tolerance_days,
            "float_tolerance_wdays": self.float_tolerance_wdays,
            "lag_tolerance": self.lag_tolerance,
            "duration_tolerance": self.duration_tolerance,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Named tolerance policies
# ---------------------------------------------------------------------------

TOLERANCE_STRICT = TolerancePolicy(
    name="STRICT",
    date_tolerance_days=0,
    float_tolerance_wdays=0,
    lag_tolerance=0.0,
    duration_tolerance=0,
    description=(
        "All fields must match exactly. No tolerance for any field. "
        "Appropriate for synthetic benchmark validation where exact agreement "
        "is expected and any difference indicates an engine error."
    ),
)

TOLERANCE_CALENDAR_AWARE = TolerancePolicy(
    name="CALENDAR_AWARE",
    date_tolerance_days=1,
    float_tolerance_wdays=1,
    lag_tolerance=0.5,
    duration_tolerance=0,
    description=(
        "Permits 1-calendar-day difference in date fields and 1-workday "
        "difference in float fields. Covers common weekend-boundary artifacts "
        "in workday arithmetic where a Friday EF and Monday EF can differ by "
        "up to 3 calendar days but represent the same CPM schedule day. "
        "Appropriate for single-calendar schedule comparisons against CPW output."
    ),
)

TOLERANCE_ADVISORY = TolerancePolicy(
    name="ADVISORY",
    date_tolerance_days=2,
    float_tolerance_wdays=2,
    lag_tolerance=1.0,
    duration_tolerance=0,
    description=(
        "Wider tolerances for preliminary review. Permits 2-calendar-day "
        "difference in dates, 2-workday difference in floats, and 1.0-workday "
        "lag tolerance. Appropriate for initial gap analysis where rough "
        "equivalence is sufficient. NOT appropriate for final forensic reliance."
    ),
)

NAMED_TOLERANCE_POLICIES: dict[str, TolerancePolicy] = {
    "STRICT": TOLERANCE_STRICT,
    "CALENDAR_AWARE": TOLERANCE_CALENDAR_AWARE,
    "ADVISORY": TOLERANCE_ADVISORY,
}


def get_tolerance_policy(name: str) -> TolerancePolicy:
    """Return the named tolerance policy. Raises KeyError for unknown names."""
    return NAMED_TOLERANCE_POLICIES[name]


# ---------------------------------------------------------------------------
# Field-level tolerance application
# ---------------------------------------------------------------------------

_DATE_FIELDS = {"early_start", "early_finish", "late_start", "late_finish"}
_FLOAT_FIELDS = {"total_float", "free_float"}
_LAG_FIELDS = {"lag", "actual_lag"}
_DURATION_FIELDS = {"original_duration"}
_EXACT_FIELDS = {"is_critical", "act_id", "rel_type"}


def within_tolerance(
    field: str,
    mip39_value: Any,
    reference_value: Any,
    policy: TolerancePolicy,
) -> tuple[bool, Optional[float]]:
    """
    Test whether a field value difference is within the policy tolerance.

    Returns:
        (within_tolerance: bool, delta: Optional[float])
        delta is the numeric difference (mip39 - reference) or None for
        non-numeric fields. For date fields, delta is in calendar days.
    """
    if mip39_value is None or reference_value is None:
        return True, None

    if field in _DATE_FIELDS:
        if isinstance(mip39_value, date) and isinstance(reference_value, date):
            delta_days = (mip39_value - reference_value).days
            return abs(delta_days) <= policy.date_tolerance_days, float(delta_days)
        return mip39_value == reference_value, None

    if field in _FLOAT_FIELDS:
        if isinstance(mip39_value, (int, float)) and isinstance(reference_value, (int, float)):
            delta = float(mip39_value) - float(reference_value)
            return abs(delta) <= policy.float_tolerance_wdays, delta
        return mip39_value == reference_value, None

    if field in _LAG_FIELDS:
        if isinstance(mip39_value, (int, float)) and isinstance(reference_value, (int, float)):
            delta = float(mip39_value) - float(reference_value)
            return abs(delta) <= policy.lag_tolerance, delta
        return mip39_value == reference_value, None

    if field in _DURATION_FIELDS:
        if isinstance(mip39_value, (int, float)) and isinstance(reference_value, (int, float)):
            delta = float(mip39_value) - float(reference_value)
            return abs(delta) <= policy.duration_tolerance, delta
        return mip39_value == reference_value, None

    # Exact match for is_critical, strings, and unknown fields
    return mip39_value == reference_value, None


def classify_field_tolerance_type(field: str, policy: TolerancePolicy) -> ToleranceType:
    """Return the ToleranceType that applies to this field under the given policy."""
    if field in _DATE_FIELDS:
        return policy.date_field_type()
    if field in _FLOAT_FIELDS:
        return policy.float_field_type()
    if field in _LAG_FIELDS:
        return policy.lag_field_type()
    return ToleranceType.EXACT
