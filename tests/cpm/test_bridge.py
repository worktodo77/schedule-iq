"""Unit tests for the ingest -> CPM engine bridge (ADR-0007 §3, E3).

These exercise the lossy day-granularity conversions in isolation on small
hand-built ingest Schedules, plus one full tiny Schedule -> engine run whose
dates are derived by hand in the comments below.
"""
import os
import sys
from datetime import date, datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest.model import (Activity, ActivityStatus, ActivityType,      # noqa: E402
                                    Calendar, ConstraintType, Relationship,
                                    RelType, Schedule, ScheduleSettings, WorkPattern)
from scheduleiq.cpm.bridge import (build_engine_inputs, resolve_lag_strategy,     # noqa: E402
                                  _trunc_toward_zero)
from scheduleiq.cpm.calendar_registry import LagCalendarStrategy                  # noqa: E402
from scheduleiq.cpm.constraints import (ConstraintType as CpmCT, StatusingMode)   # noqa: E402
from scheduleiq.cpm.engine import run_analysis                                    # noqa: E402


# --------------------------------------------------------------------------- helpers
def cal_5d(uid="C5", hpd=8.0, default=True, nonwork=None, work_exc=None):
    c = Calendar(uid=uid, name=f"{uid} 5-Day", hours_per_day=hpd, is_default=default)
    for iso in (1, 2, 3, 4, 5):
        c.work_patterns[iso] = WorkPattern(weekday=iso, spans=[("08:00", "16:00")])
    if nonwork:
        c.exceptions_nonwork = set(nonwork)
    if work_exc:
        c.exceptions_work = dict(work_exc)
    return c


def cal_7d(uid="C7", hpd=10.0):
    c = Calendar(uid=uid, name=f"{uid} 7-Day", hours_per_day=hpd, is_default=False)
    for iso in range(1, 8):
        c.work_patterns[iso] = WorkPattern(weekday=iso, spans=[("07:00", "17:00")])
    return c


def mk_sched(acts, rels=(), cals=None, dd=datetime(2025, 3, 3, 8, 0),
             settings=None):
    s = Schedule(project_id="T", project_name="T", data_date=dd,
                start_date=dd, source_sha256="")
    s.settings = settings or ScheduleSettings(relationship_lag_calendar="rcal_Predecessor")
    for c in (cals or [cal_5d()]):
        s.calendars[c.uid] = c
    for a in acts:
        s.activities[a.uid] = a
    s.relationships = list(rels)
    return s


def act(uid, code, dur_h, cal="C5", atype=ActivityType.TASK,
        status=ActivityStatus.NOT_STARTED, **kw):
    return Activity(uid=uid, code=code, name=code, atype=atype, status=status,
                   calendar_uid=cal, original_duration_hours=dur_h, **kw)


# --------------------------------------------------------------------------- durations
def test_duration_floor_and_milestone():
    a = act("1", "A", 20.0)                 # 20h / 8 = 2.5 -> floor 2
    ms = act("2", "MS", 0.0, atype=ActivityType.FINISH_MILESTONE)
    ei = build_engine_inputs(mk_sched([a, ms]))
    by = {c.act_id: c for c in ei.activities}
    assert by["1"].original_duration == 2       # floored
    assert by["2"].original_duration == 0       # milestone


def test_remaining_duration_floor_to_zero_disclosed():
    a = act("1", "A", 80.0, status=ActivityStatus.IN_PROGRESS,
            remaining_duration_hours=4.0,       # 4h/8 = 0.5 -> floor 0
            actual_start=datetime(2025, 3, 4, 8, 0))
    ei = build_engine_inputs(mk_sched([a]))
    by = {c.act_id: c for c in ei.activities}
    assert by["1"].remaining_duration == 0
    assert any("floored to 0 workdays" in d for d in ei.disclosures)


# --------------------------------------------------------------------------- lags
def test_lag_hours_to_workdays_truncate_toward_zero():
    # -16h @ 8h/day -> -2 (documented in the brief); +20h -> 2 (toward zero).
    assert _trunc_toward_zero(-16 / 8) == -2
    assert _trunc_toward_zero(20 / 8) == 2
    assert _trunc_toward_zero(-20 / 8) == -2
    a = act("1", "A", 16.0)
    b = act("2", "B", 16.0)
    rels = [Relationship("1", "2", RelType.FS, lag_hours=-16.0)]
    ei = build_engine_inputs(mk_sched([a, b], rels))
    assert ei.relationships[0].lag == -2       # negative lead preserved


def test_ss_and_ff_lag_conversion():
    a = act("1", "A", 16.0); b = act("2", "B", 16.0); c = act("3", "C", 16.0)
    rels = [Relationship("1", "2", RelType.SS, lag_hours=16.0),   # +2 wd
            Relationship("2", "3", RelType.FF, lag_hours=8.0)]    # +1 wd
    ei = build_engine_inputs(mk_sched([a, b, c], rels))
    lags = {(r.pred_id, r.succ_id): (r.rel_type, r.lag) for r in ei.relationships}
    assert lags[("1", "2")] == ("SS", 2)
    assert lags[("2", "3")] == ("FF", 1)


def test_relationship_with_excluded_endpoint_skipped():
    a = act("1", "A", 16.0)
    loe = act("2", "LOE", 0.0, atype=ActivityType.LOE)
    rels = [Relationship("1", "2", RelType.FS, lag_hours=0.0)]
    ei = build_engine_inputs(mk_sched([a, loe], rels))
    assert ei.relationships == []              # LOE endpoint -> rel dropped
    assert any("skipped" in d for d in ei.disclosures)


# --------------------------------------------------------------------------- calendars
def test_calendar_conversion_workdays_and_exceptions():
    holiday = date(2025, 4, 1)
    c5 = cal_5d(nonwork={holiday}, work_exc={date(2025, 4, 5): 8.0})  # worked Sat
    a = act("1", "A", 16.0, cal="C5")
    ei = build_engine_inputs(mk_sched([a], cals=[c5]))
    reg = ei.calendar_registry
    cpm_cal = reg.get("C5")
    assert cpm_cal.work_days == {1, 2, 3, 4, 5}
    assert holiday in cpm_cal.exception_dates              # non-work carried
    assert any("working exception" in d for d in ei.disclosures)  # worked Sat dropped


def test_empty_work_patterns_defaults_mon_fri_disclosed():
    c = Calendar(uid="C5", name="bare", hours_per_day=8.0, is_default=True)
    a = act("1", "A", 16.0, cal="C5")
    ei = build_engine_inputs(mk_sched([a], cals=[c]))
    assert ei.calendar_registry.get("C5").work_days == {1, 2, 3, 4, 5}
    assert any("no work-pattern data" in d for d in ei.disclosures)


def test_seven_day_calendar_all_days_working():
    a = act("1", "A", 30.0, cal="C7")         # 30h/10 = 3 wd
    ei = build_engine_inputs(mk_sched([a], cals=[cal_5d(), cal_7d()]))
    assert ei.calendar_registry.get("C7").work_days == {1, 2, 3, 4, 5, 6, 7}
    assert {c.act_id: c.original_duration for c in ei.activities}["1"] == 3


# --------------------------------------------------------------------------- strategy mapping
@pytest.mark.parametrize("raw,expected", [
    ("rcal_Predecessor", LagCalendarStrategy.PREDECESSOR_CALENDAR),
    ("rcal_Successor", LagCalendarStrategy.SUCCESSOR_CALENDAR),
    ("continuous 24h", LagCalendarStrategy.CONTINUOUS_24H),
    ("rcal_ProjectDefault", LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR),
    ("custom-default-cal", LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR),
])
def test_lag_strategy_mapping_table(raw, expected):
    disc = []
    assert resolve_lag_strategy(raw, disc) is expected
    assert disc == []                          # recognized -> no disclosure


@pytest.mark.parametrize("raw", [None, "", "nonsense"])
def test_lag_strategy_unrecognized_defaults_predecessor_disclosed(raw):
    disc = []
    assert resolve_lag_strategy(raw, disc) is LagCalendarStrategy.PREDECESSOR_CALENDAR
    assert any("defaulted to predecessor" in d for d in disc)


# --------------------------------------------------------------------------- constraints
def test_constraint_mapping_both_slots_and_none_skipped():
    a = act("1", "A", 16.0,
            constraint=ConstraintType.START_ON_OR_AFTER,
            constraint_date=datetime(2025, 4, 7, 8, 0),
            constraint2=ConstraintType.FINISH_ON_OR_BEFORE,
            constraint2_date=datetime(2025, 5, 1, 17, 0))
    b = act("2", "B", 16.0)                    # NONE both slots -> no constraint
    ei = build_engine_inputs(mk_sched([a, b]))
    cons = {(c.act_id, c.ctype): c.cdate for c in ei.constraints}
    assert cons[("1", CpmCT.START_ON_OR_AFTER)] == date(2025, 4, 7)
    assert cons[("1", CpmCT.FINISH_ON_OR_BEFORE)] == date(2025, 5, 1)
    assert not any(c.act_id == "2" for c in ei.constraints)


# --------------------------------------------------------------------------- pinning / statusing
def test_pinning_completed_in_progress_not_started():
    done = act("1", "DONE", 16.0, status=ActivityStatus.COMPLETED,
               actual_start=datetime(2025, 3, 3, 8, 0),
               actual_finish=datetime(2025, 3, 4, 17, 0))
    prog = act("2", "PROG", 80.0, status=ActivityStatus.IN_PROGRESS,
               remaining_duration_hours=48.0,
               actual_start=datetime(2025, 3, 5, 8, 0))
    todo = act("3", "TODO", 16.0)
    ei = build_engine_inputs(mk_sched([done, prog, todo]))
    by = {c.act_id: c for c in ei.activities}
    assert by["1"].pinned_early_start == date(2025, 3, 3)
    assert by["1"].pinned_early_finish == date(2025, 3, 4)
    assert by["2"].pinned_early_start == date(2025, 3, 5)
    assert by["2"].pinned_early_finish is None      # in-progress: ES pinned only
    assert by["2"].remaining_duration == 6          # 48h / 8
    assert by["3"].pinned_early_start is None and by["3"].pinned_early_finish is None


def test_statusing_mode_mapping():
    s_retained = mk_sched([act("1", "A", 16.0)],
                         settings=ScheduleSettings(progress_override=False,
                                                   relationship_lag_calendar="rcal_Predecessor"))
    s_override = mk_sched([act("1", "A", 16.0)],
                         settings=ScheduleSettings(progress_override=True,
                                                   relationship_lag_calendar="rcal_Predecessor"))
    assert build_engine_inputs(s_retained).statusing_mode is StatusingMode.RETAINED_LOGIC
    assert build_engine_inputs(s_override).statusing_mode is StatusingMode.PROGRESS_OVERRIDE


def test_disclosures_always_populated():
    ei = build_engine_inputs(mk_sched([act("1", "A", 16.0)]))
    assert ei.disclosures                       # at least the statusing-mode note


# --------------------------------------------------------------------------- full tiny run
def test_full_tiny_schedule_engine_run_hand_computed():
    """A->B->C FS chain, all on a Mon-Fri calendar, project start Mon 2025-03-03,
    no progress, P6_COMPATIBILITY convention (FS successor starts the NEXT workday
    after the predecessor EF).  Hand derivation:

        A dur=2:  ES Mar-03 (Mon), EF = ES + (2-1) = Mar-04 (Tue)
        B dur=3:  ES = A.EF + 1 workday = Mar-05 (Wed); EF = Mar-05 + 2 = Mar-07 (Fri)
        C dur=2:  ES = B.EF + 1 workday = Mar-10 (Mon, weekend skipped); EF = Mar-11 (Tue)
    """
    a = act("A", "A", 16.0)     # 2 wd
    b = act("B", "B", 24.0)     # 3 wd
    c = act("C", "C", 16.0)     # 2 wd
    rels = [Relationship("A", "B", RelType.FS, 0.0),
            Relationship("B", "C", RelType.FS, 0.0)]
    ei = build_engine_inputs(mk_sched([a, b, c], rels))
    res = run_analysis(
        activities=ei.activities, relationships=ei.relationships,
        project_start=ei.project_start, workday_table=ei.workday_table,
        calendar=ei.calendar, convention=ei.convention,
        calendar_registry=ei.calendar_registry, lag_strategy=ei.lag_strategy,
        constraints=ei.constraints or None, statusing_mode=ei.statusing_mode)
    assert res.is_valid
    sched = res.scheduled
    assert (sched["A"].early_start, sched["A"].early_finish) == (date(2025, 3, 3), date(2025, 3, 4))
    assert (sched["B"].early_start, sched["B"].early_finish) == (date(2025, 3, 5), date(2025, 3, 7))
    assert (sched["C"].early_start, sched["C"].early_finish) == (date(2025, 3, 10), date(2025, 3, 11))
