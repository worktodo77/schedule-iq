"""
Tests for CALC-001: Workday/Date Conversion (src/mip39/calendar_ops.py)
and the Calendar model (src/mip39/models.py).

Source: CPW-P6 Manual pp. 41-42.
All fixtures are synthetic. No proprietary data.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import json
import pytest
from datetime import date, timedelta
from pathlib import Path

from scheduleiq.cpm.models import Calendar  # noqa: E402
from scheduleiq.cpm.calendar_ops import (  # noqa: E402
    build_workday_table,
    date_to_workday,
    find_nonworking_runs,
    nonworking_search_bound,
    workday_to_date,
    _adjust_nonworkday,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Calendar model validation
# ---------------------------------------------------------------------------

class TestCalendarModel:
    def test_default_calendar_is_mon_fri(self):
        cal = Calendar(name="Standard")
        assert cal.work_days == {1, 2, 3, 4, 5}

    def test_default_hours_per_day(self):
        cal = Calendar(name="Standard")
        assert cal.hours_per_day == 8.0

    def test_is_workday_monday(self):
        cal = Calendar(name="Standard")
        monday = date(2024, 1, 1)  # known Monday
        assert cal.is_workday(monday)

    def test_is_workday_friday(self):
        cal = Calendar(name="Standard")
        friday = date(2024, 1, 5)  # known Friday
        assert cal.is_workday(friday)

    def test_is_workday_saturday_false(self):
        cal = Calendar(name="Standard")
        saturday = date(2024, 1, 6)
        assert not cal.is_workday(saturday)

    def test_is_workday_sunday_false(self):
        cal = Calendar(name="Standard")
        sunday = date(2024, 1, 7)
        assert not cal.is_workday(sunday)

    def test_custom_work_days(self):
        cal = Calendar(name="SixDay", work_days={1, 2, 3, 4, 5, 6})
        assert cal.is_workday(date(2024, 1, 6))  # Saturday
        assert not cal.is_workday(date(2024, 1, 7))  # Sunday

    def test_invalid_work_days_raises(self):
        with pytest.raises(ValueError, match="invalid ISO weekday"):
            Calendar(name="Bad", work_days={0, 1, 2})

    def test_empty_work_days_raises(self):
        with pytest.raises(ValueError, match="at least one work day"):
            Calendar(name="Empty", work_days=set())

    def test_zero_hours_per_day_raises(self):
        with pytest.raises(ValueError, match="hours_per_day must be positive"):
            Calendar(name="Zero", hours_per_day=0.0)

    def test_negative_hours_per_day_raises(self):
        with pytest.raises(ValueError, match="hours_per_day must be positive"):
            Calendar(name="Neg", hours_per_day=-8.0)


# ---------------------------------------------------------------------------
# build_workday_table
# ---------------------------------------------------------------------------

class TestBuildWorkdayTable:
    def setup_method(self):
        self.cal = Calendar(name="Standard")

    def test_standard_week_from_fixture(self):
        with open(FIXTURES / "calc001_workday_week.json") as f:
            fixture = json.load(f)

        start = date.fromisoformat(fixture["week_start"])
        end = date.fromisoformat(fixture["week_end"])
        table = build_workday_table(self.cal, start, end)

        for iso_str, expected_num in fixture["expected_workdays"].items():
            assert table[date.fromisoformat(iso_str)] == expected_num

        for iso_str in fixture["expected_non_workdays"]:
            assert date.fromisoformat(iso_str) not in table

    def test_table_length_one_week(self):
        # Mon 2024-01-01 through Sun 2024-01-07 → 5 workdays
        table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 7))
        assert len(table) == 5

    def test_workday_numbers_sequential(self):
        table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 31))
        numbers = sorted(table.values())
        assert numbers == list(range(1, len(numbers) + 1))

    def test_single_workday_range(self):
        monday = date(2024, 1, 1)
        table = build_workday_table(self.cal, monday, monday)
        assert table == {monday: 1}

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError, match="must be on or before"):
            build_workday_table(self.cal, date(2024, 1, 10), date(2024, 1, 1))

    def test_weekend_only_range_raises(self):
        # 2024-01-06 (Sat) to 2024-01-07 (Sun)
        with pytest.raises(ValueError, match="No workdays found"):
            build_workday_table(self.cal, date(2024, 1, 6), date(2024, 1, 7))

    def test_multi_week_count(self):
        # 4 weeks = 20 workdays
        table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 28))
        assert len(table) == 20

    def test_first_workday_is_1(self):
        table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 5))
        assert table[date(2024, 1, 1)] == 1

    def test_last_workday_correct(self):
        table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 5))
        assert table[date(2024, 1, 5)] == 5


# ---------------------------------------------------------------------------
# CALC-001: date_to_workday — workday dates
# ---------------------------------------------------------------------------

class TestDateToWorkdayOnWorkday:
    def setup_method(self):
        self.cal = Calendar(name="Standard")
        self.table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 31))

    def test_monday_start(self):
        assert date_to_workday(date(2024, 1, 1), self.cal, self.table, is_start=True) == 1

    def test_friday_finish(self):
        assert date_to_workday(date(2024, 1, 5), self.cal, self.table, is_start=False) == 5

    def test_second_monday(self):
        assert date_to_workday(date(2024, 1, 8), self.cal, self.table, is_start=True) == 6

    def test_workday_same_result_regardless_of_is_start(self):
        # On a workday, is_start does not change the result
        d = date(2024, 1, 3)  # Wednesday
        result_start = date_to_workday(d, self.cal, self.table, is_start=True)
        result_finish = date_to_workday(d, self.cal, self.table, is_start=False)
        assert result_start == result_finish == 3


# ---------------------------------------------------------------------------
# CALC-001: date_to_workday — non-workday adjustment (CPW Manual pp. 41-42)
# ---------------------------------------------------------------------------

class TestDateToWorkdayNonWorkdayAdjust:
    def setup_method(self):
        self.cal = Calendar(name="Standard")
        with open(FIXTURES / "calc001_nonworkday_adjust.json") as f:
            self.fixture = json.load(f)
        start = date.fromisoformat(self.fixture["table_start"])
        end = date.fromisoformat(self.fixture["table_end"])
        self.table = build_workday_table(self.cal, start, end)

    def test_all_scenarios(self):
        for scenario in self.fixture["scenarios"]:
            d = date.fromisoformat(scenario["date"])
            is_start = scenario["is_start"]
            expected_workday = scenario["expected_workday"]
            result = date_to_workday(d, self.cal, self.table, is_start=is_start)
            assert result == expected_workday, (
                f"Failed for {scenario['_note']}: "
                f"expected workday {expected_workday}, got {result}"
            )

    def test_saturday_actual_start_advances_to_monday(self):
        # CPW Manual p. 41: non-workday Actual Start → next higher workday
        saturday = date(2024, 1, 6)
        monday = date(2024, 1, 8)
        result_num = date_to_workday(saturday, self.cal, self.table, is_start=True)
        monday_num = self.table[monday]
        assert result_num == monday_num

    def test_saturday_actual_finish_retreats_to_friday(self):
        # CPW Manual p. 41: non-workday Actual Finish → next lower workday
        saturday = date(2024, 1, 6)
        friday = date(2024, 1, 5)
        result_num = date_to_workday(saturday, self.cal, self.table, is_start=False)
        friday_num = self.table[friday]
        assert result_num == friday_num

    def test_date_not_in_table_raises(self):
        tiny_table = build_workday_table(self.cal, date(2024, 1, 1), date(2024, 1, 5))
        with pytest.raises(ValueError):
            date_to_workday(date(2024, 1, 6), self.cal, tiny_table, is_start=True)


# ---------------------------------------------------------------------------
# CALC-001: workday_to_date (reverse lookup)
# ---------------------------------------------------------------------------

class TestWorkdayToDate:
    def setup_method(self):
        cal = Calendar(name="Standard")
        self.table = build_workday_table(cal, date(2024, 1, 1), date(2024, 1, 31))

    def test_workday_1_is_monday(self):
        assert workday_to_date(1, self.table) == date(2024, 1, 1)

    def test_workday_5_is_friday(self):
        assert workday_to_date(5, self.table) == date(2024, 1, 5)

    def test_workday_6_is_second_monday(self):
        assert workday_to_date(6, self.table) == date(2024, 1, 8)

    def test_invalid_workday_raises(self):
        with pytest.raises(ValueError, match="not found in table"):
            workday_to_date(9999, self.table)

    def test_zero_workday_raises(self):
        with pytest.raises(ValueError, match="not found in table"):
            workday_to_date(0, self.table)


# ---------------------------------------------------------------------------
# _adjust_nonworkday (internal helper — boundary tests)
# ---------------------------------------------------------------------------

class TestAdjustNonworkday:
    def setup_method(self):
        self.cal = Calendar(name="Standard")

    def test_saturday_forward(self):
        saturday = date(2024, 1, 6)
        assert _adjust_nonworkday(saturday, self.cal, is_start=True) == date(2024, 1, 8)

    def test_saturday_backward(self):
        saturday = date(2024, 1, 6)
        assert _adjust_nonworkday(saturday, self.cal, is_start=False) == date(2024, 1, 5)

    def test_sunday_forward(self):
        sunday = date(2024, 1, 7)
        assert _adjust_nonworkday(sunday, self.cal, is_start=True) == date(2024, 1, 8)

    def test_sunday_backward(self):
        sunday = date(2024, 1, 7)
        assert _adjust_nonworkday(sunday, self.cal, is_start=False) == date(2024, 1, 5)

    def test_no_workday_within_14_days_raises(self):
        # Calendar with no workdays — should raise within safety bound
        no_work_cal = Calendar.__new__(Calendar)
        object.__setattr__(no_work_cal, "name", "NoWork")
        object.__setattr__(no_work_cal, "work_days", set())
        object.__setattr__(no_work_cal, "hours_per_day", 8.0)
        # Monkey-patch is_workday to always return False
        no_work_cal.is_workday = lambda d: False  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="No workday found within"):
            _adjust_nonworkday(date(2024, 1, 6), no_work_cal, is_start=True)

    def test_table_bound_tracks_long_calendar_closure(self):
        closure = frozenset(
            date(2024, 1, 8) + timedelta(days=i) for i in range(21)
        )
        cal = Calendar(name="Shutdown", exception_dates=closure)
        table = build_workday_table(cal, date(2024, 1, 1), date(2024, 2, 9))
        runs = find_nonworking_runs(cal, min(table), max(table), minimum_days=15)
        assert runs == [{
            "start": date(2024, 1, 6),
            "end": date(2024, 1, 28),
            "days": 23,
        }]
        assert nonworking_search_bound(cal, min(table), max(table)) == 23
        assert _adjust_nonworkday(
            date(2024, 1, 8), cal, is_start=True, workday_table=table
        ) == date(2024, 1, 29)
