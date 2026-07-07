"""D6 — delay-event mapper.

Reads a CSV of candidate delay events (event_id, title, start, finish,
keywords, responsibility; ISO dates) and maps each to schedule activities by
(i) date overlap with the activity's actual/planned window in the update
whose reporting period contains the event, and (ii) keyword match against
the activity or its WBS name (case-insensitive, any keyword).  The output is
a candidate list — fragnet insertion-point candidates for TIA work
(ANALYTICS_PROPOSAL.md §3.1, MIP 3.6/3.7) — never a finding.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..trend.series import SeriesAnalysis


@dataclass
class EventMatch:
    activity_code: str
    activity_name: str
    reasons: list = field(default_factory=list)


@dataclass
class EventMapping:
    event_id: str
    title: str
    start: Optional[datetime]
    finish: Optional[datetime]
    keywords: list = field(default_factory=list)
    responsibility: str = ""
    schedule_label: str = ""
    matches: list = field(default_factory=list)      # list[EventMatch]
    reason: str = ""


@dataclass
class EventMapResult:
    events: list = field(default_factory=list)        # list[EventMapping]
    reason: str = ""


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def load_events_csv(path: str) -> list:
    """Parse the events CSV into plain dicts (keywords semicolon-separated)."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append({
                "event_id": (row.get("event_id") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "start": _parse_date(row.get("start")),
                "finish": _parse_date(row.get("finish")),
                "keywords": [k.strip() for k in (row.get("keywords") or "").split(";")
                            if k.strip()],
                "responsibility": (row.get("responsibility") or "").strip(),
            })
    return rows


def _select_schedule(scheds, start, finish):
    """The update whose reporting period contains the event: the first
    schedule with a data date on/after the event's finish (that update
    carries the actual/forecast dates for the period the event fell in);
    falls back to the last schedule if the event runs past every data date."""
    if not scheds:
        return None
    ref = finish or start
    if ref is None:
        return scheds[-1]
    for s in scheds:
        if s.data_date and s.data_date >= ref:
            return s
    return scheds[-1]


def _activity_window(a):
    starts = [d for d in (a.actual_start, a.planned_start, a.early_start) if d]
    finishes = [d for d in (a.actual_finish, a.planned_finish, a.early_finish) if d]
    s = min(starts) if starts else None
    f = max(finishes) if finishes else None
    return s, f


def map_events(sa: SeriesAnalysis, events_csv: Optional[str]) -> EventMapResult:
    result = EventMapResult()
    if not events_csv:
        result.reason = "no events CSV provided"
        return result
    if not sa.schedules:
        result.reason = "no schedules to map events against"
        return result
    try:
        raw_events = load_events_csv(events_csv)
    except OSError as e:
        result.reason = f"could not read events CSV: {e}"
        return result

    for ev in raw_events:
        mapping = EventMapping(event_id=ev["event_id"], title=ev["title"],
                               start=ev["start"], finish=ev["finish"],
                               keywords=ev["keywords"], responsibility=ev["responsibility"])
        s = _select_schedule(sa.schedules, ev["start"], ev["finish"])
        if s is None:
            mapping.reason = "no schedule available to map against"
            result.events.append(mapping)
            continue
        mapping.schedule_label = s.label()
        for a in s.real_activities:
            reasons = []
            a_start, a_finish = _activity_window(a)
            if (ev["start"] and ev["finish"] and a_start and a_finish
                    and a_start <= ev["finish"] and ev["start"] <= a_finish):
                reasons.append("date overlap")
            wbs = s.wbs.get(a.wbs_uid)
            haystack = f"{a.name} {wbs.name if wbs else ''}".lower()
            hit_kw = [k for k in ev["keywords"] if k.lower() in haystack]
            if hit_kw:
                reasons.append(f"keyword match: {', '.join(hit_kw)}")
            if reasons:
                mapping.matches.append(EventMatch(a.code, a.name, reasons))
        result.events.append(mapping)
    return result
