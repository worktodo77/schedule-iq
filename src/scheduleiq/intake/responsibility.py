"""D7 — responsibility overlay.

An analyst-supplied CSV (pattern, scope [wbs|activity], party
[Owner|Contractor|Neutral|TBD]) tags WBS nodes or activity-code/name
patterns (``fnmatch``) to a responsible party.  ``tag_schedule`` returns the
per-activity tagging; every window's float erosion and variance can then be
aggregated by party.  This is data aggregation only — the entitlement
opinion stays with the expert (CLAUDE.md rule 4), and every output of this
module carries the caption below.
"""
from __future__ import annotations

import csv
import fnmatch
from dataclasses import dataclass, field
from typing import Optional

from ..ingest.model import Schedule
from ..trend.series import SeriesAnalysis

CAPTION = "responsibility aggregation only — entitlement reserved to the expert"
DEFAULT_PARTY = "TBD"


@dataclass
class ResponsibilityRule:
    pattern: str
    scope: str            # wbs | activity
    party: str


@dataclass
class ActivityTag:
    code: str
    name: str
    wbs: str
    party: str


@dataclass
class PartyWindowAggregate:
    window_label: str
    party: str
    n_activities: int
    total_float_delta_days: float
    mean_float_delta_days: float


@dataclass
class ResponsibilityResult:
    rules: list = field(default_factory=list)              # list[ResponsibilityRule]
    tags_by_code: dict = field(default_factory=dict)        # latest schedule: code -> party
    by_activity: list = field(default_factory=list)         # list[ActivityTag]
    aggregates: list = field(default_factory=list)          # list[PartyWindowAggregate]
    caption: str = CAPTION
    reason: str = ""


def load_responsibility_csv(path: str) -> list:
    rules = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pattern = (row.get("pattern") or "").strip()
            scope = (row.get("scope") or "").strip().lower()
            party = (row.get("party") or "").strip() or DEFAULT_PARTY
            if pattern and scope in ("wbs", "activity"):
                rules.append(ResponsibilityRule(pattern, scope, party))
    return rules


def _party_for(schedule: Schedule, a, rules: list) -> str:
    wbs = schedule.wbs.get(a.wbs_uid)
    wbs_code = wbs.code if wbs else ""
    wbs_name = wbs.name if wbs else ""
    for r in rules:
        if r.scope == "activity" and (fnmatch.fnmatch(a.code, r.pattern)
                                      or fnmatch.fnmatch(a.name, r.pattern)):
            return r.party
        if r.scope == "wbs" and (fnmatch.fnmatch(wbs_code, r.pattern)
                                 or fnmatch.fnmatch(wbs_name, r.pattern)):
            return r.party
    return DEFAULT_PARTY


def tag_schedule(schedule: Schedule, rules: list) -> dict:
    """uid -> party for every activity in ``schedule``."""
    return {a.uid: _party_for(schedule, a, rules) for a in schedule.activities.values()}


def _tag_by_code(schedule: Schedule, rules: list) -> dict:
    return {a.code: _party_for(schedule, a, rules) for a in schedule.activities.values()}


def run_responsibility(sa: SeriesAnalysis,
                       responsibility_csv: Optional[str]) -> ResponsibilityResult:
    result = ResponsibilityResult()
    if not responsibility_csv:
        result.reason = "no responsibility mapping CSV provided"
        return result
    if not sa.schedules:
        result.reason = "no schedules to tag"
        return result
    try:
        rules = load_responsibility_csv(responsibility_csv)
    except OSError as e:
        result.reason = f"could not read responsibility CSV: {e}"
        return result
    result.rules = rules

    latest = sa.schedules[-1]
    result.tags_by_code = _tag_by_code(latest, rules)
    for a in latest.real_activities:
        wbs = latest.wbs.get(a.wbs_uid)
        result.by_activity.append(ActivityTag(
            code=a.code, name=a.name, wbs=(wbs.code or wbs.name) if wbs else "—",
            party=result.tags_by_code.get(a.code, DEFAULT_PARTY)))

    for cs in sa.changesets:
        tags = _tag_by_code(cs.later, rules)
        buckets: dict = {}
        for code, delta in cs.float_deltas.items():
            party = tags.get(code, DEFAULT_PARTY)
            buckets.setdefault(party, []).append(delta)
        label = f"{cs.earlier.label()} -> {cs.later.label()}"
        for party, vals in sorted(buckets.items()):
            result.aggregates.append(PartyWindowAggregate(
                label, party, len(vals), sum(vals), sum(vals) / len(vals)))
    return result
