"""Statistical manipulation screens (ANALYTICS_PROPOSAL.md §6.2, backlog S1).

Three independent screens, none of which is proof of anything on its own —
each returns a plain-language caution to that effect:

- ``benford_screen``: first-/last-digit distributions of original durations
  against Benford/uniform expectation, plus round-number (5-day multiple) and
  percent-complete step-clustering concentration.  Manufactured or templated
  estimates leave digit and rounding signatures that organic durations do not.
- ``distribution_drift``: two-sample Kolmogorov-Smirnov distance between
  consecutive updates' duration distributions (for activities common to both),
  and separately for newly ADDED activities against the incumbent population —
  a localized drift can flag a claim window where estimating practice changed.
- ``progress_physics``: implied production rates from TASKRSRC actuals vs the
  project's/activity's own demonstrated P90 rate, flagging remaining work
  planned at a rate never actually achieved.

Chi-square and Kolmogorov-Smirnov are implemented manually (no scipy
dependency, matching the rest of ScheduleIQ's pure-Python core).  Every
function degrades gracefully: it returns an empty/annotated result rather than
raising, consistent with analytics/paths.py's convention.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Optional

from ..ingest.model import Activity, Schedule

CAUTION = ("Statistical screens indicate patterns for review, not proof of "
           "manipulation.  Each flag is a starting point for analyst inquiry "
           "against the underlying basis of estimate and progress records, "
           "not a conclusion.")

# Benford's Law: P(first digit = d) = log10(1 + 1/d), d in 1..9
_BENFORD_FIRST = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
_UNIFORM_LAST = {d: 0.1 for d in range(0, 10)}


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _hpd(sched: Schedule, a: Activity) -> float:
    cal = sched.cal_for(a)
    return cal.hours_per_day if cal and cal.hours_per_day else 8.0


def _od_days(sched: Schedule, a: Activity) -> float:
    return a.original_duration_hours / _hpd(sched, a)


def _duration_population(sched: Schedule) -> list[Activity]:
    """Original durations in days, own calendar, > 0, excluding milestones
    (and, via real_activities, LOE/WBS-summary/hammock/MSP-summary rows)."""
    return [a for a in sched.real_activities
            if not a.is_milestone and a.original_duration_hours > 0]


def _first_digit(x: float) -> Optional[int]:
    s = f"{x:.6f}".lstrip("-").lstrip("0").lstrip(".")
    for ch in s:
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


def _last_digit(days: float) -> int:
    """Last digit of the duration rounded to the nearest whole day."""
    return int(round(days)) % 10


def chi_square(observed: dict, expected_pct: dict, n: int) -> float:
    """Manual chi-square goodness-of-fit statistic: sum((O-E)^2/E) over the
    keys of ``expected_pct`` (expected as a 0-1 probability per key)."""
    stat = 0.0
    for k, p in expected_pct.items():
        e = p * n
        o = observed.get(k, 0)
        if e > 0:
            stat += (o - e) ** 2 / e
    return stat


# --------------------------------------------------------------------------
# Benford / round-number / percent-step screen
# --------------------------------------------------------------------------
@dataclass
class BenfordResult:
    label: str
    n_durations: int = 0
    first_digit_pct: dict = field(default_factory=dict)       # 1-9 -> %
    first_digit_expected_pct: dict = field(default_factory=dict)
    chi2_first_digit: Optional[float] = None
    last_digit_pct: dict = field(default_factory=dict)        # 0-9 -> %
    last_digit_expected_pct: dict = field(default_factory=dict)
    chi2_last_digit: Optional[float] = None
    round5_pct: float = 0.0                 # % of durations that are multiples of 5d
    n_in_progress_pct: int = 0
    pct_step5_pct: float = 0.0              # % of in-progress %-complete values that are multiples of 5
    caution: str = CAUTION
    reason: str = ""


def benford_screen(schedules: list[Schedule]) -> list[BenfordResult]:
    out: list[BenfordResult] = []
    for sched in schedules:
        pop = _duration_population(sched)
        res = BenfordResult(label=sched.label())
        if not pop:
            res.reason = "no eligible (non-milestone, OD > 0) activities"
            out.append(res)
            continue
        days = [_od_days(sched, a) for a in pop]
        res.n_durations = len(days)

        # ---- first digit --------------------------------------------------
        fd_counts: dict[int, int] = {}
        for d in days:
            fd = _first_digit(d)
            if fd is not None:
                fd_counts[fd] = fd_counts.get(fd, 0) + 1
        n_fd = sum(fd_counts.values())
        res.first_digit_pct = {d: 100.0 * fd_counts.get(d, 0) / n_fd if n_fd else 0.0
                               for d in range(1, 10)}
        res.first_digit_expected_pct = {d: 100.0 * p for d, p in _BENFORD_FIRST.items()}
        res.chi2_first_digit = chi_square(fd_counts, _BENFORD_FIRST, n_fd) if n_fd else None

        # ---- last digit -----------------------------------------------------
        ld_counts: dict[int, int] = {}
        for d in days:
            ld = _last_digit(d)
            ld_counts[ld] = ld_counts.get(ld, 0) + 1
        n_ld = sum(ld_counts.values())
        res.last_digit_pct = {d: 100.0 * ld_counts.get(d, 0) / n_ld if n_ld else 0.0
                              for d in range(0, 10)}
        res.last_digit_expected_pct = {d: 100.0 * p for d, p in _UNIFORM_LAST.items()}
        res.chi2_last_digit = chi_square(ld_counts, _UNIFORM_LAST, n_ld) if n_ld else None

        # ---- round-number (5-day multiple) concentration -------------------
        round5 = [d for d in days if abs(round(d / 5.0) * 5.0 - d) < 1e-6]
        res.round5_pct = 100.0 * len(round5) / len(days)

        # ---- percent-complete step clustering (in-progress only) -----------
        in_prog = [a for a in sched.real_activities if a.in_progress]
        res.n_in_progress_pct = len(in_prog)
        if in_prog:
            step5 = [a for a in in_prog
                     if abs(round(a.pct_complete / 5.0) * 5.0 - a.pct_complete) < 1e-6]
            res.pct_step5_pct = 100.0 * len(step5) / len(in_prog)
        out.append(res)
    return out


# --------------------------------------------------------------------------
# Distribution drift (manual two-sample K-S)
# --------------------------------------------------------------------------
def _ecdf_at(sorted_sample: list[float], x: float) -> float:
    return bisect.bisect_right(sorted_sample, x) / len(sorted_sample)


def ks_distance(a: list[float], b: list[float]) -> Optional[float]:
    """Manual two-sample Kolmogorov-Smirnov distance: max |F_a(x) - F_b(x)|
    over the combined support.  Returns None when either sample is empty
    (distance undefined), else a value in [0, 1]."""
    if not a or not b:
        return None
    sa, sb = sorted(a), sorted(b)
    combined = sorted(set(sa) | set(sb))
    return max(abs(_ecdf_at(sa, x) - _ecdf_at(sb, x)) for x in combined)


@dataclass
class DriftResult:
    earlier_label: str
    later_label: str
    n_common: int = 0
    ks_common: Optional[float] = None
    n_added: int = 0
    n_incumbent: int = 0
    ks_added: Optional[float] = None
    narrative: str = ""


def distribution_drift(series_analysis) -> list[DriftResult]:
    """Per consecutive update pair: K-S distance between the OD distributions
    (in days, own calendar) of activities present in both updates (matched by
    code), and — separately — between newly ADDED activities' durations and
    the incumbent (pre-existing, common) population's current durations."""
    out: list[DriftResult] = []
    changesets = getattr(series_analysis, "changesets", [])
    for cs in changesets:
        e, l = cs.earlier, cs.later
        e_pop = {a.code: a for a in _duration_population(e)}
        l_pop = {a.code: a for a in _duration_population(l)}
        common = sorted(set(e_pop) & set(l_pop))
        earlier_days = [_od_days(e, e_pop[c]) for c in common]
        later_days = [_od_days(l, l_pop[c]) for c in common]
        res = DriftResult(earlier_label=e.label(), later_label=l.label(),
                          n_common=len(common),
                          ks_common=ks_distance(earlier_days, later_days))

        added_pop = [a for a in cs.added if not a.is_milestone
                    and a.original_duration_hours > 0]
        added_days = [_od_days(l, a) for a in added_pop]
        res.n_added = len(added_days)
        res.n_incumbent = len(later_days)
        res.ks_added = ks_distance(added_days, later_days)

        bits = [f"{res.n_common} common activit{'y' if res.n_common == 1 else 'ies'}"]
        if res.ks_common is not None:
            bits.append(f"K-S(common OD, {e.label()} vs {l.label()}) = "
                       f"{res.ks_common:.2f}")
        if res.ks_added is not None:
            bits.append(f"K-S(added OD n={res.n_added} vs incumbent OD "
                       f"n={res.n_incumbent}) = {res.ks_added:.2f}")
        else:
            bits.append(f"{res.n_added} added activit"
                       f"{'y' if res.n_added == 1 else 'ies'} — insufficient "
                       "population for a K-S comparison")
        res.narrative = "; ".join(bits) + "."
        out.append(res)
    return out


# --------------------------------------------------------------------------
# Progress physics
# --------------------------------------------------------------------------
def _working_hours_between(sched: Schedule, a: Activity, start, end) -> float:
    """Working hours available on ``a``'s own calendar between two dates
    (mirrors trend/series.py's private helper; duplicated here rather than
    imported so this module has no dependency on trend/series.py internals)."""
    if start is None or end is None or start >= end:
        return 0.0
    from datetime import timedelta
    cal = sched.cal_for(a)
    hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
    d, end_d = start.date(), end.date()
    cap = d + timedelta(days=5 * 365)
    total = 0.0
    while d < end_d and d < cap:
        if cal is not None:
            if cal.is_workday(d):
                total += hpd
        elif d.isoweekday() <= 5:
            total += hpd
        d += timedelta(days=1)
    return total


def percentile(values: list[float], pct: float) -> Optional[float]:
    """Linear-interpolation percentile (manual, no numpy)."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


@dataclass
class RatePoint:
    code: str
    period: str
    rate_per_hour: float


@dataclass
class PhysicsFinding:
    code: str
    name: str
    period: str
    required_rate_per_hour: float
    own_p90: Optional[float]
    project_p90: Optional[float]
    detail: str


@dataclass
class ProgressPhysicsResult:
    rates: list[RatePoint] = field(default_factory=list)
    project_p90: Optional[float] = None
    findings: list[PhysicsFinding] = field(default_factory=list)
    caution: str = CAUTION
    narrative: str = ""


def progress_physics(series_analysis) -> ProgressPhysicsResult:
    """Implied production rate per resourced activity per update pair (actual
    units consumed / working hours between data dates on its own calendar);
    flags remaining work whose implied REQUIRED rate (remaining units /
    remaining working hours to forecast finish) exceeds either the activity's
    own or the project's demonstrated P90 rate — recovery-schedule realism and
    the factual skeleton of acceleration/disruption arguments."""
    res = ProgressPhysicsResult()
    changesets = getattr(series_analysis, "changesets", [])
    if not changesets:
        res.narrative = "Needs at least two updates to observe a production rate."
        return res

    for cs in changesets:
        e, l = cs.earlier, cs.later
        if not (e.data_date and l.data_date and l.data_date > e.data_date):
            continue
        e_by_code = {a.code: a for a in e.real_activities}
        period = f"{e.label()} -> {l.label()}"
        for la in l.real_activities:
            if la.is_loe_or_summary or la.is_milestone or not la.resources:
                continue
            ea = e_by_code.get(la.code)
            if ea is None:
                continue
            actual_e = sum(r.actual_units for r in ea.resources)
            actual_l = sum(r.actual_units for r in la.resources)
            delta = actual_l - actual_e
            if delta <= 0:
                continue
            hours = _working_hours_between(l, la, e.data_date, l.data_date)
            if hours <= 0:
                continue
            res.rates.append(RatePoint(code=la.code, period=period,
                                       rate_per_hour=delta / hours))

    all_rates = [r.rate_per_hour for r in res.rates]
    res.project_p90 = percentile(all_rates, 90)
    by_code: dict[str, list[float]] = {}
    for r in res.rates:
        by_code.setdefault(r.code, []).append(r.rate_per_hour)

    for cs in changesets:
        l = cs.later
        dd = l.data_date
        if not dd:
            continue
        period = f"{cs.earlier.label()} -> {cs.later.label()}"
        for la in l.real_activities:
            if la.is_loe_or_summary or la.is_milestone or la.completed \
                    or not la.resources:
                continue
            remaining_units = sum(r.remaining_units for r in la.resources)
            if remaining_units <= 0:
                continue
            forecast_finish = la.early_finish or la.planned_finish
            if not forecast_finish or forecast_finish <= dd:
                continue
            hours_remaining = _working_hours_between(l, la, dd, forecast_finish)
            if hours_remaining <= 0:
                continue
            required_rate = remaining_units / hours_remaining
            own_p90 = percentile(by_code.get(la.code, []), 90)
            exceeds_own = own_p90 is not None and required_rate > own_p90
            exceeds_project = res.project_p90 is not None \
                and required_rate > res.project_p90
            if exceeds_own or exceeds_project:
                bits = [f"required rate {required_rate:.2f} units/h to finish "
                       f"remaining {remaining_units:.0f} units by "
                       f"{forecast_finish:%Y-%m-%d}"]
                if exceeds_own:
                    bits.append(f"exceeds its own demonstrated P90 "
                               f"({own_p90:.2f} units/h)")
                if exceeds_project:
                    bits.append(f"exceeds the project's demonstrated P90 "
                               f"({res.project_p90:.2f} units/h)")
                res.findings.append(PhysicsFinding(
                    code=la.code, name=la.name, period=period,
                    required_rate_per_hour=required_rate,
                    own_p90=own_p90, project_p90=res.project_p90,
                    detail="; ".join(bits)))

    res.narrative = (f"{len(res.rates)} implied production-rate observation(s) "
                     f"across the series (project P90 = "
                     f"{res.project_p90:.2f} units/h); " if res.rates else
                     "No resourced activity showed measurable actual-unit "
                     "progress between updates; ") + \
        f"{len(res.findings)} activity(ies) plan remaining work at a rate " \
        "never demonstrated."
    return res


# --------------------------------------------------------------------------
# convenience bundle for the report/excel writer
# --------------------------------------------------------------------------
def run_stats(series_analysis) -> dict:
    """Compute the full statistical-screens bundle in one call.  Never raises:
    each screen degrades to an empty/annotated result on its own."""
    sa = series_analysis
    try:
        benford = benford_screen(sa.schedules)
    except Exception as e:                      # pragma: no cover - defensive
        benford = [BenfordResult(label="(error)", reason=str(e))]
    try:
        drift = distribution_drift(sa)
    except Exception as e:                       # pragma: no cover - defensive
        drift = []
    try:
        physics = progress_physics(sa)
    except Exception as e:                        # pragma: no cover - defensive
        physics = ProgressPhysicsResult(narrative=f"error: {e}")
    return {"benford": benford, "drift": drift, "physics": physics}
