"""D4 — analysis-window boundary proposal.

Every data date is a candidate boundary.  Consecutive updates are merged
into one window only when the driving-path membership overlap between them
(``analytics.paths.path_stability``'s Jaccard, reused rather than
recomputed) is at least the configured threshold AND neither a
scheduling-settings drift (SET-01) nor a calendar-definition change
(CAL-04) fired between them — i.e. the pair looks like pure progress, not a
revision event that ought to start a new window.  Every boundary records
the driving-path summary at its end and the reason it was kept (either
"merged" with its predecessors, or why the next pair failed to merge),
feeding MIP 3.2-3.4 directly (ANALYTICS_PROPOSAL.md §3.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..analytics.paths import driving_path, path_stability
from ..trend.series import SeriesAnalysis

SETTING_FIELDS = ["retained_logic", "progress_override", "relationship_lag_calendar",
                  "critical_float_threshold_hours", "make_open_ends_critical",
                  "use_expected_finish"]

DEFAULT_OVERLAP_THRESHOLD = 0.9


@dataclass
class WindowBoundary:
    start_dd: Optional[datetime]
    end_dd: Optional[datetime]
    labels: list = field(default_factory=list)
    driving_path_summary: str = ""
    kept_reason: str = ""


@dataclass
class WindowsProposal:
    boundaries: list = field(default_factory=list)     # list[WindowBoundary]
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD
    reason: str = ""


def _settings_drift_fields(cs) -> list:
    es, ls = cs.earlier.settings, cs.later.settings
    return [f for f in SETTING_FIELDS if getattr(es, f) != getattr(ls, f)]


def _driving_summary(schedule, target_code) -> str:
    dp = driving_path(schedule, target_code)
    if not dp.steps:
        return dp.reason or "no driving path recovered"
    head = ", ".join(dp.codes[:5])
    more = f", … (+{len(dp.codes) - 5} more)" if len(dp.codes) > 5 else ""
    tgt = dp.target.code if dp.target else "?"
    return f"{len(dp.steps)} activities to {tgt}: {head}{more}"


def propose_windows(sa: SeriesAnalysis, target_code: Optional[str] = None,
                    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD) -> WindowsProposal:
    scheds = sa.schedules
    wp = WindowsProposal(overlap_threshold=overlap_threshold)
    if len(scheds) < 2:
        wp.reason = "need at least two updates to propose window boundaries"
        return wp

    if target_code is None:
        dp0 = driving_path(scheds[-1])
        target_code = dp0.target.code if dp0.target else None

    stab = path_stability(sa, target_code)          # len == n-1, aligned to sa.changesets
    pair_reasons: list = []
    for i, pair in enumerate(stab):
        cs = sa.changesets[i] if i < len(sa.changesets) else None
        drift = _settings_drift_fields(cs) if cs is not None else []
        cal_changes = len(cs.calendar_def_changes) if cs is not None else 0
        overlap_ok = pair.jaccard is not None and pair.jaccard >= overlap_threshold
        can_merge = overlap_ok and not drift and cal_changes == 0
        why_not = []
        if not overlap_ok:
            ov = "—" if pair.jaccard is None else f"{pair.jaccard:.0%}"
            why_not.append(f"driving-path overlap {ov} < {overlap_threshold:.0%}")
        if drift:
            why_not.append(f"SET-01 scheduling-settings drift ({', '.join(drift)})")
        if cal_changes:
            why_not.append(f"CAL-04 calendar-definition change(s) ({cal_changes})")
        pair_reasons.append((can_merge, "; ".join(why_not)))

    groups = [[0]]
    for i, (can_merge, _why) in enumerate(pair_reasons):
        if can_merge:
            groups[-1].append(i + 1)
        else:
            groups.append([i + 1])

    for g in groups:
        first_s, last_s = scheds[g[0]], scheds[g[-1]]
        reasons = []
        if len(g) > 1:
            merged_labels = ", ".join(scheds[i].label() for i in g)
            reasons.append(f"merged {len(g)} updates ({merged_labels}): driving-path "
                           f"overlap >= {overlap_threshold:.0%} and no SET-01/CAL-04 "
                           "findings between them")
        next_pair_idx = g[-1]
        if next_pair_idx < len(pair_reasons):
            _can, why = pair_reasons[next_pair_idx]
            reasons.append(f"boundary kept at {last_s.label()}: {why}")
        else:
            reasons.append(f"boundary kept at {last_s.label()}: end of series")
        wp.boundaries.append(WindowBoundary(
            start_dd=first_s.data_date, end_dd=last_s.data_date,
            labels=[scheds[i].label() for i in g],
            driving_path_summary=_driving_summary(last_s, target_code),
            kept_reason="; ".join(reasons)))
    return wp
