"""
Tests for V1-D: Actual lag computation (CALC-022 through CALC-025).

Covers:
  - All four relationship types (FS, SS, FF, SF)
  - Workday-number subtraction formula
  - Positive, negative, and zero lags
  - Missing dates → actual_lag=None, dates_missing populated
  - run_lag_analysis() aggregation
  - Deterministic sorting
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date, timedelta

import pytest

from scheduleiq.cpm.destatusing import (  # noqa: E402
    ActualLagResult,
    LagAnalysisResult,
    compute_actual_fs_lag,
    compute_actual_ss_lag,
    compute_actual_ff_lag,
    compute_actual_sf_lag,
    compute_actual_lag,
    run_lag_analysis,
)
from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402


# ---------------------------------------------------------------------------
# Workday table and calendar fixtures
# ---------------------------------------------------------------------------

def _make_5day_calendar() -> Calendar:
    return Calendar(
        name="5day",
        work_days={1, 2, 3, 4, 5},  # Mon-Fri
        hours_per_day=8,
        exception_dates=frozenset(),
    )


def _build_workday_table(start: date, end: date, calendar: Calendar) -> dict[date, int]:
    """Build workday number table from start to end (Mon-Fri only)."""
    table: dict[date, int] = {}
    wd_num = 1
    d = start
    while d <= end:
        if calendar.is_workday(d):
            table[d] = wd_num
            wd_num += 1
        d += timedelta(days=1)
    return table


# Use a Mon-Fri 5-day calendar
CAL = _make_5day_calendar()

# Monday–Friday of week 1
W1_MON = date(2024, 1, 1)   # wd=1
W1_TUE = date(2024, 1, 2)   # wd=2
W1_WED = date(2024, 1, 3)   # wd=3
W1_THU = date(2024, 1, 4)   # wd=4
W1_FRI = date(2024, 1, 5)   # wd=5
W2_MON = date(2024, 1, 8)   # wd=6
W2_TUE = date(2024, 1, 9)   # wd=7
W2_WED = date(2024, 1, 10)  # wd=8

WDT = _build_workday_table(W1_MON, W2_WED + timedelta(days=14), CAL)


def _rel(pred_id, succ_id, rel_type, lag=0) -> Relationship:
    return Relationship(pred_id=pred_id, succ_id=succ_id, rel_type=rel_type, lag=float(lag))


def _act(act_id, actual_start=None, actual_finish=None, early_start=None, early_finish=None) -> Activity:
    return Activity(
        act_id=act_id,
        original_duration=5,
        actual_duration=None,
        remaining_duration=None,
        percent_complete=0.0,
        early_start=early_start,
        early_finish=early_finish,
        actual_start=actual_start,
        actual_finish=actual_finish,
        calendar_id=None,
        constraint_type=None,
        constraint_date=None,
    )


# ---------------------------------------------------------------------------
# Unit tests for individual formula functions
# ---------------------------------------------------------------------------

class TestComputeActualFSLag:
    def test_positive_lag(self):
        # pred_AF = Mon (wd=1), succ_AS = Wed (wd=3) → lag = 3-1 = 2
        lag = compute_actual_fs_lag(W1_MON, W1_WED, WDT, CAL)
        assert lag == 2

    def test_zero_lag(self):
        # pred_AF = Mon, succ_AS = Mon → 1-1 = 0
        lag = compute_actual_fs_lag(W1_MON, W1_MON, WDT, CAL)
        assert lag == 0

    def test_negative_lag(self):
        # pred_AF = Wed (wd=3), succ_AS = Mon (wd=1) → 1-3 = -2
        lag = compute_actual_fs_lag(W1_WED, W1_MON, WDT, CAL)
        assert lag == -2

    def test_across_weekend(self):
        # pred_AF = Fri (wd=5), succ_AS = Mon week2 (wd=6) → 6-5 = 1
        lag = compute_actual_fs_lag(W1_FRI, W2_MON, WDT, CAL)
        assert lag == 1


class TestComputeActualSSLag:
    def test_positive_lag(self):
        # pred_AS = Mon (wd=1), succ_AS = Wed (wd=3) → 3-1 = 2
        lag = compute_actual_ss_lag(W1_MON, W1_WED, WDT, CAL)
        assert lag == 2

    def test_zero_lag(self):
        lag = compute_actual_ss_lag(W1_TUE, W1_TUE, WDT, CAL)
        assert lag == 0

    def test_negative_lag(self):
        lag = compute_actual_ss_lag(W1_WED, W1_MON, WDT, CAL)
        assert lag == -2


class TestComputeActualFFLag:
    def test_positive_lag(self):
        # pred_AF = Tue (wd=2), succ_AF = Fri (wd=5) → 5-2 = 3
        lag = compute_actual_ff_lag(W1_TUE, W1_FRI, WDT, CAL)
        assert lag == 3

    def test_zero_lag(self):
        lag = compute_actual_ff_lag(W1_FRI, W1_FRI, WDT, CAL)
        assert lag == 0

    def test_negative_lag(self):
        lag = compute_actual_ff_lag(W1_FRI, W1_MON, WDT, CAL)
        assert lag == -4


class TestComputeActualSFLag:
    def test_positive_lag(self):
        # pred_AS = Mon (wd=1), succ_AF = Fri (wd=5) → 5-1 = 4
        lag = compute_actual_sf_lag(W1_MON, W1_FRI, WDT, CAL)
        assert lag == 4

    def test_zero_lag(self):
        lag = compute_actual_sf_lag(W1_FRI, W1_FRI, WDT, CAL)
        assert lag == 0


# ---------------------------------------------------------------------------
# compute_actual_lag (dispatch)
# ---------------------------------------------------------------------------

class TestComputeActualLag:
    def test_fs_dispatch(self):
        pred = _act("P1", actual_finish=W1_MON)
        succ = _act("S1", actual_start=W1_WED)
        rel = _rel("P1", "S1", "FS", lag=0)
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.rel_type == "FS"
        assert result.actual_lag == 2
        assert result.lag_variance == 2.0
        assert result.formula_used == "FS_workday"

    def test_ss_dispatch(self):
        pred = _act("P1", actual_start=W1_MON)
        succ = _act("S1", actual_start=W1_WED)
        rel = _rel("P1", "S1", "SS", lag=1)
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.rel_type == "SS"
        assert result.actual_lag == 2
        assert result.lag_variance == 1.0  # 2 - 1

    def test_ff_dispatch(self):
        pred = _act("P1", actual_finish=W1_TUE)
        succ = _act("S1", actual_finish=W1_FRI)
        rel = _rel("P1", "S1", "FF", lag=0)
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.actual_lag == 3

    def test_sf_dispatch(self):
        pred = _act("P1", actual_start=W1_MON)
        succ = _act("S1", actual_finish=W1_FRI)
        rel = _rel("P1", "S1", "SF", lag=0)
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.actual_lag == 4

    def test_missing_pred_finish_for_fs(self):
        pred = _act("P1")  # no actual_finish
        succ = _act("S1", actual_start=W1_WED)
        rel = _rel("P1", "S1", "FS")
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.actual_lag is None
        assert result.lag_variance is None
        assert "pred_actual_finish" in result.dates_missing

    def test_missing_succ_start_for_fs(self):
        pred = _act("P1", actual_finish=W1_MON)
        succ = _act("S1")  # no actual_start
        rel = _rel("P1", "S1", "FS")
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.actual_lag is None
        assert "succ_actual_start" in result.dates_missing

    def test_negative_lag_is_negative(self):
        pred = _act("P1", actual_finish=W1_WED)
        succ = _act("S1", actual_start=W1_MON)
        rel = _rel("P1", "S1", "FS")
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.is_negative is True
        assert result.actual_lag < 0

    def test_result_fields_populated(self):
        pred = _act("P1", actual_finish=W1_MON)
        succ = _act("S1", actual_start=W1_WED)
        rel = _rel("P1", "S1", "FS", lag=1)
        result = compute_actual_lag(rel, pred, succ, WDT, CAL)
        assert result.pred_id == "P1"
        assert result.succ_id == "S1"
        assert result.planned_lag == 1.0
        assert result.lag_variance == 1.0  # 2 - 1


# ---------------------------------------------------------------------------
# run_lag_analysis()
# ---------------------------------------------------------------------------

class TestRunLagAnalysis:
    def test_computed_count(self):
        activities = {
            "P1": _act("P1", actual_finish=W1_MON),
            "S1": _act("S1", actual_start=W1_WED),
        }
        rels = [_rel("P1", "S1", "FS")]
        result = run_lag_analysis(rels, activities, WDT, CAL)
        assert result.computed_count == 1
        assert result.skipped_count == 0

    def test_skipped_when_dates_missing(self):
        activities = {
            "P1": _act("P1"),  # no actual dates
            "S1": _act("S1"),
        }
        rels = [_rel("P1", "S1", "FS")]
        result = run_lag_analysis(rels, activities, WDT, CAL)
        assert result.skipped_count == 1
        assert result.computed_count == 0

    def test_negative_count(self):
        activities = {
            "P1": _act("P1", actual_finish=W1_WED),
            "S1": _act("S1", actual_start=W1_MON),
        }
        rels = [_rel("P1", "S1", "FS")]
        result = run_lag_analysis(rels, activities, WDT, CAL)
        assert result.negative_count == 1

    def test_max_min_variance(self):
        activities = {
            "P1": _act("P1", actual_finish=W1_MON),
            "S1": _act("S1", actual_start=W1_WED),
            "P2": _act("P2", actual_finish=W1_WED),
            "S2": _act("S2", actual_start=W1_MON),
        }
        rels = [
            _rel("P1", "S1", "FS", lag=0),   # variance = +2
            _rel("P2", "S2", "FS", lag=0),   # variance = -2
        ]
        result = run_lag_analysis(rels, activities, WDT, CAL)
        assert result.max_variance == 2.0
        assert result.min_variance == -2.0

    def test_sorted_deterministically(self):
        activities = {
            "P1": _act("P1", actual_finish=W1_MON),
            "S1": _act("S1", actual_start=W1_WED),
            "P2": _act("P2", actual_finish=W1_TUE),
            "S2": _act("S2", actual_start=W1_THU),
        }
        rels = [
            _rel("P2", "S2", "FS"),
            _rel("P1", "S1", "FS"),
        ]
        result = run_lag_analysis(rels, activities, WDT, CAL)
        ids = [(r.pred_id, r.succ_id) for r in result.relationship_results]
        assert ids == sorted(ids)

    def test_missing_activity_skipped(self):
        activities = {"P1": _act("P1", actual_finish=W1_MON)}
        rels = [_rel("P1", "S_MISSING", "FS")]
        result = run_lag_analysis(rels, activities, WDT, CAL)
        assert result.skipped_count == 1
        assert result.relationship_results[0].dates_missing == ["activity_not_found"]


def test_run_lag_analysis_uses_predecessor_calendar_with_registry():
    """F3/F-13: with a CalendarRegistry, each relationship's lag is measured in the
    PREDECESSOR's calendar (PREDECESSOR_CALENDAR / ADR-012), not one global
    calendar. Without a registry the single global calendar is used (unchanged)."""
    from scheduleiq.cpm.calendar_registry import (
        CalendarRegistry, CalendarEntry, LagCalendarStrategy,
    )
    from scheduleiq.cpm.calendar_ops import build_workday_table

    start, end = date(2026, 1, 1), date(2026, 2, 1)
    mon_fri = Calendar(name="MF", work_days={1, 2, 3, 4, 5}, hours_per_day=8.0)
    continuous = Calendar(name="ALL", work_days={1, 2, 3, 4, 5, 6, 7}, hours_per_day=8.0)
    # Pred (Mon-Fri) finishes Fri 2026-01-09; succ (continuous) starts Mon 2026-01-12.
    pred = Activity(act_id="P", original_duration=5, calendar_id="MF",
                    actual_start=date(2026, 1, 5), actual_finish=date(2026, 1, 9))
    succ = Activity(act_id="S", original_duration=5, calendar_id="ALL",
                    actual_start=date(2026, 1, 12), actual_finish=date(2026, 1, 14))
    rels = [_rel("P", "S", "FS")]
    acts = {"P": pred, "S": succ}
    global_table = build_workday_table(continuous, start, end)

    # No registry -> the continuous global calendar counts the weekend: 3 workdays.
    base = run_lag_analysis(rels, acts, global_table, continuous)
    assert base.relationship_results[0].actual_lag == 3.0

    # With the registry, the predecessor's Mon-Fri calendar skips the weekend: 1.
    reg = CalendarRegistry()
    reg.register(CalendarEntry(clndr_id="MF", calendar=mon_fri, raw_clndr_data="",
                               parse_status="PARSED", parse_notes=""))
    reg.register(CalendarEntry(clndr_id="ALL", calendar=continuous, raw_clndr_data="",
                               parse_status="PARSED", parse_notes=""))
    reg.build_workday_tables(start, end)
    multi = run_lag_analysis(rels, acts, global_table, continuous, calendar_registry=reg)
    assert multi.relationship_results[0].actual_lag == 1.0
    # PREDECESSOR_CALENDAR is the default; passing it explicitly is identical.
    explicit = run_lag_analysis(
        rels, acts, global_table, continuous, calendar_registry=reg,
        lag_strategy=LagCalendarStrategy.PREDECESSOR_CALENDAR,
    )
    assert explicit.relationship_results[0].actual_lag == 1.0


def test_run_lag_analysis_flags_calendar_fallback():
    """F3/F-13 (Codex): when the predecessor's calendar can't be resolved from the
    registry the lag falls back to the global calendar AND the result discloses it
    (lag_calendar_fallback=True), so a number-moving deviation is not silent."""
    from scheduleiq.cpm.calendar_registry import CalendarRegistry, CalendarEntry
    from scheduleiq.cpm.calendar_ops import build_workday_table

    start, end = date(2026, 1, 1), date(2026, 2, 1)
    continuous = Calendar(name="ALL", work_days={1, 2, 3, 4, 5, 6, 7}, hours_per_day=8.0)
    pred = Activity(act_id="P", original_duration=5, calendar_id="MISSING",
                    actual_start=date(2026, 1, 5), actual_finish=date(2026, 1, 9))
    succ = Activity(act_id="S", original_duration=5, calendar_id="ALL",
                    actual_start=date(2026, 1, 12), actual_finish=date(2026, 1, 14))
    rels = [_rel("P", "S", "FS")]
    acts = {"P": pred, "S": succ}
    table = build_workday_table(continuous, start, end)
    reg = CalendarRegistry()
    reg.register(CalendarEntry(clndr_id="ALL", calendar=continuous, raw_clndr_data="",
                               parse_status="PARSED", parse_notes=""))
    reg.build_workday_tables(start, end)
    res = run_lag_analysis(rels, acts, table, continuous, calendar_registry=reg)
    lr = res.relationship_results[0]
    assert lr.lag_calendar_fallback is True
    assert lr.actual_lag == 3.0
    base = run_lag_analysis(rels, acts, table, continuous)
    assert base.relationship_results[0].lag_calendar_fallback is False
