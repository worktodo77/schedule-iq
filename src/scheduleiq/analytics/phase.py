"""Phase Analyzer — time-phased slicing within one schedule (Fuse parity
backlog F2; docs/FUSE_PARITY.md "Phase Analyzer (time-phased slicing)").

Fuse purpose
------------
Where series trending (``trend.series``) covers the time dimension *across*
updates, the Phase Analyzer slices a *single* schedule's activities into
calendar buckets to answer "when in time do the problems cluster?" — e.g.
logic defects concentrated in the closeout phase, or a wall of near-critical
work stacking up in one quarter.  It reuses the existing per-activity
offender lists a ``ScheduleAssessment`` already carries
(``metrics.engine.Finding.object_id``), exactly as ``analytics.ribbon`` does
for WBS — this module's kinship is ``intake.windows``' boundary logic, but
sliced by calendar date within one file rather than by data-date across
files.

Basis (documented convention)
------------------------------
Bucket membership uses ``Activity.start``/``Activity.finish`` — actual date
if present, else early/current, else planned (``ingest.model.Activity``) —
the same controlling-date convention ``analytics.paths`` uses for driving-
path walks.  An activity occupies every bucket its ``[start, finish]`` span
overlaps (half-open buckets ``[bucket_start, bucket_end)``); an activity with
neither bound resolvable is excluded and counted in ``unbucketed_activities``
(never silently dropped).  Default range is the project's
``start_date .. finish_date``; ``start``/``end`` override it.  Only
``bucket="month"`` (calendar months) and ``bucket="week"`` (7-day spans
anchored at the range start, not calendar weeks) are supported.

Finding resolution and exclusion follow ``analytics.ribbon`` exactly: a
``Finding.object_id`` must equal a real activity's ``code`` to localize;
relationship- and file-level-keyed checks never do, and are named in
``excluded_checks`` when they carry >= 1 finding anywhere but none resolve.
Series-level checks (``applies_to == "series"``) are excluded outright.

Near-critical and constraint counts are computed over the bucket's
*incomplete* population (mirrors ``metrics.checks.core``'s FLT-*/CON-*
population convention: completed activities carry stale or absent float).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ..ingest.model import ConstraintType, Schedule
from ..metrics.engine import ScheduleAssessment

NEAR_CRITICAL_FLOAT_DAYS = 10.0
SUPPORTED_BUCKETS = ("month", "week")

LABEL = ("PRELIMINARY — Phase Analyzer buckets the assessment's existing "
        "offender findings and float/constraint counts by calendar time; it "
        "shows where in time problems cluster, not an opinion on any "
        "period's risk.")


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class PhaseRow:
    bucket_label: str
    bucket_start: datetime
    bucket_end: datetime
    starting_count: int = 0
    finishing_count: int = 0
    active_count: int = 0
    remaining_hours: float = 0.0
    check_offenders: dict[str, int] = field(default_factory=dict)
    density: float = 0.0
    near_critical_count: int = 0
    near_critical_share: float = 0.0
    constraint_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_label": self.bucket_label,
            "bucket_start": self.bucket_start.isoformat(),
            "bucket_end": self.bucket_end.isoformat(),
            "starting_count": self.starting_count,
            "finishing_count": self.finishing_count,
            "active_count": self.active_count,
            "remaining_hours": round(self.remaining_hours, 2),
            "check_offenders": dict(sorted(self.check_offenders.items())),
            "density": round(self.density, 4),
            "near_critical_count": self.near_critical_count,
            "near_critical_share": round(self.near_critical_share, 4),
            "constraint_count": self.constraint_count,
        }


@dataclass
class PhaseAnalysis:
    bucket: str = "month"
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    rows: list[PhaseRow] = field(default_factory=list)
    excluded_checks: list[str] = field(default_factory=list)
    excluded_reason: dict[str, str] = field(default_factory=dict)
    unbucketed_activities: int = 0
    basis: str = ("Activity.start/.finish — actual date if present, else "
                  "early/current, else planned")
    reason: str = ""
    label: str = LABEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "rows": [r.to_dict() for r in self.rows],
            "excluded_checks": list(self.excluded_checks),
            "excluded_reason": dict(sorted(self.excluded_reason.items())),
            "unbucketed_activities": self.unbucketed_activities,
            "basis": self.basis,
            "reason": self.reason,
            "label": self.label,
        }


# --------------------------------------------------------------------------
# bucket boundary generation
# --------------------------------------------------------------------------
def _month_start(d: datetime) -> datetime:
    return datetime(d.year, d.month, 1)


def _add_month(d: datetime) -> datetime:
    return datetime(d.year + 1, 1, 1) if d.month == 12 else datetime(d.year, d.month + 1, 1)


def _generate_buckets(bucket: str, start: datetime,
                      end: datetime) -> list[tuple[str, datetime, datetime]]:
    out: list[tuple[str, datetime, datetime]] = []
    if bucket == "month":
        cur = _month_start(start)
        end_floor = end if end >= cur else cur
        while cur <= end_floor:
            nxt = _add_month(cur)
            out.append((f"{cur.year:04d}-{cur.month:02d}", cur, nxt))
            cur = nxt
    elif bucket == "week":
        cur = start
        idx = 1
        while cur <= end:
            nxt = cur + timedelta(days=7)
            out.append((f"W{idx:03d} {cur:%Y-%m-%d}", cur, nxt))
            cur = nxt
            idx += 1
    return out


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def phase_analysis(sched: Schedule, assessment: ScheduleAssessment, *,
                   bucket: str = "month", start: Optional[datetime] = None,
                   end: Optional[datetime] = None) -> PhaseAnalysis:
    pa = PhaseAnalysis(bucket=bucket, start=start, end=end)
    pop = sched.real_activities
    if not pop:
        pa.reason = "no real activities to phase-slice"
        return pa
    if bucket not in SUPPORTED_BUCKETS:
        pa.reason = f"unsupported bucket {bucket!r}; use one of {SUPPORTED_BUCKETS}"
        return pa

    spans: dict[str, tuple[datetime, datetime]] = {}
    for a in pop:
        s, f = a.start, a.finish
        if s is None and f is None:
            continue
        if s is None:
            s = f
        if f is None:
            f = s
        if f < s:
            f = s
        spans[a.code] = (s, f)
    pa.unbucketed_activities = len(pop) - len(spans)

    range_start = start or sched.start_date or (min(s for s, _ in spans.values())
                                                if spans else None)
    range_end = end or sched.finish_date or (max(f for _, f in spans.values())
                                             if spans else None)
    if range_start is None or range_end is None:
        pa.reason = "no resolvable date range (no project dates and no activity dates)"
        return pa
    if range_end < range_start:
        range_start, range_end = range_end, range_start
    pa.start, pa.end = range_start, range_end

    buckets = _generate_buckets(bucket, range_start, range_end)
    if not buckets:
        pa.reason = "date range produced no buckets"
        return pa

    by_code = {a.code: a for a in pop}
    code_to_act = {a.code: a for a in sched.activities.values()}

    # -- membership: activity code -> set of bucket indices it occupies -----
    bucket_members: list[set[str]] = [set() for _ in buckets]
    activity_buckets: dict[str, list[int]] = {}
    for code, (s, f) in spans.items():
        occ = [i for i, (_lbl, b0, b1) in enumerate(buckets) if s < b1 and f >= b0]
        if occ:
            activity_buckets[code] = occ
            for i in occ:
                bucket_members[i].add(code)

    # -- finding resolution (mirrors analytics.ribbon) -----------------------
    check_defs = {}
    # bucket idx -> check_id -> set(codes)
    offenders: list[dict[str, set[str]]] = [dict() for _ in buckets]
    global_resolved: dict[str, set[str]] = {}
    any_finding: dict[str, bool] = {}

    for mr in assessment.results:
        cd = mr.check
        if cd.applies_to == "series":
            continue
        check_defs[cd.id] = cd
        if mr.findings:
            any_finding[cd.id] = True
        for f in mr.findings:
            if f.object_id not in code_to_act:
                continue
            code = f.object_id
            occ = activity_buckets.get(code)
            if not occ:
                continue
            global_resolved.setdefault(cd.id, set()).add(code)
            for i in occ:
                offenders[i].setdefault(cd.id, set()).add(code)

    included_checks = {cid: cd for cid, cd in check_defs.items()
                       if cid in global_resolved or cid not in any_finding}
    for cid in check_defs:
        if cid not in included_checks:
            pa.excluded_checks.append(cid)
            pa.excluded_reason[cid] = ("findings do not resolve to individual "
                                       "activity codes (file-level or "
                                       "relationship-keyed check)")
    pa.excluded_checks.sort()

    # -- per-bucket rows ------------------------------------------------------
    rows = []
    for i, (label, b0, b1) in enumerate(buckets):
        members = bucket_members[i]
        active_count = len(members)
        starting = sum(1 for c in members if b0 <= spans[c][0] < b1)
        finishing = sum(1 for c in members if b0 <= spans[c][1] < b1)
        remaining_hours = sum(by_code[c].remaining_duration_hours for c in members
                              if not by_code[c].completed)

        near_critical = 0
        constraint_n = 0
        for c in members:
            act = by_code[c]
            if act.completed:
                continue
            if act.total_float_hours is not None:
                cal = sched.cal_for(act)
                hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
                if act.total_float_hours / hpd <= NEAR_CRITICAL_FLOAT_DAYS:
                    near_critical += 1
            if act.constraint != ConstraintType.NONE or act.constraint2 != ConstraintType.NONE:
                constraint_n += 1

        check_offenders = {cid: len(offenders[i].get(cid, ())) for cid in included_checks}
        total_offenders = sum(check_offenders.values())
        density = total_offenders / active_count if active_count else 0.0
        near_share = near_critical / active_count if active_count else 0.0

        rows.append(PhaseRow(
            bucket_label=label, bucket_start=b0, bucket_end=b1,
            starting_count=starting, finishing_count=finishing,
            active_count=active_count, remaining_hours=remaining_hours,
            check_offenders=check_offenders, density=density,
            near_critical_count=near_critical, near_critical_share=near_share,
            constraint_count=constraint_n))

    pa.rows = rows
    return pa
