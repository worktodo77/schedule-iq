"""
Tests for CalendarRegistry, CalendarEntry, and LagCalendarStrategy (V1-B.1).

Tests governance:
  - Registry registration and duplicate prevention
  - Default calendar lookup and fallback
  - Workday table building for all registered calendars
  - Lag strategy resolution for all four strategies
  - Continuous-24h calendar behavior
  - Summary serialization

Source: calendar_registry.py, ADR-012, ADR-007.
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

import pytest

from scheduleiq.cpm.calendar_registry import (  # noqa: E402
    CalendarEntry,
    CalendarRegistry,
    LagCalendarStrategy,
)
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.models import Calendar  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mon_fri_cal(name: str = "Mon-Fri") -> Calendar:
    return Calendar(name=name, work_days={1, 2, 3, 4, 5}, hours_per_day=8.0)


def _mon_sat_cal(name: str = "Mon-Sat") -> Calendar:
    return Calendar(name=name, work_days={1, 2, 3, 4, 5, 6}, hours_per_day=8.0)


def _entry(clndr_id: str, cal: Calendar, status: str = "PARSED") -> CalendarEntry:
    return CalendarEntry(
        clndr_id=clndr_id,
        calendar=cal,
        raw_clndr_data="",
        parse_status=status,
        parse_notes="",
    )


_START = date(2026, 1, 5)  # Monday
_END = date(2026, 2, 28)


# ---------------------------------------------------------------------------
# CalendarEntry
# ---------------------------------------------------------------------------

class TestCalendarEntry:
    def test_to_dict_has_all_keys(self):
        e = _entry("1", _mon_fri_cal())
        d = e.to_dict()
        assert d["clndr_id"] == "1"
        assert d["calendar_name"] == "Mon-Fri"
        assert d["work_days"] == [1, 2, 3, 4, 5]
        assert d["hours_per_day"] == 8.0
        assert d["exception_date_count"] == 0
        assert d["exception_dates"] == []
        assert d["parse_status"] == "PARSED"

    def test_to_dict_exception_dates_sorted(self):
        cal = Calendar(
            name="test",
            work_days={1, 2, 3, 4, 5},
            exception_dates=frozenset([date(2026, 1, 7), date(2026, 1, 14)]),
        )
        e = _entry("1", cal)
        d = e.to_dict()
        assert d["exception_dates"] == ["2026-01-07", "2026-01-14"]
        assert d["exception_date_count"] == 2


# ---------------------------------------------------------------------------
# CalendarRegistry — registration
# ---------------------------------------------------------------------------

class TestCalendarRegistryRegistration:
    def test_register_and_get(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        assert reg.get("1") is not None
        assert reg.get("1").name == "Mon-Fri"

    def test_get_unknown_returns_none(self):
        reg = CalendarRegistry()
        assert reg.get("99") is None

    def test_register_duplicate_raises(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_entry("1", _mon_fri_cal("Other")))

    def test_calendar_count(self):
        reg = CalendarRegistry()
        assert reg.calendar_count() == 0
        reg.register(_entry("1", _mon_fri_cal()))
        reg.register(_entry("2", _mon_sat_cal()))
        assert reg.calendar_count() == 2

    def test_calendar_ids_sorted(self):
        reg = CalendarRegistry()
        reg.register(_entry("B", _mon_fri_cal()))
        reg.register(_entry("A", _mon_sat_cal()))
        assert reg.calendar_ids() == ["A", "B"]

    def test_get_entry(self):
        reg = CalendarRegistry()
        entry = _entry("1", _mon_fri_cal(), status="PARTIAL")
        reg.register(entry)
        result = reg.get_entry("1")
        assert result is entry
        assert result.parse_status == "PARTIAL"

    def test_get_entry_unknown_returns_none(self):
        reg = CalendarRegistry()
        assert reg.get_entry("99") is None


# ---------------------------------------------------------------------------
# CalendarRegistry — default calendar
# ---------------------------------------------------------------------------

class TestCalendarRegistryDefault:
    def test_set_and_get_default(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.set_default("1")
        assert reg.get_default_clndr_id() == "1"
        assert reg.get_default().name == "Mon-Fri"

    def test_get_default_no_default_set_returns_first_sorted(self):
        reg = CalendarRegistry()
        reg.register(_entry("B", _mon_fri_cal("B")))
        reg.register(_entry("A", _mon_sat_cal("A")))
        # No default set — falls back to first sorted = "A"
        assert reg.get_default().name == "A"

    def test_get_default_unregistered_falls_back_to_first(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.set_default("99")  # not registered
        # Falls back to first sorted registered
        assert reg.get_default().name == "Mon-Fri"

    def test_get_default_empty_registry_returns_none(self):
        reg = CalendarRegistry()
        assert reg.get_default() is None

    def test_get_default_clndr_id_none_when_not_set(self):
        reg = CalendarRegistry()
        assert reg.get_default_clndr_id() is None


# ---------------------------------------------------------------------------
# CalendarRegistry — workday tables
# ---------------------------------------------------------------------------

class TestCalendarRegistryWorkdayTables:
    def test_tables_not_built_initially(self):
        reg = CalendarRegistry()
        assert not reg.tables_built()

    def test_build_workday_tables(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.register(_entry("2", _mon_sat_cal()))
        reg.build_workday_tables(_START, _END)
        assert reg.tables_built()

    def test_get_workday_table_after_build(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.build_workday_tables(_START, _END)
        tbl = reg.get_workday_table("1")
        assert tbl is not None
        assert date(2026, 1, 5) in tbl  # Monday
        assert date(2026, 1, 10) not in tbl  # Saturday excluded in Mon-Fri

    def test_mon_sat_table_includes_saturday(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_sat_cal()))
        reg.build_workday_tables(_START, _END)
        tbl = reg.get_workday_table("1")
        assert date(2026, 1, 10) in tbl  # Saturday
        assert date(2026, 1, 11) not in tbl  # Sunday still excluded

    def test_get_workday_table_unknown_returns_none(self):
        reg = CalendarRegistry()
        assert reg.get_workday_table("99") is None

    def test_continuous_24h_table_built(self):
        reg = CalendarRegistry()
        reg.build_workday_tables(_START, _END)
        tbl = reg.get_continuous_24h_table()
        assert tbl is not None
        assert date(2026, 1, 10) in tbl  # Saturday
        assert date(2026, 1, 11) in tbl  # Sunday

    def test_get_default_workday_table(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.set_default("1")
        reg.build_workday_tables(_START, _END)
        tbl = reg.get_default_workday_table()
        assert tbl is not None
        assert tbl is reg.get_workday_table("1")

    def test_two_calendars_same_date_range(self):
        reg = CalendarRegistry()
        reg.register(_entry("MF", _mon_fri_cal()))
        reg.register(_entry("MS", _mon_sat_cal()))
        reg.build_workday_tables(_START, _END)
        mf_tbl = reg.get_workday_table("MF")
        ms_tbl = reg.get_workday_table("MS")
        # Mon-Sat has more entries than Mon-Fri (includes Saturdays)
        assert len(ms_tbl) > len(mf_tbl)


# ---------------------------------------------------------------------------
# CalendarRegistry — exception dates in workday tables
# ---------------------------------------------------------------------------

class TestCalendarRegistryExceptionDates:
    def test_exception_date_excluded_from_table(self):
        holiday = date(2026, 1, 7)  # Wednesday
        cal = Calendar(
            name="Mon-Fri+Holiday",
            work_days={1, 2, 3, 4, 5},
            exception_dates=frozenset([holiday]),
        )
        reg = CalendarRegistry()
        reg.register(_entry("1", cal))
        reg.build_workday_tables(_START, _END)
        tbl = reg.get_workday_table("1")
        assert holiday not in tbl
        # Jan-05=1, Jan-06=2, [Jan-07 skipped], Jan-08=3
        assert tbl[date(2026, 1, 5)] == 1
        assert tbl[date(2026, 1, 6)] == 2
        assert tbl[date(2026, 1, 8)] == 3  # advances past holiday


# ---------------------------------------------------------------------------
# Continuous-24h calendar
# ---------------------------------------------------------------------------

class TestContinuous24hCalendar:
    def test_continuous_24h_calendar_properties(self):
        reg = CalendarRegistry()
        cal = reg.get_continuous_24h_calendar()
        assert cal.work_days == {1, 2, 3, 4, 5, 6, 7}
        assert cal.hours_per_day == 24.0

    def test_continuous_24h_is_workday_every_day(self):
        reg = CalendarRegistry()
        cal = reg.get_continuous_24h_calendar()
        for day_offset in range(7):
            d = date(2026, 1, 5 + day_offset)
            assert cal.is_workday(d)


# ---------------------------------------------------------------------------
# Lag strategy resolution
# ---------------------------------------------------------------------------

class TestLagStrategyResolution:
    def setup_method(self):
        self.reg = CalendarRegistry()
        self.mf_cal = _mon_fri_cal("Mon-Fri")
        self.ms_cal = _mon_sat_cal("Mon-Sat")
        self.reg.register(_entry("MF", self.mf_cal))
        self.reg.register(_entry("MS", self.ms_cal))
        self.reg.set_default("MF")
        self.reg.build_workday_tables(_START, _END)
        self.mf_tbl = self.reg.get_workday_table("MF")
        self.ms_tbl = self.reg.get_workday_table("MS")

    def test_predecessor_calendar_returns_pred_resources(self):
        cal, tbl = self.reg.resolve_lag_resources(
            LagCalendarStrategy.PREDECESSOR_CALENDAR,
            pred_clndr_id="MF",
            succ_clndr_id="MS",
            fallback_calendar=self.mf_cal,
            fallback_table=self.mf_tbl,
        )
        assert cal.name == "Mon-Fri"
        assert tbl is self.mf_tbl

    def test_successor_calendar_returns_succ_resources(self):
        cal, tbl = self.reg.resolve_lag_resources(
            LagCalendarStrategy.SUCCESSOR_CALENDAR,
            pred_clndr_id="MF",
            succ_clndr_id="MS",
            fallback_calendar=self.mf_cal,
            fallback_table=self.mf_tbl,
        )
        assert cal.name == "Mon-Sat"
        assert tbl is self.ms_tbl

    def test_project_default_calendar(self):
        cal, tbl = self.reg.resolve_lag_resources(
            LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR,
            pred_clndr_id="MS",
            succ_clndr_id="MS",
            fallback_calendar=self.ms_cal,
            fallback_table=self.ms_tbl,
        )
        assert cal.name == "Mon-Fri"  # project default is MF
        assert tbl is self.mf_tbl

    def test_continuous_24h_strategy(self):
        cal, tbl = self.reg.resolve_lag_resources(
            LagCalendarStrategy.CONTINUOUS_24H,
            pred_clndr_id="MF",
            succ_clndr_id="MS",
            fallback_calendar=self.mf_cal,
            fallback_table=self.mf_tbl,
        )
        assert cal.work_days == {1, 2, 3, 4, 5, 6, 7}
        assert date(2026, 1, 10) in tbl  # Saturday in 24h table
        assert date(2026, 1, 11) in tbl  # Sunday in 24h table

    def test_predecessor_none_falls_back(self):
        cal, tbl = self.reg.resolve_lag_resources(
            LagCalendarStrategy.PREDECESSOR_CALENDAR,
            pred_clndr_id=None,
            succ_clndr_id="MS",
            fallback_calendar=self.mf_cal,
            fallback_table=self.mf_tbl,
        )
        assert cal is self.mf_cal
        assert tbl is self.mf_tbl

    def test_unknown_clndr_id_falls_back(self):
        cal, tbl = self.reg.resolve_lag_resources(
            LagCalendarStrategy.PREDECESSOR_CALENDAR,
            pred_clndr_id="UNKNOWN",
            succ_clndr_id="MS",
            fallback_calendar=self.mf_cal,
            fallback_table=self.mf_tbl,
        )
        assert cal is self.mf_cal
        assert tbl is self.mf_tbl


# ---------------------------------------------------------------------------
# LagCalendarStrategy
# ---------------------------------------------------------------------------

class TestLagCalendarStrategy:
    def test_from_str_valid(self):
        assert LagCalendarStrategy.from_str("predecessor_calendar") == LagCalendarStrategy.PREDECESSOR_CALENDAR
        assert LagCalendarStrategy.from_str("successor_calendar") == LagCalendarStrategy.SUCCESSOR_CALENDAR
        assert LagCalendarStrategy.from_str("project_default_calendar") == LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR
        assert LagCalendarStrategy.from_str("continuous_24h") == LagCalendarStrategy.CONTINUOUS_24H

    def test_from_str_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown LagCalendarStrategy"):
            LagCalendarStrategy.from_str("bad-strategy")

    def test_values(self):
        assert LagCalendarStrategy.PREDECESSOR_CALENDAR.value == "predecessor_calendar"
        assert LagCalendarStrategy.CONTINUOUS_24H.value == "continuous_24h"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestCalendarRegistrySummary:
    def test_summary_serializable(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.set_default("1")
        s = reg.summary()
        assert s["calendar_count"] == 1
        assert s["default_clndr_id"] == "1"
        assert s["tables_built"] is False
        assert len(s["calendars"]) == 1

    def test_summary_after_tables_built(self):
        reg = CalendarRegistry()
        reg.register(_entry("1", _mon_fri_cal()))
        reg.build_workday_tables(_START, _END)
        s = reg.summary()
        assert s["tables_built"] is True
        assert s["table_range"] is not None

    def test_summary_calendars_sorted_by_id(self):
        reg = CalendarRegistry()
        reg.register(_entry("Z", _mon_fri_cal("Z")))
        reg.register(_entry("A", _mon_sat_cal("A")))
        s = reg.summary()
        ids = [c["clndr_id"] for c in s["calendars"]]
        assert ids == ["A", "Z"]
