"""Offline duration-uncertainty priors — the S10 research track
(ANALYTICS_PROPOSAL.md §6.10), scoped to the survival / ML duration-prior model
ONLY.  The "LLM-drafted quality narratives" half of §6.10 is OUT of scope here
(it lives behind expert-assist's verification gates and API access).

What this is
------------
Pool the benchmark corpus's ``actual ÷ planned`` duration-ratio samples
(:mod:`scheduleiq.analytics.corpus`), optionally sector-filtered, and fit:

  (a) empirical quantiles (always) — type-7, identical to the Monte Carlo core;
  (b) a lognormal MLE fit (μ = mean of log-ratios, σ = population std of the
      log-ratios) with a Kolmogorov-Smirnov goodness-of-fit statistic;
  (c) a Kaplan-Meier-style survival adjustment for the RIGHT-CENSORED in-progress
      observations (RD > 0 at the last update = censored at the current ratio),
      when the corpus rows carry them.  If no censored data is present it is
      noted and skipped — no invented censoring.

Everything is stdlib-only math (mirroring the Monte Carlo core's discipline —
no numpy / scipy).  Below ``min_n`` pooled observations the fit REFUSES
(NOT FITTED with a reason) — no thin-data priors, ever.

The governance wall (§6.10, verbatim)
-------------------------------------
No black-box number may reach a report.  Priors surface ONLY as Monte Carlo
spec inputs and internal diagnostics, both clearly labelled.  Therefore:

* every output dict carries the ``governance`` sentinel string
  :data:`GOVERNANCE` and a ``provenance`` block (corpus n, sectors, fit method,
  KS stat, censoring counts);
* :func:`to_uncertainty_spec` returns an
  :class:`~scheduleiq.analytics.montecarlo.EmpiricalCalibration` whose
  ``disclosures`` carry the governance + provenance strings, so that when a
  simulation runs with a research prior the provenance THREADS THROUGH into
  ``SimulationResult.disclosures`` (montecarlo appends ``spec.empirical
  .disclosures`` verbatim — we ride that channel; montecarlo.py is NOT modified).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# the governance wall (verbatim, §6.10)
# ---------------------------------------------------------------------------
GOVERNANCE = ("RESEARCH PRIOR — internal diagnostic input only; no black-box "
              "number may reach a report; Monte Carlo outputs using research "
              "priors carry their provenance")

DEFAULT_MIN_N = 30


# ---------------------------------------------------------------------------
# stdlib numerics (type-7 percentile + standard-normal CDF via erf)
# ---------------------------------------------------------------------------
def _percentile(sorted_vals: list[float], p: float) -> Optional[float]:
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


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------
@dataclass
class DurationPriors:
    fitted: bool
    n: int                                  # pooled uncensored observations
    sectors: list[str]
    reason: str = ""                        # populated when NOT FITTED
    min_n: int = DEFAULT_MIN_N
    ratios: list[float] = field(default_factory=list)          # sorted
    censored: list[float] = field(default_factory=list)        # sorted
    empirical: dict[str, Any] = field(default_factory=dict)
    lognormal: Optional[dict[str, Any]] = None
    survival: Optional[dict[str, Any]] = None
    governance: str = GOVERNANCE
    disclosures: list[str] = field(default_factory=list)

    def provenance(self) -> dict[str, Any]:
        """The provenance block that must accompany every output (§6.10)."""
        return {
            "corpus_n": self.n,
            "sectors": list(self.sectors),
            "fit_method": (self.lognormal.get("method") if self.lognormal
                           else "empirical-only"),
            "ks_stat": (self.lognormal.get("ks_stat") if self.lognormal else None),
            "censoring": {
                "n_observed": self.n,
                "n_censored": len(self.censored),
                "estimator": ("kaplan-meier (right-censored in-progress ratios)"
                              if self.survival else "none (no censored data)"),
            },
        }

    def provenance_line(self) -> str:
        """A single-line provenance string suitable for a disclosures channel."""
        p = self.provenance()
        return ("RESEARCH-PRIOR PROVENANCE — "
                f"corpus n={p['corpus_n']}, sectors={p['sectors']}, "
                f"fit={p['fit_method']}, KS={p['ks_stat']}, "
                f"censored={p['censoring']['n_censored']} of "
                f"{p['censoring']['n_observed'] + p['censoring']['n_censored']}.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fitted": self.fitted,
            "not_fitted_reason": self.reason if not self.fitted else None,
            "n": self.n,
            "min_n": self.min_n,
            "sectors": list(self.sectors),
            "empirical": self.empirical,
            "lognormal": self.lognormal,
            "survival": self.survival,
            "governance": self.governance,
            "provenance": self.provenance(),
            "disclosures": list(self.disclosures),
        }


# ---------------------------------------------------------------------------
# lognormal MLE + KS
# ---------------------------------------------------------------------------
def _fit_lognormal(ratios: list[float]) -> dict[str, Any]:
    """Lognormal MLE on positive ratios: μ = mean(log r), σ = population std of
    log r (MLE, divides by n), plus the KS statistic vs the empirical CDF."""
    logs = [math.log(r) for r in ratios]
    n = len(logs)
    mu = sum(logs) / n
    var = sum((x - mu) ** 2 for x in logs) / n            # MLE (population)
    sigma = math.sqrt(var)
    ks = _ks_lognormal(sorted(ratios), mu, sigma)
    return {"method": "lognormal_mle", "mu": mu, "sigma": sigma,
            "ks_stat": round(ks, 6),
            "note": ("μ = mean of log-ratios; σ = population std of log-ratios "
                     "(MLE); KS = sup|F_empirical − F_lognormal|.")}


def _ks_lognormal(sorted_ratios: list[float], mu: float, sigma: float) -> float:
    """One-sample KS distance between the empirical CDF of ``sorted_ratios`` and
    the fitted lognormal CDF."""
    n = len(sorted_ratios)
    if n == 0:
        return 0.0
    d = 0.0
    for i, x in enumerate(sorted_ratios):
        if sigma <= 0.0:
            f = 1.0 if x >= math.exp(mu) else 0.0
        else:
            f = _norm_cdf((math.log(x) - mu) / sigma)
        d = max(d, abs((i + 1) / n - f), abs(f - i / n))
    return d


# ---------------------------------------------------------------------------
# Kaplan-Meier survival adjustment (right-censored in-progress ratios)
# ---------------------------------------------------------------------------
def _kaplan_meier(events: list[float], censored: list[float]) -> dict[str, Any]:
    """Kaplan-Meier survival S(t) = P(ratio > t) treating a completed ratio as
    an EVENT at its value and an in-progress ratio as RIGHT-CENSORED at its
    current value.

    At each distinct event time t_i (ascending): n_i = observations (events +
    censored) with value >= t_i (at risk); d_i = events at exactly t_i;
    S(t_i) = Π_{j<=i} (1 − d_j / n_j).  Censored observations stay at risk up to
    their censoring time and then leave without an event (they lower n_i for
    later times only).  The survival-adjusted median is the smallest t with
    S(t) <= 0.5 (None if survival never falls to 0.5 — the sample is too
    censored to reach the median, disclosed)."""
    all_obs = [(v, True) for v in events] + [(v, False) for v in censored]
    n_total = len(all_obs)
    event_times = sorted(set(events))
    steps: list[dict[str, Any]] = []
    surv = 1.0
    for t in event_times:
        at_risk = sum(1 for v, _ in all_obs if v >= t)
        d = sum(1 for v in events if v == t)
        if at_risk > 0:
            surv *= (1.0 - d / at_risk)
        steps.append({"t": round(t, 6), "at_risk": at_risk, "events": d,
                      "survival": round(surv, 6)})
    median = None
    for s in steps:
        if s["survival"] <= 0.5:
            median = s["t"]
            break
    return {
        "estimator": "kaplan-meier (right-censored in-progress ratios)",
        "n_total": n_total, "n_events": len(events), "n_censored": len(censored),
        "steps": steps,
        "median_ratio": median,
        "note": ("S(t) = P(actual÷planned ratio > t); in-progress activities are "
                 "right-censored at their current (actual-so-far ÷ planned) "
                 "ratio.  Median = smallest t with S(t) <= 0.5."),
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def fit_duration_priors(corpus, *, sector: Optional[str] = None,
                        min_n: int = DEFAULT_MIN_N) -> DurationPriors:
    """Fit offline duration-uncertainty priors from ``corpus``' pooled
    actual÷planned ratio samples (optionally sector-filtered).  Below ``min_n``
    pooled observations the fit REFUSES (NOT FITTED, disclosed)."""
    rows = [r for r in corpus.rows if sector is None or r.sector == sector]
    sectors = sorted({r.sector for r in rows})
    ratios: list[float] = []
    censored: list[float] = []
    for r in rows:
        ratios.extend(float(x) for x in r.ratio_sample)
        censored.extend(float(x) for x in r.censored_sample)
    ratios = sorted(x for x in ratios if x > 0.0)
    censored = sorted(x for x in censored if x > 0.0)
    n = len(ratios)

    priors = DurationPriors(fitted=False, n=n, sectors=sectors, min_n=min_n,
                            ratios=ratios, censored=censored)

    if n < min_n:
        priors.reason = (f"NOT FITTED — only {n} pooled ratio observation(s) "
                         f"{'in sector ' + repr(sector) if sector else 'in the corpus'} "
                         f"(< min_n={min_n}); no thin-data priors are produced "
                         "(§6.10 governance).")
        priors.disclosures.append(priors.reason)
        return priors

    # (a) empirical quantiles — always
    priors.empirical = {
        "n": n, "mean": round(sum(ratios) / n, 6),
        "min": ratios[0], "max": ratios[-1],
        "p10": _percentile(ratios, 10.0), "p25": _percentile(ratios, 25.0),
        "p50": _percentile(ratios, 50.0), "p75": _percentile(ratios, 75.0),
        "p90": _percentile(ratios, 90.0),
    }

    # (b) lognormal MLE + KS
    priors.lognormal = _fit_lognormal(ratios)

    # (c) Kaplan-Meier survival adjustment (only when censored data present)
    if censored:
        priors.survival = _kaplan_meier(ratios, censored)
        priors.disclosures.append(
            f"{len(censored)} right-censored in-progress observation(s) folded "
            "into a Kaplan-Meier survival adjustment.")
    else:
        priors.disclosures.append(
            "no censored (in-progress) observations in the corpus rows; the "
            "Kaplan-Meier survival adjustment is skipped (noted, not invented).")

    priors.fitted = True
    priors.disclosures.append(GOVERNANCE)
    return priors


def to_uncertainty_spec(priors: DurationPriors, *, dist: str = "empirical"):
    """Expose fitted priors as the empirical tier of
    :class:`~scheduleiq.analytics.montecarlo.UncertaintySpec` — an
    :class:`EmpiricalCalibration` that ``run_simulation`` consumes UNCHANGED.

    ``dist="empirical"`` bootstraps the pooled ratio sample; ``dist="lognormal"``
    uses the fitted μ / σ.  The governance + provenance strings are attached to
    the calibration's ``disclosures`` so they THREAD THROUGH into
    ``SimulationResult.disclosures`` (montecarlo rides that channel verbatim)."""
    from .montecarlo import EmpiricalCalibration
    if not priors.fitted:
        raise ValueError("cannot build an uncertainty spec from NOT-FITTED "
                         f"priors: {priors.reason}")
    d = (dist or "empirical").strip().lower()
    if d not in ("empirical", "lognormal"):
        raise ValueError(f"dist must be 'empirical' or 'lognormal', got {dist!r}")

    ratios = sorted(priors.ratios)
    n = len(ratios)
    emp = priors.empirical
    disclosures = [GOVERNANCE, priors.provenance_line()]

    if d == "lognormal":
        ln = priors.lognormal or {}
        return EmpiricalCalibration(
            n=n, ratios=ratios, mean=emp["mean"],
            p10=emp["p10"], p50=emp["p50"], p90=emp["p90"],
            method="lognormal", log_mu=ln.get("mu", 0.0),
            log_sigma=ln.get("sigma", 0.0), disclosures=disclosures)
    return EmpiricalCalibration(
        n=n, ratios=ratios, mean=emp["mean"],
        p10=emp["p10"], p50=emp["p50"], p90=emp["p90"],
        method="bootstrap", disclosures=disclosures)


def prior_report(priors: DurationPriors) -> dict[str, Any]:
    """Internal diagnostic summary (quantiles, fit params, KS, censoring) for
    the internal workbook surface — a later wiring step; this only produces the
    dict.  Carries the governance sentinel and the provenance block (§6.10)."""
    return {
        "title": "Duration-uncertainty research priors (internal diagnostic)",
        "fitted": priors.fitted,
        "not_fitted_reason": priors.reason if not priors.fitted else None,
        "n": priors.n,
        "sectors": list(priors.sectors),
        "empirical_quantiles": priors.empirical,
        "lognormal_fit": priors.lognormal,
        "survival_adjustment": priors.survival,
        "governance": GOVERNANCE,
        "provenance": priors.provenance(),
        "disclosures": list(priors.disclosures),
        "surface": ("INTERNAL DIAGNOSTIC ONLY — this dict feeds the internal "
                    "workbook and Monte Carlo spec inputs; no value here may be "
                    "quoted as a report number (§6.10 governance wall)."),
    }
