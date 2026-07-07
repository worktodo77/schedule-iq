"""N2 — as-built work-pattern reconstruction (ANALYTICS_PROPOSAL.md §8.2).

Turns the timestamps the schedule files already contain into disruption-grade
OBSERVATIONS: the de facto working calendar implied by the record, weekend/
overtime working, dormant spans on near-critical work, and a work-intensity
heatmap.  Everything here is a reading of the ACTUAL start/finish dates the
tool of record stored — nothing is rescheduled and nothing is forecast, so
there is no CPM engine and no ADR-0007 handshake in play.

Every product is preliminary and reserved to the expert (CLAUDE.md §4):
causation, entitlement, acceleration, and suspension are the expert's to
find.  This module surfaces the pattern and discloses its population sizes and
thresholds; it draws no conclusion.

Products
--------
* ``de_facto_calendars`` / ``wbs_divergence`` — per assigned calendar and per
  top-level WBS node, the distribution of actual starts/finishes by ISO
  weekday, the observed working days (a weekday whose share of events clears
  ``OBSERVED_WEEKDAY_SHARE`` is "observed working"), and the planned-vs-observed
  divergence against the assigned calendar's work days ("assumed 6-day weeks;
  record shows 5").
* ``weekend_events`` — actual events landing on days the ASSIGNED calendar
  calls non-working (weekends/holidays/exceptions), bucketed by update window
  with keys compatible with the §6.3 pacing screen's window labels (no import
  from pacing.py; the labels are reconstructed independently).
* ``dormant_spans`` — in-progress activities on/near the driving path whose
  remaining duration did not fall between two updates and whose WBS siblings
  recorded no actual events in that window: a zero-progress span >= the
  documented threshold.
* ``heatmap`` — per ISO week × top-level WBS node, the count of actual events
  (data only; no figure this wave).

Never raises: a schedule list with no actuals returns an empty analysis
carrying a ``reason``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from ..ingest.model import Activity, Calendar, Schedule
from ..intake._util import working_days_between

LABEL = ("PRELIMINARY — as-built work-pattern reconstruction; observational "
         "only, causation/acceleration/suspension reserved to the expert")

# A weekday counts as an "observed working day" for a group once its share of
# the group's actual events clears this fraction — high enough to ignore a
# stray one-off event, low enough to catch a genuine second/weekend shift.
OBSERVED_WEEKDAY_SHARE = 0.05
# Minimum zero-progress span (working days, measured on the activity's calendar)
# before an in-progress near-critical activity is flagged dormant.
DORMANCY_MIN_WORKING_DAYS = 15.0
# Total float at/below which an activity is treated as on/near the driving path
# when neither a driving-path flag nor a critical flag is stored on the record.
NEAR_CRITICAL_FLOAT_DAYS = 5.0

_ISO_NAME = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class WeekdayProfile:
    """De facto weekday distribution for one calendar or WBS node."""
    scope: str                       # "calendar" | "wbs"
    key: str                         # calendar uid or wbs code
    name: str
    population_events: int
    weekday_counts: dict[int, int]   # ISO weekday -> event count
    observed_working_days: list[int]
    assigned_working_days: list[int]
    assigned_basis: str
    divergence: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "key": self.key,
            "name": self.name,
            "population_events": self.population_events,
            "weekday_counts": {str(k): self.weekday_counts[k]
                               for k in sorted(self.weekday_counts)},
            "observed_working_days": list(self.observed_working_days),
            "assigned_working_days": list(self.assigned_working_days),
            "assigned_basis": self.assigned_basis,
            "divergence": self.divergence,
            "note": self.note,
        }


@dataclass
class WeekendEvent:
    activity_uid: str
    activity_code: str
    wbs_code: str
    calendar_uid: Optional[str]
    calendar_name: str
    event_type: str                  # "start" | "finish"
    event_date: str                  # isoformat
    weekday: int
    schedule_label: str
    window_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_uid": self.activity_uid,
            "activity_code": self.activity_code,
            "wbs_code": self.wbs_code,
            "calendar_uid": self.calendar_uid,
            "calendar_name": self.calendar_name,
            "event_type": self.event_type,
            "event_date": self.event_date,
            "weekday": self.weekday,
            "schedule_label": self.schedule_label,
            "window_key": self.window_key,
        }


@dataclass
class DormantSpan:
    activity_uid: str
    activity_code: str
    wbs_code: str
    window_key: str
    span_start: str                  # isoformat (actual start)
    span_end: str                    # isoformat (later data date)
    working_days: float
    remaining_hours: float
    on_driving_path: bool
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_uid": self.activity_uid,
            "activity_code": self.activity_code,
            "wbs_code": self.wbs_code,
            "window_key": self.window_key,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "working_days": self.working_days,
            "remaining_hours": self.remaining_hours,
            "on_driving_path": self.on_driving_path,
            "basis": self.basis,
        }


@dataclass
class HeatCell:
    iso_week: str                    # "2025-W23"
    wbs_code: str
    event_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"iso_week": self.iso_week, "wbs_code": self.wbs_code,
                "event_count": self.event_count}


@dataclass
class WorkPatternAnalysis:
    label: str
    de_facto_calendars: list[WeekdayProfile]
    wbs_divergence: list[WeekdayProfile]
    weekend_events: list[WeekendEvent]
    weekend_by_window: dict[str, int]
    dormant_spans: list[DormantSpan]
    heatmap: list[HeatCell]
    summary: dict[str, int]
    disclosures: list[str]
    thresholds: dict[str, float]
    reason: str = ""
    pacing_window_note: str = ("weekend/overtime window keys mirror the §6.3 "
                               "pacing screen's '<earlier label> -> <later "
                               "label>' window labels for cross-reference; no "
                               "code is shared between the two screens.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "de_facto_calendars": [p.to_dict() for p in self.de_facto_calendars],
            "wbs_divergence": [p.to_dict() for p in self.wbs_divergence],
            "weekend_events": [e.to_dict() for e in self.weekend_events],
            "weekend_by_window": dict(sorted(self.weekend_by_window.items())),
            "dormant_spans": [d.to_dict() for d in self.dormant_spans],
            "heatmap": [c.to_dict() for c in self.heatmap],
            "summary": dict(self.summary),
            "disclosures": list(self.disclosures),
            "thresholds": dict(self.thresholds),
            "reason": self.reason,
            "pacing_window_note": self.pacing_window_note,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _as_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def _assigned_workdays(cal: Optional[Calendar]) -> set[int]:
    """ISO weekdays the calendar treats as working.  Empty work_patterns is the
    P6 default of Mon-Fri (mirrors ``Calendar.is_workday``)."""
    if cal is None:
        return {1, 2, 3, 4, 5}
    if cal.work_patterns:
        return {wd for wd, p in cal.work_patterns.items() if p.spans}
    return {1, 2, 3, 4, 5}


def _top_wbs(sched: Schedule, wbs_uid: Optional[str]) -> tuple[str, str]:
    """Top-level WBS node (the highest ancestor below the project root) for an
    activity's WBS uid, returned as (code, name).  Falls back to the raw uid."""
    if not wbs_uid or wbs_uid not in sched.wbs:
        return (wbs_uid or "(none)", wbs_uid or "(none)")
    chain = []
    node = sched.wbs.get(wbs_uid)
    seen: set[str] = set()
    while node is not None and node.uid not in seen:
        seen.add(node.uid)
        chain.append(node)
        parent = node.parent_uid
        node = sched.wbs.get(parent) if parent else None
    # chain is [self, ..., root]; the top-level trade is the node just below root
    top = chain[-2] if len(chain) >= 2 else chain[-1]
    return (top.code or top.uid, top.name or top.code or top.uid)


def _observed_days(counts: dict[int, int], total: int) -> list[int]:
    if total <= 0:
        return []
    return sorted(wd for wd, c in counts.items()
                  if c / total >= OBSERVED_WEEKDAY_SHARE)


def _fmt_days(days: set[int] | list[int]) -> str:
    return "-".join(_ISO_NAME[d] for d in sorted(days)) if days else "(none)"


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def reconstruct_work_patterns(schedules: list[Schedule]) -> WorkPatternAnalysis:
    """Reconstruct the de facto working pattern from a schedule series.

    ``schedules`` may be a single file or the whole update series; they are
    ordered by data date internally.  See the module docstring for the four
    products.  Never raises.
    """
    thresholds = {
        "observed_weekday_share": OBSERVED_WEEKDAY_SHARE,
        "dormancy_min_working_days": DORMANCY_MIN_WORKING_DAYS,
        "near_critical_float_days": NEAR_CRITICAL_FLOAT_DAYS,
    }
    ordered = sorted(schedules, key=lambda s: (s.data_date or s.export_date
                                               or datetime.max))
    if not ordered:
        return WorkPatternAnalysis(
            LABEL, [], [], [], {}, [], [],
            {"schedules": 0, "actual_events": 0, "activities_with_actuals": 0},
            ["no schedules supplied"], thresholds,
            reason="no schedules supplied")

    # -- window keys (compatible with the pacing screen's labels) -------------
    windows: list[tuple[Optional[datetime], Optional[datetime], str]] = []
    for i in range(1, len(ordered)):
        e, l = ordered[i - 1], ordered[i]
        windows.append((e.data_date, l.data_date, f"{e.label()} -> {l.label()}"))

    def _window_for(d: date) -> str:
        for e_dd, l_dd, key in windows:
            if e_dd and l_dd and e_dd.date() < d <= l_dd.date():
                return key
        return "outside update windows"

    # -- collect actual events, deduped by (uid, type, date) across the series
    # (the same actual reported in two updates counts once; the first-seen
    # schedule anchors its window/label).
    seen_ev: set[tuple[str, str, date]] = set()
    events: list[dict] = []
    activities_with_actuals: set[str] = set()
    for sched in ordered:
        for a in sched.real_activities:
            for typ, dt_val in (("start", a.actual_start), ("finish", a.actual_finish)):
                d = _as_date(dt_val)
                if d is None:
                    continue
                activities_with_actuals.add(a.code)
                sig = (a.code, typ, d)
                if sig in seen_ev:
                    continue
                seen_ev.add(sig)
                cal = sched.cal_for(a)
                top_code, _top_name = _top_wbs(sched, a.wbs_uid)
                events.append({
                    "uid": a.uid, "code": a.code, "type": typ, "date": d,
                    "weekday": d.isoweekday(), "wbs": top_code,
                    "cal_uid": a.calendar_uid, "cal": cal,
                    "cal_name": cal.name if cal else "",
                    "schedule": sched,
                })

    if not events:
        return WorkPatternAnalysis(
            LABEL, [], [], [], {}, [], [],
            {"schedules": len(ordered), "actual_events": 0,
             "activities_with_actuals": 0},
            ["schedule series carries no actual dates on real activities"],
            thresholds, reason="no actual dates to reconstruct a work pattern")

    # -- de facto calendars ---------------------------------------------------
    by_cal: dict[Optional[str], dict] = {}
    for ev in events:
        b = by_cal.setdefault(ev["cal_uid"], {"counts": {}, "cal": ev["cal"],
                                              "name": ev["cal_name"]})
        b["counts"][ev["weekday"]] = b["counts"].get(ev["weekday"], 0) + 1
    de_facto: list[WeekdayProfile] = []
    for cal_uid in sorted(by_cal, key=lambda k: (k is None, k or "")):
        b = by_cal[cal_uid]
        total = sum(b["counts"].values())
        observed = _observed_days(b["counts"], total)
        assigned = sorted(_assigned_workdays(b["cal"]))
        div = set(observed) != set(assigned)
        note = (f"assigned {_fmt_days(assigned)} ({len(assigned)}-day); "
                f"record shows {_fmt_days(observed)} ({len(observed)}-day)")
        de_facto.append(WeekdayProfile(
            "calendar", cal_uid or "(none)", b["name"] or (cal_uid or "(none)"),
            total, dict(b["counts"]), observed, assigned,
            "assigned calendar work_patterns", div, note))

    # -- per-WBS divergence ---------------------------------------------------
    by_wbs: dict[str, dict] = {}
    for ev in events:
        b = by_wbs.setdefault(ev["wbs"], {"counts": {}, "cal_counts": {}})
        b["counts"][ev["weekday"]] = b["counts"].get(ev["weekday"], 0) + 1
        if ev["cal"] is not None:
            b["cal_counts"][ev["cal_uid"]] = b["cal_counts"].get(ev["cal_uid"], 0) + 1
    wbs_div: list[WeekdayProfile] = []
    cal_by_uid = {}
    for ev in events:
        if ev["cal_uid"] is not None and ev["cal"] is not None:
            cal_by_uid[ev["cal_uid"]] = (ev["cal"], ev["cal_name"])
    for wbs_code in sorted(by_wbs):
        b = by_wbs[wbs_code]
        total = sum(b["counts"].values())
        observed = _observed_days(b["counts"], total)
        # assigned = the dominant calendar among this node's actualized work
        dom_cal_uid = None
        if b["cal_counts"]:
            dom_cal_uid = max(sorted(b["cal_counts"]),
                              key=lambda k: b["cal_counts"][k])
        dom_cal = cal_by_uid.get(dom_cal_uid, (None, ""))[0] if dom_cal_uid else None
        dom_name = cal_by_uid.get(dom_cal_uid, (None, ""))[1] if dom_cal_uid else ""
        assigned = sorted(_assigned_workdays(dom_cal))
        div = set(observed) != set(assigned)
        note = (f"assigned {_fmt_days(assigned)} (dominant calendar "
                f"{dom_name or dom_cal_uid or 'default Mon-Fri'}); "
                f"record shows {_fmt_days(observed)}")
        wbs_div.append(WeekdayProfile(
            "wbs", wbs_code, wbs_code, total, dict(b["counts"]), observed,
            assigned, f"dominant assigned calendar for WBS {wbs_code}", div, note))

    # -- weekend / non-working events -----------------------------------------
    weekend: list[WeekendEvent] = []
    weekend_by_window: dict[str, int] = {}
    for ev in sorted(events, key=lambda e: (e["date"], e["code"], e["type"])):
        cal = ev["cal"]
        d = ev["date"]
        nonwork = (not cal.is_workday(d)) if cal is not None else (d.isoweekday() > 5)
        if not nonwork:
            continue
        wkey = _window_for(d)
        weekend.append(WeekendEvent(
            ev["uid"], ev["code"], ev["wbs"], ev["cal_uid"], ev["cal_name"],
            ev["type"], d.isoformat(), ev["weekday"], ev["schedule"].label(), wkey))
        weekend_by_window[wkey] = weekend_by_window.get(wkey, 0) + 1

    # -- dormancy (needs consecutive updates) ---------------------------------
    dormant: list[DormantSpan] = []
    for i in range(1, len(ordered)):
        e, l = ordered[i - 1], ordered[i]
        if not (e.data_date and l.data_date):
            continue
        wkey = f"{e.label()} -> {l.label()}"
        e_by_code = {a.code: a for a in e.real_activities}
        # actual events (start/finish) recorded per WBS node inside this window
        events_by_wbs: dict[str, int] = {}
        for a in l.real_activities:
            top_code, _n = _top_wbs(l, a.wbs_uid)
            for dv in (a.actual_start, a.actual_finish):
                d = _as_date(dv)
                if d and e.data_date.date() < d <= l.data_date.date():
                    events_by_wbs[top_code] = events_by_wbs.get(top_code, 0) + 1
        for a in l.real_activities:
            if not a.in_progress or a.actual_start is None or a.actual_finish is not None:
                continue
            prior = e_by_code.get(a.code)
            if prior is None or not prior.in_progress:
                continue
            # no remaining-duration decrease over the window
            if a.remaining_duration_hours < prior.remaining_duration_hours - 1e-6:
                continue
            on_dp, basis = _on_driving_path(a, l)
            if not on_dp:
                continue
            top_code, _n = _top_wbs(l, a.wbs_uid)
            if events_by_wbs.get(top_code, 0) > 0:
                continue                      # WBS siblings progressed -> not dormant
            cal = l.cal_for(a)
            wd = working_days_between(cal, a.actual_start, l.data_date)
            if wd is None or wd < DORMANCY_MIN_WORKING_DAYS:
                continue
            dormant.append(DormantSpan(
                a.uid, a.code, top_code, wkey,
                _as_date(a.actual_start).isoformat(),
                _as_date(l.data_date).isoformat(), float(wd),
                a.remaining_duration_hours, on_dp, basis))

    # -- work-intensity heatmap ----------------------------------------------
    heat: dict[tuple[str, str], int] = {}
    for ev in events:
        iso_y, iso_w, _ = ev["date"].isocalendar()
        wk = f"{iso_y:04d}-W{iso_w:02d}"
        heat[(wk, ev["wbs"])] = heat.get((wk, ev["wbs"]), 0) + 1
    heatmap = [HeatCell(wk, wbs, n)
               for (wk, wbs), n in sorted(heat.items())]

    disclosures = [
        f"population: {len(events)} actual events on "
        f"{len(activities_with_actuals)} real activities across "
        f"{len(ordered)} update(s); events deduplicated by "
        "(activity, start/finish, date) across the series.",
        f"a weekday is reported as an observed working day once its share of "
        f"a group's events reaches {OBSERVED_WEEKDAY_SHARE:.0%}.",
        f"dormancy threshold: {DORMANCY_MIN_WORKING_DAYS:g} working days of "
        "zero progress (no RD decrease and no WBS-sibling actual events).",
    ]
    if len(ordered) < 2:
        disclosures.append("single schedule supplied: dormancy detection needs "
                           "a series and was skipped.")

    summary = {
        "schedules": len(ordered),
        "actual_events": len(events),
        "activities_with_actuals": len(activities_with_actuals),
        "weekend_events": len(weekend),
        "dormant_spans": len(dormant),
        "calendars_divergent": sum(1 for p in de_facto if p.divergence),
        "wbs_nodes_divergent": sum(1 for p in wbs_div if p.divergence),
    }

    return WorkPatternAnalysis(
        LABEL, de_facto, wbs_div, weekend, weekend_by_window, dormant, heatmap,
        summary, disclosures, thresholds)


def _on_driving_path(a: Activity, sched: Schedule) -> tuple[bool, str]:
    """Reuse the record's own criticality markers — a driving-path flag, a
    stored critical flag, or total float at/below the near-critical threshold.
    No CPM engine is run."""
    if a.is_longest_path:
        return True, "driving-path flag (record)"
    if a.is_critical_flag:
        return True, "critical flag (record)"
    tf = a.total_float_days(sched.cal_for(a))
    if tf is not None and tf <= NEAR_CRITICAL_FLOAT_DAYS:
        return True, f"total float {tf:g}d <= {NEAR_CRITICAL_FLOAT_DAYS:g}d (record)"
    return False, ""
