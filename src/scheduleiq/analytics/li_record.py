"""Five bespoke Long International metrics (ANALYTICS_PROPOSAL.md §9.2 LHL,
§9.3 FRB, §10.1 BDI, §10.3 IL, §10.5 MML; backlog N7/N8/N11/N13/N15).

None of these needs the (not-yet-built) CPM engine: they read the tool-of-
record dates, floats, and the change register that ``compare.diff`` and
``analytics.paths`` already compute, and reason about survival, forecast
accuracy, baseline provenance, response latency, and productivity contrast.
Every public entry point degrades gracefully — missing data yields a result
carrying a ``reason`` string, never an exception — matching the discipline of
``analytics.paths`` and ``analytics.statistical``.

- ``logic_half_life`` (LHL): Kaplan-Meier survival of relationship signatures
  across the update series, on/off driving-path split.
- ``forecast_reliability_band`` (FRB): empirical forecast-error bands by
  horizon, from the schedule's own track record of forecast vs. actual finish.
- ``baseline_dilution_index`` (BDI): the share of the latest driving path's
  length that was never in the original baseline (added activities/logic).
- ``intervention_latency`` (IL): updates/days between a chain's float turning
  negative and the first responsive edit on that chain.
- ``measured_mile_locator`` (MML): per top-level WBS node, the clean vs. most-
  impacted productivity window and their contrast ratio.

``run_li_record`` bundles all five behind one call for the report/matrix
integration to consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..ingest.model import Activity, Schedule
from ..intake._util import working_days_between
from .paths import driving_path
from .statistical import percentile

# --------------------------------------------------------------------------
# Kaplan-Meier estimator (LHL's statistical core; kept generic/testable)
# --------------------------------------------------------------------------
@dataclass
class KMPoint:
    t: float
    at_risk: int
    events: int
    survival: float


@dataclass
class KMResult:
    median: Optional[float] = None
    median_reached: bool = False
    n: int = 0
    censored: int = 0
    curve: list[KMPoint] = field(default_factory=list)


def kaplan_meier(lifespans: list[tuple[float, bool]]) -> KMResult:
    """Kaplan-Meier survival estimate over ``lifespans`` = (duration, is_censored).

    Returns the median survival time — the earliest ``t`` at which S(t) <= 0.5.
    When the curve never crosses 0.5 within the observed follow-up (heavily
    right-censored data, or very few events — common with short update series),
    the median is formally "not reached"; rather than surface an unusable
    None/inf on a headline metric, the LONGEST OBSERVED FOLLOW-UP (the maximum
    lifespan, censored observations included) is reported as the conservative
    lower bound, flagged via ``median_reached=False`` so report text can
    qualify the number ("at least N months of follow-up, not yet resolved")
    instead of silently overstating precision.  (Audit ruling L2, v0.4.5: the
    pre-0.4.5 fallback used the last EVENT time, which with a single early
    death degenerated to "at least 0.0" while every survivor had demonstrably
    lived the full series — S(t) stays above 0.5 through the end of follow-up,
    so the median provably exceeds the longest observed lifespan.)
    """
    res = KMResult(n=len(lifespans), censored=sum(1 for _, c in lifespans if c))
    if not lifespans:
        return res
    event_times = sorted({d for d, c in lifespans if not c})
    s = 1.0
    for t in event_times:
        at_risk = sum(1 for d, _ in lifespans if d >= t)
        events = sum(1 for d, c in lifespans if d == t and not c)
        if at_risk <= 0:
            continue
        s *= (1 - events / at_risk)
        res.curve.append(KMPoint(t=t, at_risk=at_risk, events=events, survival=s))
        if res.median is None and s <= 0.5:
            res.median = t
            res.median_reached = True
    if res.median is None:
        res.median = max(d for d, _ in lifespans)
        res.median_reached = False
    return res


# --------------------------------------------------------------------------
# N7 / §9.2 — LHL: Logic Half-Life
# --------------------------------------------------------------------------
@dataclass
class LHLVariant:
    median_days: Optional[float] = None       # primary basis (v0.4.5 ruling L5/L7)
    median_updates: Optional[float] = None    # derived: median_days / mean interval
    median_months: Optional[float] = None     # median_days / 30.44
    median_reached: bool = False
    n: int = 0
    censored: int = 0


@dataclass
class LHLResult:
    overall: Optional[LHLVariant] = None
    on_path: Optional[LHLVariant] = None
    off_path: Optional[LHLVariant] = None
    on_off_ratio: Optional[float] = None
    mean_update_interval_days: Optional[float] = None
    exclude_first_pair: bool = True           # as REQUESTED by the caller
    first_pair_excluded: bool = False         # what actually happened (ruling L6)
    split_dropped: int = 0                    # instances unclassifiable on/off (ruling L8)
    disclosures: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class _RelInstance:
    key: tuple                    # (pred_code, succ_code, rtype)
    birth_idx: int
    last_alive_idx: int
    lag_state: tuple
    censored: bool = True
    completed_at_idx: Optional[int] = None    # censored at completion (ruling L4b)


def _relationship_signatures(sched: Schedule) -> dict[tuple, tuple]:
    """(pred_code, succ_code, rtype) -> sorted tuple of lag_hours values seen
    under that signature in ``sched`` (usually a single value; kept as a
    tuple to tolerate the rare duplicate-relationship case — note the
    consequence, disclosed: deleting ONE of two duplicates changes the tuple
    and reads as a modification of the merged signature, audit X2).
    Relationships with an LOE/WBS-summary/hammock endpoint are excluded from
    the survival population (ruling L4a — hammock re-tying is bookkeeping,
    not plan instability), as are relationships whose endpoints do not
    resolve to an activity."""
    sig: dict[tuple, list] = {}
    for r in sched.relationships:
        p, q = sched.activities.get(r.pred_uid), sched.activities.get(r.succ_uid)
        if p is None or q is None:
            continue
        if p.is_loe_or_summary or q.is_loe_or_summary:
            continue
        key = (p.code, q.code, r.rtype.value)
        sig.setdefault(key, []).append(round(r.lag_hours, 3))
    return {k: tuple(sorted(v)) for k, v in sig.items()}


def _completed_keys(sched: Schedule, keys) -> set:
    """The subset of ``keys`` whose BOTH endpoints are completed in ``sched``
    (used for censoring at completion, ruling L4b)."""
    by_code = {a.code: a for a in sched.activities.values()}
    out = set()
    for key in keys:
        p, q = by_code.get(key[0]), by_code.get(key[1])
        if p is not None and q is not None and p.completed and q.completed:
            out.add(key)
    return out


def _build_instances(scheds: list[Schedule]) -> list[_RelInstance]:
    """Track every relationship signature's lifespan across ``scheds``.

    A relationship DIES (event) at the first update where its
    (pred_code, succ_code, rtype) key is absent, OR present with a changed
    lag state (type changes are already captured by the key itself
    disappearing).  It is CENSORED (still alive when observation stops) at
    the last schedule, or — ruling L4b — at the first update where both its
    endpoints are completed: logic attached to finished work is effectively
    immortal and would otherwise inflate survival, so observation stops
    there (its live history still counts; a completion-window lag edit is
    treated as completion, i.e. cleanup noise on finished work, not churn).
    Ties born with both endpoints already completed are never observed.
    """
    instances: list[_RelInstance] = []
    open_inst: dict[tuple, _RelInstance] = {}
    retired: set = set()          # completion-censored keys still present
    sigs = [_relationship_signatures(s) for s in scheds]
    comps = [_completed_keys(s, sig.keys()) for s, sig in zip(scheds, sigs)]
    for idx, sig in enumerate(sigs):
        for key in list(open_inst):
            inst = open_inst[key]
            if key not in sig:
                inst.censored = False
                instances.append(inst)
                del open_inst[key]
            elif key in comps[idx]:
                inst.censored = True
                inst.completed_at_idx = idx
                instances.append(inst)
                del open_inst[key]
                retired.add(key)
            elif sig[key] != inst.lag_state:
                inst.censored = False
                instances.append(inst)
                del open_inst[key]
                open_inst[key] = _RelInstance(key=key, birth_idx=idx,
                                              last_alive_idx=idx,
                                              lag_state=sig[key])
            else:
                inst.last_alive_idx = idx
        for key in list(retired):
            if key not in sig:
                retired.discard(key)
        for key, lag_state in sig.items():
            if key in open_inst or key in retired:
                continue
            if key in comps[idx]:
                continue                      # born on completed work: not observed
            open_inst[key] = _RelInstance(key=key, birth_idx=idx,
                                          last_alive_idx=idx,
                                          lag_state=lag_state)
    instances.extend(open_inst.values())
    return instances


_DAYS_PER_MONTH = 30.44


def logic_half_life(series_analysis, exclude_first_pair: bool = True) -> LHLResult:
    """Kaplan-Meier median survival of a relationship signature, in months,
    with an on-driving-path vs. off-path split.

    Conventions (v0.4.5 audit rulings — see docs/audit/LHL_audit_2026-07-09.md
    and ANALYTICS_PROPOSAL §9.2):

    - *Units (L5):* each lifespan is measured directly in CALENDAR DAYS
      between data dates (birth data-date -> death/censor date); KM runs in
      days and months = days / 30.44.  No mean-cadence conversion, so
      irregular update spacing cannot distort the median.  Requires the used
      schedules to carry strictly increasing data dates; otherwise the
      months basis is withheld (never negative, never a silent None — L9), a
      degraded update-count median is reported for information only, and
      LI-02 is ungradeable (L10).
    - *Death dating (L7):* a deletion/modification is only known to fall
      inside the window (last-seen, first-absent]; the death is dated at the
      window MIDPOINT (standard interval-censored convention).
    - *Censoring:* at the last data date, or at completion (L4b — see
      ``_build_instances``).
    - *Not reached (L2):* when S(t) never crosses 0.5 the reported median is
      the longest observed follow-up, flagged ``median_reached=False``.
    - *Split (L8):* an instance is ON-path if its edge was on the
      tool-of-record driving path at ANY update while it was alive
      ("ever became driving"); instances whose alive updates all lack a
      resolvable driving path are dropped from the split (counted in
      ``split_dropped``, disclosed).  Ratio > 1 = driving-path logic MORE
      stable; suppressed unless both medians were actually reached.

    ``exclude_first_pair`` (default True, per §9.2) drops the baseline
    schedule from the survival cohort entirely when at least three schedules
    are available (deaths in the baseline window are unobserved; ties born
    in the baseline start their clock at update 1).  With exactly two
    schedules the exclusion cannot apply and the pair is used;
    ``first_pair_excluded`` reports what actually happened (L6).
    """
    schedules = list(getattr(series_analysis, "schedules", []))
    res = LHLResult(exclude_first_pair=exclude_first_pair)
    if len(schedules) < 2:
        res.reason = "needs at least two schedules to observe relationship survival"
        return res
    if exclude_first_pair and len(schedules) >= 3:
        scheds = schedules[1:]
        res.first_pair_excluded = True
        res.disclosures.append(
            "Baseline pair excluded (default): the baseline schedule is dropped "
            "from the survival cohort — deaths in the baseline window are "
            "unobserved and baseline-born ties start their clock at update 1.")
    else:
        scheds = schedules
        if exclude_first_pair:
            res.disclosures.append(
                "Baseline-pair exclusion REQUESTED BUT NOT APPLIED: it needs at "
                "least three schedules; with exactly two, the baseline pair is "
                "the only observable window and is used.")

    try:
        instances = _build_instances(scheds)
    except Exception as e:                          # pragma: no cover - defensive
        res.reason = f"failed to build relationship instances: {e}"
        return res
    if not instances:
        res.reason = "no relationships observed in the series"
        return res

    res.disclosures.append(
        "Signature = (pred code, succ code, link type), keyed by activity CODE: "
        "a re-coded activity reads as logic death + rebirth (consistent with the "
        "code-keyed logic-churn diff); a lag or type change ends a lifespan "
        "(modification); parallel duplicate ties collapse into one signature "
        "(sorted lag tuple), so deleting one duplicate reads as a modification "
        "of the merged signature.")
    res.disclosures.append(
        "Population: relationships with an LOE/WBS-summary/hammock endpoint are "
        "excluded; ties are censored at the update both endpoints complete; "
        "ties born on already-completed work are not observed; relationships "
        "with unresolvable endpoints are skipped.")

    # -- time basis (rulings L5/L7/L9) -----------------------------------
    dds = [s.data_date for s in scheds]
    intervals = [(b - a).days for a, b in zip(dds, dds[1:])
                 if a is not None and b is not None]
    mean_interval = sum(intervals) / len(intervals) if intervals else None
    res.mean_update_interval_days = mean_interval

    if any(d is None for d in dds):
        dates_ok, dates_problem = False, "one or more schedules lack a data date"
    elif any(b <= a for a, b in zip(dds, dds[1:])):
        dates_ok, dates_problem = False, ("data dates are not strictly "
                                          "increasing across the series")
    else:
        dates_ok, dates_problem = True, ""

    def lifespan_days(inst: _RelInstance) -> float:
        birth = dds[inst.birth_idx]
        if not inst.censored:
            a, b = dds[inst.last_alive_idx], dds[inst.last_alive_idx + 1]
            end = a + (b - a) / 2                 # midpoint of the dying window
        elif inst.completed_at_idx is not None:
            end = dds[inst.completed_at_idx]      # censored at completion
        else:
            end = dds[-1]                         # censored at end of follow-up
        return (end - birth).total_seconds() / 86400.0

    if dates_ok:
        res.disclosures.append(
            "Units: lifespans in calendar days between data dates; deaths dated "
            "at the midpoint of the disappearance window; months = days / 30.44.")
    else:
        res.disclosures.append(
            f"MONTHS BASIS UNAVAILABLE ({dates_problem}): update-count medians "
            "are reported for information only (deaths dated at the last-seen "
            "update); LI-02 is ungradeable on this series.")

    def to_variant(subset: list[_RelInstance]) -> Optional[LHLVariant]:
        if not subset:
            return None
        if dates_ok:
            km = kaplan_meier([(lifespan_days(i), i.censored) for i in subset])
            days = km.median
            return LHLVariant(
                median_days=days,
                median_updates=(days / mean_interval
                                if days is not None and mean_interval else None),
                median_months=(days / _DAYS_PER_MONTH if days is not None else None),
                median_reached=km.median_reached, n=km.n, censored=km.censored)
        km = kaplan_meier([(float(i.last_alive_idx - i.birth_idx), i.censored)
                           for i in subset])
        return LHLVariant(median_days=None, median_updates=km.median,
                          median_months=None, median_reached=km.median_reached,
                          n=km.n, censored=km.censored)

    res.overall = to_variant(instances)
    ov = res.overall
    res.disclosures.append(
        f"Censoring: {ov.censored}/{ov.n} relationship instances censored "
        f"({100.0 * ov.censored / ov.n:.0f}%)."
        + ("" if ov.median_reached else
           "  Median not reached within follow-up; the reported value is the "
           "longest observed follow-up (a lower bound)."))

    # -- on/off-path split (ruling L8: membership at ANY point in life) ---
    edge_cache: dict[int, Optional[set]] = {}
    path_errors: list[str] = []

    def edges_at(idx: int) -> Optional[set]:
        if idx not in edge_cache:
            try:
                dp = driving_path(scheds[idx])
                if dp.steps and len(dp.steps) >= 2:
                    edges = set()
                    for i in range(len(dp.steps) - 1):
                        rel = dp.steps[i].driving_rel
                        if rel is not None:
                            edges.add((dp.steps[i].code, dp.steps[i + 1].code,
                                      rel.rtype.value))
                    edge_cache[idx] = edges
                else:
                    edge_cache[idx] = None
            except Exception as e:                   # pragma: no cover - defensive
                edge_cache[idx] = None
                path_errors.append(str(e))
        return edge_cache[idx]

    on_insts: list[_RelInstance] = []
    off_insts: list[_RelInstance] = []
    dropped = 0
    for inst in instances:
        alive = [edges_at(i) for i in range(inst.birth_idx, inst.last_alive_idx + 1)]
        resolved = [e for e in alive if e is not None]
        if not resolved:
            dropped += 1
            continue
        (on_insts if any(inst.key in e for e in resolved) else off_insts).append(inst)
    res.split_dropped = dropped

    if all(v is None for v in edge_cache.values()):
        res.reason = ("on/off-path split unavailable (driving path could not be "
                     "resolved for any update in the series); overall LHL only." +
                     (f"  ({'; '.join(path_errors)})" if path_errors else ""))
        return res

    res.on_path = to_variant(on_insts)
    res.off_path = to_variant(off_insts)
    res.disclosures.append(
        "Split basis: an instance is on-path if its edge was on the "
        "tool-of-record driving path at ANY update while alive; ratio > 1 = "
        "driving-path logic MORE stable than off-path logic."
        + (f"  {dropped} instance(s) unclassifiable (no resolvable driving path "
           f"during their life) and dropped from the split." if dropped else ""))
    if (res.on_path and res.off_path
            and res.on_path.median_reached and res.off_path.median_reached
            and res.on_path.median_months is not None
            and res.off_path.median_months not in (None, 0)):
        res.on_off_ratio = res.on_path.median_months / res.off_path.median_months
    elif res.on_path and res.off_path:
        res.disclosures.append(
            "On/off ratio suppressed: one or both medians were not reached "
            "(a ratio of lower bounds is not a ratio of half-lives).")
    return res


# --------------------------------------------------------------------------
# N8 / §9.3 — FRB: Forecast Reliability Band
# --------------------------------------------------------------------------
@dataclass
class FRBObservation:
    code: str
    name: str
    forecast_label: str
    resolved_label: str
    horizon_days: float
    error_days: float


@dataclass
class FRBBucket:
    label: str
    lo: float
    hi: float
    n: int = 0
    bias_days: Optional[float] = None
    p10_days: Optional[float] = None
    p90_days: Optional[float] = None


@dataclass
class FRBResult:
    observations: list[FRBObservation] = field(default_factory=list)
    buckets: list[FRBBucket] = field(default_factory=list)
    reason: str = ""


_FRB_BUCKETS = [(0.0, 30.0, "0-30d"), (30.0, 90.0, "30-90d"),
               (90.0, 180.0, "90-180d"), (180.0, float("inf"), ">180d")]


def _bucket_for(horizon_days: float) -> Optional[tuple]:
    for lo, hi, label in _FRB_BUCKETS:
        if lo < horizon_days <= hi:
            return (lo, hi, label)
    return None


def _bucket_stats(errors: list[float]
                  ) -> tuple[int, Optional[float], Optional[float], Optional[float]]:
    """n, bias (median), P10, P90 — all via linear-interpolated percentiles."""
    n = len(errors)
    if n == 0:
        return 0, None, None, None
    return n, percentile(errors, 50), percentile(errors, 10), percentile(errors, 90)


def _add_workdays(start: datetime, days: float) -> datetime:
    """Shift ``start`` by a signed count of Mon-Fri 8h working days (FRB uses
    a fixed calendar, not each activity's own, so forecasts from different
    calendars are bandable on one common scale)."""
    if not days:
        return start
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    cur = start
    guard = 0
    while remaining > 1e-9 and guard < 5000:
        guard += 1
        cur = cur + timedelta(days=step)
        if cur.isoweekday() <= 5:
            remaining -= 1
    frac = abs(days) - int(abs(days))
    if frac:
        cur = cur + timedelta(hours=step * frac * 8.0)
    return cur


def forecast_reliability_band(series_analysis) -> FRBResult:
    """Empirical forecast-error bands: for every update (except the last) and
    every then-incomplete activity, find the first LATER update reporting an
    actual finish (as of its own data date) and record the error — actual
    minus forecast, in working days (Mon-Fri 8h) — bucketed by forecast
    horizon in calendar days."""
    schedules = list(getattr(series_analysis, "schedules", []))
    res = FRBResult()
    if len(schedules) < 2:
        res.reason = "needs at least two schedules to observe a forecast outcome"
        return res

    code_index = [{a.code: a for a in s.activities.values()} for s in schedules]
    for i, u in enumerate(schedules[:-1]):
        if u.data_date is None:
            continue
        for a in u.incomplete_activities:
            f = a.early_finish or a.planned_finish
            if f is None:
                continue
            horizon = (f - u.data_date).days
            for j in range(i + 1, len(schedules)):
                l = schedules[j]
                la = code_index[j].get(a.code)
                if la and la.actual_finish and l.data_date and la.actual_finish <= l.data_date:
                    e = working_days_between(None, f, la.actual_finish)
                    if e is not None:
                        res.observations.append(FRBObservation(
                            code=a.code, name=a.name, forecast_label=u.label(),
                            resolved_label=l.label(), horizon_days=float(horizon),
                            error_days=e))
                    break

    for lo, hi, label in _FRB_BUCKETS:
        errs = [o.error_days for o in res.observations if lo < o.horizon_days <= hi]
        n, bias, p10, p90 = _bucket_stats(errs)
        res.buckets.append(FRBBucket(label=label, lo=lo, hi=hi, n=n,
                                     bias_days=bias, p10_days=p10, p90_days=p90))
    if not res.observations:
        res.reason = ("no activity in the series both carried a forecast finish "
                     "and later reported an actual finish")
    return res


def frb_apply_forward(frb: FRBResult, forecast_finish: Optional[datetime],
                      as_of: Optional[datetime]
                      ) -> tuple[Optional[datetime], Optional[datetime], str]:
    """Given a live forecast finish and the as-of (data) date it was made
    from, return the (P10, P90) completion-date band from the matching
    horizon bucket's empirical error distribution, or (None, None, reason)
    when the bucket does not exist or has fewer than 5 observations."""
    if forecast_finish is None or as_of is None:
        return None, None, "missing forecast finish or as-of date"
    horizon = (forecast_finish - as_of).days
    b = _bucket_for(horizon)
    if b is None:
        return None, None, f"horizon {horizon}d falls outside the defined buckets"
    bucket = next((x for x in frb.buckets if x.label == b[2]), None)
    if bucket is None or bucket.n < 5:
        n = bucket.n if bucket else 0
        return None, None, (f"bucket {b[2]} has only {n} observation(s) (< 5) — "
                           "insufficient track record to band this forecast")
    lo_date = _add_workdays(forecast_finish, bucket.p10_days)
    hi_date = _add_workdays(forecast_finish, bucket.p90_days)
    return lo_date, hi_date, ""


# --------------------------------------------------------------------------
# N11 / §10.1 — BDI: Baseline Dilution Index
# --------------------------------------------------------------------------
@dataclass
class BDIStep:
    code: str
    baseline_original: bool
    length_days: float


@dataclass
class BDIElement:
    code: str
    kind: str                     # "activity" | "relationship"
    detail: str
    first_appeared: str = "NOT FOUND — REVIEW"


@dataclass
class BDIResult:
    bdi_pct: Optional[float] = None
    baseline_label: str = ""
    latest_label: str = ""
    steps: list[BDIStep] = field(default_factory=list)
    decomposition: list[BDIElement] = field(default_factory=list)
    reason: str = ""


def _step_length_days(sched: Schedule, act: Activity) -> float:
    """Remaining duration if the step still has remaining work, else original
    duration (so completed steps still contribute their historical length
    instead of vanishing at RD=0); milestones are 0 either way."""
    hours = act.remaining_duration_hours if act.remaining_duration_hours > 0 \
        else act.original_duration_hours
    cal = sched.cal_for(act)
    hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
    return hours / hpd if hpd else 0.0


def baseline_dilution_index(series_analysis) -> BDIResult:
    """% of the LATEST schedule's driving-path length attributable to
    post-baseline elements: an activity not in the baseline, or one whose
    driving relationship into the next step was not in the baseline's
    relationship set (ANALYTICS_PROPOSAL §10.1)."""
    schedules = list(getattr(series_analysis, "schedules", []))
    res = BDIResult()
    if len(schedules) < 2:
        res.reason = "needs a baseline plus at least one update"
        return res
    baseline, latest = schedules[0], schedules[-1]
    res.baseline_label, res.latest_label = baseline.label(), latest.label()

    try:
        dp = driving_path(latest)
    except Exception as e:                           # pragma: no cover - defensive
        res.reason = f"driving_path failed: {e}"
        return res
    if dp.reason or not dp.steps:
        res.reason = dp.reason or "latest schedule has no driving path"
        return res

    base_codes = {a.code for a in baseline.activities.values()}
    base_edges = set()
    for r in baseline.relationships:
        p, q = baseline.activities.get(r.pred_uid), baseline.activities.get(r.succ_uid)
        if p and q:
            base_edges.add((p.code, q.code, r.rtype.value))

    changesets = list(getattr(series_analysis, "changesets", []))
    total_len = 0.0
    post_len = 0.0
    for i, step in enumerate(dp.steps):
        length = _step_length_days(latest, step.activity)
        total_len += length
        in_baseline_act = step.code in base_codes
        edge = None
        if step.driving_rel is not None and i + 1 < len(dp.steps):
            edge = (step.code, dp.steps[i + 1].code, step.driving_rel.rtype.value)
            edge_in_baseline = edge in base_edges
        else:
            edge_in_baseline = True     # terminal node: nothing to test for (b)
        baseline_original = in_baseline_act and edge_in_baseline
        res.steps.append(BDIStep(code=step.code, baseline_original=baseline_original,
                                 length_days=length))
        if baseline_original:
            continue
        post_len += length

        label = "NOT FOUND — REVIEW"
        if not in_baseline_act:
            for cs in changesets:
                if any(a.code == step.code for a in cs.added):
                    label = cs.later.label()
                    break
            res.decomposition.append(BDIElement(
                code=step.code, kind="activity",
                detail=f"{step.code} is not present in the baseline",
                first_appeared=label))
        else:
            pred_code, succ_code = edge[0], edge[1]
            rtype_val = edge[2]
            for cs in changesets:
                for lc in cs.logic_changes:
                    if (lc.kind == "added" and lc.pred_code == pred_code
                            and lc.succ_code == succ_code
                            and lc.detail.split()[0] == rtype_val):
                        label = cs.later.label()
                        break
                if label != "NOT FOUND — REVIEW":
                    break
            res.decomposition.append(BDIElement(
                code=f"{pred_code}->{succ_code}", kind="relationship",
                detail=f"{rtype_val} relationship {pred_code}->{succ_code} not in baseline",
                first_appeared=label))

    if total_len <= 0:
        res.bdi_pct = 0.0
        res.reason = "driving path has zero total length (all milestones)"
    else:
        res.bdi_pct = 100.0 * post_len / total_len
    return res


# --------------------------------------------------------------------------
# N13 / §10.3 — IL: Intervention Latency
# --------------------------------------------------------------------------
@dataclass
class ILEvent:
    chain_codes: list[str]
    emergence_pair_index: int
    emergence_label: str
    emergence_date: Optional[datetime]
    response_pair_index: Optional[int] = None
    response_label: Optional[str] = None
    response_detail: str = ""
    il_updates: Optional[int] = None
    il_days: Optional[float] = None
    unresolved: bool = False


@dataclass
class ILResult:
    events: list[ILEvent] = field(default_factory=list)
    median_il_updates: Optional[float] = None
    median_il_days: Optional[float] = None
    unresolved_count: int = 0
    reason: str = ""


def _connected_components(edges: list[tuple[str, str]], nodes: set[str]) -> list[set[str]]:
    """Connected components of ``nodes`` under the (undirected) ``edges``
    restricted to pairs both inside ``nodes`` — used to group a negative-float
    activity set into distinct chains."""
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in edges:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    seen: set[str] = set()
    comps: list[set[str]] = []
    for n in nodes:
        if n in seen:
            continue
        stack, comp = [n], set()
        seen.add(n)
        while stack:
            cur = stack.pop()
            comp.add(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        comps.append(comp)
    return comps


def _budget_units_sum(act: Activity) -> float:
    return sum(r.budget_units for r in act.resources)


def _response_in(cs, chain_codes: set[str]) -> str:
    """First responsive edit in ``cs`` touching any code in ``chain_codes``:
    logic added/modified, a duration decrease, a calendar change, or a
    resource/budget-units increase.  Empty string if none found."""
    for lc in cs.logic_changes:
        if lc.kind in ("added", "modified") and (lc.pred_code in chain_codes
                                                  or lc.succ_code in chain_codes):
            return f"logic {lc.kind}: {lc.pred_code}->{lc.succ_code} ({lc.detail})"
    for ch in cs.duration_changes:
        if ch.code in chain_codes:
            try:
                before, after = float(ch.before.rstrip("h")), float(ch.after.rstrip("h"))
            except ValueError:
                before = after = 0.0
            if after < before:
                return f"duration decrease on {ch.code}: {ch.before} -> {ch.after}"
    for ch in cs.calendar_changes:
        if ch.code in chain_codes:
            return f"calendar change on {ch.code}: {ch.before} -> {ch.after}"
    e_by_code = {a.code: a for a in cs.earlier.activities.values()}
    l_by_code = {a.code: a for a in cs.later.activities.values()}
    for code in sorted(chain_codes):
        ea, la = e_by_code.get(code), l_by_code.get(code)
        if ea is not None and la is not None:
            eb, lb = _budget_units_sum(ea), _budget_units_sum(la)
            if lb > eb + 1e-6:
                return f"resource/budget increase on {code}: {eb:.1f} -> {lb:.1f} units"
    return ""


def intervention_latency(series_analysis) -> ILResult:
    """Per update pair, group activities whose total float turned negative
    (TF_later < 0 <= TF_earlier) into connected chains; scan later
    changesets for the first responsive edit touching that chain, measuring
    latency in update pairs and calendar days (ANALYTICS_PROPOSAL §10.3)."""
    changesets = list(getattr(series_analysis, "changesets", []))
    res = ILResult()
    if not changesets:
        res.reason = "needs at least two schedules to observe float transitions"
        return res

    for i, cs in enumerate(changesets):
        e, l = cs.earlier, cs.later
        e_by_code = {a.code: a for a in e.activities.values()}
        l_by_code = {a.code: a for a in l.activities.values()}
        neg_codes: set[str] = set()
        for code in cs.float_deltas:
            ea, la = e_by_code.get(code), l_by_code.get(code)
            if ea is None or la is None:
                continue
            tf_e = ea.total_float_days(e.cal_for(ea))
            tf_l = la.total_float_days(l.cal_for(la))
            if tf_e is not None and tf_l is not None and tf_l < 0 <= tf_e:
                neg_codes.add(code)
        if not neg_codes:
            continue

        edges = [(p.code, q.code) for r in l.relationships
                if (p := l.activities.get(r.pred_uid)) is not None
                and (q := l.activities.get(r.succ_uid)) is not None]
        for comp in _connected_components(edges, neg_codes):
            ev = ILEvent(chain_codes=sorted(comp), emergence_pair_index=i,
                        emergence_label=f"{e.label()} -> {l.label()}",
                        emergence_date=l.data_date)
            for j in range(i + 1, len(changesets)):
                detail = _response_in(changesets[j], comp)
                if detail:
                    ev.response_pair_index = j
                    ev.response_label = (f"{changesets[j].earlier.label()} -> "
                                        f"{changesets[j].later.label()}")
                    ev.response_detail = detail
                    ev.il_updates = j - i
                    rd = changesets[j].later.data_date
                    if rd and l.data_date:
                        ev.il_days = (rd - l.data_date).days
                    break
            if ev.response_pair_index is None:
                ev.unresolved = True
            res.events.append(ev)

    resolved_updates = [ev.il_updates for ev in res.events
                        if not ev.unresolved and ev.il_updates is not None]
    resolved_days = [ev.il_days for ev in res.events
                     if not ev.unresolved and ev.il_days is not None]
    res.unresolved_count = sum(1 for ev in res.events if ev.unresolved)
    if resolved_updates:
        res.median_il_updates = percentile(resolved_updates, 50)
    if resolved_days:
        res.median_il_days = percentile(resolved_days, 50)
    if not res.events:
        res.reason = "no activity transitioned from non-negative to negative total float"
    return res


# --------------------------------------------------------------------------
# N15 / §10.5 — MML: Measured-Mile Locator
# --------------------------------------------------------------------------
MML_CAPTION = "preliminary — measured-mile period selection is confirmed by the expert"


@dataclass
class MMLWindowRow:
    window_label: str
    start: Optional[datetime]
    end: Optional[datetime]
    basis: str                    # "resource" | "activity-day fallback"
    productivity: Optional[float]
    n_activities: int
    excluded_by_event: bool = False


@dataclass
class MMLWbsResult:
    wbs_code: str
    wbs_name: str
    windows: list[MMLWindowRow] = field(default_factory=list)
    clean_window: Optional[MMLWindowRow] = None
    impacted_window: Optional[MMLWindowRow] = None
    ratio: Optional[float] = None
    no_clean_mile: bool = False
    reason: str = ""


@dataclass
class MMLResult:
    wbs_results: list[MMLWbsResult] = field(default_factory=list)
    caption: str = MML_CAPTION
    reason: str = ""


def _root_wbs_uid(sched: Schedule) -> Optional[str]:
    for uid, node in sched.wbs.items():
        if node.parent_uid is None:
            return uid
    return None


def _top_level_ancestor(sched: Schedule, root_uid: str, wbs_uid: Optional[str]):
    seen: set = set()
    cur = wbs_uid
    while cur is not None and cur not in seen:
        seen.add(cur)
        node = sched.wbs.get(cur)
        if node is None:
            return None
        if node.parent_uid == root_uid:
            return node
        cur = node.parent_uid
    return None


def _mml_working_hours(cal, start: Optional[datetime], end: Optional[datetime]) -> float:
    if start is None or end is None or start >= end:
        return 0.0
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


def _default_cal(sched: Schedule):
    for c in sched.calendars.values():
        if c.is_default:
            return c
    return next(iter(sched.calendars.values()), None)


def _overlaps_event(start, end, events) -> bool:
    if not events or start is None or end is None:
        return False
    for ev in events:
        es, ee = ev[0], ev[1]
        if es is None or ee is None:
            continue
        if start <= ee and es <= end:
            return True
    return False


def measured_mile_locator(series_analysis, events: Optional[list[tuple]] = None) -> MMLResult:
    """Per top-level WBS node (children of the project node) and per update-
    pair window, compute productivity (actual resource units consumed per
    working hour, falling back to activity-days completed per working day
    when a node has no resource actuals); locate the clean and most-impacted
    windows and their contrast ratio (ANALYTICS_PROPOSAL §10.5)."""
    schedules = list(getattr(series_analysis, "schedules", []))
    res = MMLResult()
    if len(schedules) < 2:
        res.reason = "needs at least two schedules to observe a productivity window"
        return res
    latest = schedules[-1]
    root_uid = _root_wbs_uid(latest)
    if root_uid is None:
        res.reason = "no project WBS root node found in the latest schedule"
        return res
    top_nodes = [n for n in latest.wbs.values() if n.parent_uid == root_uid]
    if not top_nodes:
        res.reason = "no top-level WBS nodes (children of the project node) found"
        return res

    for node in top_nodes:
        wr = MMLWbsResult(wbs_code=node.code, wbs_name=node.name)
        for e, l in zip(schedules, schedules[1:]):
            e_by_code = {a.code: a for a in e.activities.values()}
            cal = _default_cal(l)
            work_hours = _mml_working_hours(cal, e.data_date, l.data_date)
            work_days = working_days_between(cal, e.data_date, l.data_date) or 0.0
            resource_delta, act_days_completed, n_acts = 0.0, 0.0, 0
            for la in l.activities.values():
                if la.is_loe_or_summary:
                    continue
                top = _top_level_ancestor(l, root_uid, la.wbs_uid)
                if top is None or top.uid != node.uid:
                    continue
                n_acts += 1
                ea = e_by_code.get(la.code)
                if ea is not None:
                    resource_delta += (sum(r.actual_units for r in la.resources)
                                      - sum(r.actual_units for r in ea.resources))
                    if la.completed and not ea.completed:
                        act_days_completed += la.duration_days(l.cal_for(la))
            if resource_delta > 1e-9 and work_hours > 0:
                basis, productivity = "resource", resource_delta / work_hours
            else:
                basis = "activity-day fallback"
                productivity = (act_days_completed / work_days) if work_days > 0 else None
            wr.windows.append(MMLWindowRow(
                window_label=f"{e.label()} -> {l.label()}", start=e.data_date,
                end=l.data_date, basis=basis, productivity=productivity,
                n_activities=n_acts,
                excluded_by_event=_overlaps_event(e.data_date, l.data_date, events)))

        valid = [w for w in wr.windows if w.productivity is not None]
        if not valid:
            wr.reason = ("no productivity could be computed for any window "
                        "(no resource or activity-day data)")
            res.wbs_results.append(wr)
            continue

        clean_candidates = [w for w in valid if not w.excluded_by_event] or valid
        wr.clean_window = max(clean_candidates, key=lambda w: w.productivity)
        wr.impacted_window = min(valid, key=lambda w: w.productivity)
        if wr.clean_window.productivity and wr.clean_window.productivity > 1e-9:
            wr.ratio = max(0.0, min(1.0, wr.impacted_window.productivity
                                    / wr.clean_window.productivity))
        vals = [w.productivity for w in valid]
        spread_tight = (max(vals) - min(vals)) <= 0.15 * max(vals) if max(vals) > 0 else True
        all_overlap_event = bool(events) and all(w.excluded_by_event for w in valid)
        wr.no_clean_mile = spread_tight or all_overlap_event
        res.wbs_results.append(wr)
    return res


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------
@dataclass
class LiRecordResult:
    lhl: LHLResult
    frb: FRBResult
    bdi: BDIResult
    il: ILResult
    mml: MMLResult


def run_li_record(series_analysis, exclude_first_pair: bool = True,
                  events: Optional[list[tuple]] = None) -> LiRecordResult:
    """Compute all five LI-record metrics in one call.  Never raises: each
    metric degrades to an empty/annotated result on its own error."""
    try:
        lhl = logic_half_life(series_analysis, exclude_first_pair=exclude_first_pair)
    except Exception as e:                           # pragma: no cover - defensive
        lhl = LHLResult(reason=f"error: {e}")
    try:
        frb = forecast_reliability_band(series_analysis)
    except Exception as e:                           # pragma: no cover - defensive
        frb = FRBResult(reason=f"error: {e}")
    try:
        bdi = baseline_dilution_index(series_analysis)
    except Exception as e:                           # pragma: no cover - defensive
        bdi = BDIResult(reason=f"error: {e}")
    try:
        il = intervention_latency(series_analysis)
    except Exception as e:                           # pragma: no cover - defensive
        il = ILResult(reason=f"error: {e}")
    try:
        mml = measured_mile_locator(series_analysis, events=events)
    except Exception as e:                           # pragma: no cover - defensive
        mml = MMLResult(reason=f"error: {e}")
    return LiRecordResult(lhl=lhl, frb=frb, bdi=bdi, il=il, mml=mml)
