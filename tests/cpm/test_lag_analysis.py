"""
Tests for CALC-002 (Lag Workday Conversion) and CALC-003 (Lag Variance).
Source: src/mip39/lag_analysis.py

All fixtures are synthetic. No proprietary data.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import json
import pytest
from datetime import date
from pathlib import Path

from scheduleiq.cpm.models import Calendar  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.lag_analysis import apply_lag, compute_lag_between, lag_variance  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared test state
# ---------------------------------------------------------------------------

_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2024, 1, 1), date(2024, 1, 31))

# January 2024 workday reference (Mon–Fri calendar):
#   Jan 1 (Mon) = wd1,  Jan 2 = wd2,  Jan 3 = wd3,  Jan 4 = wd4,  Jan 5 (Fri) = wd5
#   Jan 8 (Mon) = wd6,  Jan 9 = wd7,  Jan 10 = wd8, Jan 11 = wd9, Jan 12 (Fri) = wd10
#   Jan 15 (Mon) = wd11, Jan 16 = wd12, Jan 17 = wd13, Jan 18 = wd14, Jan 19 (Fri) = wd15


# ---------------------------------------------------------------------------
# CALC-002: apply_lag — workday dates
# ---------------------------------------------------------------------------

class TestApplyLagWorkdayAnchor:
    def test_lag_zero_returns_same_date(self):
        # wd1 + 0 = wd1 = Jan 1
        assert apply_lag(date(2024, 1, 1), 0, _TABLE, _CAL) == date(2024, 1, 1)

    def test_lag_positive_within_week(self):
        # wd1 + 2 = wd3 = Jan 3
        assert apply_lag(date(2024, 1, 1), 2, _TABLE, _CAL) == date(2024, 1, 3)

    def test_lag_positive_crosses_weekend(self):
        # wd5 + 1 = wd6 = Jan 8 (Friday → Monday)
        assert apply_lag(date(2024, 1, 5), 1, _TABLE, _CAL) == date(2024, 1, 8)

    def test_lag_positive_crosses_two_weekends(self):
        # wd5 + 6 = wd11 = Jan 15 (Friday + 6 workdays = next-next Monday)
        assert apply_lag(date(2024, 1, 5), 6, _TABLE, _CAL) == date(2024, 1, 15)

    def test_lag_negative_lead_within_week(self):
        # wd8 - 2 = wd6 = Jan 8
        assert apply_lag(date(2024, 1, 10), -2, _TABLE, _CAL) == date(2024, 1, 8)

    def test_lag_negative_crosses_weekend_backward(self):
        # wd6 - 1 = wd5 = Jan 5 (Monday → Friday)
        assert apply_lag(date(2024, 1, 8), -1, _TABLE, _CAL) == date(2024, 1, 5)

    def test_lag_full_workweek(self):
        # wd6 + 5 = wd11 = Jan 15 (exactly one 5-day week)
        assert apply_lag(date(2024, 1, 8), 5, _TABLE, _CAL) == date(2024, 1, 15)


# ---------------------------------------------------------------------------
# CALC-002: apply_lag — non-workday anchors
# ---------------------------------------------------------------------------

class TestApplyLagNonWorkdayAnchor:
    def test_saturday_anchor_start_type_advances_before_lag(self):
        # Jan 6 (Sat) → advance to Jan 8 (Mon, wd6), then +1 → wd7 = Jan 9
        result = apply_lag(date(2024, 1, 6), 1, _TABLE, _CAL, anchor_is_start=True)
        assert result == date(2024, 1, 9)

    def test_saturday_anchor_finish_type_retreats_before_lag(self):
        # Jan 6 (Sat) → retreat to Jan 5 (Fri, wd5), then +1 → wd6 = Jan 8
        result = apply_lag(date(2024, 1, 6), 1, _TABLE, _CAL, anchor_is_start=False)
        assert result == date(2024, 1, 8)

    def test_sunday_anchor_start_type(self):
        # Jan 7 (Sun) → advance to Jan 8 (Mon, wd6), then +2 → wd8 = Jan 10
        result = apply_lag(date(2024, 1, 7), 2, _TABLE, _CAL, anchor_is_start=True)
        assert result == date(2024, 1, 10)

    def test_sunday_anchor_finish_type(self):
        # Jan 7 (Sun) → retreat to Jan 5 (Fri, wd5), then +2 → wd7 = Jan 9
        result = apply_lag(date(2024, 1, 7), 2, _TABLE, _CAL, anchor_is_start=False)
        assert result == date(2024, 1, 9)

    def test_saturday_finish_type_lag_zero(self):
        # Jan 6 (Sat) → retreat to Jan 5 (Fri, wd5), then +0 → wd5 = Jan 5
        result = apply_lag(date(2024, 1, 6), 0, _TABLE, _CAL, anchor_is_start=False)
        assert result == date(2024, 1, 5)

    def test_saturday_start_type_and_finish_type_differ(self):
        # Saturday with lag=1 produces different results based on anchor direction
        start_result = apply_lag(date(2024, 1, 6), 1, _TABLE, _CAL, anchor_is_start=True)
        finish_result = apply_lag(date(2024, 1, 6), 1, _TABLE, _CAL, anchor_is_start=False)
        assert start_result != finish_result
        assert start_result == date(2024, 1, 9)
        assert finish_result == date(2024, 1, 8)


# ---------------------------------------------------------------------------
# CALC-002: apply_lag — error cases
# ---------------------------------------------------------------------------

class TestApplyLagErrors:
    def test_fractional_lag_raises(self):
        with pytest.raises(ValueError, match="fractional lag"):
            apply_lag(date(2024, 1, 1), 1.5, _TABLE, _CAL)

    def test_anchor_outside_table_raises(self):
        # Feb 1 is outside the Jan table
        with pytest.raises(ValueError):
            apply_lag(date(2024, 2, 1), 0, _TABLE, _CAL)

    def test_result_outside_table_raises(self):
        # Jan 31 (wd23) + 5 = wd28, which is outside the Jan 31 table
        with pytest.raises(ValueError):
            apply_lag(date(2024, 1, 31), 5, _TABLE, _CAL)


# ---------------------------------------------------------------------------
# CALC-002: apply_lag — fixture-driven
# ---------------------------------------------------------------------------

class TestApplyLagFixtures:
    def setup_method(self):
        with open(FIXTURES / "lag_scenarios.json") as f:
            self.fixture = json.load(f)
        start = date.fromisoformat(self.fixture["table_start"])
        end = date.fromisoformat(self.fixture["table_end"])
        self.table = build_workday_table(Calendar(name="Standard"), start, end)
        self.cal = Calendar(name="Standard")

    def test_all_apply_lag_scenarios(self):
        for scenario in self.fixture["apply_lag_scenarios"]:
            anchor = date.fromisoformat(scenario["anchor"])
            lag = scenario["lag_workdays"]
            anchor_is_start = scenario["anchor_is_start"]
            expected = date.fromisoformat(scenario["expected"])
            result = apply_lag(anchor, lag, self.table, self.cal,
                               anchor_is_start=anchor_is_start)
            assert result == expected, (
                f"Failed for '{scenario['_note']}': "
                f"expected {expected}, got {result}"
            )


# ---------------------------------------------------------------------------
# CALC-002: compute_lag_between
# ---------------------------------------------------------------------------

class TestComputeLagBetween:
    def test_same_date_lag_zero(self):
        # Jan 5 → Jan 5: wd5 - wd5 = 0
        assert compute_lag_between(date(2024, 1, 5), date(2024, 1, 5), _TABLE, _CAL) == 0

    def test_friday_to_monday_lag_one(self):
        # Jan 5 (wd5) → Jan 8 (wd6): 6 - 5 = 1
        assert compute_lag_between(date(2024, 1, 5), date(2024, 1, 8), _TABLE, _CAL) == 1

    def test_monday_to_friday_lag_four(self):
        # Jan 8 (wd6) → Jan 12 (wd10): 10 - 6 = 4
        assert compute_lag_between(date(2024, 1, 8), date(2024, 1, 12), _TABLE, _CAL) == 4

    def test_full_week_lag_five(self):
        # Jan 8 (wd6) → Jan 15 (wd11): 11 - 6 = 5 (one full work week)
        assert compute_lag_between(date(2024, 1, 8), date(2024, 1, 15), _TABLE, _CAL) == 5

    def test_negative_lag_out_of_sequence(self):
        # Jan 10 (wd8) → Jan 8 (wd6): 6 - 8 = -2 (out-of-sequence)
        assert compute_lag_between(date(2024, 1, 10), date(2024, 1, 8), _TABLE, _CAL) == -2

    def test_nonworkday_from_date_adjusted_finish_type(self):
        # Sat Jan 6 retreats to Jan 5 (wd5, finish-type); to=Jan 8 (wd6): 6 - 5 = 1
        result = compute_lag_between(
            date(2024, 1, 6), date(2024, 1, 8), _TABLE, _CAL,
            from_is_start=False, to_is_start=True
        )
        assert result == 1

    def test_nonworkday_to_date_adjusted_start_type(self):
        # from=Jan 5 (wd5); Sun Jan 7 advances to Jan 8 (wd6, start-type): 6 - 5 = 1
        result = compute_lag_between(
            date(2024, 1, 5), date(2024, 1, 7), _TABLE, _CAL,
            from_is_start=False, to_is_start=True
        )
        assert result == 1

    def test_default_direction_matches_fs_convention(self):
        # Default: from_is_start=False (finish-type), to_is_start=True (start-type)
        # Same as computing as-built lag for a FS relationship
        result = compute_lag_between(date(2024, 1, 5), date(2024, 1, 8), _TABLE, _CAL)
        assert result == 1

    def test_from_date_outside_table_raises(self):
        with pytest.raises(ValueError):
            compute_lag_between(date(2024, 2, 1), date(2024, 1, 8), _TABLE, _CAL)

    def test_to_date_outside_table_raises(self):
        with pytest.raises(ValueError):
            compute_lag_between(date(2024, 1, 5), date(2024, 2, 1), _TABLE, _CAL)


# ---------------------------------------------------------------------------
# CALC-002: compute_lag_between — fixture-driven
# ---------------------------------------------------------------------------

class TestComputeLagBetweenFixtures:
    def setup_method(self):
        with open(FIXTURES / "lag_scenarios.json") as f:
            self.fixture = json.load(f)
        start = date.fromisoformat(self.fixture["table_start"])
        end = date.fromisoformat(self.fixture["table_end"])
        self.table = build_workday_table(Calendar(name="Standard"), start, end)
        self.cal = Calendar(name="Standard")

    def test_all_compute_lag_scenarios(self):
        for scenario in self.fixture["compute_lag_between_scenarios"]:
            from_date = date.fromisoformat(scenario["from_date"])
            to_date = date.fromisoformat(scenario["to_date"])
            from_is_start = scenario["from_is_start"]
            to_is_start = scenario["to_is_start"]
            expected = scenario["expected_lag"]
            result = compute_lag_between(
                from_date, to_date, self.table, self.cal,
                from_is_start=from_is_start, to_is_start=to_is_start
            )
            assert result == expected, (
                f"Failed for '{scenario['_note']}': "
                f"expected {expected}, got {result}"
            )


# ---------------------------------------------------------------------------
# CALC-003: lag_variance
# ---------------------------------------------------------------------------

class TestLagVariance:
    def test_no_change_zero_variance(self):
        assert lag_variance(2, 2) == 0

    def test_lag_grew_positive_variance(self):
        assert lag_variance(1, 4) == 3

    def test_lag_shrank_negative_variance(self):
        assert lag_variance(5, 3) == -2

    def test_zero_planned_lag(self):
        assert lag_variance(0, 2) == 2

    def test_zero_built_lag(self):
        assert lag_variance(3, 0) == -3

    def test_both_zero(self):
        assert lag_variance(0, 0) == 0

    def test_float_inputs(self):
        assert lag_variance(1.5, 3.0) == pytest.approx(1.5)

    def test_negative_planned_lag_lead(self):
        # Planned lead of -2 grew to 0 → variance = +2
        assert lag_variance(-2, 0) == 2

    def test_large_values(self):
        assert lag_variance(10, 50) == 40


# ---------------------------------------------------------------------------
# CALC-003: lag_variance — fixture-driven
# ---------------------------------------------------------------------------

class TestLagVarianceFixtures:
    def setup_method(self):
        with open(FIXTURES / "lag_scenarios.json") as f:
            self.fixture = json.load(f)

    def test_all_lag_variance_scenarios(self):
        for scenario in self.fixture["lag_variance_scenarios"]:
            planned = scenario["as_planned_lag"]
            built = scenario["as_built_lag"]
            expected = scenario["expected_variance"]
            result = lag_variance(planned, built)
            assert result == pytest.approx(expected), (
                f"Failed for '{scenario['_note']}': "
                f"expected {expected}, got {result}"
            )
