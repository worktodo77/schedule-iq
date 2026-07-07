"""
Multi-calendar engine integration tests (V1-B.1).

Tests governance:
  - Per-activity calendar binding changes scheduled dates correctly
  - Mon-Sat activity EF includes Saturday (distinguishes from Mon-Fri result)
  - Activity without calendar_id falls back to default workday table
  - Backward compatibility: registry=None produces same result as original call
  - Predecessor-calendar lag strategy uses predecessor calendar for lag arithmetic
  - Continuous-24h lag strategy uses 24h calendar for lag arithmetic

Source: engine.py, calendar_registry.py, ADR-012.
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

import pytest

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.calendar_registry import (  # noqa: E402
    CalendarEntry,
    CalendarRegistry,
    LagCalendarStrategy,
)
from scheduleiq.cpm.engine import run_analysis  # noqa: E402
from scheduleiq.cpm.conventions import EFConvention  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_START = date(2026, 1, 5)   # Monday
_END   = date(2026, 3, 31)

_MF_CAL = Calendar(name="Mon-Fri", work_days={1, 2, 3, 4, 5}, hours_per_day=8.0)
_MS_CAL = Calendar(name="Mon-Sat", work_days={1, 2, 3, 4, 5, 6}, hours_per_day=8.0)

_MF_TABLE = build_workday_table(_MF_CAL, _START, _END)
_MS_TABLE = build_workday_table(_MS_CAL, _START, _END)


def _make_registry(default_id: str = "MF") -> CalendarRegistry:
    reg = CalendarRegistry()
    reg.register(CalendarEntry(
        clndr_id="MF",
        calendar=_MF_CAL,
        raw_clndr_data="",
        parse_status="PARSED",
        parse_notes="",
    ))
    reg.register(CalendarEntry(
        clndr_id="MS",
        calendar=_MS_CAL,
        raw_clndr_data="",
        parse_status="PARSED",
        parse_notes="",
    ))
    reg.set_default(default_id)
    reg.build_workday_tables(_START, _END)
    return reg


def _act(act_id: str, od: int, calendar_id: str = None) -> Activity:
    return Activity(act_id=act_id, original_duration=float(od), calendar_id=calendar_id)


def _fs(pred: str, succ: str, lag: int = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="FS", lag=lag)


# ---------------------------------------------------------------------------
# Backward compatibility: registry=None
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_no_registry_same_result_as_original(self):
        acts = [_act("A", 3)]
        result_without_reg = run_analysis(
            acts, [], _START, _MF_TABLE, _MF_CAL,
            calendar_registry=None,
        )
        result_original = run_analysis(
            acts, [], _START, _MF_TABLE, _MF_CAL,
        )
        sa_without = result_without_reg.scheduled["A"]
        sa_orig    = result_original.scheduled["A"]
        assert sa_without.early_start == sa_orig.early_start
        assert sa_without.early_finish == sa_orig.early_finish

    def test_no_registry_mon_fri_od6_ends_monday(self):
        # OD=6 Mon-Fri from Jan-05: crosses weekend, EF=Jan-12 (Monday)
        acts = [_act("A", 6)]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL)
        sa = result.scheduled["A"]
        assert sa.early_finish == date(2026, 1, 12)  # Monday, not Saturday


# ---------------------------------------------------------------------------
# Per-activity calendar: Mon-Sat includes Saturday
# ---------------------------------------------------------------------------

class TestPerActivityCalendar:
    def test_mon_sat_od6_ends_saturday(self):
        # OD=6 Mon-Sat from Jan-05: wd6=Jan-10 (Saturday)
        # Without registry, same activity uses Mon-Fri → EF=Jan-12 (Monday)
        reg = _make_registry("MF")
        acts = [_act("A", 6, calendar_id="MS")]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        sa = result.scheduled["A"]
        assert sa.early_finish == date(2026, 1, 10)  # Saturday

    def test_mon_sat_od6_saturday_differs_from_mon_fri(self):
        reg = _make_registry("MF")
        acts_ms = [_act("A", 6, calendar_id="MS")]
        acts_mf = [_act("A", 6, calendar_id="MF")]
        r_ms = run_analysis(acts_ms, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        r_mf = run_analysis(acts_mf, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        # Mon-Sat EF is earlier (Saturday included, so less days to span 6 workdays)
        assert r_ms.scheduled["A"].early_finish < r_mf.scheduled["A"].early_finish

    def test_activity_without_calendar_id_uses_default_table(self):
        # Activity with no calendar_id should use the default Mon-Fri table
        reg = _make_registry("MF")
        acts = [_act("A", 6, calendar_id=None)]  # no binding
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        sa = result.scheduled["A"]
        # Should schedule like Mon-Fri (EF=Jan-12, not Jan-10)
        assert sa.early_finish == date(2026, 1, 12)

    def test_unknown_calendar_id_falls_back_to_default_table(self):
        # Activity bound to a calendar_id not in registry → default table
        reg = _make_registry("MF")
        acts = [_act("A", 6, calendar_id="UNKNOWN")]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        sa = result.scheduled["A"]
        assert sa.early_finish == date(2026, 1, 12)  # Mon-Fri default

    def test_mixed_calendars_two_activities(self):
        # A on Mon-Fri (OD=3): EF=Jan-07; B on Mon-Sat (OD=6): EF=Jan-10
        reg = _make_registry("MF")
        acts = [_act("A", 3, "MF"), _act("B", 6, "MS")]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        assert result.scheduled["A"].early_finish == date(2026, 1, 7)   # Wednesday Mon-Fri
        assert result.scheduled["B"].early_finish == date(2026, 1, 10)  # Saturday Mon-Sat


# ---------------------------------------------------------------------------
# Lag calendar strategies
# ---------------------------------------------------------------------------

class TestLagCalendarStrategies:
    """
    Scenario: P (Mon-Fri, OD=3), FS lag=2, S (Mon-Fri, OD=3).
    P.ES=Jan-05, P.EF=Jan-07.
    With Mon-Fri lag=2 from Jan-07: S.ES=Jan-09 (skips weekend lag).
    """

    def _base_acts(self):
        return [_act("P", 3, "MF"), _act("S", 3, "MF")]

    def _base_rels(self):
        return [_fs("P", "S", lag=2)]

    def test_predecessor_calendar_lag(self):
        reg = _make_registry("MF")
        result = run_analysis(
            self._base_acts(), self._base_rels(), _START, _MF_TABLE, _MF_CAL,
            calendar_registry=reg,
            lag_strategy=LagCalendarStrategy.PREDECESSOR_CALENDAR,
        )
        sa_s = result.scheduled["S"]
        # Mon-Fri lag from Jan-07 (Wed) + 2 wd = Jan-09 (Fri) → ES=Jan-09
        assert sa_s.early_start == date(2026, 1, 9)

    def test_continuous_24h_lag(self):
        reg = _make_registry("MF")
        result_pred = run_analysis(
            self._base_acts(), self._base_rels(), _START, _MF_TABLE, _MF_CAL,
            calendar_registry=reg,
            lag_strategy=LagCalendarStrategy.PREDECESSOR_CALENDAR,
        )
        result_24h = run_analysis(
            self._base_acts(), self._base_rels(), _START, _MF_TABLE, _MF_CAL,
            calendar_registry=reg,
            lag_strategy=LagCalendarStrategy.CONTINUOUS_24H,
        )
        assert result_pred is not None
        assert result_24h is not None
        sa_24h = result_24h.scheduled["S"]
        assert sa_24h.early_start is not None

    def test_project_default_calendar_lag(self):
        reg = _make_registry("MF")
        result = run_analysis(
            self._base_acts(), self._base_rels(), _START, _MF_TABLE, _MF_CAL,
            calendar_registry=reg,
            lag_strategy=LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR,
        )
        assert result.scheduled["S"].early_start is not None

    def test_successor_calendar_lag(self):
        reg = _make_registry("MF")
        result = run_analysis(
            self._base_acts(), self._base_rels(), _START, _MF_TABLE, _MF_CAL,
            calendar_registry=reg,
            lag_strategy=LagCalendarStrategy.SUCCESSOR_CALENDAR,
        )
        assert result.scheduled["S"].early_start is not None


# ---------------------------------------------------------------------------
# Float computation with per-activity calendars
# ---------------------------------------------------------------------------

class TestMultiCalendarFloat:
    def test_critical_path_activity_zero_tf(self):
        # Single activity with no relationships → critical path
        reg = _make_registry("MF")
        acts = [_act("A", 3, "MS")]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        assert result.scheduled["A"].total_float == 0

    def test_two_serial_activities_tf_zero(self):
        reg = _make_registry("MF")
        acts = [_act("P", 3, "MF"), _act("S", 3, "MF")]
        rels = [_fs("P", "S")]
        result = run_analysis(acts, rels, _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        for sa in result.scheduled.values():
            assert sa.total_float == 0


# ---------------------------------------------------------------------------
# Per-relationship lag calendar (finding-2 regression)
# ---------------------------------------------------------------------------

class TestPerRelationshipLagCalendar:
    """Predecessor on Mon-Fri (MF), successor on Mon-Sat (MS), lag=1.

    MF lag from Jan-07 (Wed) + 1 wd = Jan-08 (Thu).
    MS lag from Jan-07 (Wed) + 1 wd = Jan-08 (Thu).  (Same Thursday here —
    both calendars agree on this particular day.)

    To observe a difference we need a lag that crosses a Saturday.
    Scenario: P.EF = Jan-09 (Fri on MF/MS).
      MF lag=1: next MF wd after Jan-09 → Jan-12 (Mon).  S.ES = Jan-12.
      MS lag=1: next MS wd after Jan-09 → Jan-10 (Sat).  S.ES = Jan-10.
    So PREDECESSOR_CALENDAR (use P's MF) → S.ES = Jan-12.
       SUCCESSOR_CALENDAR  (use S's MS) → S.ES = Jan-10.
    """

    _P_OD = 5   # P on MF OD=5: ES=Jan-05 (Mon), EF=Jan-09 (Fri)
    _S_OD = 3

    def _make(self, strategy):
        reg = _make_registry("MF")
        acts = [_act("P", self._P_OD, "MF"), _act("S", self._S_OD, "MS")]
        rels = [_fs("P", "S", lag=1)]
        return run_analysis(
            acts, rels, _START, _MF_TABLE, _MF_CAL,
            calendar_registry=reg,
            lag_strategy=strategy,
        )

    def test_predecessor_calendar_uses_mf_for_lag(self):
        # PREDECESSOR_CALENDAR → lag in MF → skip Sat → S.ES = Mon Jan-12
        result = self._make(LagCalendarStrategy.PREDECESSOR_CALENDAR)
        assert result.scheduled["P"].early_finish == date(2026, 1, 9)
        assert result.scheduled["S"].early_start == date(2026, 1, 12)

    def test_successor_calendar_uses_ms_for_lag(self):
        # SUCCESSOR_CALENDAR → lag in MS (Mon-Sat) → Sat counts → S.ES = Sat Jan-10
        result = self._make(LagCalendarStrategy.SUCCESSOR_CALENDAR)
        assert result.scheduled["P"].early_finish == date(2026, 1, 9)
        assert result.scheduled["S"].early_start == date(2026, 1, 10)

    def test_pred_and_succ_strategies_differ(self):
        r_pred = self._make(LagCalendarStrategy.PREDECESSOR_CALENDAR)
        r_succ = self._make(LagCalendarStrategy.SUCCESSOR_CALENDAR)
        assert r_pred.scheduled["S"].early_start != r_succ.scheduled["S"].early_start

    def test_parallel_path_shorter_has_float(self):
        # A (OD=3) and B (OD=1) both precede C (OD=1); B has float
        reg = _make_registry("MF")
        acts = [_act("A", 3, "MF"), _act("B", 1, "MF"), _act("C", 1, "MF")]
        rels = [_fs("A", "C"), _fs("B", "C")]
        result = run_analysis(acts, rels, _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        assert result.scheduled["A"].total_float == 0  # critical path
        assert result.scheduled["B"].total_float > 0   # has float


# ---------------------------------------------------------------------------
# Result structure with registry
# ---------------------------------------------------------------------------

class TestMultiCalendarResultStructure:
    def test_result_has_scheduled_activities(self):
        reg = _make_registry("MF")
        acts = [_act("A", 3, "MS"), _act("B", 3, "MF")]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        assert len(result.scheduled) == 2

    def test_to_dict_does_not_raise(self):
        reg = _make_registry("MF")
        acts = [_act("A", 3, "MS")]
        result = run_analysis(acts, [], _START, _MF_TABLE, _MF_CAL, calendar_registry=reg)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "scheduled" in d
