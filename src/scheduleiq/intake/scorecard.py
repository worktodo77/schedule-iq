"""D1 — data-completeness scorecard and client RFI-list generator.

Every engagement starts by asking "what do we have, and what should we ask
the client for?" (ANALYTICS_PROPOSAL.md §3.1).  This module answers both
from the files themselves: update cadence and gaps against the dominant
cadence, missing months, whether the earliest file is a clean native
baseline (predates progress) or already-progressed, source-format mix,
per-file SCHEDOPTIONS presence, and resource/cost loading completeness —
then drafts the document-request ("RFI") lines an analyst would otherwise
write by hand.  Purely descriptive: no conclusion about the schedule's
quality is drawn here, only about what data is (or is not) present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..ingest.model import Schedule
from ..trend.series import SeriesAnalysis
from ._util import cadence_label, format_month_range, months_between

RESOURCE_LOADING_MIN_PCT = 50.0
COST_LOADING_MIN_PCT = 50.0
GAP_MULTIPLE = 1.5     # a gap this many times the dominant cadence gets flagged


@dataclass
class RfiItem:
    topic: str
    text: str


@dataclass
class GapInfo:
    from_label: str
    to_label: str
    from_date: Optional[datetime]
    to_date: Optional[datetime]
    days: float
    expected_days: Optional[float]
    missing_months: list = field(default_factory=list)


@dataclass
class FileCompletenessInfo:
    file: str
    label: str
    format: str
    has_schedoptions: bool
    pct_resourced: float
    pct_cost_loaded: float


@dataclass
class ScorecardResult:
    n_files: int = 0
    date_range: tuple = (None, None)
    intervals_days: list = field(default_factory=list)
    dominant_cadence_days: Optional[float] = None
    cadence_label: str = ""
    gaps: list = field(default_factory=list)             # list[GapInfo]
    missing_months: list = field(default_factory=list)   # list[str] "YYYY-MM"
    baseline_file: Optional[str] = None
    baseline_has_progress: Optional[bool] = None
    format_mix: dict = field(default_factory=dict)
    files: list = field(default_factory=list)             # list[FileCompletenessInfo]
    rfi_items: list = field(default_factory=list)         # list[RfiItem]
    reason: str = ""


def _dominant_interval(intervals: list) -> Optional[float]:
    if not intervals:
        return None
    s = sorted(intervals)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _has_progress(s: Schedule) -> bool:
    for a in s.real_activities:
        if a.actual_start is not None or a.pct_complete > 0 or a.completed or a.in_progress:
            return True
    return False


def _has_schedoptions(s: Schedule) -> bool:
    st = s.settings
    if st.raw:
        return True
    fields = (st.retained_logic, st.progress_override, st.actual_dates,
              st.relationship_lag_calendar, st.critical_float_threshold_hours,
              st.critical_definition, st.make_open_ends_critical, st.use_expected_finish)
    return any(f is not None for f in fields)


def _loading_pct(s: Schedule) -> tuple:
    real = s.real_activities
    if not real:
        return 0.0, 0.0
    resourced = sum(1 for a in real if a.resources)
    costed = sum(1 for a in real if a.budget_cost or a.actual_cost or a.remaining_cost
                 or any(r.budget_cost or r.actual_cost for r in a.resources))
    return 100.0 * resourced / len(real), 100.0 * costed / len(real)


def build_scorecard(sa: SeriesAnalysis) -> ScorecardResult:
    """Build the completeness scorecard (and RFI list) for a parsed series."""
    scheds = sa.schedules
    sc = ScorecardResult(n_files=len(scheds))
    if not scheds:
        sc.reason = "no schedule files were provided"
        return sc

    ordered = sorted(scheds, key=lambda s: (s.data_date or s.export_date
                                            or s.start_date or datetime.min))
    dds = [s.data_date for s in ordered if s.data_date]
    sc.date_range = (min(dds), max(dds)) if dds else (None, None)

    intervals = []
    for i in range(1, len(ordered)):
        a, b = ordered[i - 1].data_date, ordered[i].data_date
        if a and b:
            intervals.append((b - a).days)
    sc.intervals_days = intervals
    sc.dominant_cadence_days = _dominant_interval(intervals)
    sc.cadence_label = cadence_label(sc.dominant_cadence_days)

    if sc.dominant_cadence_days and sc.dominant_cadence_days > 0:
        for i in range(1, len(ordered)):
            a, b = ordered[i - 1].data_date, ordered[i].data_date
            if not (a and b):
                continue
            gap_days = (b - a).days
            if gap_days > GAP_MULTIPLE * sc.dominant_cadence_days:
                mm = months_between(a, b)
                sc.gaps.append(GapInfo(ordered[i - 1].label(), ordered[i].label(),
                                       a, b, float(gap_days), sc.dominant_cadence_days, mm))
                sc.missing_months.extend(mm)

    sc.baseline_file = ordered[0].source_file
    sc.baseline_has_progress = _has_progress(ordered[0])

    for s in ordered:
        fmt = s.source_format or "unknown"
        sc.format_mix[fmt] = sc.format_mix.get(fmt, 0) + 1

    for s in ordered:
        pr, pc = _loading_pct(s)
        sc.files.append(FileCompletenessInfo(
            file=s.source_file, label=s.label(), format=s.source_format,
            has_schedoptions=_has_schedoptions(s), pct_resourced=pr, pct_cost_loaded=pc))

    sc.rfi_items = _build_rfi(sc)
    return sc


def _build_rfi(sc: ScorecardResult) -> list:
    items: list = []
    if sc.baseline_has_progress:
        items.append(RfiItem(
            "baseline",
            "Provide the native baseline programme (the earliest file provided, "
            f"{sc.baseline_file}, already contains progress)."))
    for g in sc.gaps:
        rng = format_month_range(g.missing_months)
        items.append(RfiItem(
            "cadence-gap",
            f"Provide monthly updates for the gap {rng or (g.from_label + ' to ' + g.to_label)} "
            f"— no update was provided between {g.from_label} and {g.to_label} "
            f"({g.days:.0f} calendar days, against a dominant cadence of "
            f"{g.expected_days:.0f})."))
    if len(sc.format_mix) > 1:
        mix = ", ".join(f"{v} in {k}" for k, v in sorted(sc.format_mix.items()))
        items.append(RfiItem(
            "format",
            f"Confirm a single native scheduling format for all future updates; the "
            f"file set as provided mixes formats ({mix})."))
    for f in sc.files:
        if not f.has_schedoptions:
            items.append(RfiItem(
                "schedoptions",
                f"Confirm scheduling options (SCHEDOPTIONS absent from file {f.file})."))
    for f in sc.files:
        if f.pct_resourced < RESOURCE_LOADING_MIN_PCT:
            items.append(RfiItem(
                "resource-loading",
                f"Confirm resource loading completeness for {f.file} — only "
                f"{f.pct_resourced:.0f}% of activities carry a resource assignment."))
        if f.pct_cost_loaded < COST_LOADING_MIN_PCT:
            items.append(RfiItem(
                "cost-loading",
                f"Confirm cost loading completeness for {f.file} — only "
                f"{f.pct_cost_loaded:.0f}% of activities carry a cost."))
    return items


def rfi_lines(sc: ScorecardResult) -> list:
    """The draft RFI lines only, in generation order."""
    return [item.text for item in sc.rfi_items]
