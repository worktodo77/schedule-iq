"""D2 — as-planned vs as-built variance register.

Per activity present in both the first (baseline) and last file of the
series: baseline vs actual/forecast start and finish, the working-day
variance on the activity's own (latest) calendar, duration growth, and
driving-path membership on the latest schedule (via ``analytics.paths``,
never recomputed here).  Sorted by absolute finish variance descending —
the raw material every delay-analysis method starts from
(ANALYTICS_PROPOSAL.md §3.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..analytics.paths import driving_path
from ..trend.series import SeriesAnalysis
from ._util import working_days_between


@dataclass
class VarianceRow:
    code: str
    name: str
    baseline_start: Optional[datetime]
    baseline_finish: Optional[datetime]
    current_start: Optional[datetime]
    current_finish: Optional[datetime]
    start_variance_days: Optional[float]
    finish_variance_days: Optional[float]
    baseline_duration_days: Optional[float]
    current_duration_days: Optional[float]
    duration_growth_days: Optional[float]
    on_driving_path: bool


@dataclass
class VarianceRegister:
    baseline_label: str = ""
    current_label: str = ""
    rows: list = field(default_factory=list)      # list[VarianceRow]
    reason: str = ""


def build_variance_register(sa: SeriesAnalysis) -> VarianceRegister:
    scheds = sa.schedules
    vr = VarianceRegister()
    if len(scheds) < 2:
        vr.reason = "need at least a baseline and one later update to compute variance"
        return vr

    baseline, current = scheds[0], scheds[-1]
    vr.baseline_label, vr.current_label = baseline.label(), current.label()

    b_by_code = {a.code: a for a in baseline.activities.values()}
    c_by_code = {a.code: a for a in current.activities.values()}
    common = sorted(set(b_by_code) & set(c_by_code))
    if not common:
        vr.reason = "no activity codes are common to the baseline and the latest update"
        return vr

    dp = driving_path(current)
    driving_codes = set(dp.codes)

    rows: list = []
    for code in common:
        ba, ca = b_by_code[code], c_by_code[code]
        if ba.is_loe_or_summary or ca.is_loe_or_summary:
            continue
        b_start, b_finish = ba.start, ba.finish            # actual wins, else early, else plan
        c_start, c_finish = ca.start, ca.finish
        cal = current.cal_for(ca)
        sv = working_days_between(cal, b_start, c_start)
        fv = working_days_between(cal, b_finish, c_finish)

        b_cal = baseline.cal_for(ba)
        b_dur = ba.duration_days(b_cal)
        c_dur_hours = (ca.at_completion_duration_hours
                      if ca.at_completion_duration_hours is not None
                      else ca.original_duration_hours)
        hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
        c_dur = c_dur_hours / hpd if hpd else None
        growth = (c_dur - b_dur) if (b_dur is not None and c_dur is not None) else None

        rows.append(VarianceRow(
            code=code, name=ca.name or ba.name,
            baseline_start=b_start, baseline_finish=b_finish,
            current_start=c_start, current_finish=c_finish,
            start_variance_days=sv, finish_variance_days=fv,
            baseline_duration_days=b_dur, current_duration_days=c_dur,
            duration_growth_days=growth, on_driving_path=code in driving_codes))

    # sort by |finish variance| descending; rows with no computable variance last
    rows.sort(key=lambda r: (r.finish_variance_days is None,
                             -abs(r.finish_variance_days) if r.finish_variance_days is not None
                             else 0.0))
    vr.rows = rows
    return vr
