"""
Ported from the LI MIP 3.9 tool (mip39.calendar_ops) per ADR-0007 — port-and-validate.
CALC-001: Workday / Date Conversion

Converts between calendar dates and workday numbers using a simplified
Calendar model (Phase 2). Implements the non-workday adjustment rule
from CPW-P6 Manual pp. 41–42:

  "If the activity date is an Actual Start and falls on a non-workday
   then the next higher workday is found. If the activity date is an
   Actual Finish and the date falls on a non-workday, then the next
   lower workday is found."

Phase 2 simplifications (ADR-002):
  - Integer workday numbers (no hour-level precision; deferred to Phase 3).
  - No exception dates (holidays). Work days are determined solely by weekday.
  - Single calendar model; multi-calendar logic deferred.

Source: CPW-P6 Manual pp. 41–42 (Lag Analysis subsection).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from .models import Calendar


# ---------------------------------------------------------------------------
# Workday table construction
# ---------------------------------------------------------------------------

def build_workday_table(calendar: Calendar, start: date, end: date) -> dict[date, int]:
    """
    Build a mapping from calendar date → workday number for [start, end] inclusive.

    Workday numbering begins at 1 on the first workday on or after start.
    Non-workdays are not assigned a workday number and are absent from the table.

    CPW Manual p. 41: the calendar is built as a listing covering the full
    project date range. Phase 2 uses integer workday numbers.

    Args:
        calendar: The Calendar defining which days are workdays.
        start:    First calendar date to include (inclusive).
        end:      Last calendar date to include (inclusive).

    Returns:
        Dict mapping each workday date to its sequential workday number (1-based).

    Raises:
        ValueError: If start > end, or if no workdays exist in the range.
    """
    if start > end:
        raise ValueError(
            f"start ({start}) must be on or before end ({end})."
        )

    table: dict[date, int] = {}
    workday_number = 1
    current = start
    while current <= end:
        if calendar.is_workday(current):
            table[current] = workday_number
            workday_number += 1
        current += timedelta(days=1)

    if not table:
        raise ValueError(
            f"No workdays found in range {start} to {end} for calendar {calendar.name!r}."
        )

    return table


def build_calendar_resources(
    source: Any,
    lo: date,
    hi: date,
    *,
    calendar: Any = None,
    registry: Any = None,
) -> tuple[dict[date, int], Any]:
    """The single normal path for building a window/run's DEFAULT workday table
    and — when the import carries a multi-calendar ``CalendarRegistry`` — ensuring
    that registry's per-calendar tables cover ``[lo, hi]`` (ADR-029 r2 Slice A).

    Lives in this core module (not the api layer) so both the API adapter
    (``api/engine_runner``) and core engine consumers (``windows/pipeline``) use
    one helper without a backwards core→api import.

    ``source`` is the table-source object (an ``ImportXerResult``, a
    ``WindowDefinition``, or a ``WindowState.imported``); it must expose
    ``.calendar`` and is read for ``.calendar_registry`` defensively. Sites that
    hold only a bare ``Calendar`` (e.g. the interop harness) pass ``source=None``
    with ``calendar=`` / ``registry=`` directly.

    ``[lo, hi]`` is the ALREADY-PADDED window the caller computed; the helper adds
    NO padding of its own — padding policy stays at the call site so each
    consumer's window (notably the pipeline's 14d-before / 3650d-after headroom)
    is preserved.

    Returns ``(default_table, registry_or_none)``. When ``registry`` is None this
    is byte-identical to ``build_workday_table(calendar, lo, hi)`` — the registry
    path is purely additive. The registry build is range-aware + atomic
    (``ensure_workday_tables``): a calendar with no workdays in range raises (a
    disclosed hard error) rather than silently single-calendaring.

    NOTE (ADR-029 r2): this only serves the table-BUILDING sites. Pure consumers
    (the CPM core, destatus rules/transformations, lag arithmetic) receive a
    prebuilt table and must NOT be routed through here.
    """
    if calendar is None:
        if source is None:
            raise ValueError(
                "build_calendar_resources: pass either source or calendar."
            )
        calendar = source.calendar
    if registry is None and source is not None:
        registry = getattr(source, "calendar_registry", None)

    table = build_workday_table(calendar, lo, hi)
    if registry is not None:
        registry.ensure_workday_tables(lo, hi)
    return table, registry


def resolve_activity_workday_resources(
    activity: Any,
    default_table: dict[date, int],
    default_calendar: Calendar,
    registry: Any = None,
) -> tuple[dict[date, int], Calendar]:
    """Return the ``(workday_table, calendar)`` ONE activity's workday arithmetic
    must use under multi-calendar (ADR-029 r2): the activity's OWN calendar + its
    pre-built per-calendar table when a registry carries both; otherwise the project
    default. Pure consumers that count workdays for a single activity (destatusing
    rules / actual-duration derivation, the rectification calibration comparison)
    call this per activity so a 7-day / holiday / weather activity is not measured
    on the project-default 5-day table.

    Byte-identical to ``(default_table, default_calendar)`` when ``registry`` is None
    (single-calendar), when the activity has no ``calendar_id``, or when the
    registry's table for that calendar is not built (the upstream
    ``build_calendar_resources`` ensures it; this is the defensive fallback)."""
    if registry is not None:
        cid = getattr(activity, "calendar_id", None)
        if cid is not None:
            t = registry.get_workday_table(cid)
            c = registry.get(cid)
            if t is not None and c is not None:
                return t, c
    return default_table, default_calendar


# ---------------------------------------------------------------------------
# CALC-001: date → workday conversion with non-workday adjustment
# ---------------------------------------------------------------------------

def nearest_workday_index(table: dict[date, int], d: date) -> int:
    """
    Return the workday-table index for date ``d``.

    Computed CPM dates always land on workdays (present in ``table``). V2-A
    actual-date-anchored CPM, however, can pin an activity at a real ACTUAL
    date that falls on a non-workday (e.g. a Saturday actual finish), which is
    absent from the table. For those, snap to the nearest workday (search
    outward up to 7 days) so workday arithmetic (float, longest-path tightness)
    stays defined. Non-pinned schedules never hit the fallback, so existing
    behavior is unchanged. This is a table-only helper (no Calendar needed); for
    the direction-aware CPW adjustment rule use ``date_to_workday`` instead.
    """
    v = table.get(d)
    if v is not None:
        return v
    for delta in range(1, 8):
        nxt = table.get(d + timedelta(days=delta))
        if nxt is not None:
            return nxt
        prv = table.get(d - timedelta(days=delta))
        if prv is not None:
            return prv
    raise KeyError(d)


def date_to_workday(
    d: date,
    calendar: Calendar,
    workday_table: dict[date, int],
    is_start: bool,
) -> int:
    """
    CALC-001 — Convert a calendar date to a workday number.

    If d is already a workday, returns its workday number directly.
    If d is a non-workday, applies the CPW adjustment rule (Manual pp. 41–42):
      - Actual Start (is_start=True):  advance to the next higher workday.
      - Actual Finish (is_start=False): retreat to the next lower workday.

    Args:
        d:              The calendar date to convert.
        calendar:       The Calendar defining workdays.
        workday_table:  Prebuilt workday table covering at least d and its
                        immediate neighbours.
        is_start:       True if d is an Actual Start; False if Actual Finish.

    Returns:
        The workday number for the adjusted date.

    Raises:
        ValueError: If d is not covered by workday_table, or if the
                    non-workday adjustment moves outside the table range.
    """
    if calendar.is_workday(d):
        if d not in workday_table:
            raise ValueError(
                f"Date {d} is a workday but is not in the workday table. "
                "Ensure the table covers the full project date range."
            )
        return workday_table[d]

    # Non-workday — apply CPW adjustment rule
    adjusted = _adjust_nonworkday(d, calendar, is_start)

    if adjusted not in workday_table:
        raise ValueError(
            f"Adjusted date {adjusted} (from non-workday {d}) is not in the "
            "workday table. Ensure the table covers the full project date range."
        )

    return workday_table[adjusted]


def _adjust_nonworkday(d: date, calendar: Calendar, is_start: bool) -> date:
    """
    Move d to the nearest workday in the direction specified by is_start.

    is_start=True  → next higher workday (forward in time).
    is_start=False → next lower workday (backward in time).

    Raises ValueError if no workday is found within 14 calendar days
    (guards against misconfigured calendars with no workdays).
    """
    step = timedelta(days=1) if is_start else timedelta(days=-1)
    candidate = d + step
    limit = 14  # safety bound

    for _ in range(limit):
        if calendar.is_workday(candidate):
            return candidate
        candidate += step

    direction = "forward" if is_start else "backward"
    raise ValueError(
        f"No workday found within 14 days {direction} from {d} "
        f"in calendar {calendar.name!r}. Check calendar configuration."
    )


# ---------------------------------------------------------------------------
# Reverse lookup: workday number → date
# ---------------------------------------------------------------------------

def workday_to_date(
    workday_number: int,
    workday_table: dict[date, int],
) -> date:
    """
    Reverse-lookup: return the calendar date for a given workday number.

    Args:
        workday_number: The 1-based workday number to look up.
        workday_table:  Prebuilt workday table.

    Returns:
        The calendar date corresponding to workday_number.

    Raises:
        ValueError: If workday_number is not present in the table.
    """
    reverse: dict[int, date] = {v: k for k, v in workday_table.items()}
    if workday_number not in reverse:
        raise ValueError(
            f"Workday number {workday_number} not found in table. "
            f"Table covers workdays 1–{max(reverse, default=0)}."
        )
    return reverse[workday_number]


def is_table_coverage_error(exc: BaseException) -> bool:
    """True for any table-COVERAGE failure raised in this module — i.e. a computed
    workday index or date fell OUTSIDE the built table, which growing the window
    fixes. Single source of truth for the three coverage messages raised above:

      * ``workday_to_date``:           "Workday number N not found in table."
      * ``date_to_workday`` (workday):  "Date ... is not in the workday table."
      * ``date_to_workday`` (adjusted): "Adjusted date ... is not in the workday table."

    Deliberately EXCLUDES the misconfigured-calendar error ("No workday found
    within 14 days ... Check calendar configuration") — growing the window cannot
    fix a calendar with no workdays, so that must fail loudly, not loop/retry.

    Used by api.engine_runner.build_resources_with_growth (retry-on-underflow) and
    by destatusing.engine (re-raise so the underflow reaches that backstop instead
    of being masked as a DST_011 rule-application failure)."""
    if not isinstance(exc, ValueError):
        return False
    msg = str(exc)
    return "not found in table" in msg or "not in the workday table" in msg


def find_actuals_in_calendar_nonworking(
    activities: Any,
    registry: Any,
    default_calendar: Calendar,
    *,
    window_days: int = 14,
) -> list[dict]:
    """Disclose (ADR-029 4.7b #22) activities whose ``actual_start`` / ``actual_finish``
    falls INSIDE their assigned calendar's non-working period deeply enough that the
    date cannot snap to a workday within ``window_days`` in the direction the engine
    snaps it (start → forward, finish → backward, matching ``_adjust_nonworkday``).

    This is the data inconsistency behind the "No workday found within N days …
    Check calendar configuration" error: an as-built date recorded on a day the
    activity's OWN calendar marks as non-working — e.g. an actual sitting inside a
    multi-week shutdown. The engine paths degrade gracefully (skip) rather than
    crash, but the analyst must SEE it (it is NOT a parse bug — the calendar is
    correctly parsed; the actual date is genuinely inconsistent with it).

    Pure calendar arithmetic (no workday table). Returns one finding per
    ``(activity, field)``: ``{act_id, field, date, calendar, window_days}``, in
    activity order (deterministic)."""
    findings: list[dict] = []
    for a in activities:
        cal = default_calendar
        cid = getattr(a, "calendar_id", None)
        if registry is not None and cid is not None:
            resolved = registry.get(cid)
            if resolved is not None:
                cal = resolved
        for field, is_start in (("actual_start", True), ("actual_finish", False)):
            d = getattr(a, field, None)
            if d is None or cal.is_workday(d):
                continue
            step = 1 if is_start else -1
            snappable = any(
                cal.is_workday(d + timedelta(days=step * k))
                for k in range(1, window_days + 1)
            )
            if not snappable:
                findings.append({
                    "act_id": getattr(a, "act_id", None),
                    "field": field,
                    "date": d.isoformat(),
                    "calendar": getattr(cal, "name", None),
                    "window_days": window_days,
                })
    return findings
