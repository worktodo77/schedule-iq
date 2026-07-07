"""D5 — concurrency screening.

Flags update pairs where two or more distinct near-critical chains
(``analytics.paths.float_paths``, band <= 10 working days) each lost at
least 5 working days of float (from ``ChangeSet.float_deltas``) or slipped
their forecast finish — a candidate list for the concurrency review only.
Concurrency is an entitlement question and every output of this module
carries the caption below (ANALYTICS_PROPOSAL.md §3.1; SCL Delay and
Disruption Protocol, 2nd ed., §10).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..analytics.paths import float_paths
from ..trend.series import SeriesAnalysis
from ._util import working_days_between

CAPTION = "concurrency candidates — preliminary, for expert review"
DEFAULT_BAND_DAYS = 10.0
DEFAULT_MIN_LOSS_DAYS = 5.0


@dataclass
class ConcurrencyCandidate:
    window_label: str
    path_a_codes: list
    path_b_codes: list
    path_a_float_delta_days: Optional[float]
    path_b_float_delta_days: Optional[float]
    path_a_finish_slip_days: Optional[float]
    path_b_finish_slip_days: Optional[float]


@dataclass
class ConcurrencyScreen:
    candidates: list = field(default_factory=list)   # list[ConcurrencyCandidate]
    caption: str = CAPTION
    reason: str = ""


def _path_signal(cs, fp, cal_for_last):
    deltas = [cs.float_deltas[c] for c in fp.codes if c in cs.float_deltas]
    mean_delta = sum(deltas) / len(deltas) if deltas else None
    last_code = fp.codes[-1]
    e_by_code = {a.code: a for a in cs.earlier.activities.values()}
    l_by_code = {a.code: a for a in cs.later.activities.values()}
    ea, la = e_by_code.get(last_code), l_by_code.get(last_code)
    slip = None
    if ea is not None and la is not None:
        slip = working_days_between(cal_for_last, ea.finish, la.finish)
    return mean_delta, slip


def screen_concurrency(sa: SeriesAnalysis, target_code: Optional[str] = None,
                       band_days: float = DEFAULT_BAND_DAYS,
                       min_loss_days: float = DEFAULT_MIN_LOSS_DAYS) -> ConcurrencyScreen:
    screen = ConcurrencyScreen()
    if len(sa.schedules) < 2:
        screen.reason = "need at least two updates to screen for concurrency"
        return screen

    for cs in sa.changesets:
        later = cs.later
        fps = float_paths(later, target_code, n=20, band_days=band_days)
        if len(fps) < 2:
            continue
        qualifying = []
        for fp in fps:
            cal = later.cal_for(fp.activities[-1]) if fp.activities else None
            delta, slip = _path_signal(cs, fp, cal)
            lost_float = delta is not None and delta <= -min_loss_days
            slipped = slip is not None and slip >= min_loss_days
            if lost_float or slipped:
                qualifying.append((fp, delta, slip))
        for i in range(len(qualifying)):
            for j in range(i + 1, len(qualifying)):
                fa, da, sa_ = qualifying[i]
                fb, db, sb_ = qualifying[j]
                if set(fa.codes) == set(fb.codes):
                    continue
                screen.candidates.append(ConcurrencyCandidate(
                    window_label=f"{cs.earlier.label()} -> {cs.later.label()}",
                    path_a_codes=fa.codes, path_b_codes=fb.codes,
                    path_a_float_delta_days=da, path_b_float_delta_days=db,
                    path_a_finish_slip_days=sa_, path_b_finish_slip_days=sb_))
    return screen
