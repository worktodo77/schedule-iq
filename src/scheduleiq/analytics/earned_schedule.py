"""Earned-schedule forecast credibility (ANALYTICS_PROPOSAL.md §6.4, backlog S3).

Earned schedule (Lipke) restates earned value in TIME rather than money, which
is what a schedule expert actually wants: an independent completion forecast
to set against the CPM forecast the tool of record is reporting each period.

Method, using the FIRST schedule in the series as the fixed baseline:

- PV(t): a cumulative curve built once from the baseline's own activities,
  each contributing its weight (cost-weighted when the baseline carries
  budget cost, else a simple count) at its planned/baseline finish date —
  "how much of the baseline plan was to be complete by date t."
- EV at update i's data date: the SAME measure, but over activities that are
  ACTUALLY complete as of update i (matched back to the baseline population by
  activity code).
- ES(t): the time coordinate on the PV curve at which cumulative PV equals the
  current EV, found by linear interpolation between the two baseline curve
  points that bracket it (the standard earned-schedule interpolation) — i.e.
  "the plan says this much progress should have been earned by ES(t), and
  that's the point on the ORIGINAL timeline we've actually reached."
- AT: elapsed calendar time from the baseline start to the update's data date.
- SPI(t) = ES/AT; TSPI(t) = (PD - ES) / (PD - AT), the "to complete SPI(t)" —
  the pace the REMAINING plan requires, in the same units; PD is the baseline
  planned duration to the baseline finish.
- IEAC(t) = PD / SPI(t), the earned-schedule independent forecast duration,
  also expressed as a forecast finish date (baseline start + IEAC(t) days).

This never disagrees with the CPM engine's own forecast — it is a deliberately
independent, tool-agnostic cross-check computed purely from the plan and
progress record (ADR-0004 spirit: two lenses, not two schedulers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

DAY = timedelta(days=1)


@dataclass
class EarnedSchedulePoint:
    label: str                        # update label (schedule.label())
    data_date: Optional[datetime]
    at_days: float                    # elapsed calendar days, baseline start -> data date
    pv_value: float                   # PV(data date) on the baseline curve (context)
    ev_value: float                   # EV at this update
    es_days: float                    # ES(t) in calendar days from baseline start
    es_date: Optional[datetime]
    spi_t: Optional[float]
    tspi_t: Optional[float]
    ieac_days: Optional[float]
    ieac_date: Optional[datetime]
    interpretation: str = ""


@dataclass
class EarnedScheduleResult:
    baseline_label: str = ""
    basis: str = ""                    # "cost" | "count"
    baseline_start: Optional[datetime] = None
    baseline_finish: Optional[datetime] = None
    planned_duration_days: Optional[float] = None
    points: list[EarnedSchedulePoint] = field(default_factory=list)
    reason: str = ""


def _target_date(a) -> Optional[datetime]:
    return a.baseline_finish or a.planned_finish


def _days(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 86400.0


def _build_pv_curve(baseline, weight_of) -> list[tuple[datetime, float]]:
    """Cumulative (date, PV) points, starting at (baseline_start, 0)."""
    by_date: dict[datetime, float] = {}
    for a in baseline.real_activities:
        td = _target_date(a)
        if td is None:
            continue
        by_date[td] = by_date.get(td, 0.0) + weight_of(a)
    start = baseline.start_date or (min(by_date) if by_date else None)
    points: list[tuple[datetime, float]] = [(start, 0.0)] if start else []
    running = 0.0
    for d in sorted(by_date):
        running += by_date[d]
        points.append((d, running))
    return points


def _es_days(curve: list[tuple[datetime, float]], ev: float,
            baseline_start: datetime) -> float:
    """Linear interpolation of the time at which cumulative PV == ev."""
    if not curve:
        return 0.0
    if ev <= curve[0][1]:
        return _days(baseline_start, curve[0][0])
    if ev >= curve[-1][1]:
        return _days(baseline_start, curve[-1][0])
    for (d0, v0), (d1, v1) in zip(curve, curve[1:]):
        if v0 <= ev <= v1:
            frac = (ev - v0) / (v1 - v0) if v1 != v0 else 0.0
            days0, days1 = _days(baseline_start, d0), _days(baseline_start, d1)
            return days0 + frac * (days1 - days0)
    return _days(baseline_start, curve[-1][0])


def _interpret(spi_t: Optional[float], tspi_t: Optional[float]) -> str:
    parts = []
    if spi_t is not None:
        tag = ("ahead of" if spi_t > 1.02 else
               "behind" if spi_t < 0.98 else "on")
        parts.append(f"SPI(t) {spi_t:.2f} — {tag} baseline pace")
    if tspi_t is not None:
        if tspi_t > 1.10:
            parts.append(f"TSPI(t) {tspi_t:.2f} > 1.10: remaining plan "
                        "requires performance never demonstrated")
        elif tspi_t > 1.0:
            parts.append(f"TSPI(t) {tspi_t:.2f}: remaining plan requires "
                        "performance above that demonstrated to date")
        else:
            parts.append(f"TSPI(t) {tspi_t:.2f}: remaining plan requires "
                        "performance at or below that demonstrated to date")
    return "; ".join(parts) if parts else "insufficient data to interpret"


def earned_schedule(series_analysis) -> EarnedScheduleResult:
    """Compute the earned-schedule table from a SeriesAnalysis, one row per
    update AFTER the baseline (the first schedule IS the baseline, not an
    update over itself)."""
    schedules = getattr(series_analysis, "schedules", [])
    result = EarnedScheduleResult()
    if len(schedules) < 2:
        result.reason = "needs at least two schedules (a baseline plus one update)"
        return result

    baseline = schedules[0]
    result.baseline_label = baseline.label()
    pop = [a for a in baseline.real_activities if _target_date(a) is not None]
    if not pop:
        result.reason = "baseline has no activities with a planned/baseline finish date"
        return result

    # Cost-weighting is only meaningful when cost data actually covers the
    # population; a handful of costed activities among many uncosted ones
    # would otherwise let the PV/EV curve be driven by whichever few
    # activities happen to carry rolled-up cost rather than genuine progress.
    costed = sum(1 for a in pop if a.budget_cost > 0)
    result.basis = "cost" if costed and costed / len(pop) > 0.5 else "count"
    weight_of = (lambda a: a.budget_cost) if result.basis == "cost" else (lambda a: 1.0)

    curve = _build_pv_curve(baseline, weight_of)
    if not curve or curve[-1][1] <= 0:
        result.reason = "baseline planned-value curve is empty (no resolvable start date or weights)"
        return result

    baseline_start = curve[0][0]
    baseline_finish = baseline.finish_date or curve[-1][0]
    result.baseline_start = baseline_start
    result.baseline_finish = baseline_finish
    pd_days = _days(baseline_start, baseline_finish)
    result.planned_duration_days = pd_days

    for sched in schedules[1:]:
        dd = sched.data_date
        if dd is None:
            continue
        at_days = _days(baseline_start, dd)
        l_by_code = {a.code: a for a in sched.activities.values()}
        ev = 0.0
        pv_now = 0.0
        for a in pop:
            td = _target_date(a)
            if td is not None and td <= dd:
                pv_now += weight_of(a)
            la = l_by_code.get(a.code)
            if la is not None and la.completed:
                ev += weight_of(a)
        es_days_val = _es_days(curve, ev, baseline_start)
        es_date = baseline_start + timedelta(days=es_days_val)

        spi_t = (es_days_val / at_days) if at_days > 1e-9 else None
        denom = pd_days - at_days
        tspi_t = ((pd_days - es_days_val) / denom) if abs(denom) > 1e-9 else None
        ieac_days = (pd_days / spi_t) if spi_t and spi_t > 1e-9 else None
        ieac_date = (baseline_start + timedelta(days=ieac_days)
                    if ieac_days is not None else None)

        result.points.append(EarnedSchedulePoint(
            label=sched.label(), data_date=dd, at_days=at_days, pv_value=pv_now,
            ev_value=ev, es_days=es_days_val, es_date=es_date,
            spi_t=spi_t, tspi_t=tspi_t, ieac_days=ieac_days, ieac_date=ieac_date,
            interpretation=_interpret(spi_t, tspi_t)))
    return result
