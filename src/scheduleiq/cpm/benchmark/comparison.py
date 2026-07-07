"""
INFRA-012: Phase 7 Machine-Readable Comparison Artifacts.

Provides structured, serializable diff types for comparing benchmark
expected outputs against actual engine outputs. Comparison artifacts
are the primary evidence record for forensic review.

Types:
  FloatDiff          — total-float or free-float divergence per activity
  DateDiff           — date divergence (ES/EF/LS/LF) per activity
  PathDiff           — critical-path composition divergence
  WarningDiff        — warning-code presence divergence
  NormalizationDiff  — normalization-category-count divergence
  ConventionDiff     — side-by-side INCLUSIVE_DAY vs P6_COMPATIBILITY comparison

Functions:
  compare_float_results(expected, actual) -> list[FloatDiff]
  compare_date_results(expected, actual)  -> list[DateDiff]
  compare_paths(expected_ids, actual_ids) -> PathDiff
  compare_warning_codes(expected, actual) -> WarningDiff

Governance (ADR-009):
  - All diffs include the expected and actual values explicitly.
  - No silent suppression of differences.
  - All diff objects are serializable via to_dict().

Source: ADR-009 — Benchmark Governance.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.comparison) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Float diff
# ---------------------------------------------------------------------------

@dataclass
class FloatDiff:
    """
    Divergence in total-float or free-float for a single activity.

    Fields:
        activity_id: Activity identifier.
        field:       "total_float" or "free_float".
        expected:    Expected value in workdays.
        actual:      Actual value produced by the engine.
        delta:       actual - expected (signed; positive = actual is larger).
    """
    activity_id: str
    field: str
    expected: int
    actual: int
    delta: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "delta": self.delta,
        }


# ---------------------------------------------------------------------------
# Date diff
# ---------------------------------------------------------------------------

@dataclass
class DateDiff:
    """
    Divergence in a date field (ES, EF, LS, or LF) for a single activity.

    Fields:
        activity_id: Activity identifier.
        field:       "early_start", "early_finish", "late_start", or "late_finish".
        expected:    Expected ISO 8601 date string.
        actual:      Actual ISO 8601 date string produced by the engine.
    """
    activity_id: str
    field: str
    expected: str
    actual: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
        }


# ---------------------------------------------------------------------------
# Path diff
# ---------------------------------------------------------------------------

@dataclass
class PathDiff:
    """
    Divergence in critical-path composition.

    Fields:
        expected_ids:        Expected activity IDs on the critical path.
        actual_ids:          Actual activity IDs reported by the engine.
        missing_from_actual: Activities expected to be critical but are absent.
        extra_in_actual:     Activities reported as critical but not expected.
        order_differs:       True when the ID sets match but ordering differs.
    """
    expected_ids: list[str]
    actual_ids: list[str]
    missing_from_actual: list[str]
    extra_in_actual: list[str]
    order_differs: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_ids": list(self.expected_ids),
            "actual_ids": list(self.actual_ids),
            "missing_from_actual": list(self.missing_from_actual),
            "extra_in_actual": list(self.extra_in_actual),
            "order_differs": self.order_differs,
        }


# ---------------------------------------------------------------------------
# Warning diff
# ---------------------------------------------------------------------------

@dataclass
class WarningDiff:
    """
    Divergence in expected vs actual warning codes.

    Fields:
        expected_codes: Warning codes that the benchmark expects to be present.
        actual_codes:   Warning codes actually emitted by the engine.
        missing:        Codes expected but absent from actual output.
        extra:          Codes present in actual but not expected.
    """
    expected_codes: list[str]
    actual_codes: list[str]
    missing: list[str]
    extra: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_codes": list(self.expected_codes),
            "actual_codes": list(self.actual_codes),
            "missing": list(self.missing),
            "extra": list(self.extra),
        }


# ---------------------------------------------------------------------------
# Normalization diff
# ---------------------------------------------------------------------------

@dataclass
class NormalizationDiff:
    """
    Divergence in normalization-category counts between expected and actual.

    Fields:
        expected_categories: Expected category → count mapping.
        actual_categories:   Actual category → count mapping from engine output.
        changed_categories:  Categories whose counts differ.
    """
    expected_categories: dict[str, int]
    actual_categories: dict[str, int]
    changed_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_categories": dict(self.expected_categories),
            "actual_categories": dict(self.actual_categories),
            "changed_categories": list(self.changed_categories),
        }


# ---------------------------------------------------------------------------
# Convention diff
# ---------------------------------------------------------------------------

@dataclass
class ConventionDiff:
    """
    Side-by-side comparison of INCLUSIVE_DAY vs P6_COMPATIBILITY outputs.

    Fields:
        benchmark_id:    Benchmark identifier.
        convention_a:    First convention name.
        convention_b:    Second convention name.
        date_diffs:      Date fields that differ between the two conventions.
        float_diffs:     Float fields that differ between the two conventions.
        path_changed:    True when critical-path composition differs.
        duration_diffs:  Project-duration difference (if any).
    """
    benchmark_id: str
    convention_a: str
    convention_b: str
    date_diffs: list[DateDiff] = field(default_factory=list)
    float_diffs: list[FloatDiff] = field(default_factory=list)
    path_changed: bool = False
    duration_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "convention_a": self.convention_a,
            "convention_b": self.convention_b,
            "date_diffs": [d.to_dict() for d in self.date_diffs],
            "float_diffs": [d.to_dict() for d in self.float_diffs],
            "path_changed": self.path_changed,
            "duration_changed": self.duration_changed,
        }


# ---------------------------------------------------------------------------
# Comparison functions
# ---------------------------------------------------------------------------

def compare_float_results(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[FloatDiff]:
    """
    Compare expected vs actual float values across all activities.

    Args:
        expected: Dict of activity_id → ExpectedActivityResult.to_dict().
        actual:   Dict of activity_id → ScheduledActivity.to_dict().

    Returns:
        List of FloatDiff for every activity where total_float or free_float
        differs. Empty list when all float values match.
    """
    diffs: list[FloatDiff] = []
    for act_id in sorted(expected):
        exp_act = expected[act_id]
        act_act = actual.get(act_id)
        if act_act is None:
            continue
        for float_field in ("total_float", "free_float"):
            exp_val = exp_act[float_field]
            act_val = act_act[float_field]
            if exp_val != act_val:
                diffs.append(FloatDiff(
                    activity_id=act_id,
                    field=float_field,
                    expected=exp_val,
                    actual=act_val,
                    delta=act_val - exp_val,
                ))
    return diffs


def compare_date_results(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[DateDiff]:
    """
    Compare expected vs actual date fields across all activities.

    Args:
        expected: Dict of activity_id → ExpectedActivityResult.to_dict().
        actual:   Dict of activity_id → ScheduledActivity.to_dict().

    Returns:
        List of DateDiff for every activity/field pair that differs.
    """
    diffs: list[DateDiff] = []
    date_fields = ("early_start", "early_finish", "late_start", "late_finish")
    for act_id in sorted(expected):
        exp_act = expected[act_id]
        act_act = actual.get(act_id)
        if act_act is None:
            continue
        for date_field in date_fields:
            exp_val = exp_act[date_field]
            act_val = act_act[date_field]
            if exp_val != act_val:
                diffs.append(DateDiff(
                    activity_id=act_id,
                    field=date_field,
                    expected=exp_val,
                    actual=act_val,
                ))
    return diffs


def compare_paths(
    expected_ids: list[str],
    actual_ids: list[str],
) -> PathDiff:
    """
    Compare expected vs actual critical-path activity ID lists.

    Args:
        expected_ids: Activity IDs expected on the critical path.
        actual_ids:   Activity IDs actually reported by the engine.

    Returns:
        PathDiff with missing/extra sets and order_differs flag.
    """
    expected_set = set(expected_ids)
    actual_set = set(actual_ids)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    order_differs = (
        not missing and not extra and expected_ids != actual_ids
    )
    return PathDiff(
        expected_ids=list(expected_ids),
        actual_ids=list(actual_ids),
        missing_from_actual=missing,
        extra_in_actual=extra,
        order_differs=order_differs,
    )


def compare_warning_codes(
    expected_codes: list[str],
    actual_codes: list[str],
) -> WarningDiff:
    """
    Compare expected vs actual warning codes (presence check only).

    Args:
        expected_codes: Warning codes the benchmark expects to be present.
        actual_codes:   Warning codes actually emitted by the engine run.

    Returns:
        WarningDiff with missing/extra code lists.
    """
    expected_set = set(expected_codes)
    actual_set = set(actual_codes)
    return WarningDiff(
        expected_codes=sorted(expected_codes),
        actual_codes=sorted(actual_codes),
        missing=sorted(expected_set - actual_set),
        extra=sorted(actual_set - expected_set),
    )
