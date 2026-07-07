"""
Per-activity-calendar destatusing (ADR-029 r2 Codex HOLD P1).

Destatusing rule math (actual-duration derivation, Rule D/F remaining duration,
blindsight) must count workdays in each activity's OWN calendar, not the single
project-default table. A Monday→next-Monday span is 7 workdays on a 7-day calendar
but 5 on a 5-day calendar — even at 8h/day. Single-calendar (registry None) stays
byte-identical.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

import pytest

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_registry import CalendarEntry, CalendarRegistry, LagCalendarStrategy  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table, resolve_activity_workday_resources  # noqa: E402
from scheduleiq.cpm.destatusing.engine import DestatusingInput, run_destatusing  # noqa: E402
from scheduleiq.cpm.destatusing.policies import DestatusingPolicy  # noqa: E402
# NOT PORTED IN W1b: depends on mip39.api (from mip39.api.routes.analyst import _derive_actual_durations)

_MF = Calendar(name="MF", work_days={1, 2, 3, 4, 5}, hours_per_day=8.0)
_C7 = Calendar(name="C7", work_days={1, 2, 3, 4, 5, 6, 7}, hours_per_day=8.0)
# 5-day with a mid-week holiday on Wed 2026-01-07.
_H5 = Calendar(name="H5", work_days={1, 2, 3, 4, 5},
               exception_dates=frozenset({date(2026, 1, 7)}), hours_per_day=8.0)
_LO, _HI = date(2025, 1, 1), date(2027, 1, 1)
_MF_TABLE = build_workday_table(_MF, _LO, _HI)


def _registry() -> CalendarRegistry:
    r = CalendarRegistry()
    r.register(CalendarEntry(clndr_id="MF", calendar=_MF))
    r.register(CalendarEntry(clndr_id="C7", calendar=_C7))
    r.register(CalendarEntry(clndr_id="H5", calendar=_H5))
    r.set_default("MF")
    r.build_workday_tables(_LO, _HI)
    return r


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def test_resolver_picks_activity_calendar_else_default():
    reg = _registry()
    a7 = Activity(act_id="A7", original_duration=1, calendar_id="C7")
    t, c = resolve_activity_workday_resources(a7, _MF_TABLE, _MF, reg)
    assert c.name == "C7"
    # calendar-less activity → default
    a0 = Activity(act_id="A0", original_duration=1, calendar_id=None)
    t0, c0 = resolve_activity_workday_resources(a0, _MF_TABLE, _MF, reg)
    assert c0 is _MF and t0 is _MF_TABLE
    # registry None → default
    t1, c1 = resolve_activity_workday_resources(a7, _MF_TABLE, _MF, None)
    assert c1 is _MF and t1 is _MF_TABLE


# ---------------------------------------------------------------------------
# _derive_actual_durations (the headline Codex P1 test)
# ---------------------------------------------------------------------------

# NOT PORTED IN W1b: depends on mip39.api (test_derive_actual_duration_per_calendar)
# NOT PORTED IN W1b: depends on mip39.api (test_derive_actual_duration_skips_holiday)
# NOT PORTED IN W1b: depends on mip39.api (test_derive_actual_duration_single_calendar_unchanged)


# ---------------------------------------------------------------------------
# Rule D remaining-duration counted in the activity's calendar (via run_destatusing)
# ---------------------------------------------------------------------------

def _rule_d_activity(calendar_id):
    # AS before new_dd, AF after new_dd ⇒ Rule D (in-progress at the new data date).
    return Activity(
        act_id="X", original_duration=20, calendar_id=calendar_id,
        actual_start=date(2026, 1, 5), actual_finish=date(2026, 1, 21),
        actual_duration=5,
    )


def _run(reg, cal_id):
    inp = DestatusingInput(
        activities=[_rule_d_activity(cal_id)],
        relationships=[],
        new_data_date=date(2026, 1, 14),   # Wednesday
        old_data_date=date(2026, 2, 1),
        workday_table=_MF_TABLE,
        calendar=_MF,
        policy=DestatusingPolicy.ADVISORY_ONLY,
        run_lag_analysis=False,
        run_autodrive=False,
        calendar_registry=reg,
    )
    res = run_destatusing(inp)
    return {a.act_id: a for a in res.destatused_activities}["X"]


def test_rule_d_remaining_duration_per_calendar():
    # RD = workdays(new_dd 01-14 → AF 01-21). On C7 (7-day) = 7; on MF (5-day) = 5.
    x7 = _run(_registry(), "C7")
    assert x7.remaining_duration == 7
    x5 = _run(_registry(), "MF")
    assert x5.remaining_duration == 5


def test_rule_d_single_calendar_unchanged():
    # registry None → the 7-day activity is (wrongly, but as before) counted on the
    # default 5-day table → RD == 5. Locks in single-calendar byte-compatibility.
    x = _run(None, "C7")
    assert x.remaining_duration == 5


# ---------------------------------------------------------------------------
# Codex r2 P2: no silent single-calendar fallback when a registry is unready
# ---------------------------------------------------------------------------

def test_run_destatusing_rejects_unready_registry():
    # A present-but-unbuilt registry must RAISE (like run_analysis / run_lag_analysis),
    # not silently compute Rule D/F on the project-default calendar — even with
    # run_lag_analysis=False (which skips the later lag guard).
    reg = CalendarRegistry()
    reg.register(CalendarEntry(clndr_id="C7", calendar=_C7))
    reg.set_default("C7")  # tables NOT built → do not cover the run range
    inp = DestatusingInput(
        activities=[_rule_d_activity("C7")],
        relationships=[],
        new_data_date=date(2026, 1, 14),
        old_data_date=date(2026, 2, 1),
        workday_table=_MF_TABLE,
        calendar=_MF,
        policy=DestatusingPolicy.ADVISORY_ONLY,
        run_lag_analysis=False,
        run_autodrive=False,
        calendar_registry=reg,
    )
    with pytest.raises(ValueError, match="do not cover the run range"):
        run_destatusing(inp)


# ---------------------------------------------------------------------------
# Codex r2 P2: destatusing actual-lag analysis honours the configured strategy
# ---------------------------------------------------------------------------

def test_destatusing_actual_lag_honours_lag_strategy():
    # pred P on C7 (7-day), succ S on MF (5-day); FS, actuals span a weekend, so the
    # actual lag counts differently under predecessor (C7) vs successor (MF).
    P = Activity(act_id="P", original_duration=1, calendar_id="C7",
                 actual_start=date(2026, 1, 5), actual_finish=date(2026, 1, 9))   # Fri
    S = Activity(act_id="S", original_duration=1, calendar_id="MF",
                 actual_start=date(2026, 1, 14), actual_finish=date(2026, 1, 16))  # Wed
    rel = Relationship(pred_id="P", succ_id="S", rel_type="FS", lag=0)

    def _actual_lag(strategy):
        inp = DestatusingInput(
            activities=[P, S], relationships=[rel],
            new_data_date=date(2026, 1, 20), old_data_date=date(2026, 2, 1),
            workday_table=_MF_TABLE, calendar=_MF,
            policy=DestatusingPolicy.ADVISORY_ONLY,
            run_lag_analysis=True, run_autodrive=False,
            calendar_registry=_registry(), lag_strategy=strategy,
        )
        res = run_destatusing(inp)
        return res.lag_analysis.relationship_results[0].actual_lag

    assert _actual_lag(LagCalendarStrategy.PREDECESSOR_CALENDAR) == 5.0  # C7, weekend counts
    assert _actual_lag(LagCalendarStrategy.SUCCESSOR_CALENDAR) == 3.0    # MF, weekend skipped
