"""D3 — float consumption ledger.

Per update pair and per activity: the total-float delta already computed by
``compare.diff.ChangeSet.float_deltas`` (working days on the activity's own
latest calendar), aggregated by WBS node and by float band; plus a float-
erosion-by-window summary (min/mean float per update, and how much mean
float was consumed since the previous update) — the raw material for the
classic float-erosion-by-window chart (ANALYTICS_PROPOSAL.md §3.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..trend.series import SeriesAnalysis
from ._util import band_label


@dataclass
class FloatDeltaRow:
    pair_label: str
    code: str
    name: str
    wbs: str
    delta_days: float
    band: str


@dataclass
class GroupAggregate:
    pair_label: str
    key: str                  # WBS node label, or float band label
    n_activities: int
    total_delta_days: float
    mean_delta_days: float


@dataclass
class ErosionWindow:
    label: str
    min_float_days: Optional[float]
    mean_float_days: Optional[float]
    consumed_days: Optional[float]     # previous window's mean minus this one's (None on first)


@dataclass
class FloatLedger:
    rows: list = field(default_factory=list)              # list[FloatDeltaRow]
    by_wbs: list = field(default_factory=list)             # list[GroupAggregate]
    by_band: list = field(default_factory=list)            # list[GroupAggregate]
    erosion_by_window: list = field(default_factory=list)  # list[ErosionWindow]
    reason: str = ""


def _wbs_label(schedule, act) -> str:
    node = schedule.wbs.get(act.wbs_uid)
    if node:
        return node.code or node.name or act.wbs_uid or "—"
    return act.wbs_uid or "—"


def build_float_ledger(sa: SeriesAnalysis) -> FloatLedger:
    fl = FloatLedger()
    if not sa.schedules:
        fl.reason = "no schedules to build a float ledger from"
        return fl
    if not sa.changesets:
        fl.reason = "need at least two updates to compute float deltas"

    for cs in sa.changesets:
        pair_label = f"{cs.earlier.label()} -> {cs.later.label()}"
        later_by_code = {a.code: a for a in cs.later.activities.values()}
        wbs_bucket: dict = {}
        band_bucket: dict = {}
        for code, delta in cs.float_deltas.items():
            act = later_by_code.get(code)
            if act is None or act.is_loe_or_summary:
                continue
            wbs = _wbs_label(cs.later, act)
            band = band_label(act.total_float_days(cs.later.cal_for(act)))
            fl.rows.append(FloatDeltaRow(pair_label, code, act.name, wbs, delta, band))
            wbs_bucket.setdefault(wbs, []).append(delta)
            band_bucket.setdefault(band, []).append(delta)
        for key, vals in sorted(wbs_bucket.items()):
            fl.by_wbs.append(GroupAggregate(pair_label, key, len(vals), sum(vals),
                                            sum(vals) / len(vals)))
        for key, vals in sorted(band_bucket.items()):
            fl.by_band.append(GroupAggregate(pair_label, key, len(vals), sum(vals),
                                             sum(vals) / len(vals)))

    prev_mean = None
    for s in sa.schedules:
        floats = [f for f in (a.total_float_days(s.cal_for(a)) for a in s.real_activities
                              if not a.completed and a.total_float_hours is not None)
                 if f is not None]
        mn = min(floats) if floats else None
        mean = sum(floats) / len(floats) if floats else None
        consumed = (prev_mean - mean) if (prev_mean is not None and mean is not None) else None
        fl.erosion_by_window.append(ErosionWindow(s.label(), mn, mean, consumed))
        if mean is not None:
            prev_mean = mean

    return fl
