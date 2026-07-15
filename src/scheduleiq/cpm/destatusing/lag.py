"""
V1-D: Actual lag computation and lag analysis framework.

Implements the four actual-lag formulas from the 2014 Avalon paper §3
(CALC-022 through CALC-025) and a workday-based lag analysis engine.

Primary method: workday-number subtraction (CPW-P6 Manual pp. 41-42).
Cross-validation formulas (calendar-day equivalents) from CALC-022-025.

Lag formulas (CALC-022 through CALC-025 from 2014 Avalon paper):
  FS: actual_lag = workday(succ_AS) - workday(pred_AF)
  SS: actual_lag = workday(succ_AS) - workday(pred_AS)
  FF: actual_lag = workday(succ_AF) - workday(pred_AF)
  SF: actual_lag = workday(succ_AF) - workday(pred_AS)

Calendar used for workday-table lookups: when ``run_lag_analysis`` is given a
``CalendarRegistry`` it resolves the per-relationship calendar via the active
``LagCalendarStrategy`` (default PREDECESSOR_CALENDAR — lag measured in the
predecessor activity's calendar, V1-B.1 / ADR-012); without a registry it uses
the single supplied calendar for every relationship (F3/F-13 — previously the
ONLY behavior, so this module's per-relationship strategy claim was aspirational
until F3 wired it through).

Source: CPW-P6 Manual pp. 41-44; 2014 Avalon paper §3; ADR-012; ADR-014.

Ported from the LI MIP 3.9 tool (mip39.destatusing.lag) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..models import Activity, Calendar, Relationship
from ..calendar_ops import _adjust_nonworkday, resolve_activity_workday_resources
from ..calendar_registry import LagCalendarStrategy


# ---------------------------------------------------------------------------
# Actual lag result
# ---------------------------------------------------------------------------

@dataclass
class ActualLagResult:
    """
    Actual lag for a single relationship, computed from as-built dates.

    Fields:
        pred_id         — Predecessor activity ID.
        succ_id         — Successor activity ID.
        rel_type        — Relationship type ("FS", "SS", "FF", "SF").
        planned_lag     — Original planned lag (workdays).
        actual_lag      — Computed actual lag (workdays). None if dates missing.
        lag_variance    — actual_lag - planned_lag. None if actual_lag is None.
        is_negative     — True if actual_lag < 0.
        is_driving      — Set by auto-drive; True when this is the minimum-variance
                          predecessor for its successor.
        lag_reset_to    — When non-driving: planned_lag (lag reset by auto-drive).
                          None when driving or single-predecessor.
        dates_missing   — List of date field names that were None; explains why
                          actual_lag is None.
        formula_used    — Which formula computed the lag (e.g., "FS_workday").
    """
    pred_id: str
    succ_id: str
    rel_type: str
    planned_lag: float
    actual_lag: Optional[float]
    lag_variance: Optional[float]
    is_negative: bool
    is_driving: bool = False
    lag_reset_to: Optional[float] = None
    dates_missing: list[str] = field(default_factory=list)
    formula_used: str = ""
    # F3/F-13 (Codex) — the calendar this lag was actually measured in, and whether
    # the registry strategy fell back to the global calendar (resolution failed /
    # the resolved calendar was unavailable). A fallback is a disclosed deviation.
    lag_calendar_id: Optional[str] = None
    lag_calendar_fallback: bool = False

    @property
    def rel_key(self) -> str:
        return f"({self.pred_id},{self.succ_id},{self.rel_type})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pred_id": self.pred_id,
            "succ_id": self.succ_id,
            "rel_type": self.rel_type,
            "planned_lag": self.planned_lag,
            "actual_lag": self.actual_lag,
            "lag_variance": self.lag_variance,
            "is_negative": self.is_negative,
            "is_driving": self.is_driving,
            "lag_reset_to": self.lag_reset_to,
            "dates_missing": list(self.dates_missing),
            "formula_used": self.formula_used,
            "lag_calendar_id": self.lag_calendar_id,
            "lag_calendar_fallback": self.lag_calendar_fallback,
        }


# ---------------------------------------------------------------------------
# Workday-number helpers
# ---------------------------------------------------------------------------

def _wd(
    d: date,
    workday_table: dict[date, int],
    calendar: Calendar,
    is_start: bool,
) -> int:
    """Return the workday number for d, adjusting non-workdays first."""
    if not calendar.is_workday(d):
        d = _adjust_nonworkday(
            d, calendar, is_start=is_start, workday_table=workday_table
        )
    num = workday_table.get(d)
    if num is None:
        raise ValueError(
            f"_wd: date {d} not in workday table after adjustment. "
            "Extend the workday table range."
        )
    return num


# ---------------------------------------------------------------------------
# CALC-022 through CALC-025: actual lag computation
# ---------------------------------------------------------------------------

def compute_actual_fs_lag(
    pred_af: date,
    succ_as: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> int:
    """
    CALC-022 — Actual FS lag.

    actual_lag = workday(succ_AS) - workday(pred_AF)

    For FS relationships: lag is measured from predecessor finish to
    successor start. A positive value means succ started later than pred
    finished (normal). Negative means succ started before pred finished (OOS).

    Source: CPW-P6 Manual pp. 41-42; 2014 Avalon paper §3 Equation 1.
    """
    return _wd(succ_as, workday_table, calendar, True) - _wd(pred_af, workday_table, calendar, False)


def compute_actual_ss_lag(
    pred_as: date,
    succ_as: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> int:
    """
    CALC-023 — Actual SS lag.

    actual_lag = workday(succ_AS) - workday(pred_AS)

    Source: CPW-P6 Manual pp. 41-42; 2014 Avalon paper §3 Equation 2.
    """
    return _wd(succ_as, workday_table, calendar, True) - _wd(pred_as, workday_table, calendar, True)


def compute_actual_ff_lag(
    pred_af: date,
    succ_af: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> int:
    """
    CALC-024 — Actual FF lag.

    actual_lag = workday(succ_AF) - workday(pred_AF)

    Source: CPW-P6 Manual pp. 41-42; 2014 Avalon paper §3 Equation 3.
    """
    return _wd(succ_af, workday_table, calendar, False) - _wd(pred_af, workday_table, calendar, False)


def compute_actual_sf_lag(
    pred_as: date,
    succ_af: date,
    workday_table: dict[date, int],
    calendar: Calendar,
) -> int:
    """
    CALC-025 — Actual SF lag.

    actual_lag = workday(succ_AF) - workday(pred_AS)

    Source: CPW-P6 Manual pp. 41-42; 2014 Avalon paper §3 Equation 4.
    """
    return _wd(succ_af, workday_table, calendar, False) - _wd(pred_as, workday_table, calendar, True)


def compute_actual_lag(
    rel: Relationship,
    pred_activity: Activity,
    succ_activity: Activity,
    workday_table: dict[date, int],
    calendar: Calendar,
    registry: Any = None,
) -> ActualLagResult:
    """
    CALC-002 / CALC-022-025 — Compute actual lag for a relationship.

    Uses workday-number subtraction (primary method per CPW Manual pp. 41-42).
    Falls back to None when required actual dates are missing.

    FS/FF: uses predecessor Actual Finish (pred_AF).
    SS/SF: uses predecessor Actual Start (pred_AS).
    FS/SS: uses successor Actual Start (succ_AS).
    FF/SF: uses successor Actual Finish (succ_AF).

    Returns an ActualLagResult with actual_lag=None and dates_missing populated
    when required dates are unavailable.

    ADR-029 r2 (#8): when ``registry`` is supplied, the lag is counted on the
    PREDECESSOR's calendar (predecessor-calendar default — consistent with
    run_lag_analysis's resolve_lag_resources and the rectification calibration
    gate). ``registry=None`` keeps the passed ``workday_table``/``calendar``
    (single-calendar), so all existing callers are byte-identical.
    """
    if registry is not None:
        workday_table, calendar = resolve_activity_workday_resources(
            pred_activity, workday_table, calendar, registry
        )
    pred_as = pred_activity.actual_start
    pred_af = pred_activity.actual_finish
    succ_as = succ_activity.actual_start
    succ_af = succ_activity.actual_finish
    rel_type = rel.rel_type

    # Check required dates per relationship type
    required: dict[str, date | None] = {}
    if rel_type == "FS":
        required = {"pred_actual_finish": pred_af, "succ_actual_start": succ_as}
    elif rel_type == "SS":
        required = {"pred_actual_start": pred_as, "succ_actual_start": succ_as}
    elif rel_type == "FF":
        required = {"pred_actual_finish": pred_af, "succ_actual_finish": succ_af}
    elif rel_type == "SF":
        required = {"pred_actual_start": pred_as, "succ_actual_finish": succ_af}

    missing = [k for k, v in required.items() if v is None]
    if missing:
        return ActualLagResult(
            pred_id=rel.pred_id,
            succ_id=rel.succ_id,
            rel_type=rel_type,
            planned_lag=rel.lag,
            actual_lag=None,
            lag_variance=None,
            is_negative=False,
            dates_missing=missing,
            formula_used=f"{rel_type}_workday_unavailable",
        )

    try:
        if rel_type == "FS":
            actual_lag = compute_actual_fs_lag(pred_af, succ_as, workday_table, calendar)  # type: ignore[arg-type]
            formula = "FS_workday"
        elif rel_type == "SS":
            actual_lag = compute_actual_ss_lag(pred_as, succ_as, workday_table, calendar)  # type: ignore[arg-type]
            formula = "SS_workday"
        elif rel_type == "FF":
            actual_lag = compute_actual_ff_lag(pred_af, succ_af, workday_table, calendar)  # type: ignore[arg-type]
            formula = "FF_workday"
        else:  # SF
            actual_lag = compute_actual_sf_lag(pred_as, succ_af, workday_table, calendar)  # type: ignore[arg-type]
            formula = "SF_workday"
    except ValueError as exc:
        return ActualLagResult(
            pred_id=rel.pred_id,
            succ_id=rel.succ_id,
            rel_type=rel_type,
            planned_lag=rel.lag,
            actual_lag=None,
            lag_variance=None,
            is_negative=False,
            dates_missing=[f"workday_table_error: {exc}"],
            formula_used=f"{rel_type}_workday_error",
        )

    variance = float(actual_lag) - rel.lag
    return ActualLagResult(
        pred_id=rel.pred_id,
        succ_id=rel.succ_id,
        rel_type=rel_type,
        planned_lag=rel.lag,
        actual_lag=float(actual_lag),
        lag_variance=variance,
        is_negative=actual_lag < 0,
        formula_used=formula,
    )


# ---------------------------------------------------------------------------
# Lag analysis summary
# ---------------------------------------------------------------------------

@dataclass
class LagAnalysisResult:
    """
    Summary of lag analysis across all relationships in the destatused schedule.

    Fields:
        relationship_results — ActualLagResult per relationship, sorted by
                               (pred_id, succ_id, rel_type) for determinism.
        computed_count       — Relationships with actual_lag computed.
        skipped_count        — Relationships with missing dates (no actual_lag).
        negative_count       — Relationships with actual_lag < 0.
        max_variance         — Largest positive lag variance observed.
        min_variance         — Most negative lag variance observed.
        driving_rel_count    — Relationships designated as driving (set by auto-drive).
    """
    relationship_results: list[ActualLagResult]
    computed_count: int
    skipped_count: int
    negative_count: int
    max_variance: Optional[float]
    min_variance: Optional[float]
    driving_rel_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_results": [r.to_dict() for r in self.relationship_results],
            "computed_count": self.computed_count,
            "skipped_count": self.skipped_count,
            "negative_count": self.negative_count,
            "max_variance": self.max_variance,
            "min_variance": self.min_variance,
            "driving_rel_count": self.driving_rel_count,
        }


def run_lag_analysis(
    relationships: list[Relationship],
    activities: dict[str, Activity],
    workday_table: dict[date, int],
    calendar: Calendar,
    calendar_registry: Optional[Any] = None,
    lag_strategy: LagCalendarStrategy = LagCalendarStrategy.PREDECESSOR_CALENDAR,
) -> LagAnalysisResult:
    """
    Compute actual lags for all relationships in the destatused schedule.

    Activities must be the DESTATUSED activity set (post-transformation).
    Relationships with missing actual dates are recorded with actual_lag=None.

    F3/F-13 — when ``calendar_registry`` is supplied, each relationship's lag is
    measured in the calendar resolved by ``lag_strategy`` (default
    PREDECESSOR_CALENDAR), so a multi-calendar schedule no longer forces one
    calendar onto every lag. The single ``calendar``/``workday_table`` are the
    documented fallback (used for every relationship when no registry is given,
    or when the resolved calendar is unavailable).

    Returns a LagAnalysisResult with per-relationship results sorted
    deterministically by (pred_id, succ_id, rel_type).
    """
    # No silent single-calendar fallback (ADR-029 r2, Codex guardrail 3): if a
    # registry is supplied it must COVER the run range. The per-relationship
    # disclosed fallback below only handles a SINGLE activity's missing/unknown
    # calendar; a wholesale unready/out-of-range registry would otherwise quietly
    # single-calendar every lag, so reject it with a disclosed diagnostic. The
    # shared resource helper ensures coverage upstream before destatus/lag runs.
    if calendar_registry is not None and workday_table:
        _cov = getattr(calendar_registry, "tables_cover", None)
        _lo, _hi = min(workday_table), max(workday_table)
        if not (callable(_cov) and _cov(_lo, _hi)):
            raise ValueError(
                "run_lag_analysis: calendar_registry is present but its per-calendar "
                f"tables do not cover the run range [{_lo} .. {_hi}]. Call "
                "ensure_workday_tables() before lag analysis — refusing to silently "
                "single-calendar every lag."
            )

    results: list[ActualLagResult] = []
    for rel in sorted(relationships, key=lambda r: (r.pred_id, r.succ_id, r.rel_type)):
        pred = activities.get(rel.pred_id)
        succ = activities.get(rel.succ_id)
        if pred is None or succ is None:
            results.append(ActualLagResult(
                pred_id=rel.pred_id,
                succ_id=rel.succ_id,
                rel_type=rel.rel_type,
                planned_lag=rel.lag,
                actual_lag=None,
                lag_variance=None,
                is_negative=False,
                dates_missing=["activity_not_found"],
                formula_used="skipped",
            ))
            continue
        # F3/F-13 — resolve the per-relationship lag calendar (predecessor's by
        # default) from the registry; fall back to the single global calendar.
        # Codex: capture which calendar was used + whether it fell back, so a
        # number-moving deviation is disclosed, not silent.
        rel_calendar, rel_table = calendar, workday_table
        lag_cal_id: Optional[str] = getattr(calendar, "name", None)
        used_fallback = False
        if calendar_registry is not None:
            intended_id = (
                getattr(pred, "calendar_id", None)
                if lag_strategy == LagCalendarStrategy.PREDECESSOR_CALENDAR
                else getattr(succ, "calendar_id", None)
                if lag_strategy == LagCalendarStrategy.SUCCESSOR_CALENDAR
                else None
            )
            try:
                rel_calendar, rel_table = calendar_registry.resolve_lag_resources(
                    lag_strategy,
                    getattr(pred, "calendar_id", None),
                    getattr(succ, "calendar_id", None),
                    calendar,
                    workday_table,
                )
                resolvable = intended_id is not None and (
                    calendar_registry.get(intended_id) is not None
                    and calendar_registry.get_workday_table(intended_id) is not None
                )
                if intended_id is not None and not resolvable:
                    used_fallback = True
                    lag_cal_id = getattr(calendar, "name", None)
                else:
                    lag_cal_id = intended_id or getattr(rel_calendar, "name", None)
            except Exception:
                rel_calendar, rel_table = calendar, workday_table
                used_fallback = intended_id is not None
                lag_cal_id = getattr(calendar, "name", None)
        lr = compute_actual_lag(rel, pred, succ, rel_table, rel_calendar)
        lr.lag_calendar_id = lag_cal_id
        lr.lag_calendar_fallback = used_fallback
        results.append(lr)

    computed = [r for r in results if r.actual_lag is not None]
    variances = [r.lag_variance for r in computed if r.lag_variance is not None]
    return LagAnalysisResult(
        relationship_results=results,
        computed_count=len(computed),
        skipped_count=len(results) - len(computed),
        negative_count=sum(1 for r in computed if r.is_negative),
        max_variance=max(variances) if variances else None,
        min_variance=min(variances) if variances else None,
    )
