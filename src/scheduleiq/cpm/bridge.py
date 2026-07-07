"""Bridge: ScheduleIQ ingest ``Schedule`` -> ported CPM engine inputs (ADR-0007 §3, E3).

The ingest model (``scheduleiq.ingest.model``) carries durations and floats in
HOURS and dates as ``datetime`` (P6-native).  The ported CPM engine
(``scheduleiq.cpm``) is a day-granularity engine: integer workday durations,
``date`` objects, workday tables, a ``CalendarRegistry``, and a
``LagCalendarStrategy``.  This module performs the one lossy conversion between
the two, and — per ADR-0007's "port-and-validate, disclose every severance"
discipline — records **every** lossy step in ``EngineInputs.disclosures`` so the
handshake (``scheduleiq.cpm.handshake``) can surface exactly what the engine did
to the file before re-scheduling it.

Conversion is day-granularity throughout (ADR-0007 §2; source M-CPM-03):
  * durations: hours -> integer workdays via the ACTIVITY'S OWN calendar
    hours_per_day, floored; milestones -> 0.
  * lags: hours -> integer workdays via the lag-strategy's divisor calendar,
    truncated toward zero (sign preserved: a -16h lead at 8h/day -> -2 workdays).
  * statusing: actual-date anchoring ("pinning", ADR-019) — completed activities
    pin ES/EF at their actual dates; in-progress activities pin ES at the actual
    start and carry a remaining duration; not-started activities are unpinned.
  * constraints: ingest ConstraintType (both P6 constraint slots) -> cpm
    SchedulingConstraint (LIM-028 date constraints, closed in the port).
  * calendars: each ingest Calendar -> cpm Calendar in a CalendarRegistry keyed
    by uid.  Working exceptions (e.g. a worked Saturday) CANNOT be represented in
    the cpm Calendar model and are disclosed per calendar.

Nothing here writes back to the schedule of record: the engine output is a
diagnostic delta (ADR-0007 §4), never a competing schedule.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ..ingest.model import (Activity as IngestActivity, Calendar as IngestCalendar,
                            ConstraintType as IngestConstraintType, Schedule)
from .calendar_ops import build_workday_table
from .calendar_registry import CalendarEntry, CalendarRegistry, LagCalendarStrategy
from .constraints import (ConstraintType as CpmConstraintType, SchedulingConstraint,
                         StatusingMode)
from .conventions import EFConvention
from .models import Activity as CpmActivity, Calendar as CpmCalendar, Relationship as CpmRelationship


# ---------------------------------------------------------------------------
# EngineInputs container
# ---------------------------------------------------------------------------

@dataclass
class EngineInputs:
    """Everything ``run_analysis`` needs, converted from one ingest Schedule.

    ``disclosures`` is the running list of every lossy day-granularity
    conversion the bridge performed (ADR-0007 discipline).  It is carried
    forward into the handshake result.
    """

    activities: list[CpmActivity]
    relationships: list[CpmRelationship]
    project_start: date
    workday_table: dict[date, int]
    calendar: CpmCalendar
    calendar_registry: CalendarRegistry
    lag_strategy: LagCalendarStrategy
    constraints: list[SchedulingConstraint]
    statusing_mode: StatusingMode
    disclosures: list[str] = field(default_factory=list)
    convention: EFConvention = EFConvention.P6_COMPATIBILITY
    # uid -> analyst-facing code, so handshake/checks can name activities by code.
    code_by_uid: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Small day-granularity helpers
# ---------------------------------------------------------------------------

def _trunc_toward_zero(x: float) -> int:
    """Truncate toward zero, sign-preserving, with a tiny epsilon so exact
    multiples represented as floats (e.g. 16/8 = 1.9999999) do not lose a unit."""
    if x >= 0:
        return int(math.floor(x + 1e-9))
    return int(math.ceil(x - 1e-9))


def _floor_div_hours(hours: float, hpd: float) -> int:
    """Floor hours -> whole workdays on an hpd-hour day (source M-CPM-03)."""
    if hpd <= 0:
        hpd = 8.0
    return int(math.floor(hours / hpd + 1e-9))


def _as_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def _hpd_of(cal: Optional[IngestCalendar]) -> float:
    return cal.hours_per_day if (cal and cal.hours_per_day) else 8.0


# ---------------------------------------------------------------------------
# Calendar conversion
# ---------------------------------------------------------------------------

def _convert_calendar(ical: IngestCalendar, disclosures: list[str]) -> CpmCalendar:
    """One ingest Calendar -> one cpm Calendar.  Working exceptions cannot be
    represented and are disclosed per calendar."""
    work_days = {iso for iso, wp in ical.work_patterns.items() if wp.hours > 0}
    label = ical.name or ical.uid
    if not ical.work_patterns:
        work_days = {1, 2, 3, 4, 5}
        disclosures.append(
            f"calendar {label!r} has no work-pattern data; defaulted to Mon-Fri "
            "(ISO 1-5) working week."
        )
    elif not work_days:
        # patterns present but every day zero-hours — refuse an empty week
        # (cpm Calendar rejects it) and disclose.
        work_days = {1, 2, 3, 4, 5}
        disclosures.append(
            f"calendar {label!r} has work patterns but no working weekday; "
            "defaulted to Mon-Fri (ISO 1-5)."
        )
    if ical.exceptions_work:
        disclosures.append(
            f"calendar {label!r} carries {len(ical.exceptions_work)} working "
            "exception(s) (e.g. a worked weekend); the day-granularity engine "
            "calendar cannot represent working exceptions — they are dropped "
            "(non-working exceptions/holidays are preserved)."
        )
    return CpmCalendar(
        name=label,
        work_days=work_days,
        hours_per_day=_hpd_of(ical),
        exception_dates=frozenset(ical.exceptions_nonwork),
    )


# ---------------------------------------------------------------------------
# Constraint conversion
# ---------------------------------------------------------------------------

def _convert_constraint(uid: str, ct: IngestConstraintType, cdate: Optional[datetime],
                        disclosures: list[str]) -> Optional[SchedulingConstraint]:
    if ct == IngestConstraintType.NONE:
        return None
    try:
        cpm_ct = CpmConstraintType[ct.name]   # names align 1:1 (verified)
    except KeyError:
        disclosures.append(f"activity {uid}: constraint {ct.value!r} not mappable "
                           "to the engine constraint vocabulary; skipped.")
        return None
    d = _as_date(cdate)
    if d is None and cpm_ct is not CpmConstraintType.AS_LATE_AS_POSSIBLE:
        disclosures.append(f"activity {uid}: {ct.value} constraint has no date; skipped.")
        return None
    return SchedulingConstraint(act_id=uid, ctype=cpm_ct, cdate=d)


# ---------------------------------------------------------------------------
# Lag-calendar strategy resolution (SCHEDOPTIONS E3)
# ---------------------------------------------------------------------------

def resolve_lag_strategy(raw: Optional[str], disclosures: list[str]) -> LagCalendarStrategy:
    """Map the parsed P6 ``sched_calendar_on_relationship_lag`` value onto the
    engine's LagCalendarStrategy (case-insensitive substring match)."""
    if raw:
        low = raw.lower()
        if "24" in low:
            return LagCalendarStrategy.CONTINUOUS_24H
        if "pred" in low:
            return LagCalendarStrategy.PREDECESSOR_CALENDAR
        if "succ" in low:
            return LagCalendarStrategy.SUCCESSOR_CALENDAR
        if "proj" in low or "default" in low:
            return LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR
    disclosures.append(
        f"lag calendar setting missing/unrecognized ({raw!r}); defaulted to "
        "predecessor calendar (P6 convention)."
    )
    return LagCalendarStrategy.PREDECESSOR_CALENDAR


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_engine_inputs(
    sched: Schedule,
    convention: EFConvention = EFConvention.P6_COMPATIBILITY,
) -> EngineInputs:
    """Convert one ingest Schedule into day-granularity CPM engine inputs.

    Population is ``sched.real_activities`` (LOE/summary/hammock excluded).
    Every lossy step is recorded in the returned ``disclosures`` list.
    """
    disclosures: list[str] = []

    reals = sched.real_activities
    excluded = len(sched.activities) - len(reals)
    if excluded:
        disclosures.append(
            f"{excluded} LOE/summary/hammock activity(ies) excluded from the CPM "
            "population (real activities only)."
        )
    real_uids = {a.uid for a in reals}
    code_by_uid = {a.uid: a.code for a in reals}

    # -- Calendars -> registry ---------------------------------------------
    registry = CalendarRegistry()
    cpm_cals: dict[str, CpmCalendar] = {}
    for uid, ical in sched.calendars.items():
        cpm_cal = _convert_calendar(ical, disclosures)
        cpm_cals[uid] = cpm_cal
        registry.register(CalendarEntry(clndr_id=uid, calendar=cpm_cal,
                                       parse_status="PARSED"))
    # Default calendar selection: the is_default one; else the calendar assigned
    # to the most real activities; else a synthetic Mon-Fri default.
    default_uid: Optional[str] = None
    for uid, ical in sched.calendars.items():
        if ical.is_default:
            default_uid = uid
            break
    if default_uid is None and sched.calendars:
        counts: dict[str, int] = {}
        for a in reals:
            if a.calendar_uid in cpm_cals:
                counts[a.calendar_uid] = counts.get(a.calendar_uid, 0) + 1
        if counts:
            default_uid = max(sorted(counts), key=lambda k: counts[k])
        else:
            default_uid = sorted(sched.calendars)[0]
        disclosures.append(
            f"no calendar flagged default; using {cpm_cals[default_uid].name!r} "
            "(most-assigned / lowest clndr_id) as the project-default calendar."
        )
    if default_uid is None:
        # No calendars at all — synthesize a standard 5-day, 8h default.
        default_uid = "__default__"
        synth = CpmCalendar(name="Standard 5-Day (synthesized)")
        cpm_cals[default_uid] = synth
        registry.register(CalendarEntry(clndr_id=default_uid, calendar=synth,
                                       parse_status="DEFERRED"))
        disclosures.append("schedule carries no calendars; synthesized a standard "
                           "Mon-Fri 8h default calendar.")
    registry.set_default(default_uid)
    default_cal = cpm_cals[default_uid]

    # -- project_start -----------------------------------------------------
    project_start = _as_date(sched.data_date)
    if project_start is None:
        candidates = [_as_date(a.planned_start) or _as_date(a.early_start)
                     for a in reals]
        candidates = [d for d in candidates if d is not None]
        if not candidates:
            raise ValueError("build_engine_inputs: schedule has no data date and no "
                             "planned/early start dates to anchor project_start.")
        project_start = min(candidates)
        disclosures.append(
            f"no data date; project_start fell back to the earliest planned/early "
            f"start ({project_start.isoformat()})."
        )

    # -- Activities: durations + statusing (pinning) -----------------------
    cpm_acts: list[CpmActivity] = []
    rd_floor_to_zero = 0
    inprog_no_actual = 0
    hpd_by_uid: dict[str, float] = {}
    for a in reals:
        ical = sched.cal_for(a)
        hpd = _hpd_of(ical)
        hpd_by_uid[a.uid] = hpd
        od = 0 if a.is_milestone else _floor_div_hours(a.original_duration_hours, hpd)

        pes = pef = None
        rd: Optional[int] = None
        if a.completed:
            pes = _as_date(a.actual_start)
            pef = _as_date(a.actual_finish) or _as_date(a.actual_start)
            if pes is None:
                # completed but no actual start — cannot pin; treat as unpinned.
                disclosures.append(f"activity {a.code}: completed but no actual start; "
                                   "cannot pin (scheduled from logic).")
        elif a.in_progress:
            pes = _as_date(a.actual_start)
            rd = 0 if a.is_milestone else _floor_div_hours(a.remaining_duration_hours, hpd)
            if a.remaining_duration_hours > 0 and rd == 0:
                rd_floor_to_zero += 1
            if pes is None:
                inprog_no_actual += 1
        # not-started: no pins, no remaining override.

        cid = a.calendar_uid if a.calendar_uid in cpm_cals else None
        cpm_acts.append(CpmActivity(
            act_id=a.uid,
            original_duration=od,
            remaining_duration=rd,
            calendar_id=cid,
            pinned_early_start=pes,
            pinned_early_finish=pef,
        ))
    if rd_floor_to_zero:
        disclosures.append(
            f"{rd_floor_to_zero} in-progress activity(ies) had a positive remaining "
            "duration that floored to 0 workdays (day-granularity approximation)."
        )
    if inprog_no_actual:
        disclosures.append(
            f"{inprog_no_actual} in-progress activity(ies) had no actual start to pin; "
            "scheduled from logic instead."
        )

    # -- Lag-calendar strategy + statusing mode (SCHEDOPTIONS) -------------
    lag_strategy = resolve_lag_strategy(
        sched.settings.relationship_lag_calendar, disclosures)
    statusing_mode = (StatusingMode.PROGRESS_OVERRIDE
                     if sched.settings.progress_override
                     else StatusingMode.RETAINED_LOGIC)
    disclosures.append(
        f"statusing mode: {statusing_mode.value} "
        f"(from SCHEDOPTIONS progress_override={sched.settings.progress_override!r})."
    )

    # -- Relationships: lag hours -> workdays via the strategy divisor ------
    def _lag_divisor(pred_uid: str, succ_uid: str) -> float:
        if lag_strategy is LagCalendarStrategy.CONTINUOUS_24H:
            return 24.0
        if lag_strategy is LagCalendarStrategy.SUCCESSOR_CALENDAR:
            return hpd_by_uid.get(succ_uid, _hpd_of(sched.calendars.get(default_uid)))
        if lag_strategy is LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR:
            return default_cal.hours_per_day
        # PREDECESSOR_CALENDAR (default)
        return hpd_by_uid.get(pred_uid, _hpd_of(sched.calendars.get(default_uid)))

    cpm_rels: list[CpmRelationship] = []
    skipped_rels = 0
    for r in sched.relationships:
        if r.pred_uid not in real_uids or r.succ_uid not in real_uids:
            skipped_rels += 1
            continue
        lag_wd = _trunc_toward_zero(r.lag_hours / _lag_divisor(r.pred_uid, r.succ_uid))
        cpm_rels.append(CpmRelationship(
            pred_id=r.pred_uid, succ_id=r.succ_uid,
            rel_type=r.rtype.value, lag=lag_wd,
        ))
    if skipped_rels:
        disclosures.append(
            f"{skipped_rels} relationship(s) skipped: an endpoint was excluded from "
            "the CPM population (LOE/summary) or does not resolve to an activity."
        )

    # -- Constraints (both P6 slots) ---------------------------------------
    constraints: list[SchedulingConstraint] = []
    for a in reals:
        for ct, cd in ((a.constraint, a.constraint_date),
                       (a.constraint2, a.constraint2_date)):
            con = _convert_constraint(a.uid, ct, cd, disclosures)
            if con is not None:
                constraints.append(con)

    # -- Workday tables ----------------------------------------------------
    seen_dates: list[date] = [project_start]
    for a in reals:
        for dt in (a.early_start, a.early_finish, a.late_start, a.late_finish,
                   a.actual_start, a.actual_finish, a.planned_start, a.planned_finish,
                   a.constraint_date, a.constraint2_date):
            d = _as_date(dt)
            if d is not None:
                seen_dates.append(d)
    lo = min(seen_dates) - timedelta(days=60)
    hi = max(seen_dates) + timedelta(days=400)
    workday_table = build_workday_table(default_cal, lo, hi)
    registry.ensure_workday_tables(lo, hi)

    return EngineInputs(
        activities=cpm_acts,
        relationships=cpm_rels,
        project_start=project_start,
        workday_table=workday_table,
        calendar=default_cal,
        calendar_registry=registry,
        lag_strategy=lag_strategy,
        constraints=constraints,
        statusing_mode=statusing_mode,
        disclosures=disclosures,
        convention=convention,
        code_by_uid=code_by_uid,
    )
