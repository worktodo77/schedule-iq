"""Monte Carlo / Schedule Risk Analysis (SRA) core (backlog M1 / M2 / M4) — the
engine-side probabilistic module on top of the ported CPM engine (ADR-0007).

Forensic purpose
----------------
Given the analyst-selected target (a completion milestone or any activity), this
module re-schedules the file's network thousands of times under sampled
remaining-duration uncertainty and (optionally) a risk-event register, and
reports the target's completion **distribution** — P10/P50/P80/P90 against the
deterministic engine date — plus the per-activity criticality index, cruciality
(duration-sensitivity), a tornado, and a merge-bias figure.  Every probabilistic
date is a **diagnostic delta** (ADR-0007 §4): the tool-of-record dates remain the
schedule; the deterministic engine date and the tool-of-record record date are
both carried alongside the sample so the three are never confused.

Causation, entitlement (EOT / compensation), concurrency, and quantum remain
**PRELIMINARY**, reserved to the expert (CLAUDE.md §4; AACE 29R-03; SCL Protocol
2nd ed.).  Nothing here states a legal conclusion.

Model decisions (all documented, none hidden — ADR-005)
-------------------------------------------------------
* **Three input tiers** (§4a-c), combinable with per-activity precedence
  ``3-point > template match > calibration/empirical default``; the resolved tier
  and parameters are recorded per activity as *provenance*.
    a. templates — global uncertainty bands by activity type / WBS prefix / code
       prefix, expressed as percentages **relative to the remaining duration**
       (multiplicative).
    b. three_point — per-activity optimistic / most-likely / pessimistic in
       **absolute workdays** (CSV import via :func:`load_three_point_csv`).
    c. empirical — the project's own demonstrated ``actual ÷ planned`` duration
       ratios harvested from the update series (:func:`calibrate_from_series`),
       applied multiplicatively to remaining work.  This mirrors the completed-
       activity duration harvesting in :mod:`scheduleiq.analytics.li_indices`
       (``_demonstrated_series`` / ``Activity.duration_days``) and is the
       forward application of the FRB concept (ANALYTICS_PROPOSAL.md §9.3).
* **Distributions**: triangular, PERT (standard beta-PERT, λ = 4; sampled by
  numerically inverting the regularized incomplete beta — stdlib only), and
  uniform.  Every distribution is sampled by **inverse-CDF from a percentile
  u ∈ [0, 1]**, which is what makes Latin Hypercube stratification and the
  systemic-correlation blend well-defined.
* **Latin Hypercube sampling**: for N iterations × K activity dimensions, each
  dimension's [0, 1] range is split into N equal strata; one jittered sample is
  drawn per stratum and the strata are independently shuffled across iterations
  (:func:`_latin_hypercube`).  This gives even coverage of each activity's
  uncertainty range with far fewer iterations than crude Monte Carlo.
* **Systemic correlation** (rho): a single common factor ``z`` is drawn per
  iteration and blended into every activity's percentile,
  ``u_i = clamp(rho*z + (1-rho)*u_i, 0, 1)``.  This is a documented **rank-blend
  approximation** of positive systemic correlation — NOT a full copula: at
  ``rho = 1`` every activity shares one percentile (perfectly rank-correlated),
  at ``rho = 0`` the LHS draws are independent.  Correlation widens the
  completion distribution (merge-bias mechanics), which is asserted in the tests.
* **Risk events**: each ``{id, probability, impact 3-point, affected_code}`` is a
  Bernoulli trial per iteration; when it fires, the sampled impact (workdays) is
  **added to the affected activity's sampled remaining duration**.  Fragnet
  insertion into the network is OUT OF SCOPE and disclosed — the impact is a
  duration add on an existing activity (default: the target's binding
  predecessor when no ``affected_code`` is given).
* **Iteration engine**: the ingest schedule is bridged to CPM inputs ONCE; each
  iteration mutates only the remaining durations of **incomplete real
  activities** (completed activities stay pinned at their actuals; milestones are
  excluded) in WORKDAYS (round half up, min 0), then reschedules via
  ``run_analysis``.  Per iteration it collects the target early finish, the
  project finish, and per-activity criticality using the **total-float ≤ 0**
  convention documented in :mod:`scheduleiq.analytics.impact` (consistent with
  P5 constraint-free criticality; the engine's longest-path flag is degenerate
  under constraint distortion).

Everything is deterministic given the required ``seed`` — ``to_dict()`` is
byte-stable for a fixed seed.  ``sra_readiness`` is the M4 gate: it screens the
schedule for leads, hard constraints, and open ends (plus the SET-02 handshake)
and either clears the run (READY), brands it (DIAGNOSTIC_ONLY), or refuses it
(REFUSED — the same handshake gate every engine feature uses).
"""
from __future__ import annotations

import copy
import csv
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from ..cpm.bridge import EngineInputs, build_engine_inputs
from ..cpm.calendar_ops import build_workday_table, nearest_workday_index, workday_to_date
from ..cpm.engine import run_analysis
from ..cpm.handshake import (HandshakeRefusal, HandshakeResult, run_handshake)
from ..ingest.model import Activity, ConstraintType, Schedule
# reuse impact.py's target-resolution precedence, record-finish reader, and
# handshake-summary serializer so the engine-side analytics modules stay aligned.
from .impact import _hs_summary, _record_finish, _resolve_target


# ===========================================================================
# module constants (thresholds / caps — with rationale)
# ===========================================================================
# SRA-readiness screens (ANALYTICS_PROPOSAL.md §4): a screen "fails" the moment a
# single instance is present — leads, hard constraints, and open ends each
# distort a Monte Carlo result (a lead compresses the path invisibly, a hard
# constraint pins dates against sampled logic, an open end has no forward path so
# its sampled slippage never reaches the target).  Fuse/Acumen practice brands or
# blocks on exactly these, so the trip count is ZERO, not a tolerance band.
LEAD_SCREEN_MAX = 0
HARD_CONSTRAINT_SCREEN_MAX = 0
OPEN_END_SCREEN_MAX = 0

# The handshake threshold below which EVERY engine feature refuses (ADR-0007);
# the SRA gate uses the same number so simulation is never offered on a file
# whose dates the engine cannot reproduce.
HANDSHAKE_THRESHOLD_DEFAULT = 99.0

# Hard constraints for the SRA screen: MANDATORY_* plus Start-On / Finish-On
# (spec §4 "MANDATORY_*, plus SO/FO") — the two-way pins that override logic.
_HARD_CONSTRAINT_TYPES = frozenset({
    ConstraintType.MANDATORY_START, ConstraintType.MANDATORY_FINISH,
    ConstraintType.START_ON, ConstraintType.FINISH_ON,
})

# Determinism guardrail: iterations are capped so a fat-fingered request cannot
# spin for minutes; the cap is disclosed rather than silently clamped.
ITERATIONS_CAP = 5000
# Tornado / sensitivity table size (spec: top 15 by cruciality).
_TORNADO_TOP_N = 15

_PRELIMINARY = (
    "PRELIMINARY — the completion distribution, criticality index, cruciality, "
    "and merge-bias figures are diagnostic outputs of a schedule risk model; "
    "causation, entitlement (EOT/compensation), concurrency, and quantum are "
    "reserved to the expert (AACE 29R-03; SCL Protocol 2nd ed.)."
)


# ===========================================================================
# small numeric helpers (stdlib only — no numpy/scipy; the repo core is
# stdlib-pure like the engine, confirmed against pyproject.toml)
# ===========================================================================
def _round_half_up(x: float) -> int:
    """Round half away from zero to the nearest integer (P6/CPW convention)."""
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _percentile(sorted_vals: list[float], p: float) -> Optional[float]:
    """Linear-interpolation percentile (type 7), ``p`` in [0, 100]."""
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    rank = (p / 100.0) * (n - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = rank - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _rank(xs: list[float]) -> list[float]:
    """Average (fractional) ranks, tie-aware — for Spearman."""
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0.0 or syy <= 0.0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation = Pearson on average ranks (stdlib only)."""
    return _pearson(_rank(x), _rank(y))


def _variance(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return sum((v - m) ** 2 for v in xs) / (n - 1)


def _norm_ppf(p: float) -> float:
    """Standard-normal quantile (Acklam's rational approximation).  Used only for
    the empirical lognormal-fit sampling mode."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Numerical Recipes ``betacf``)."""
    MAXIT, EPS, FPMIN = 200, 3.0e-12, 1.0e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b) ∈ [0, 1] (Numerical Recipes)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Inverse regularized incomplete beta by bisection (I_x monotone in x).
    Stdlib-only PERT sampling relies on this."""
    p = _clamp01(p)
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _betai(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ===========================================================================
# distribution inverse-CDF samplers (percentile u -> value in the same units)
# ===========================================================================
def _sample_uniform(u: float, low: float, high: float) -> float:
    return low + _clamp01(u) * (high - low)


def _sample_triangular(u: float, low: float, mode: float, high: float) -> float:
    if high <= low:
        return low
    u = _clamp01(u)
    c = (mode - low) / (high - low)
    if u < c:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1.0 - u) * (high - low) * (high - mode))


def _sample_pert(u: float, low: float, mode: float, high: float,
                 lam: float = 4.0) -> float:
    """Standard beta-PERT (λ = 4): map u through the scaled Beta inverse-CDF."""
    if high <= low:
        return low
    a = 1.0 + lam * (mode - low) / (high - low)
    b = 1.0 + lam * (high - mode) / (high - low)
    return low + _beta_ppf(u, a, b) * (high - low)


_DIST_SAMPLERS: dict[str, Callable[[float, float, float, float], float]] = {
    "triangular": lambda u, lo, mo, hi: _sample_triangular(u, lo, mo, hi),
    "pert": lambda u, lo, mo, hi: _sample_pert(u, lo, mo, hi),
    "uniform": lambda u, lo, mo, hi: _sample_uniform(u, lo, hi),
}


def _dist_name(dist: str) -> str:
    d = (dist or "triangular").strip().lower()
    return d if d in _DIST_SAMPLERS else "triangular"


# ===========================================================================
# input-spec dataclasses (§4a-c)
# ===========================================================================
@dataclass
class TemplateRule:
    """Tier (a): a global uncertainty band, matched by activity type, WBS-code
    prefix, or activity-code prefix.  Percentages are RELATIVE to the remaining
    duration (multiplicative): a band low_pct=-20, high_pct=+30 on a 10-wd
    remainder samples between 8 and 13 wd."""
    match: str                       # "" matches all; else atype value / code prefix / WBS prefix
    dist: str = "triangular"
    low_pct: float = 0.0
    high_pct: float = 0.0
    mode_pct: float = 0.0


@dataclass
class ThreePointRow:
    """Tier (b): per-activity three-point in ABSOLUTE remaining workdays."""
    code: str
    optimistic_days: float
    most_likely_days: float
    pessimistic_days: float
    dist: str = "triangular"


@dataclass
class EmpiricalCalibration:
    """Tier (c): the project's demonstrated ``actual ÷ planned`` duration-ratio
    sample, applied multiplicatively to remaining work.  ``sample_ratio`` draws a
    ratio from a percentile: bootstrap from the empirical sample (n < 20) or a
    fitted lognormal (n ≥ 20) — a documented choice."""
    n: int
    ratios: list[float]              # sorted ascending
    mean: float
    p10: Optional[float]
    p50: Optional[float]
    p90: Optional[float]
    method: str = "bootstrap"        # "bootstrap" | "lognormal"
    log_mu: float = 0.0
    log_sigma: float = 0.0
    disclosures: list[str] = field(default_factory=list)

    def sample_ratio(self, u: float) -> float:
        if self.n <= 0:
            return 1.0
        if self.method == "lognormal":
            return math.exp(self.log_mu + self.log_sigma * _norm_ppf(_clamp01(u)))
        idx = min(self.n - 1, int(_clamp01(u) * self.n))
        return self.ratios[idx]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n, "mean": self.mean, "p10": self.p10, "p50": self.p50,
            "p90": self.p90, "method": self.method,
            "log_mu": self.log_mu, "log_sigma": self.log_sigma,
            "disclosures": list(self.disclosures),
        }


@dataclass
class UncertaintySpec:
    """The combined three-tier uncertainty specification.  Per-activity precedence
    at resolution time: an explicit three-point row (by code) beats a template
    match, which beats the empirical calibration default."""
    templates: list[TemplateRule] = field(default_factory=list)
    three_point: list[ThreePointRow] = field(default_factory=list)
    empirical: Optional[EmpiricalCalibration] = None


@dataclass
class ThreePointDist:
    """A three-point distribution over ABSOLUTE workdays (risk-event impacts and
    the internal representation of tier-b rows)."""
    optimistic_days: float
    most_likely_days: float
    pessimistic_days: float
    dist: str = "triangular"

    def sample(self, u: float) -> float:
        s = _DIST_SAMPLERS[_dist_name(self.dist)]
        return s(u, self.optimistic_days, self.most_likely_days, self.pessimistic_days)


@dataclass
class RiskEvent:
    """A probabilistic risk event: Bernoulli(probability) per iteration; when it
    fires, ``impact_dist`` (workdays) is ADDED to the affected activity's sampled
    remaining duration.  ``affected_code`` names the activity; when ``None`` the
    impact lands on the target's binding predecessor.  Fragnet insertion into the
    network is out of scope (disclosed)."""
    id: str
    probability: float
    impact_dist: ThreePointDist
    affected_code: Optional[str] = None


# ===========================================================================
# tier-b CSV loader
# ===========================================================================
def load_three_point_csv(path: str) -> list[ThreePointRow]:
    """Load a per-activity three-point CSV.

    Columns (header row required, case-insensitive): ``code``, ``optimistic_days``,
    ``most_likely_days``, ``pessimistic_days``, and optional ``dist``
    (triangular | pert | uniform; default triangular).  Blank/comment (``#``) rows
    are skipped."""
    rows: list[ThreePointRow] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        norm = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}
        for r in reader:
            code = (r.get(norm.get("code", "code"), "") or "").strip()
            if not code or code.startswith("#"):
                continue
            rows.append(ThreePointRow(
                code=code,
                optimistic_days=float(r[norm["optimistic_days"]]),
                most_likely_days=float(r[norm["most_likely_days"]]),
                pessimistic_days=float(r[norm["pessimistic_days"]]),
                dist=_dist_name((r.get(norm.get("dist", "dist"), "") or "triangular")),
            ))
    return rows


# ===========================================================================
# tier-c empirical calibration (harvest actual ÷ planned from the series)
# ===========================================================================
def _count_workdays_inclusive(cal, d0: date, d1: date) -> int:
    if d0 > d1:
        return 0
    n = 0
    d = d0
    cap = d0 + timedelta(days=20 * 365)
    while d <= d1 and d < cap:
        if cal is None or cal.is_workday(d):
            n += 1
        d += timedelta(days=1)
    return n


def calibrate_from_series(schedules: list[Schedule]) -> EmpiricalCalibration:
    """Harvest the ``actual ÷ planned`` duration ratios of activities completed
    across an ordered update series (mirrors the completed-activity duration
    harvesting in :mod:`scheduleiq.analytics.li_indices`; the forward application
    of the FRB concept, ANALYTICS_PROPOSAL.md §9.3).

    For each completed real activity (deduplicated by code, latest occurrence
    wins) with both actual dates: ``actual`` = workdays between actual start and
    actual finish on its own calendar; ``planned`` = the baseline duration in
    workdays (baseline start→finish) when present, else the original duration in
    workdays.  Ratios with a non-positive numerator or denominator are skipped.
    Robust to missing baselines (disclosed).  Sampling draws a ratio from a
    percentile: bootstrap when n < 20, fitted lognormal when n ≥ 20."""
    disclosures: list[str] = []
    ratios: list[float] = []
    no_baseline = 0
    skipped = 0
    seen: set[str] = set()

    ordered = list(reversed(schedules))  # latest first -> latest completion wins
    for sched in ordered:
        for a in sched.real_activities:
            if a.is_milestone or not a.completed:
                continue
            if a.code in seen:
                continue
            if a.actual_start is None or a.actual_finish is None:
                continue
            seen.add(a.code)
            cal = sched.cal_for(a)
            actual_wd = _count_workdays_inclusive(
                cal, a.actual_start.date(), a.actual_finish.date())
            if a.baseline_start is not None and a.baseline_finish is not None:
                planned_wd = float(_count_workdays_inclusive(
                    cal, a.baseline_start.date(), a.baseline_finish.date()))
            else:
                planned_wd = a.duration_days(cal)
                no_baseline += 1
            if actual_wd <= 0 or planned_wd <= 0:
                skipped += 1
                continue
            ratios.append(actual_wd / planned_wd)

    ratios.sort()
    n = len(ratios)
    if no_baseline:
        disclosures.append(
            f"{no_baseline} completed activity(ies) had no linked baseline; their "
            "planned duration fell back to the original duration in workdays.")
    if skipped:
        disclosures.append(
            f"{skipped} completed activity(ies) skipped (non-positive actual or "
            "planned workday duration).")
    if n == 0:
        disclosures.append("no completed activity yielded a usable actual÷planned "
                           "ratio; empirical calibration is empty.")
        return EmpiricalCalibration(n=0, ratios=[], mean=1.0, p10=None, p50=None,
                                    p90=None, method="bootstrap",
                                    disclosures=disclosures)

    mean = sum(ratios) / n
    method = "bootstrap"
    log_mu = log_sigma = 0.0
    if n >= 20:
        logs = [math.log(r) for r in ratios]
        log_mu = sum(logs) / n
        log_sigma = math.sqrt(sum((x - log_mu) ** 2 for x in logs) / (n - 1))
        method = "lognormal"
        disclosures.append(
            f"n={n} ≥ 20: sampling uses a fitted lognormal (μ={log_mu:.4f}, "
            f"σ={log_sigma:.4f}) rather than a bootstrap of the raw sample.")
    else:
        disclosures.append(
            f"n={n} < 20: sampling bootstraps the raw ratio sample (no distribution "
            "fitted).")
    return EmpiricalCalibration(
        n=n, ratios=ratios, mean=mean,
        p10=_percentile(ratios, 10), p50=_percentile(ratios, 50),
        p90=_percentile(ratios, 90), method=method,
        log_mu=log_mu, log_sigma=log_sigma, disclosures=disclosures)


# ===========================================================================
# M4 — SRA-readiness gate
# ===========================================================================
@dataclass
class SraReadiness:
    """The M4 screen result.  ``verdict`` is READY (clear), DIAGNOSTIC_ONLY
    (simulate but brand), or REFUSED (handshake below threshold — the same gate
    every engine feature uses)."""
    verdict: str
    leads: int
    hard_constraints: int
    open_ends: int
    handshake_passed: bool
    handshake: Optional[dict[str, Any]] = None
    screens_failed: list[str] = field(default_factory=list)
    open_end_codes: list[str] = field(default_factory=list)

    def branding(self) -> Optional[str]:
        if self.verdict == "DIAGNOSTIC_ONLY":
            return ("DIAGNOSTIC ONLY — SRA-readiness screens failed: "
                    + "; ".join(self.screens_failed))
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "leads": self.leads,
            "hard_constraints": self.hard_constraints,
            "open_ends": self.open_ends,
            "open_end_codes": list(self.open_end_codes),
            "handshake_passed": self.handshake_passed,
            "screens_failed": list(self.screens_failed),
            "branding": self.branding(),
            "handshake": self.handshake,
            "screen_definitions": {
                "leads": "relationships with a negative lag (lead)",
                "hard_constraints": "MANDATORY_START/FINISH, START_ON, FINISH_ON",
                "open_ends": ("incomplete real non-milestone activities with no "
                              "predecessor OR no successor relationship"),
            },
        }


def _count_screens(sched: Schedule) -> tuple[int, int, int, list[str]]:
    """(leads, hard_constraints, open_ends, open_end_codes) — engine-independent."""
    leads = sum(1 for r in sched.relationships if r.lag_hours < 0)

    hard = 0
    for a in sched.real_activities:
        for ct in (a.constraint, a.constraint2):
            if ct in _HARD_CONSTRAINT_TYPES:
                hard += 1

    have_pred: set[str] = set()
    have_succ: set[str] = set()
    for r in sched.relationships:
        have_pred.add(r.succ_uid)     # succ has a predecessor
        have_succ.add(r.pred_uid)     # pred has a successor
    open_codes: list[str] = []
    for a in sched.real_activities:
        if a.completed or a.is_milestone:
            continue
        if a.uid not in have_pred or a.uid not in have_succ:
            open_codes.append(a.code)
    open_codes.sort()
    return leads, hard, len(open_codes), open_codes


def sra_readiness(sched: Schedule,
                  threshold_pct: float = HANDSHAKE_THRESHOLD_DEFAULT) -> SraReadiness:
    """Screen ``sched`` for SRA readiness (M4, ANALYTICS_PROPOSAL.md §4).

    REFUSED when the ADR-0007 handshake is below ``threshold_pct`` (engine cannot
    reproduce the file's dates); otherwise DIAGNOSTIC_ONLY when any of the
    leads / hard-constraint / open-end screens trips, else READY."""
    leads, hard, open_ends, open_codes = _count_screens(sched)
    try:
        hs = run_handshake(sched, threshold_pct=threshold_pct)
        hs_summary = _hs_summary(hs)
        passed = hs.passed
    except Exception as exc:  # pragma: no cover - defensive
        hs_summary = {"error": f"handshake unavailable: {exc}"}
        passed = False

    screens: list[str] = []
    if leads > LEAD_SCREEN_MAX:
        screens.append(f"{leads} lead(s) (negative lags)")
    if hard > HARD_CONSTRAINT_SCREEN_MAX:
        screens.append(f"{hard} hard constraint(s) (MANDATORY/SO/FO)")
    if open_ends > OPEN_END_SCREEN_MAX:
        screens.append(f"{open_ends} open end(s)")

    if not passed:
        verdict = "REFUSED"
    elif screens:
        verdict = "DIAGNOSTIC_ONLY"
    else:
        verdict = "READY"

    return SraReadiness(
        verdict=verdict, leads=leads, hard_constraints=hard, open_ends=open_ends,
        handshake_passed=passed, handshake=hs_summary, screens_failed=screens,
        open_end_codes=open_codes)


# ===========================================================================
# Latin Hypercube sampling (module-level so it is directly testable)
# ===========================================================================
def _latin_hypercube(n: int, k: int, rng: random.Random) -> list[list[float]]:
    """N×K matrix of stratified [0, 1) percentiles.  Each column splits [0, 1)
    into N strata; one jittered sample is taken per stratum and the strata are
    independently shuffled across the N rows.  Guarantees exactly one sample in
    each of the N strata per dimension (the LHS property)."""
    matrix: list[list[float]] = [[0.0] * k for _ in range(n)]
    for col in range(k):
        perm = list(range(n))
        rng.shuffle(perm)
        for row in range(n):
            jitter = rng.random()
            matrix[row][col] = (perm[row] + jitter) / n
    return matrix


# ===========================================================================
# per-activity resolution (tier precedence + provenance)
# ===========================================================================
@dataclass
class _Varying:
    uid: str
    code: str
    base_remaining: int              # base remaining duration in workdays
    in_progress: bool
    tier: str
    sampler: Callable[[float], float]  # percentile u -> final remaining workdays
    params: dict[str, Any]


@dataclass
class ActivityProvenance:
    code: str
    uid: str
    tier: str
    base_remaining_workdays: int
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "uid": self.uid, "tier": self.tier,
                "base_remaining_workdays": self.base_remaining_workdays,
                "params": self.params}


def _template_matches(rule: TemplateRule, act: Activity, sched: Schedule) -> bool:
    m = rule.match or ""
    if m == "":
        return True
    if act.atype.value == m:
        return True
    if act.code.startswith(m):
        return True
    wbs = sched.wbs.get(act.wbs_uid) if act.wbs_uid else None
    if wbs is not None and (wbs.code or "").startswith(m):
        return True
    return False


def _make_absolute_sampler(dist: str, low: float, mode: float, high: float
                           ) -> Callable[[float], float]:
    s = _DIST_SAMPLERS[_dist_name(dist)]
    return lambda u: s(u, low, mode, high)


def _make_multiplicative_sampler(dist: str, base: float, low_pct: float,
                                 mode_pct: float, high_pct: float
                                 ) -> Callable[[float], float]:
    low = base * (1.0 + low_pct / 100.0)
    mode = base * (1.0 + mode_pct / 100.0)
    high = base * (1.0 + high_pct / 100.0)
    s = _DIST_SAMPLERS[_dist_name(dist)]
    return lambda u: s(u, low, mode, high)


def _resolve_varying(sched: Schedule, ei: EngineInputs, spec: UncertaintySpec
                     ) -> list[_Varying]:
    """Resolve each incomplete real non-milestone activity to a distribution by
    precedence (3-point > template > empirical), recording provenance.  Activities
    matched by no tier are FIXED (omitted here — no dimension)."""
    tp_by_code = {r.code: r for r in spec.three_point}
    base_by_uid = {a.act_id: a for a in ei.activities}
    out: list[_Varying] = []
    for a in sched.real_activities:
        if a.completed or a.is_milestone:
            continue
        base_act = base_by_uid.get(a.uid)
        if base_act is None:
            continue
        if a.in_progress:
            base_rem = base_act.remaining_duration
            in_prog = True
        else:
            base_rem = base_act.original_duration
            in_prog = False
        if base_rem is None:
            base_rem = 0
        base_rem = int(base_rem)

        tier: str
        sampler: Callable[[float], float]
        params: dict[str, Any]

        tp = tp_by_code.get(a.code)
        if tp is not None:
            tier = "three_point"
            sampler = _make_absolute_sampler(
                tp.dist, tp.optimistic_days, tp.most_likely_days, tp.pessimistic_days)
            params = {"dist": _dist_name(tp.dist),
                      "optimistic_days": tp.optimistic_days,
                      "most_likely_days": tp.most_likely_days,
                      "pessimistic_days": tp.pessimistic_days,
                      "units": "absolute workdays"}
        else:
            rule = next((r for r in spec.templates if _template_matches(r, a, sched)),
                        None)
            if rule is not None:
                tier = "template"
                sampler = _make_multiplicative_sampler(
                    rule.dist, float(base_rem), rule.low_pct, rule.mode_pct,
                    rule.high_pct)
                params = {"dist": _dist_name(rule.dist), "match": rule.match,
                          "low_pct": rule.low_pct, "mode_pct": rule.mode_pct,
                          "high_pct": rule.high_pct,
                          "units": "percent of remaining duration"}
            elif spec.empirical is not None and spec.empirical.n > 0:
                tier = "empirical"
                emp = spec.empirical
                sampler = (lambda u, _b=float(base_rem), _e=emp:
                           _b * _e.sample_ratio(u))
                params = {"method": emp.method, "n": emp.n,
                          "units": "actual÷planned ratio × remaining duration"}
            else:
                continue  # no tier -> fixed activity, not a dimension

        out.append(_Varying(uid=a.uid, code=a.code, base_remaining=base_rem,
                            in_progress=in_prog, tier=tier, sampler=sampler,
                            params=params))
    out.sort(key=lambda v: v.code)
    return out


# ===========================================================================
# result container
# ===========================================================================
@dataclass
class SimulationResult:
    iterations: int = 0
    seed: int = 0
    correlation: float = 0.0
    target_uid: Optional[str] = None
    target_code: Optional[str] = None
    target_name: Optional[str] = None
    resolved_how: str = ""
    target_calendar: str = ""

    readiness: Optional[dict[str, Any]] = None
    branding: Optional[str] = None
    handshake_mode: str = "require"

    # deterministic + record anchors (presentation rule)
    deterministic_engine_finish: Optional[date] = None
    deterministic_offset: Optional[int] = None
    record_finish: Optional[date] = None

    # the target completion sample (offsets for math, dates for display)
    target_offsets: list[int] = field(default_factory=list)
    target_dates: list[str] = field(default_factory=list)

    percentiles: dict[str, Any] = field(default_factory=dict)
    criticality_index: list[dict[str, Any]] = field(default_factory=list)
    cruciality: list[dict[str, Any]] = field(default_factory=list)
    tornado: list[dict[str, Any]] = field(default_factory=list)
    merge_bias: dict[str, Any] = field(default_factory=dict)
    input_provenance: list[dict[str, Any]] = field(default_factory=list)
    risk_events: list[dict[str, Any]] = field(default_factory=list)

    disclosures: list[str] = field(default_factory=list)
    preliminary: str = _PRELIMINARY

    def percentile_date(self, key: str) -> Optional[str]:
        p = self.percentiles.get(key)
        return p.get("date") if isinstance(p, dict) else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "seed": self.seed,
            "correlation": self.correlation,
            "target": {"uid": self.target_uid, "code": self.target_code,
                       "name": self.target_name, "calendar": self.target_calendar,
                       "resolved_how": self.resolved_how},
            "readiness": self.readiness,
            "branding": self.branding,
            "handshake_mode": self.handshake_mode,
            "presentation_rule": (
                "Tool-of-record dates are the schedule; the probabilistic dates "
                "below are diagnostic. The deterministic engine finish and the "
                "record finish are carried alongside, never merged (ADR-0007 §4)."),
            "deterministic_engine_finish": (
                self.deterministic_engine_finish.isoformat()
                if self.deterministic_engine_finish else None),
            "record_finish": (self.record_finish.isoformat()
                              if self.record_finish else None),
            "percentiles": self.percentiles,
            "target_sample": {"offsets": list(self.target_offsets),
                              "dates": list(self.target_dates)},
            "criticality_index": self.criticality_index,
            "cruciality": self.cruciality,
            "tornado": self.tornado,
            "merge_bias": self.merge_bias,
            "input_provenance": self.input_provenance,
            "risk_events": self.risk_events,
            "disclosures": list(self.disclosures),
            "preliminary": self.preliminary,
        }


# ===========================================================================
# iteration engine helpers
# ===========================================================================
def _run_ei(ei: EngineInputs, activities) -> Any:
    return run_analysis(
        activities=activities,
        relationships=ei.relationships,
        project_start=ei.project_start,
        workday_table=ei.workday_table,
        calendar=ei.calendar,
        convention=ei.convention,
        calendar_registry=ei.calendar_registry,
        lag_strategy=ei.lag_strategy,
        constraints=ei.constraints or None,
        statusing_mode=ei.statusing_mode,
    )


def _mutate_activities(base_acts, changes: dict[str, int], inprog: set[str]):
    """Return an activities list with ``changes`` (uid -> new remaining workdays)
    applied; unchanged activities are shared (the engine copies internally)."""
    out = []
    for a in base_acts:
        nr = changes.get(a.act_id)
        if nr is None:
            out.append(a)
        else:
            b = copy.copy(a)
            if a.act_id in inprog:
                b.remaining_duration = nr
            else:
                b.original_duration = nr
            out.append(b)
    return out


def _widen_tables(ei: EngineInputs) -> None:
    """Extend the default workday table and per-calendar registry tables so that
    inflated sampled durations never run off the end of the table."""
    lo = ei.project_start - timedelta(days=120)
    hi = ei.project_start + timedelta(days=3650)   # 10y headroom; cheap at ~20 acts
    ei.workday_table = build_workday_table(ei.calendar, lo, hi)
    ei.calendar_registry.ensure_workday_tables(lo, hi)


# ===========================================================================
# public entry point
# ===========================================================================
def run_simulation(sched: Schedule, *, target: Optional[str] = None,
                   spec: UncertaintySpec, iterations: int = 1000,
                   seed: int, correlation: float = 0.0,
                   risk_events: Optional[list[RiskEvent]] = None,
                   handshake: str = "require",
                   threshold_pct: float = HANDSHAKE_THRESHOLD_DEFAULT
                   ) -> SimulationResult:
    """Run the Monte Carlo / SRA simulation for ``target`` on ``sched``.

    ``seed`` is REQUIRED — the run is fully deterministic (determinism is a hard
    requirement; there is no entropy default).  ``handshake="require"`` gates on
    the M4 readiness verdict and raises :class:`HandshakeRefusal` on REFUSED;
    ``handshake="skip"`` bypasses the refusal (disclosed).  A DIAGNOSTIC_ONLY
    verdict stamps every result dict with a ``branding`` string.
    """
    if handshake not in ("require", "skip"):
        raise ValueError(f"handshake must be 'require' or 'skip', got {handshake!r}")

    out = SimulationResult(seed=seed, correlation=correlation, handshake_mode=handshake)

    # -- M4 readiness gate ----------------------------------------------------
    readiness = sra_readiness(sched, threshold_pct=threshold_pct)
    out.readiness = readiness.to_dict()
    out.branding = readiness.branding()
    if readiness.verdict == "REFUSED":
        if handshake == "skip":
            out.disclosures.append(
                "handshake='skip': the ADR-0007 validation gate was BYPASSED "
                "(analyst/test escape hatch); the file did NOT pass SET-02, so the "
                "probabilistic dates are unvalidated against the record.")
        else:
            hs = readiness.handshake or {}
            raise HandshakeRefusal(
                "ADR-0007 validation handshake refused: SET-02 match rate "
                f"{hs.get('match_rate_pct')}% is below the "
                f"{threshold_pct:.0f}% threshold. The Monte Carlo module will not "
                "run against this file; the tool-of-record dates remain the "
                "schedule. (Pass handshake='skip' to override for diagnostics.)")
    elif readiness.verdict == "DIAGNOSTIC_ONLY":
        out.disclosures.append(readiness.branding())

    # -- iterations cap -------------------------------------------------------
    if iterations > ITERATIONS_CAP:
        out.disclosures.append(
            f"requested {iterations} iterations capped at {ITERATIONS_CAP} "
            "(determinism/performance guardrail).")
        iterations = ITERATIONS_CAP
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    out.iterations = iterations
    if not (0.0 <= correlation <= 1.0):
        raise ValueError("correlation (rho) must be in [0, 1]")

    # -- target resolution (record dates; engine-independent) -----------------
    tgt, how = _resolve_target(sched, target)
    out.resolved_how = how
    if tgt is None:
        out.disclosures.append(f"target could not be resolved: {how}")
        return out
    out.target_uid, out.target_code, out.target_name = tgt.uid, tgt.code, tgt.name
    cal = sched.cal_for(tgt)
    out.target_calendar = (cal.name or cal.uid) if cal else (tgt.calendar_uid or "")
    out.record_finish = (_record_finish(tgt).date()
                         if _record_finish(tgt) is not None else None)

    # -- bridge ONCE + widen tables ------------------------------------------
    ei = build_engine_inputs(sched)
    out.disclosures.extend(ei.disclosures)
    _widen_tables(ei)

    # deterministic baseline run (the reference the sample is measured against)
    base = _run_ei(ei, ei.activities)
    if base is None or not base.is_valid:
        raise ValueError("Monte Carlo cannot run: the baseline engine network is "
                         "invalid (blocking validation issues); simulation needs a "
                         "schedulable network.")
    det_sa = base.scheduled.get(tgt.uid)
    if det_sa is None:
        out.disclosures.append("target not present in the engine population; no "
                               "simulation performed.")
        return out
    det_ef = det_sa.early_finish
    out.deterministic_engine_finish = det_ef

    # unified target-calendar workday table for commensurable offsets
    tgt_tbl = (ei.calendar_registry.get_workday_table(tgt.calendar_uid)
               if tgt.calendar_uid else None) or ei.workday_table
    det_offset = nearest_workday_index(tgt_tbl, det_ef)
    out.deterministic_offset = det_offset

    # -- resolve per-activity distributions (tier precedence + provenance) ----
    varying = _resolve_varying(sched, ei, spec)
    out.input_provenance = [
        ActivityProvenance(v.code, v.uid, v.tier, v.base_remaining, v.params).to_dict()
        for v in varying]
    inprog_uids = {v.uid for v in varying if v.in_progress}
    K = len(varying)

    risk_events = list(risk_events or [])
    if risk_events:
        out.disclosures.append(
            "risk events add sampled impact days to an affected activity's "
            "remaining duration; fragnet insertion into the network is out of "
            "scope for this wave (disclosed).")
        # resolve affected uid for each event (default: target binding predecessor)
        code_to_uid = {a.code: a.uid for a in sched.real_activities}
        default_pred = _binding_predecessor(ei, base, tgt.uid)
    resolved_risk: list[tuple[RiskEvent, Optional[str]]] = []
    for ev in risk_events:
        if ev.affected_code is not None:
            auid = code_to_uid.get(ev.affected_code)
        else:
            auid = default_pred
        resolved_risk.append((ev, auid))
        out.risk_events.append({
            "id": ev.id, "probability": ev.probability,
            "affected_code": ev.affected_code,
            "affected_uid": auid,
            "impact_dist": {"dist": _dist_name(ev.impact_dist.dist),
                            "optimistic_days": ev.impact_dist.optimistic_days,
                            "most_likely_days": ev.impact_dist.most_likely_days,
                            "pessimistic_days": ev.impact_dist.pessimistic_days}})

    # activities that a risk event can mutate even if they carry no distribution
    risk_uids = {auid for _, auid in resolved_risk if auid is not None}
    risk_inprog = {a.uid for a in sched.real_activities
                   if a.in_progress and a.uid in risk_uids}
    inprog_uids |= risk_inprog
    base_remaining_of: dict[str, int] = {}
    base_by_uid = {a.act_id: a for a in ei.activities}
    for auid in risk_uids:
        ba = base_by_uid.get(auid)
        if ba is None:
            continue
        rem = ba.remaining_duration if ba.remaining_duration is not None else ba.original_duration
        base_remaining_of[auid] = int(rem or 0)

    # -- the Monte Carlo loop -------------------------------------------------
    rng = random.Random(seed)
    lhs = _latin_hypercube(iterations, K, rng)

    offsets: list[int] = []
    dates: list[str] = []
    sampled_matrix: list[list[int]] = []          # per iteration, per varying act
    crit_counts: dict[str, int] = {v.uid: 0 for v in varying}
    # also track criticality for every incomplete real activity (index output)
    all_incomplete = [a for a in sched.real_activities if not a.completed]
    crit_counts_all: dict[str, int] = {a.uid: 0 for a in all_incomplete}
    code_by_uid = {a.uid: a.code for a in sched.real_activities}
    name_by_uid = {a.uid: a.name for a in sched.real_activities}

    for i in range(iterations):
        z = rng.random()
        changes: dict[str, int] = {}
        # seed risk-affected activities with their base remaining so an impact
        # can be added even when the activity carries no distribution.
        remaining_now: dict[str, int] = dict(base_remaining_of)
        row: list[int] = []
        for k, v in enumerate(varying):
            u = _clamp01(correlation * z + (1.0 - correlation) * lhs[i][k])
            val = v.sampler(u)
            rd = max(0, _round_half_up(val))
            row.append(rd)
            remaining_now[v.uid] = rd
        sampled_matrix.append(row)

        # risk events (Bernoulli + impact add), consuming rng in a fixed order
        for ev, auid in resolved_risk:
            rb = rng.random()
            ru = rng.random()
            if rb < ev.probability and auid is not None:
                impact = max(0, _round_half_up(ev.impact_dist.sample(ru)))
                remaining_now[auid] = remaining_now.get(auid, 0) + impact

        # only activities whose remaining actually differs from base need mutation
        for uid, rd in remaining_now.items():
            ba = base_by_uid.get(uid)
            if ba is None:
                continue
            base_rem = (ba.remaining_duration if uid in inprog_uids
                        else ba.original_duration)
            if base_rem is None:
                base_rem = 0
            if rd != int(base_rem):
                changes[uid] = rd

        res = _run_ei(ei, _mutate_activities(ei.activities, changes, inprog_uids))
        if res is None or not res.is_valid:  # pragma: no cover - defensive
            raise RuntimeError(f"iteration {i} produced an invalid network; "
                               "durations-only mutation should preserve validity.")
        sa = res.scheduled.get(tgt.uid)
        ef = sa.early_finish
        offsets.append(nearest_workday_index(tgt_tbl, ef))
        dates.append(ef.isoformat())
        for a in all_incomplete:
            s2 = res.scheduled.get(a.uid)
            if s2 is not None and s2.total_float <= 0:
                crit_counts_all[a.uid] += 1
                if a.uid in crit_counts:
                    crit_counts[a.uid] += 1

    out.target_offsets = offsets
    out.target_dates = dates

    # -- percentiles ----------------------------------------------------------
    srt = sorted(offsets)
    out.percentiles = _percentile_block(srt, tgt_tbl, det_ef, det_offset,
                                        out.record_finish)

    # -- criticality index (all incomplete, TF<=0 convention) ----------------
    crit_rows = []
    for a in all_incomplete:
        if a.is_milestone:
            # milestones can be critical too; include for completeness
            pass
        crit_rows.append({
            "code": a.code, "uid": a.uid,
            "criticality_index_pct": round(100.0 * crit_counts_all[a.uid] / iterations, 2),
        })
    crit_rows.sort(key=lambda r: (-r["criticality_index_pct"], r["code"]))
    out.criticality_index = crit_rows

    # -- cruciality (|Spearman(sampled duration, target offset)|) + tornado ---
    cruc_rows = []
    for k, v in enumerate(varying):
        col = [sampled_matrix[i][k] for i in range(iterations)]
        rho_s = _spearman([float(c) for c in col], [float(o) for o in offsets])
        cruc_rows.append({
            "code": v.code, "uid": v.uid, "tier": v.tier,
            "cruciality": round(abs(rho_s), 4),
            "spearman": round(rho_s, 4),
            "criticality_index_pct": round(100.0 * crit_counts[v.uid] / iterations, 2),
        })
    cruc_rows.sort(key=lambda r: (-r["cruciality"], r["code"]))
    out.cruciality = cruc_rows
    out.tornado = cruc_rows[:_TORNADO_TOP_N]

    # -- merge bias (target: deterministic vs P50) ---------------------------
    p50_off = out.percentiles.get("P50", {}).get("offset")
    out.merge_bias = {
        "scope": "target only",
        "note": ("merge bias at the target = P50 completion offset − deterministic "
                 "completion offset (workdays); the top merge-node exhibit from "
                 "§2.3 is deferred — only the target merge bias is computed here."),
        "deterministic_offset": det_offset,
        "p50_offset": p50_off,
        "merge_bias_workdays": (round(p50_off - det_offset, 2)
                                if p50_off is not None else None),
    }
    if spec.empirical is not None:
        out.disclosures.extend(spec.empirical.disclosures)

    return out


def _binding_predecessor(ei: EngineInputs, res, target_uid: str) -> Optional[str]:
    """The predecessor whose early finish is nearest the target's early start —
    the default risk-impact landing point when no ``affected_code`` is given."""
    tsa = res.scheduled.get(target_uid)
    if tsa is None:
        return None
    preds = [r.pred_id for r in ei.relationships if r.succ_id == target_uid]
    best = None
    best_ef = None
    for pid in preds:
        psa = res.scheduled.get(pid)
        if psa is None:
            continue
        if best_ef is None or psa.early_finish > best_ef:
            best_ef, best = psa.early_finish, pid
    return best if best is not None else target_uid


def _percentile_block(sorted_offsets: list[int], tgt_tbl: dict[date, int],
                      det_ef: date, det_offset: int,
                      record_finish: Optional[date]) -> dict[str, Any]:
    def _to_date(off: Optional[float]) -> Optional[str]:
        if off is None:
            return None
        try:
            return workday_to_date(int(round(off)), tgt_tbl).isoformat()
        except Exception:  # pragma: no cover - clamped table edges
            return None

    block: dict[str, Any] = {
        "convention": ("offsets are workday numbers on the target calendar; dates "
                       "map the offset back to a calendar date. P-values are "
                       "diagnostic vs the deterministic engine finish."),
        "deterministic_engine_finish": det_ef.isoformat(),
        "deterministic_offset": det_offset,
        "record_finish": record_finish.isoformat() if record_finish else None,
    }
    for key, p in (("P10", 10.0), ("P50", 50.0), ("P80", 80.0), ("P90", 90.0)):
        off = _percentile([float(o) for o in sorted_offsets], p)
        block[key] = {
            "offset": round(off, 2) if off is not None else None,
            "date": _to_date(off),
            "workdays_vs_deterministic": (round(off - det_offset, 2)
                                          if off is not None else None),
        }
    return block
