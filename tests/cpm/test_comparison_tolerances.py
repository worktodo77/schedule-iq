"""
V1-G: Tests for comparison_validation/tolerances.py.

Covers:
  - TolerancePolicy field type predicates
  - within_tolerance() for date, float, lag, duration, exact fields
  - Named policies (STRICT, CALENDAR_AWARE, ADVISORY) values
  - None-value handling (both sides)
  - to_dict() serialization
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date

from scheduleiq.cpm.compare.tolerances import (  # noqa: E402
    NAMED_TOLERANCE_POLICIES,
    TOLERANCE_ADVISORY,
    TOLERANCE_CALENDAR_AWARE,
    TOLERANCE_STRICT,
    TolerancePolicy,
    ToleranceType,
    classify_field_tolerance_type,
    within_tolerance,
)


# ---------------------------------------------------------------------------
# Named policy values
# ---------------------------------------------------------------------------

class TestNamedPolicies:

    def test_strict_all_zero(self):
        p = TOLERANCE_STRICT
        assert p.date_tolerance_days == 0
        assert p.float_tolerance_wdays == 0
        assert p.lag_tolerance == 0.0
        assert p.duration_tolerance == 0

    def test_calendar_aware_values(self):
        p = TOLERANCE_CALENDAR_AWARE
        assert p.date_tolerance_days == 1
        assert p.float_tolerance_wdays == 1
        assert p.lag_tolerance == 0.5

    def test_advisory_values(self):
        p = TOLERANCE_ADVISORY
        assert p.date_tolerance_days == 2
        assert p.float_tolerance_wdays == 2
        assert p.lag_tolerance == 1.0

    def test_named_dict_has_all_three(self):
        assert "STRICT" in NAMED_TOLERANCE_POLICIES
        assert "CALENDAR_AWARE" in NAMED_TOLERANCE_POLICIES
        assert "ADVISORY" in NAMED_TOLERANCE_POLICIES

    def test_policies_are_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            TOLERANCE_STRICT.date_tolerance_days = 99  # type: ignore

    def test_to_dict_keys(self):
        d = TOLERANCE_STRICT.to_dict()
        for key in ("name", "date_tolerance_days", "float_tolerance_wdays",
                    "lag_tolerance", "duration_tolerance", "description"):
            assert key in d


# ---------------------------------------------------------------------------
# TolerancePolicy predicates
# ---------------------------------------------------------------------------

class TestTolerancePolicyPredicates:

    def test_date_field_type_strict_is_exact(self):
        assert TOLERANCE_STRICT.date_field_type() == ToleranceType.EXACT

    def test_date_field_type_calendar_aware_is_calendar_day(self):
        assert TOLERANCE_CALENDAR_AWARE.date_field_type() == ToleranceType.CALENDAR_DAY

    def test_float_field_type_strict_is_exact(self):
        assert TOLERANCE_STRICT.float_field_type() == ToleranceType.EXACT

    def test_float_field_type_advisory_is_float_workday(self):
        assert TOLERANCE_ADVISORY.float_field_type() == ToleranceType.FLOAT_WORKDAY

    def test_lag_field_type_strict_is_exact(self):
        assert TOLERANCE_STRICT.lag_field_type() == ToleranceType.EXACT

    def test_lag_field_type_calendar_aware_is_lag(self):
        assert TOLERANCE_CALENDAR_AWARE.lag_field_type() == ToleranceType.LAG


# ---------------------------------------------------------------------------
# within_tolerance — date fields
# ---------------------------------------------------------------------------

class TestWithinToleranceDates:

    def test_exact_date_match_strict(self):
        d = date(2024, 3, 15)
        ok, delta = within_tolerance("early_finish", d, d, TOLERANCE_STRICT)
        assert ok is True
        assert delta == 0.0

    def test_one_day_over_strict_fails(self):
        ok, delta = within_tolerance(
            "early_finish", date(2024, 3, 16), date(2024, 3, 15), TOLERANCE_STRICT
        )
        assert ok is False
        assert delta == 1.0

    def test_one_day_over_calendar_aware_passes(self):
        ok, delta = within_tolerance(
            "early_finish", date(2024, 3, 16), date(2024, 3, 15), TOLERANCE_CALENDAR_AWARE
        )
        assert ok is True
        assert delta == 1.0

    def test_two_day_over_calendar_aware_fails(self):
        ok, delta = within_tolerance(
            "late_finish", date(2024, 3, 17), date(2024, 3, 15), TOLERANCE_CALENDAR_AWARE
        )
        assert ok is False
        assert delta == 2.0

    def test_two_day_over_advisory_passes(self):
        ok, delta = within_tolerance(
            "early_start", date(2024, 3, 17), date(2024, 3, 15), TOLERANCE_ADVISORY
        )
        assert ok is True

    def test_negative_delta_date(self):
        ok, delta = within_tolerance(
            "late_start", date(2024, 3, 14), date(2024, 3, 15), TOLERANCE_CALENDAR_AWARE
        )
        assert ok is True
        assert delta == -1.0

    def test_all_date_fields_respected(self):
        for field in ("early_start", "early_finish", "late_start", "late_finish"):
            ok, _ = within_tolerance(
                field, date(2024, 3, 16), date(2024, 3, 15), TOLERANCE_STRICT
            )
            assert ok is False, f"Field {field} should fail strict tolerance"


# ---------------------------------------------------------------------------
# within_tolerance — float fields
# ---------------------------------------------------------------------------

class TestWithinToleranceFloat:

    def test_exact_float_match(self):
        ok, delta = within_tolerance("total_float", 5, 5, TOLERANCE_STRICT)
        assert ok is True
        assert delta == 0.0

    def test_float_diff_one_strict_fails(self):
        ok, delta = within_tolerance("total_float", 5, 4, TOLERANCE_STRICT)
        assert ok is False
        assert delta == 1.0

    def test_float_diff_one_calendar_aware_passes(self):
        ok, delta = within_tolerance("total_float", 5, 4, TOLERANCE_CALENDAR_AWARE)
        assert ok is True

    def test_free_float_field(self):
        ok, delta = within_tolerance("free_float", 3, 5, TOLERANCE_CALENDAR_AWARE)
        assert ok is False
        assert delta == -2.0


# ---------------------------------------------------------------------------
# within_tolerance — is_critical (exact)
# ---------------------------------------------------------------------------

class TestWithinToleranceExact:

    def test_is_critical_exact_match(self):
        ok, delta = within_tolerance("is_critical", True, True, TOLERANCE_ADVISORY)
        assert ok is True
        assert delta is None

    def test_is_critical_mismatch(self):
        ok, delta = within_tolerance("is_critical", True, False, TOLERANCE_ADVISORY)
        assert ok is False
        assert delta is None


# ---------------------------------------------------------------------------
# within_tolerance — duration
# ---------------------------------------------------------------------------

class TestWithinToleranceDuration:

    def test_duration_exact_strict(self):
        ok, delta = within_tolerance("original_duration", 10, 10, TOLERANCE_STRICT)
        assert ok is True

    def test_duration_diff_strict_fails(self):
        ok, delta = within_tolerance("original_duration", 11, 10, TOLERANCE_STRICT)
        assert ok is False
        assert delta == 1.0


# ---------------------------------------------------------------------------
# within_tolerance — None handling
# ---------------------------------------------------------------------------

class TestWithinToleranceNone:

    def test_mip39_none_returns_true(self):
        ok, delta = within_tolerance("total_float", None, 5, TOLERANCE_STRICT)
        assert ok is True
        assert delta is None

    def test_ref_none_returns_true(self):
        ok, delta = within_tolerance("early_finish", date(2024, 3, 15), None, TOLERANCE_STRICT)
        assert ok is True
        assert delta is None

    def test_both_none_returns_true(self):
        ok, delta = within_tolerance("total_float", None, None, TOLERANCE_STRICT)
        assert ok is True


# ---------------------------------------------------------------------------
# classify_field_tolerance_type
# ---------------------------------------------------------------------------

class TestClassifyFieldToleranceType:

    def test_date_field_strict(self):
        assert classify_field_tolerance_type("early_finish", TOLERANCE_STRICT) == ToleranceType.EXACT

    def test_date_field_calendar_aware(self):
        assert classify_field_tolerance_type("early_finish", TOLERANCE_CALENDAR_AWARE) == ToleranceType.CALENDAR_DAY

    def test_float_field_strict(self):
        assert classify_field_tolerance_type("total_float", TOLERANCE_STRICT) == ToleranceType.EXACT

    def test_float_field_advisory(self):
        assert classify_field_tolerance_type("total_float", TOLERANCE_ADVISORY) == ToleranceType.FLOAT_WORKDAY

    def test_unknown_field_is_exact(self):
        assert classify_field_tolerance_type("some_unknown_field", TOLERANCE_ADVISORY) == ToleranceType.EXACT
