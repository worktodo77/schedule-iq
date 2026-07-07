"""Intake-accelerator pack (backlog D1-D8; ANALYTICS_PROPOSAL.md §3.1).

Everything in this package is "no engine needed — high value, low effort"
intake material for a delay expert receiving a client's schedule set: a
data-completeness scorecard and RFI generator (D1), an as-planned vs
as-built variance register (D2), a float consumption ledger (D3), a
windows auto-segmentation proposal (D4), a concurrency screen (D5), a
delay-event mapper (D6), a responsibility overlay (D7), and an evergreen-
activity detector (D8).

Every accelerator degrades gracefully: on missing or insufficient data it
returns its own result dataclass with an explanatory ``reason`` and empty
collections rather than raising, so a partial or single-file intake never
sinks a run.  ``run_intake`` bundles all eight for the report and Excel
writers, wrapping each call so one accelerator's failure cannot take down
the others.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..trend.series import SeriesAnalysis
from .concurrency import ConcurrencyScreen, screen_concurrency
from .events import EventMapResult, map_events
from .evergreen import EvergreenResult, find_evergreen_activities
from .float_ledger import FloatLedger, build_float_ledger
from .responsibility import ResponsibilityResult, run_responsibility
from .scorecard import ScorecardResult, build_scorecard
from .variance import VarianceRegister, build_variance_register
from .windows import WindowsProposal, propose_windows

__all__ = [
    "IntakeResults", "run_intake",
    "ScorecardResult", "build_scorecard",
    "VarianceRegister", "build_variance_register",
    "FloatLedger", "build_float_ledger",
    "WindowsProposal", "propose_windows",
    "ConcurrencyScreen", "screen_concurrency",
    "EventMapResult", "map_events",
    "ResponsibilityResult", "run_responsibility",
    "EvergreenResult", "find_evergreen_activities",
]


@dataclass
class IntakeResults:
    scorecard: ScorecardResult
    variance: VarianceRegister
    float_ledger: FloatLedger
    windows: WindowsProposal
    concurrency: ConcurrencyScreen
    events: EventMapResult
    responsibility: ResponsibilityResult
    evergreen: EvergreenResult


def _safe(builder, empty_cls, *args, **kwargs):
    try:
        return builder(*args, **kwargs)
    except Exception as e:                    # an accelerator must never sink a run
        return empty_cls(reason=f"accelerator failed: {e}")


def run_intake(series_analysis: SeriesAnalysis, events_csv: Optional[str] = None,
              responsibility_csv: Optional[str] = None) -> IntakeResults:
    """Run all eight intake accelerators over one series and bundle them."""
    return IntakeResults(
        scorecard=_safe(build_scorecard, ScorecardResult, series_analysis),
        variance=_safe(build_variance_register, VarianceRegister, series_analysis),
        float_ledger=_safe(build_float_ledger, FloatLedger, series_analysis),
        windows=_safe(propose_windows, WindowsProposal, series_analysis),
        concurrency=_safe(screen_concurrency, ConcurrencyScreen, series_analysis),
        events=_safe(map_events, EventMapResult, series_analysis, events_csv),
        responsibility=_safe(run_responsibility, ResponsibilityResult, series_analysis,
                             responsibility_csv),
        evergreen=_safe(find_evergreen_activities, EvergreenResult, series_analysis),
    )
