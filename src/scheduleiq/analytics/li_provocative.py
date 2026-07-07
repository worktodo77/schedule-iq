"""LI-proprietary provocative indices (backlog N16-N20; ANALYTICS_PROPOSAL §11).

The third bespoke LI metric set — deliberately provocative triage instruments
that quantify things experts normally leave to instinct or advocacy:

* **SMI** — Schedule Manipulation Indicator (§11.1): a composite of the
  independent curation signals already computed (TRD-05 retroactive actuals,
  LOG-10 hollow logic, SET-01 settings flips, CAL-04 calendar edits,
  statistical anomalies, DUR-03/-04 silent replans, and churn timing), each
  scored for presence, severity, and timing on a PUBLISHED weighting, 0-100.
* **DDI** — Directed Date Index (§11.2): consecutive updates a milestone date
  held station multiplied by the mean deterioration z-score of the schedule's
  own fundamentals over that span.
* **ARR** — Attribution Robustness Ratio (§11.3): per party, min share / max
  share of attributed delay across the computable N4 robustness variants.
* **PPS** — Pacing Plausibility Score (§11.4): the recognized pacing criteria
  scored per §6.3 pacing candidate on a published weighting, 0-100.
* **RSA** — Rebuttal Surface Area (§11.5): the share of attributed delay
  resting on contested ground (method-sensitive / data-fragile /
  path-ambiguous), with every component named and classified.

Binding guardrails (§11, CLAUDE.md §2/§4).  Every output of this module:

* is a TRIAGE INDICATOR — "observations consistent with …", NEVER a finding of
  intent or of manipulation; the standing sentence cap is "warrants
  explanation" and no stronger language appears anywhere in the output;
* decomposes to named, citable observations (an index the expert cannot
  explain observation-by-observation is a liability);
* enumerates the innocent explanations for every contributing signal in the
  output text itself, so the tribunal-duty principle (evidence presented both
  ways) is built in, not left to the analyst's discipline;
* defaults to a PRIVILEGED / INTERNAL surface (``privileged=True``,
  ``surface="internal"``): these indices are not part of the standard report.

Nothing here raises: every entry point degrades to a result carrying a
``reason`` string, matching ``analytics.li_indices`` / ``analytics.paths``.
ARR and RSA ride on the N4 methodology sweep and take a precomputed
``RobustnessCertificate`` (or its ``to_dict()``); when none is supplied, or the
sweep carried no responsibility overlay, they degrade to NOT COMPUTABLE (they
do NOT import the certificate machinery, keeping this module free of the CPM
dependency).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

# The standing sentence cap: no output of this module carries language stronger
# than this (§11.1 — "expressly excluded from report language stronger than
# 'warrants explanation'").  Deliberately avoids the words "intent" and
# "manipulation proven".
SENTENCE_CAP = "warrants explanation"
SURFACE = "internal"
NOT_COMPUTABLE = "NOT COMPUTABLE"

_TRIAGE_NOTE = (
    "Triage indicator only — an observation consistent with schedule curation "
    "that " + SENTENCE_CAP + ".  It is not a finding that any curation occurred, "
    "and every contributing signal has innocent explanations that must be "
    "checked against the contemporaneous record (CLAUDE.md §2/§4; SCL Protocol "
    "2nd ed.; AACE RP 29R-03).")


# ==========================================================================
# 1. SMI — Schedule Manipulation Indicator  (§11.1, N16 -> LI-11)
# ==========================================================================
# Published weighting (constants + rationale).  Each curation signal carries a
# weight reflecting how directly it rewrites the record without touching visible
# scope: retroactive actual-date changes (TRD-05) and scheduling-settings flips
# (SET-01) each silently re-time the whole forecast, so they are weighted as
# critical (3) — the same weight the Report Card gives them and the level at
# which TRD-05 is a series gate; hollow logic (LOG-10) and silent replans
# (DUR-03/-04) are strong corroborating signals (2); calendar-definition edits
# (CAL-04) and the statistical anomaly screen (STAT) are supporting signals (1).
SMI_SIGNAL_WEIGHTS: dict[str, float] = {
    "TRD-05": 3.0,   # retroactive actual-date changes
    "SET-01": 3.0,   # scheduling-settings drift / flips
    "LOG-10": 2.0,   # hollow logic inserted into existing chains
    "DUR":    2.0,   # silent replans (DUR-03 not-started RD edits + DUR-04)
    "CAL-04": 1.0,   # calendar-definition edits
    "STAT":   1.0,   # Benford / round-number / percent-step anomalies
}
# Count at which a count-based signal's severity saturates to 100.  Mirrors the
# Report Card's zero-tolerance ``count_ceiling`` (5): five offending records is
# the point a "should never happen" condition has become systemic rather than
# isolated.
SMI_SATURATION = 5.0
# Sub-weights within one signal's 0-100 score: presence that the signal fired at
# all, its severity (saturating count), and its timing correlation with a claim
# submission.  When no claim dates are available the timing sub-weight is dropped
# and presence/severity are renormalized (disclosed) — the score is never
# punished for absent event data.
SMI_SUB_WEIGHTS = {"presence": 0.30, "severity": 0.50, "timing": 0.20}
# A signal edit "before a claim" if it lands within this many calendar days
# ahead of a claim-submission date drawn from the D6 event list.
SMI_CHURN_WINDOW_DAYS = 60

SMI_INNOCENT_EXPLANATIONS: dict[str, str] = {
    "TRD-05": ("retroactive corrections may reflect legitimate record cleanup or "
               "the correction of a prior mis-keying — verify against daily "
               "reports and the contemporaneous record."),
    "SET-01": ("a scheduling-settings change may reflect a deliberate, disclosed "
               "methodology decision (e.g. adopting progress override after an "
               "out-of-sequence period) — verify against the update narratives."),
    "LOG-10": ("a short inserted activity may represent genuine newly-defined "
               "scope or added detail rather than path engineering — verify "
               "against the change register and correspondence."),
    "DUR":    ("remaining-duration reductions may reflect real re-planning, "
               "resequencing, or productivity gains — verify against progress "
               "records and the basis of estimate."),
    "CAL-04": ("a calendar edit may reflect a legitimate shift-pattern or "
               "holiday-schedule change agreed for the works — verify against "
               "the contract calendar and correspondence."),
    "STAT":   ("digit, round-number and percent-step signatures can arise from "
               "legitimate templated estimating or rounded reporting "
               "conventions — a prompt for inquiry against the basis of "
               "estimate, never proof."),
}

SMI_SIGNAL_LABELS: dict[str, str] = {
    "TRD-05": "retroactive actual-date changes",
    "SET-01": "scheduling-settings drift",
    "LOG-10": "hollow logic",
    "DUR":    "silent remaining-duration replans (DUR-03/DUR-04)",
    "CAL-04": "calendar-definition edits",
    "STAT":   "statistical anomalies (Benford / round-number / percent-step)",
}


@dataclass
class SmiSignal:
    key: str
    label: str
    weight: float
    count: int
    presence: float                 # 0 or 100
    severity: float                 # 0-100 (saturating count)
    timing: Optional[float]         # 0/100 or None when no claim dates
    score: float                    # 0-100 signal composite
    findings: list[str]             # named underlying observations
    innocent_explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {"signal": self.key, "label": self.label, "weight": self.weight,
                "count": self.count, "presence": _r(self.presence),
                "severity": _r(self.severity), "timing": _r(self.timing),
                "score": _r(self.score), "findings": list(self.findings),
                "innocent_explanation": self.innocent_explanation}


@dataclass
class SmiResult:
    smi: Optional[float] = None
    signals: list[SmiSignal] = field(default_factory=list)
    timing_available: bool = False
    interpretation: str = ""
    note: str = _TRIAGE_NOTE
    privileged: bool = True
    surface: str = SURFACE
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": "SMI", "smi": _r(self.smi),
                "signals": [s.to_dict() for s in self.signals],
                "timing_available": self.timing_available,
                "interpretation": self.interpretation, "note": self.note,
                "privileged": self.privileged, "surface": self.surface,
                "reason": self.reason}


def _smi_signal_score(count: int, timing: Optional[float]) -> tuple[float, float, float]:
    """Return (presence, severity, signal_score) for one signal.

    presence = 100 if count > 0 else 0; severity = 100*min(1, count/SATURATION);
    the signal composite blends presence/severity/timing on ``SMI_SUB_WEIGHTS``,
    renormalizing over presence+severity when ``timing`` is None (no claim
    dates)."""
    presence = 100.0 if count > 0 else 0.0
    severity = 100.0 * min(1.0, count / SMI_SATURATION)
    wp, ws, wt = (SMI_SUB_WEIGHTS["presence"], SMI_SUB_WEIGHTS["severity"],
                  SMI_SUB_WEIGHTS["timing"])
    if timing is None:
        denom = wp + ws
        score = (wp * presence + ws * severity) / denom if denom else 0.0
    else:
        score = wp * presence + ws * severity + wt * timing
    return presence, severity, score


def _compute_smi(signal_counts: dict[str, int],
                 timing_hits: dict[str, Optional[bool]],
                 findings: dict[str, list[str]],
                 claim_dates_available: bool) -> SmiResult:
    """Core SMI arithmetic over the six published signals.  Exported via the
    public entry point; kept separate so the composite can be unit-tested on
    hand-built counts (mirrors ``robustness.compute_stability_stats``)."""
    res = SmiResult(timing_available=claim_dates_available)
    wsum = 0.0
    acc = 0.0
    for key, weight in SMI_SIGNAL_WEIGHTS.items():
        count = int(signal_counts.get(key, 0))
        hit = timing_hits.get(key)
        timing = None if not claim_dates_available or hit is None else (100.0 if hit else 0.0)
        presence, severity, score = _smi_signal_score(count, timing)
        res.signals.append(SmiSignal(
            key=key, label=SMI_SIGNAL_LABELS[key], weight=weight, count=count,
            presence=presence, severity=severity, timing=timing, score=score,
            findings=list(findings.get(key, [])),
            innocent_explanation=SMI_INNOCENT_EXPLANATIONS[key]))
        acc += weight * score
        wsum += weight
    res.smi = acc / wsum if wsum else 0.0
    fired = [s for s in res.signals if s.count > 0]
    lead = max(res.signals, key=lambda s: s.weight * s.score) if res.signals else None
    band = ("run the standard checks and move on" if res.smi < 30
            else ("review the contributing signals" if res.smi < 60
                  else "budget for forensic review"))
    res.interpretation = (
        f"SMI {res.smi:.1f}/100 across {len(fired)} of {len(res.signals)} "
        f"curation signals"
        + (f"; {lead.label} is the largest contributor" if lead and lead.score else "")
        + f" — {band}.  {_TRIAGE_NOTE}"
        + ("" if claim_dates_available else
           "  (No claim-submission dates were available from the event list, so "
           "the timing sub-score is omitted and presence/severity are "
           "renormalized — disclosed.)"))
    return res


def _claim_dates(events: Optional[list]) -> list[datetime]:
    """Claim-submission dates drawn from the D6 event list: any event whose
    title/category names a claim/EOT submission."""
    out: list[datetime] = []
    for ev in events or []:
        title = str(ev.get("title") or "").lower()
        cat = str(ev.get("category") or ev.get("type") or "").lower()
        if "claim" in title or "claim" in cat or "eot" in title or "eot" in cat:
            d = ev.get("finish") or ev.get("start")
            if isinstance(d, datetime):
                out.append(d)
    return out


def _timing_hit(change_dates: list[datetime], claim_dates: list[datetime]) -> bool:
    for cd in change_dates:
        for claim in claim_dates:
            if 0 <= (claim - cd).days <= SMI_CHURN_WINDOW_DAYS:
                return True
    return False


def schedule_manipulation_indicator(sa, events: Optional[list] = None) -> SmiResult:
    """Composite SMI over the series ``sa``.  Reads the already-computed curation
    checks off ``sa.series_results`` (TRD-05/SET-01/CAL-04/LOG-10/DUR-04), the
    per-file DUR-03 result, and the statistical screen, scoring each for
    presence/severity/timing on the published weighting."""
    schedules = list(getattr(sa, "schedules", []))
    if len(schedules) < 2:
        return SmiResult(reason="series has fewer than two updates")

    counts: dict[str, int] = {}
    finds: dict[str, list[str]] = {}
    change_dates: dict[str, list[datetime]] = {}

    def _grab(cid: str, key: str) -> None:
        r = _series_result(sa, cid)
        if r is None:
            counts[key] = 0
            finds[key] = []
            return
        counts[key] = int(r.value or 0)
        finds[key] = [f"{f.object_id}: {f.detail}" for f in r.findings[:10]]

    _grab("TRD-05", "TRD-05")
    _grab("SET-01", "SET-01")
    _grab("CAL-04", "CAL-04")
    _grab("LOG-10", "LOG-10")

    # DUR: silent replans = DUR-04 (series) + DUR-03 (latest per-file).
    dur04 = _series_result(sa, "DUR-04")
    dur_count = int(dur04.value or 0) if dur04 else 0
    dur_finds = ([f"{f.object_id}: {f.detail}" for f in dur04.findings[:8]]
                 if dur04 else [])
    dur03 = None
    for a in reversed(getattr(sa, "assessments", [])):
        r = a.result("DUR-03") if hasattr(a, "result") else None
        if r is not None and r.value is not None:
            dur03 = r
            break
    if dur03 is not None:
        dur_count += int(dur03.value or 0)
        dur_finds += [f"{f.object_id}: {f.detail}" for f in dur03.findings[:4]]
    counts["DUR"] = dur_count
    finds["DUR"] = dur_finds

    # STAT: statistical-anomaly count on the latest schedule (Benford screen).
    stat_count, stat_finds = _stat_anomalies(schedules)
    counts["STAT"] = stat_count
    finds["STAT"] = stat_finds

    # timing: concentrate change dates per signal against claim dates.
    claim_dates = _claim_dates(events)
    available = bool(claim_dates)
    for cs in getattr(sa, "changesets", []):
        dd = getattr(cs.later, "data_date", None)
        if not isinstance(dd, datetime):
            continue
        if cs.actual_date_changes:
            change_dates.setdefault("TRD-05", []).append(dd)
        if cs.calendar_def_changes:
            change_dates.setdefault("CAL-04", []).append(dd)
    timing_hits: dict[str, Optional[bool]] = {}
    for key in SMI_SIGNAL_WEIGHTS:
        cds = change_dates.get(key)
        timing_hits[key] = _timing_hit(cds, claim_dates) if cds else None

    return _compute_smi(counts, timing_hits, finds, available)


def _stat_anomalies(schedules) -> tuple[int, list[str]]:
    """Count statistical-anomaly flags on the latest schedule via the Benford
    screen: excessive round-5 duration concentration, percent-complete step-5
    clustering, and a heavy last-digit chi-square.  Returns (count, names)."""
    try:
        from .statistical import benford_screen
        rs = benford_screen(schedules)
    except Exception:                       # pragma: no cover - defensive
        return 0, []
    if not rs:
        return 0, []
    b = rs[-1]
    hits: list[str] = []
    if b.round5_pct is not None and b.round5_pct > 60.0:
        hits.append(f"{b.round5_pct:.0f}% of durations are 5-day multiples")
    if b.n_in_progress_pct and b.pct_step5_pct is not None and b.pct_step5_pct > 80.0:
        hits.append(f"{b.pct_step5_pct:.0f}% of in-progress %-complete on 5% steps")
    if b.chi2_last_digit is not None and b.chi2_last_digit > 27.88:   # ~chi2_0.001, df9
        hits.append(f"last-digit chi-square {b.chi2_last_digit:.1f} (heavy)")
    return len(hits), hits


# ==========================================================================
# 2. DDI — Directed Date Index  (§11.2, N17 -> LI-12)
# ==========================================================================
DDI_MIN_UPDATES = 3          # need >= 3 records to z-score the fundamentals
DDI_DATE_TOL_DAYS = 1        # a held date is one within +-1 day of the prior update

DDI_FUNDAMENTALS = ("RDI (recovery debt)", "BWI (bow-wave)",
                    "FCBI (criticality-weighted burn)",
                    "constraint additions near target",
                    "uncompensated duration compressions")

_DDI_FINDING = (
    "the forecast completion is increasingly unsupported by the schedule's own "
    "internal indicators")


@dataclass
class DdiResult:
    ddi: Optional[float] = None
    target_code: Optional[str] = None
    held_updates: int = 0
    held_labels: list[str] = field(default_factory=list)
    mean_deterioration_z: Optional[float] = None
    fundamentals: dict[str, list[Optional[float]]] = field(default_factory=dict)
    per_update_z: list[Optional[float]] = field(default_factory=list)
    interpretation: str = ""
    note: str = _TRIAGE_NOTE
    privileged: bool = True
    surface: str = SURFACE
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": "DDI", "ddi": _r(self.ddi), "target_code": self.target_code,
                "held_updates": self.held_updates, "held_labels": list(self.held_labels),
                "mean_deterioration_z": _r(self.mean_deterioration_z),
                "fundamentals": {k: [_r(x) for x in v]
                                 for k, v in self.fundamentals.items()},
                "per_update_z": [_r(x) for x in self.per_update_z],
                "interpretation": self.interpretation, "note": self.note,
                "finding": _DDI_FINDING, "privileged": self.privileged,
                "surface": self.surface, "reason": self.reason}


def _zscores(series: list[Optional[float]]) -> list[Optional[float]]:
    """Population z-scores of a per-update fundamental series; ``None`` entries
    pass through as ``None``; a zero-variance (or <2 observed) series yields all
    zeros (no deterioration signal, not undefined)."""
    vals = [v for v in series if v is not None]
    if len(vals) < 2:
        return [0.0 if v is not None else None for v in series]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = math.sqrt(var)
    if std <= 0:
        return [0.0 if v is not None else None for v in series]
    return [((v - mean) / std) if v is not None else None for v in series]


def _ddi_arithmetic(fundamentals: dict[str, list[Optional[float]]],
                    held_indices: list[int]
                    ) -> tuple[Optional[float], list[Optional[float]], Optional[float]]:
    """The DDI product.  z-score each fundamental across all updates (oriented so
    higher = more deterioration), average the available z's per update, then
    average over ``held_indices`` and multiply by the held count.

    Returns (ddi, per_update_mean_z, mean_over_held).  Exported for unit
    testing on hand-built fundamentals."""
    if not fundamentals:
        return None, [], None
    n = max(len(v) for v in fundamentals.values())
    z_by_fund = {k: _zscores(v) for k, v in fundamentals.items()}
    per_update: list[Optional[float]] = []
    for i in range(n):
        zs = [z_by_fund[k][i] for k in z_by_fund
              if i < len(z_by_fund[k]) and z_by_fund[k][i] is not None]
        per_update.append(sum(zs) / len(zs) if zs else None)
    held_z = [per_update[i] for i in held_indices
              if 0 <= i < len(per_update) and per_update[i] is not None]
    if not held_z:
        return None, per_update, None
    mean_held = sum(held_z) / len(held_z)
    return len(held_indices) * mean_held, per_update, mean_held


def _held_run(finish_dates: list[Optional[datetime]],
              tol_days: int = DDI_DATE_TOL_DAYS) -> list[int]:
    """Indices of the maximal TRAILING run of updates over which the milestone
    finish held station (each within ``tol_days`` of the previous update's
    finish).  A run of ``k`` held intervals spans ``k+1`` update indices."""
    idx = [i for i, d in enumerate(finish_dates) if d is not None]
    if len(idx) < 2:
        return list(idx)
    # walk backwards from the end while consecutive present finishes hold
    run = [idx[-1]]
    for k in range(len(idx) - 1, 0, -1):
        later, earlier = idx[k], idx[k - 1]
        if abs((finish_dates[later] - finish_dates[earlier]).days) <= tol_days:
            run.append(earlier)
        else:
            break
    return sorted(run)


def directed_date_index(sa, indices=None, target: Optional[str] = None) -> DdiResult:
    """DDI over the series ``sa``.  Resolves the terminal/selected milestone
    (default: the latest late-type-constrained finish milestone, as BWI does),
    counts the trailing updates its forecast finish held station, and multiplies
    by the mean deterioration z-score of the fundamentals over that span.

    ``indices`` may be a precomputed :class:`li_indices.LiIndicesResult` (reused
    to avoid recomputing the float paths); otherwise it is computed here."""
    schedules = list(getattr(sa, "schedules", []))
    if len(schedules) < DDI_MIN_UPDATES:
        return DdiResult(reason=f"{NOT_COMPUTABLE}: DDI needs at least "
                                f"{DDI_MIN_UPDATES} updates to z-score the "
                                "fundamentals (short series)")
    from .li_indices import run_li_indices, _resolve_bwi_target, _find_by_code, _late_type
    ri = indices if indices is not None else run_li_indices(sa)

    tgt = target or _resolve_bwi_target(schedules, None)
    res = DdiResult(target_code=tgt)
    if tgt is None:
        res.reason = f"{NOT_COMPUTABLE}: no terminal milestone could be resolved"
        return res

    finish_dates: list[Optional[datetime]] = []
    for s in schedules:
        a = _find_by_code(s, tgt)
        finish_dates.append(a.finish if a is not None else None)

    held = _held_run(finish_dates)
    res.held_updates = len(held)
    res.held_labels = [schedules[i].label() for i in held]

    # fundamentals per update (oriented so higher = more deterioration).
    n = len(schedules)
    rdi_series = [(ri.rdi.rows[i].cumulative_days if i < len(ri.rdi.rows) else None)
                  for i in range(n)]
    bwi_series = [(ri.bwi.rows[i].bwi if i < len(ri.bwi.rows) else None)
                  for i in range(n)]
    # FCBI cumulative burn: n-1 windows -> align to updates with a leading 0.
    fcbi_cum = list(ri.fcbi.cumulative)
    fcbi_series: list[Optional[float]] = [0.0] + fcbi_cum if fcbi_cum else [None] * n
    fcbi_series = (fcbi_series + [None] * n)[:n]

    constraint_series: list[Optional[float]] = []
    for s in schedules:
        cnt = 0
        tgt_fin = None
        ta = _find_by_code(s, tgt)
        tgt_fin = ta.finish if ta is not None else None
        for a in s.activities.values():
            if getattr(a, "is_loe_or_summary", False):
                continue
            if _late_type(a) and (tgt_fin is None or (a.finish is not None
                                                      and a.finish <= tgt_fin)):
                cnt += 1
        constraint_series.append(float(cnt))

    # uncompensated duration compressions: cumulative DUR-04 findings by update.
    dur04 = _series_result(sa, "DUR-04")
    comp_series: list[Optional[float]] = [0.0] * n
    if dur04 is not None:
        for i, s in enumerate(schedules):
            lbl = s.label()
            comp_series[i] = float(sum(1 for f in dur04.findings
                                       if str(f.detail).rstrip().endswith(f"({lbl})")))
        running = 0.0
        for i in range(n):
            running += comp_series[i] or 0.0
            comp_series[i] = running

    res.fundamentals = {
        "RDI (recovery debt)": rdi_series,
        "BWI (bow-wave)": bwi_series,
        "FCBI (criticality-weighted burn)": fcbi_series,
        "constraint additions near target": constraint_series,
        "uncompensated duration compressions": comp_series,
    }

    if len(held) < 2:
        res.reason = (f"{NOT_COMPUTABLE}: the milestone {tgt} did not hold station "
                      "across two or more consecutive updates (no directed-date "
                      "span to measure)")
        return res

    ddi, per_z, mean_held = _ddi_arithmetic(res.fundamentals, held)
    res.per_update_z = per_z
    res.mean_deterioration_z = mean_held
    res.ddi = ddi
    if ddi is None:
        res.reason = (f"{NOT_COMPUTABLE}: no fundamental could be z-scored over "
                      "the held span")
        return res
    res.interpretation = (
        f"DDI {ddi:.2f}: {tgt} held station across {len(held)} consecutive "
        f"update(s) while the schedule's own fundamentals deteriorated by a mean "
        f"{mean_held:+.2f} z over that span — {_DDI_FINDING}; why the date was "
        "held is expressly left open (owner pressure, genuine recovery intent, "
        "or negotiation posture).  " + _TRIAGE_NOTE)
    return res


# ==========================================================================
# 3. ARR — Attribution Robustness Ratio  (§11.3, N18 -> LI-13)
# ==========================================================================
@dataclass
class ArrParty:
    party: str
    min_share: float
    max_share: float
    arr: Optional[float]
    n_variants: int
    shares: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"party": self.party, "min_share": _r(self.min_share),
                "max_share": _r(self.max_share), "arr": _r(self.arr),
                "n_variants": self.n_variants,
                "shares": [_r(x) for x in self.shares]}


@dataclass
class ArrResult:
    parties: list[ArrParty] = field(default_factory=list)
    excluded_parties: list[str] = field(default_factory=list)
    n_variants: int = 0
    interpretation: str = ""
    note: str = _TRIAGE_NOTE
    privileged: bool = True
    surface: str = SURFACE
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": "ARR", "parties": [p.to_dict() for p in self.parties],
                "excluded_parties": list(self.excluded_parties),
                "n_variants": self.n_variants, "interpretation": self.interpretation,
                "note": self.note, "privileged": self.privileged,
                "surface": self.surface, "reason": self.reason}


def _cert_view(certificate) -> tuple[bool, list[dict[str, Any]]]:
    """Normalize a RobustnessCertificate (object) or its ``to_dict()`` to
    (overlay, [ {computable, per_party} ... ]) without importing the certificate
    machinery."""
    if certificate is None:
        return False, []
    if isinstance(certificate, dict):
        overlay = bool(certificate.get("overlay"))
        rows = []
        for v in certificate.get("variants", []):
            rows.append({"computable": bool(v.get("computable", True)),
                         "per_party": dict(v.get("per_party") or {})})
        return overlay, rows
    overlay = bool(getattr(certificate, "overlay", False))
    rows = []
    for v in getattr(certificate, "variants", []):
        rows.append({"computable": bool(getattr(v, "computable", True)),
                     "per_party": dict(getattr(v, "per_party", {}) or {})})
    return overlay, rows


def attribution_robustness_ratio(certificate) -> ArrResult:
    """Per party, ``ARR = min share / max share`` of attributed delay across the
    computable N4 variants (share = party total / all-party total per variant).
    Parties with zero attribution in every variant are excluded with a note.
    No certificate, or a sweep with no responsibility overlay -> NOT COMPUTABLE."""
    if certificate is None:
        return ArrResult(reason=f"{NOT_COMPUTABLE}: no robustness certificate "
                                "supplied (ARR rides on the N4 methodology sweep)")
    overlay, rows = _cert_view(certificate)
    if not overlay:
        return ArrResult(reason=f"{NOT_COMPUTABLE}: the robustness sweep carried "
                                "no responsibility overlay, so there is no "
                                "per-party attribution to test")
    shares_by_party: dict[str, list[float]] = {}
    n = 0
    for row in rows:
        if not row["computable"]:
            continue
        pp = row["per_party"]
        total = sum(v for v in pp.values())
        if total <= 0:
            continue
        n += 1
        for party in set(pp) | set(shares_by_party):
            shares_by_party.setdefault(party, [])
        for party in shares_by_party:
            shares_by_party[party].append(pp.get(party, 0.0) / total)
    res = ArrResult(n_variants=n)
    if n == 0:
        res.reason = (f"{NOT_COMPUTABLE}: no computable variant carried a "
                      "non-zero per-party attribution")
        return res
    for party, shares in sorted(shares_by_party.items()):
        if max(shares) <= 0:
            res.excluded_parties.append(party)
            continue
        mn, mx = min(shares), max(shares)
        res.parties.append(ArrParty(party=party, min_share=mn, max_share=mx,
                                    arr=(mn / mx if mx > 0 else None),
                                    n_variants=len(shares), shares=list(shares)))
    res.parties.sort(key=lambda p: (p.arr if p.arr is not None else 1.0))
    if res.parties:
        weakest = res.parties[0]
        res.interpretation = (
            f"Across {n} computable method variant(s), "
            + "; ".join(f"{p.party} ARR {p.arr:.2f} (share {p.min_share:.0%}-"
                        f"{p.max_share:.0%})" for p in res.parties)
            + f".  {weakest.party}'s attribution is the most method-dependent "
              f"(ARR {weakest.arr:.2f}; 1.0 = method-independent).  Knowing a "
              "conclusion's robustness is required diligence.  " + _TRIAGE_NOTE)
    if res.excluded_parties:
        res.interpretation += (f"  Excluded (zero attribution in every variant): "
                               f"{', '.join(res.excluded_parties)}.")
    return res


# ==========================================================================
# 4. PPS — Pacing Plausibility Score  (§11.4, N19 -> LI-14)
# ==========================================================================
# Published criteria weights (sourced to the SCL Protocol 2nd ed. pacing
# guidance and the recognized US pacing criteria).  Contemporaneous float
# existence and proportionality-to-float are the load-bearing legal predicates,
# so they and the demonstrable-float criterion carry the most weight; reversibility
# and re-acceleration are corroborating.  Sum = 1.0.
PPS_CRITERIA_WEIGHTS = {
    "float_at_start": 0.25,             # did float demonstrably exist at deceleration start
    "contemporaneous_awareness": 0.20,  # awareness of the parent critical delay
    "proportionality": 0.20,            # deceleration proportionate to available float
    "reversibility": 0.20,              # resources redeployed, not demobilized
    "reacceleration": 0.15,             # re-acceleration followed the parent's resolution
}
PPS_NEUTRAL = 50.0     # missing-evidence criteria score neutral, never zero (§11.4)

PPS_CRITERIA_LABELS = {
    "float_at_start": "float demonstrably existed when deceleration began",
    "contemporaneous_awareness": "contemporaneous awareness of the parent critical delay",
    "proportionality": "deceleration proportionate to the float available",
    "reversibility": "reversible (resources redeployed, not demobilized)",
    "reacceleration": "re-acceleration followed the parent delay's resolution",
}


@dataclass
class PpsInstance:
    window_label: str
    chain_codes: list[str]
    pps: float
    criteria: dict[str, Optional[float]]        # criterion -> 0/50/100 (None -> neutral)
    evidence: dict[str, str]                    # criterion -> named evidence
    neutral_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"window": self.window_label, "chain": list(self.chain_codes),
                "pps": _r(self.pps),
                "criteria": {k: _r(v) for k, v in self.criteria.items()},
                "evidence": dict(self.evidence),
                "neutral_criteria": list(self.neutral_criteria)}


@dataclass
class PpsResult:
    instances: list[PpsInstance] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: dict(PPS_CRITERIA_WEIGHTS))
    interpretation: str = ""
    note: str = _TRIAGE_NOTE
    privileged: bool = True
    surface: str = SURFACE
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": "PPS", "instances": [i.to_dict() for i in self.instances],
                "weights": dict(self.weights), "interpretation": self.interpretation,
                "note": self.note, "privileged": self.privileged,
                "surface": self.surface, "reason": self.reason}


def _score_pps(criteria: dict[str, Optional[float]]) -> tuple[float, list[str]]:
    """Weighted PPS over the five criteria.  A ``None`` criterion (missing
    evidence) scores the neutral placeholder, never zero, and is listed as
    neutral.  Exported for unit testing on hand-built criteria."""
    total = 0.0
    neutral: list[str] = []
    for key, w in PPS_CRITERIA_WEIGHTS.items():
        v = criteria.get(key)
        if v is None:
            v = PPS_NEUTRAL
            neutral.append(key)
        total += w * v
    return total, neutral


def _pps_from_candidate(cand, events_available: bool) -> PpsInstance:
    crit: dict[str, Optional[float]] = {}
    ev: dict[str, str] = {}

    fl = getattr(cand, "float_at_start_days", None)
    if fl is None:
        crit["float_at_start"] = None
        ev["float_at_start"] = "float at deceleration start unknown (neutral)"
    else:
        crit["float_at_start"] = 100.0 if fl > 0 else 0.0
        ev["float_at_start"] = f"float at start {fl:.1f} wd"

    if not events_available:
        crit["contemporaneous_awareness"] = None
        ev["contemporaneous_awareness"] = "no event list supplied (neutral)"
    else:
        aware = bool(getattr(cand, "contemporaneous_awareness", False))
        crit["contemporaneous_awareness"] = 100.0 if aware else 0.0
        titles = getattr(cand, "contemporaneous_events", []) or []
        ev["contemporaneous_awareness"] = (
            "contemporaneous event(s): " + ", ".join(t for t in titles if t)
            if aware else "no contemporaneous event overlaps this window")

    if fl is None:
        crit["proportionality"] = None
        ev["proportionality"] = "float unknown -> proportionality neutral"
    elif fl <= 0:
        crit["proportionality"] = 0.0
        ev["proportionality"] = "no float available -> deceleration not proportionate"
    else:
        crit["proportionality"] = 100.0
        ev["proportionality"] = (f"deceleration occurred within {fl:.1f} wd of "
                                 "available float")

    rev = str(getattr(cand, "reversibility", "") or "")
    if "consistent with reversibility" in rev:
        crit["reversibility"] = 100.0
    elif "reduces reversibility" in rev:
        crit["reversibility"] = 0.0
    else:
        crit["reversibility"] = None
    ev["reversibility"] = rev or "no reversibility read (neutral)"

    reaccel = getattr(cand, "reacceleration", None)
    if reaccel is None:
        crit["reacceleration"] = None
        ev["reacceleration"] = ("re-acceleration after the parent's resolution not "
                                "observable from this window alone (neutral)")
    else:
        crit["reacceleration"] = 100.0 if reaccel else 0.0
        ev["reacceleration"] = ("re-acceleration observed after parent resolution"
                                if reaccel else "no re-acceleration observed")

    pps, neutral = _score_pps(crit)
    return PpsInstance(
        window_label=getattr(cand, "window_label", ""),
        chain_codes=list(getattr(cand, "chain_codes", []) or []),
        pps=pps, criteria=crit, evidence=ev, neutral_criteria=neutral)


def pacing_plausibility(sa, events: Optional[list] = None) -> PpsResult:
    """Score every §6.3 pacing candidate against the five recognized pacing
    criteria on the published weighting.  Missing-evidence criteria score
    neutral (never zero), disclosed per instance."""
    try:
        from .pacing import pacing_candidates
        cands = pacing_candidates(sa, events)
    except Exception as e:                  # pragma: no cover - defensive
        return PpsResult(reason=f"pacing screen error: {e}")
    res = PpsResult()
    if not cands:
        res.reason = ("no pacing candidate surfaced by the §6.3 screen "
                      "(nothing to score)")
        return res
    for c in cands:
        res.instances.append(_pps_from_candidate(c, events_available=events is not None))
    res.instances.sort(key=lambda i: i.pps, reverse=True)
    top = res.instances[0]
    res.interpretation = (
        f"{len(res.instances)} pacing candidate(s) scored; strongest PPS "
        f"{top.pps:.0f}/100 ({top.window_label}).  The score triages which "
        "pacing assertions deserve expert investment — the same table applies "
        "symmetrically to an opposing expert's pacing claim.  " + _TRIAGE_NOTE)
    return res


# ==========================================================================
# 5. RSA — Rebuttal Surface Area  (§11.5, N20 -> LI-15)
# ==========================================================================
RSA_METHOD_SPREAD_WD = 2.0    # a window whose total moves > 2 wd across variants
                              # is method-sensitive (mirrors STABLE_RANGE_WD)
RSA_PCI_FLOOR = 0.20          # PCI below this in a window -> path-ambiguous

RSA_CLASSES = ("method-sensitive", "data-fragile", "path-ambiguous", "robust")


@dataclass
class RsaComponent:
    window_label: str
    delay_workdays: float
    classification: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {"window": self.window_label, "delay_workdays": _r(self.delay_workdays),
                "classification": self.classification, "evidence": self.evidence}


@dataclass
class RsaResult:
    rsa_pct: Optional[float] = None            # contested share of attributed delay
    total_delay_workdays: float = 0.0
    contested_delay_workdays: float = 0.0
    components: list[RsaComponent] = field(default_factory=list)
    class_totals: dict[str, float] = field(default_factory=dict)
    interpretation: str = ""
    note: str = _TRIAGE_NOTE
    privileged: bool = True
    surface: str = SURFACE
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"index": "RSA", "rsa_pct": _r(self.rsa_pct),
                "total_delay_workdays": _r(self.total_delay_workdays),
                "contested_delay_workdays": _r(self.contested_delay_workdays),
                "components": [c.to_dict() for c in self.components],
                "class_totals": {k: _r(v) for k, v in self.class_totals.items()},
                "interpretation": self.interpretation, "note": self.note,
                "privileged": self.privileged, "surface": self.surface,
                "reason": self.reason}


def _classify_rsa_windows(windows: list[dict[str, Any]],
                          method_sensitive_labels: set[str],
                          data_fragile_labels: set[str],
                          low_pci_labels: set[str]) -> RsaResult:
    """Classify each attributed-delay window and compute the contested share.
    Priority: data-fragile > method-sensitive > path-ambiguous > robust (a
    window resting on records failing integrity checks is the least defensible).
    Exported for unit testing on hand-built windows + flag sets."""
    res = RsaResult()
    class_totals = {k: 0.0 for k in RSA_CLASSES}
    total = 0.0
    contested = 0.0
    for w in windows:
        label = str(w.get("window", ""))
        delay = abs(float(w.get("total_workdays") or 0.0))
        total += delay
        if label in data_fragile_labels:
            cls = "data-fragile"
            evidence = ("window overlaps records failing integrity checks "
                        "(TRD-05 retroactive actuals / DAT-05 as-built anomalies / "
                        "DUR-04 compression)")
        elif label in method_sensitive_labels:
            cls = "method-sensitive"
            evidence = (f"window total moves > {RSA_METHOD_SPREAD_WD:g} wd across the "
                        "N4 method variants")
        elif label in low_pci_labels:
            cls = "path-ambiguous"
            evidence = (f"path concentration (PCI) below {RSA_PCI_FLOOR:g} in this "
                        "window — the controlling path is contestable")
        else:
            cls = "robust"
            evidence = "survives the N4 sweep, integrity checks, and the PCI floor"
        class_totals[cls] += delay
        if cls != "robust":
            contested += delay
        res.components.append(RsaComponent(label, delay, cls, evidence))
    res.total_delay_workdays = total
    res.contested_delay_workdays = contested
    res.class_totals = class_totals
    res.rsa_pct = (100.0 * contested / total) if total > 0 else None
    return res


def rebuttal_surface_area(certificate, sa=None, indices=None) -> RsaResult:
    """Decompose the attributed delay (the primary N4 variant's windows) into
    components classified method-sensitive / data-fragile / path-ambiguous /
    robust, and report the share resting on contested ground.  Same NOT
    COMPUTABLE guards as ARR (no certificate, or no responsibility overlay)."""
    if certificate is None:
        return RsaResult(reason=f"{NOT_COMPUTABLE}: no robustness certificate "
                                "supplied (RSA rides on the N4 methodology sweep)")
    overlay, _rows = _cert_view(certificate)
    if not overlay:
        return RsaResult(reason=f"{NOT_COMPUTABLE}: the robustness sweep carried "
                                "no responsibility overlay")

    primary_windows, per_label_totals = _primary_windows(certificate)
    if not primary_windows:
        return RsaResult(reason=f"{NOT_COMPUTABLE}: the certificate has no primary "
                                "variant windows to decompose")

    # method-sensitive: a window whose total moves > RSA_METHOD_SPREAD_WD across
    # every variant that measured a window of the same label.
    method_labels: set[str] = set()
    for label, totals in per_label_totals.items():
        if totals and (max(totals) - min(totals)) > RSA_METHOD_SPREAD_WD:
            method_labels.add(label)

    data_fragile = _data_fragile_labels(sa) if sa is not None else set()
    low_pci = _low_pci_labels(sa, indices) if sa is not None else set()
    # only classify against windows we actually have
    labels = {str(w.get("window", "")) for w in primary_windows}
    data_fragile &= labels
    low_pci &= labels

    res = _classify_rsa_windows(primary_windows, method_labels, data_fragile, low_pci)
    if res.rsa_pct is None:
        res.reason = (f"{NOT_COMPUTABLE}: attributed delay across the primary "
                      "windows is zero")
        return res
    contested_classes = [c for c in RSA_CLASSES[:-1] if res.class_totals.get(c, 0) > 0]
    res.interpretation = (
        f"RSA {res.rsa_pct:.0f}%: {res.contested_delay_workdays:.1f} of "
        f"{res.total_delay_workdays:.1f} attributed workday-units sit on contested "
        f"ground ({', '.join(contested_classes) or 'none'}).  Run on our own draft "
        "this is the pre-signature audit; run on an opposing analysis it is the "
        "cross-examination map — symmetric by construction.  " + _TRIAGE_NOTE)
    return res


def _primary_windows(certificate) -> tuple[list[dict[str, Any]], dict[str, list[float]]]:
    """(primary variant's windows, per-window-label totals across all computable
    variants) from a certificate object or its to_dict()."""
    if isinstance(certificate, dict):
        variants = certificate.get("variants", [])
        prim = next((v for v in variants if v.get("is_primary")), None)
        prim_windows = list(prim.get("windows", [])) if prim else []
        per_label: dict[str, list[float]] = {}
        for v in variants:
            if not v.get("computable", True):
                continue
            for w in v.get("windows", []):
                per_label.setdefault(str(w.get("window", "")), []).append(
                    abs(float(w.get("total_workdays") or 0.0)))
        return prim_windows, per_label
    prim = certificate.primary() if hasattr(certificate, "primary") else None
    prim_windows = list(getattr(prim, "windows", [])) if prim else []
    per_label = {}
    for v in getattr(certificate, "variants", []):
        if not getattr(v, "computable", True):
            continue
        for w in getattr(v, "windows", []):
            per_label.setdefault(str(w.get("window", "")), []).append(
                abs(float(w.get("total_workdays") or 0.0)))
    return prim_windows, per_label


def _data_fragile_labels(sa) -> set[str]:
    """Window labels ("earlier -> later") overlapping records that fail integrity
    checks: TRD-05 retroactive actuals or DUR-04 compression in that window, or a
    DAT-05 as-built anomaly on either endpoint file."""
    out: set[str] = set()
    dat05_labels: set[str] = set()
    for a in getattr(sa, "assessments", []):
        r = a.result("DAT-05") if hasattr(a, "result") else None
        if r is not None and r.value:
            dat05_labels.add(a.schedule.label())
    for cs in getattr(sa, "changesets", []):
        label = f"{cs.earlier.label()}->{cs.later.label()}"
        if cs.actual_date_changes:
            out.add(label)
        if cs.earlier.label() in dat05_labels or cs.later.label() in dat05_labels:
            out.add(label)
    dur04 = _series_result(sa, "DUR-04")
    if dur04 is not None:
        for cs in getattr(sa, "changesets", []):
            lbl = cs.later.label()
            if any(str(f.detail).rstrip().endswith(f"({lbl})") for f in dur04.findings):
                out.add(f"{cs.earlier.label()}->{lbl}")
    return out


def _low_pci_labels(sa, indices=None) -> set[str]:
    """Window labels whose LATER update carries a PCI below ``RSA_PCI_FLOOR``."""
    from .li_indices import run_li_indices
    ri = indices if indices is not None else run_li_indices(sa)
    pci = ri.pci
    low: set[str] = set()
    label_pci = dict(zip(pci.labels, pci.per_update))
    for cs in getattr(sa, "changesets", []):
        v = label_pci.get(cs.later.label())
        if v is not None and v < RSA_PCI_FLOOR:
            low.add(f"{cs.earlier.label()}->{cs.later.label()}")
    return low


# ==========================================================================
# shared helpers + bundle
# ==========================================================================
def _series_result(sa, cid: str):
    for r in getattr(sa, "series_results", []):
        if getattr(r.check, "id", None) == cid:
            return r
    return None


def _r(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    v = round(float(x) + 0.0, 4)
    return int(v) if v == int(v) else v


@dataclass
class LiProvocativeResult:
    smi: SmiResult
    ddi: DdiResult
    arr: ArrResult
    pps: PpsResult
    rsa: RsaResult

    def to_dict(self) -> dict[str, Any]:
        return {"smi": self.smi.to_dict(), "ddi": self.ddi.to_dict(),
                "arr": self.arr.to_dict(), "pps": self.pps.to_dict(),
                "rsa": self.rsa.to_dict(),
                "privileged": True, "surface": SURFACE}


def run_li_provocative(sa, certificate=None, events: Optional[list] = None,
                       indices=None) -> LiProvocativeResult:
    """Compute all five provocative indices in one call.  Never raises: each
    index degrades to a result carrying a ``reason``.  ``certificate`` is an
    optional precomputed :class:`robustness.RobustnessCertificate` (or its
    dict) feeding ARR and RSA; absent it, those two report NOT COMPUTABLE."""
    from .li_indices import run_li_indices
    if indices is None:
        try:
            indices = run_li_indices(sa)
        except Exception:                   # pragma: no cover - defensive
            indices = None
    try:
        smi = schedule_manipulation_indicator(sa, events)
    except Exception as e:                  # pragma: no cover - defensive
        smi = SmiResult(reason=f"error: {e}")
    try:
        ddi = directed_date_index(sa, indices=indices)
    except Exception as e:                  # pragma: no cover - defensive
        ddi = DdiResult(reason=f"error: {e}")
    try:
        arr = attribution_robustness_ratio(certificate)
    except Exception as e:                  # pragma: no cover - defensive
        arr = ArrResult(reason=f"error: {e}")
    try:
        pps = pacing_plausibility(sa, events)
    except Exception as e:                  # pragma: no cover - defensive
        pps = PpsResult(reason=f"error: {e}")
    try:
        rsa = rebuttal_surface_area(certificate, sa=sa, indices=indices)
    except Exception as e:                  # pragma: no cover - defensive
        rsa = RsaResult(reason=f"error: {e}")
    return LiProvocativeResult(smi=smi, ddi=ddi, arr=arr, pps=pps, rsa=rsa)
