"""D8 — evergreen-activity detector.

Flags activities whose reported percent complete rose across at least two
consecutive update pairs while the remaining duration FAILED TO KEEP UP with
the claimed progress: rd_last > rd_first x (1 - total pct gain/100) + 8h
tolerance (the inverse of the DUR-04 compression test).  Percent-complete
creep with no commensurate schedule effect is the statused-on-paper work
that poisons EV and progress narratives (ANALYTICS_PROPOSAL.md §3.1).

A forecast finish that fails to move earlier is deliberately NOT a trigger —
a healthy progressing activity's forecast finish normally holds station, so
that condition over-flags (verified on fixtures); it is retained as an
annotation only.  Completed activities are excluded.  Per-activity history is
retained so every flagged activity's trajectory is visible, not just the flag.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..trend.series import SeriesAnalysis

DEFAULT_MIN_CONSECUTIVE_PAIRS = 2
DEFAULT_RD_TOLERANCE_HOURS = 8.0


@dataclass
class EvergreenHistoryPoint:
    label: str
    pct_complete: float
    remaining_duration_hours: float
    forecast_finish: Optional[datetime]


@dataclass
class EvergreenActivity:
    code: str
    name: str
    history: list = field(default_factory=list)     # list[EvergreenHistoryPoint]
    pct_increase_total: float = 0.0
    remaining_duration_change_hours: float = 0.0     # negative = RD fell
    forecast_finish_moved_earlier: bool = False


@dataclass
class EvergreenResult:
    activities: list = field(default_factory=list)   # list[EvergreenActivity]
    reason: str = ""


def _forecast_finish(a):
    return a.early_finish or a.planned_finish


def find_evergreen_activities(sa: SeriesAnalysis,
                              min_consecutive_pairs: int = DEFAULT_MIN_CONSECUTIVE_PAIRS,
                              rd_tolerance_hours: float = DEFAULT_RD_TOLERANCE_HOURS
                              ) -> EvergreenResult:
    result = EvergreenResult()
    scheds = sa.schedules
    if len(scheds) < min_consecutive_pairs + 1:
        result.reason = (f"need at least {min_consecutive_pairs + 1} updates to observe "
                         f"{min_consecutive_pairs} consecutive percent-complete increases")
        return result

    by_code: dict = {}
    for idx, s in enumerate(scheds):
        for a in s.real_activities:
            by_code.setdefault(a.code, {})[idx] = a

    for code, by_idx in by_code.items():
        idxs = sorted(by_idx)
        run = [idxs[0]]
        runs = []
        for i in idxs[1:]:
            prev = run[-1]
            if i == prev + 1 and by_idx[i].pct_complete > by_idx[prev].pct_complete:
                run.append(i)
            else:
                if len(run) >= min_consecutive_pairs + 1:
                    runs.append(run)
                run = [i]
        if len(run) >= min_consecutive_pairs + 1:
            runs.append(run)

        for run in runs:
            first_a, last_a = by_idx[run[0]], by_idx[run[-1]]
            if last_a.completed:
                continue                       # finished work cannot be evergreen
            pct_gain = last_a.pct_complete - first_a.pct_complete
            rd_first = first_a.remaining_duration_hours
            rd_last = last_a.remaining_duration_hours
            rd_decrease = rd_first - rd_last
            # RD failed to keep up with the claimed progress (DUR-04 inverse)
            rd_expected = rd_first * (1 - max(0.0, pct_gain) / 100.0)
            ff_first, ff_last = _forecast_finish(first_a), _forecast_finish(last_a)
            moved_earlier = bool(ff_first and ff_last and ff_last < ff_first)
            if rd_last > rd_expected + rd_tolerance_hours:
                history = [EvergreenHistoryPoint(
                    scheds[i].label(), by_idx[i].pct_complete,
                    by_idx[i].remaining_duration_hours, _forecast_finish(by_idx[i]))
                    for i in run]
                result.activities.append(EvergreenActivity(
                    code=code, name=last_a.name, history=history,
                    pct_increase_total=last_a.pct_complete - first_a.pct_complete,
                    remaining_duration_change_hours=-rd_decrease,
                    forecast_finish_moved_earlier=moved_earlier))

    result.activities.sort(key=lambda e: -e.pct_increase_total)
    return result
