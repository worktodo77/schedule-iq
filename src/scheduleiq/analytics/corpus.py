"""Internal benchmark corpus (ANALYTICS_PROPOSAL.md §6.9, backlog S9).

Persist ANONYMIZED metric outcomes per reviewed project (locally / on Synology
per §6.9 — this module takes any path) so every chart can carry a defensible
context line drawn from the firm's own documented review history:

    "this schedule's logic quality is in the bottom quartile of process-plant
     schedules LI has reviewed."

Design constraints (ADR-0006 offline; the governance wall of §6.10):
-----------------------------------------------------------------
* **Offline, stdlib-only.**  No network, no API.  Percentile arithmetic mirrors
  :mod:`scheduleiq.analytics.montecarlo` (linear-interpolation / type-7).
* **Anonymized by default, disclosed.**  A stored row carries NO project names,
  NO activity names or codes, and NO dates beyond durations / ratios / cadence
  intervals.  Before a row is written, its serialized text is asserted to
  contain none of a documented blocklist (project name, project id, source
  file, activity names) harvested from the very sources it was built from — a
  leak raises rather than ships (CLAUDE-style verification discipline).
* **Append-only JSONL with a ``schema_version``**; one row per reviewed project
  snapshot.  Dedup is by ``corpus_id`` (re-adding the same project REPLACES its
  row, disclosed).  Loading is corruption-tolerant: a bad line is skipped with a
  disclosure, never a crash.
* **Small-n honesty.**  :meth:`BenchmarkCorpus.context_for` refuses to place a
  project against fewer than :data:`MIN_CONTEXT_N` peers (per sector filter) and
  discloses it, and every placement discloses the peer count ``n``.

The per-project ``actual ÷ planned`` duration-ratio sample is harvested via
:func:`scheduleiq.analytics.montecarlo.calibrate_from_series` (reused, not
re-implemented) so the corpus and the Monte Carlo empirical tier speak the same
number; in-progress activities are additionally harvested as RIGHT-CENSORED
ratios (actual-so-far ÷ planned) for the survival-adjusted duration priors in
:mod:`scheduleiq.analytics.priors` (S10).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping, Optional

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
CORPUS_SCHEMA_VERSION = 1

# The refusal floor for percentile placement (small-n honesty, §6.9).
MIN_CONTEXT_N = 5

# The documented anonymization blocklist (CLAUDE.md verification discipline):
# these source-derived strings must NOT appear anywhere in a stored row.
ANON_BLOCKLIST_FIELDS = ("project_name", "project_id", "source_file",
                         "activity names")
# tokens shorter than this are ignored by the leak scan (a 1-2 char activity
# code such as "A" would spuriously collide with letter grades / check ids;
# codes never reach a row anyway — only distinctive names are asserted).
_ANON_MIN_TOKEN = 3


# ---------------------------------------------------------------------------
# stdlib percentile (type-7, identical to montecarlo._percentile) so corpus and
# simulation percentiles are computed the same way.
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


def _count_workdays_inclusive(cal, d0: date, d1: date) -> int:
    """Inclusive workday count on ``cal`` (mirrors montecarlo's helper)."""
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


# ===========================================================================
# row
# ===========================================================================
@dataclass
class CorpusRow:
    """One reviewed-project snapshot in the corpus (anonymized)."""
    corpus_id: str
    sector: str
    schema_version: int = CORPUS_SCHEMA_VERSION
    anonymized: bool = True
    n_updates: int = 1
    # per-check {id: {"value": float|None, "status": str}} from the final update
    # plus the series-level (TRD-*/EVM-*/LI-*) results.
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    health_score: Optional[float] = None
    grades: Optional[dict[str, Any]] = None          # report-card, if present
    series_stats: dict[str, Any] = field(default_factory=dict)
    ratio_sample: list[float] = field(default_factory=list)     # completed a/p
    ratio_meta: dict[str, Any] = field(default_factory=dict)
    censored_sample: list[float] = field(default_factory=list)  # in-progress a/p
    provenance: dict[str, Any] = field(default_factory=dict)

    def metric_values(self) -> dict[str, float]:
        """Flat {metric_id: value} view for percentile placement (health score
        surfaces under the reserved key ``health_score``)."""
        out: dict[str, float] = {}
        for cid, rec in self.checks.items():
            v = rec.get("value")
            if v is not None:
                out[cid] = float(v)
        if self.health_score is not None:
            out["health_score"] = float(self.health_score)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "corpus_id": self.corpus_id,
            "sector": self.sector,
            "anonymized": self.anonymized,
            "n_updates": self.n_updates,
            "checks": self.checks,
            "health_score": self.health_score,
            "grades": self.grades,
            "series_stats": self.series_stats,
            "ratio_sample": list(self.ratio_sample),
            "ratio_meta": self.ratio_meta,
            "censored_sample": list(self.censored_sample),
            "provenance": self.provenance,
        }

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "CorpusRow":
        return CorpusRow(
            corpus_id=str(d.get("corpus_id", "")),
            sector=str(d.get("sector", "")),
            schema_version=int(d.get("schema_version", CORPUS_SCHEMA_VERSION)),
            anonymized=bool(d.get("anonymized", True)),
            n_updates=int(d.get("n_updates", 1)),
            checks=dict(d.get("checks", {})),
            health_score=d.get("health_score"),
            grades=d.get("grades"),
            series_stats=dict(d.get("series_stats", {})),
            ratio_sample=[float(x) for x in d.get("ratio_sample", [])],
            ratio_meta=dict(d.get("ratio_meta", {})),
            censored_sample=[float(x) for x in d.get("censored_sample", [])],
            provenance=dict(d.get("provenance", {})),
        )


# ===========================================================================
# context (percentile placement for a chart line)
# ===========================================================================
@dataclass
class MetricPlacement:
    metric_id: str
    value: float
    corpus_p25: Optional[float]
    corpus_p50: Optional[float]
    corpus_p75: Optional[float]
    n: int
    placement_pct: float             # % of peers at or below this value

    def quartile_phrase(self) -> str:
        p = self.placement_pct
        if p <= 25.0:
            return "the bottom quartile"
        if p <= 50.0:
            return "the second quartile (below the median)"
        if p <= 75.0:
            return "the third quartile (above the median)"
        return "the top quartile"

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "corpus_p25": self.corpus_p25,
                "corpus_p50": self.corpus_p50, "corpus_p75": self.corpus_p75,
                "n": self.n, "placement_pct": self.placement_pct}


@dataclass
class CorpusContext:
    sector: Optional[str]
    n: int                                   # peer projects in the filter
    metrics: dict[str, MetricPlacement] = field(default_factory=dict)
    disclosures: list[str] = field(default_factory=list)
    refused: bool = False

    def line(self, metric_id: str, *, sector_label: Optional[str] = None) -> Optional[str]:
        """A report-ready chart context line, or None if the metric was not
        placed (refused / absent)."""
        mp = self.metrics.get(metric_id)
        if mp is None:
            return None
        noun = sector_label or (f"{self.sector} " if self.sector else "") + \
            "schedules LI has reviewed"
        if sector_label:
            noun = f"{sector_label} schedules LI has reviewed"
        return (f"{metric_id} = {mp.value:g} — in {mp.quartile_phrase()} of "
                f"{noun} (n={mp.n}).")

    def to_dict(self) -> dict[str, Any]:
        return {"sector": self.sector, "n": self.n, "refused": self.refused,
                "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
                "disclosures": list(self.disclosures)}


# ===========================================================================
# the store
# ===========================================================================
class BenchmarkCorpus:
    """A local JSONL benchmark store (one row per reviewed-project snapshot)."""

    def __init__(self, path: str):
        self.path = path
        self.rows: list[CorpusRow] = []
        self.load_disclosures: list[str] = []
        self._load()

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        self.rows = []
        self.load_disclosures = []
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as fh:
            for i, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    self.rows.append(CorpusRow.from_dict(d))
                except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                    self.load_disclosures.append(
                        f"corpus line {i} skipped: not valid JSON / row schema "
                        "(corruption-tolerant load; the line was not counted).")

    def _rewrite(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for r in self.rows:
                fh.write(json.dumps(r.to_dict(), ensure_ascii=False,
                                    sort_keys=True) + "\n")

    def _append_line(self, row: CorpusRow) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row.to_dict(), ensure_ascii=False,
                                sort_keys=True) + "\n")

    # -- low-level add (dedup by corpus_id; append-only unless replacing) --
    def add_row(self, row: CorpusRow) -> CorpusRow:
        existing = next((i for i, r in enumerate(self.rows)
                         if r.corpus_id == row.corpus_id), None)
        if existing is not None:
            self.rows[existing] = row
            self._rewrite()               # replace in place, disclosed by caller
            row.provenance = dict(row.provenance)
            row.provenance["replaced"] = True
        else:
            self.rows.append(row)
            self._append_line(row)
        return row

    # -- harvest a reviewed project into an anonymized row -----------------
    def add_project(self, sa, *, sector: str, anonymize: bool = True,
                    corpus_id: Optional[str] = None) -> CorpusRow:
        """Harvest per-project outcomes from a :class:`SeriesAnalysis` (or a
        single-schedule assessment wrapped in one) into an anonymized row and
        persist it.  ``anonymize`` defaults on and is enforced by a blocklist
        assertion before the row is written."""
        from ..metrics.engine import evaluate           # lazy (avoid heavy import)
        try:
            from .montecarlo import calibrate_from_series
        except Exception:                                # pragma: no cover
            calibrate_from_series = None

        schedules, assessments, series_results, health = _unpack_sa(sa, evaluate)
        last = schedules[-1]

        # per-check values/statuses (final update) + series-level results
        checks: dict[str, dict[str, Any]] = {}
        if assessments:
            for r in assessments[-1].results:
                checks[r.check.id] = {"value": r.value, "status": r.status}
        for r in series_results:
            checks[r.check.id] = {"value": r.value, "status": r.status}

        # report-card grades if the scorecard module is available (additive,
        # never sinks the harvest).
        grades = _harvest_grades(sa)

        # completed-activity actual/planned ratio sample (reuse montecarlo)
        ratio_sample: list[float] = []
        ratio_meta: dict[str, Any] = {}
        if calibrate_from_series is not None:
            emp = calibrate_from_series(schedules)
            ratio_sample = list(emp.ratios)
            ratio_meta = {"n": emp.n, "mean": emp.mean, "p10": emp.p10,
                          "p50": emp.p50, "p90": emp.p90, "method": emp.method,
                          "source": "montecarlo.calibrate_from_series"}
        censored_sample = _harvest_censored(last)

        row = CorpusRow(
            corpus_id="",                # set below
            sector=sector,
            anonymized=bool(anonymize),
            n_updates=len(schedules),
            checks=checks,
            health_score=round(health, 1) if health is not None else None,
            grades=grades,
            series_stats=_series_stats(schedules),
            ratio_sample=[round(x, 6) for x in ratio_sample],
            ratio_meta=ratio_meta,
            censored_sample=[round(x, 6) for x in censored_sample],
        )

        # corpus_id = sha256 prefix of the source hashes unless caller supplies
        source_hashes = [s.source_sha256 for s in schedules if s.source_sha256]
        if corpus_id is not None:
            row.corpus_id = corpus_id
        elif source_hashes:
            h = hashlib.sha256("|".join(source_hashes).encode("utf-8")).hexdigest()
            row.corpus_id = h[:16]
        else:
            # deterministic fallback for in-memory schedules with no source hash
            basis = json.dumps({"checks": row.checks,
                                "ratios": row.ratio_sample,
                                "sector": sector}, sort_keys=True, default=str)
            row.corpus_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

        row.provenance = {"schema_version": CORPUS_SCHEMA_VERSION,
                          "sectors": [sector], "n_updates": len(schedules),
                          "anonymized": bool(anonymize),
                          "ratio_source": "montecarlo.calibrate_from_series"}

        if anonymize:
            leaked = _anonymization_leaks(row, schedules)
            assert not leaked, (
                "anonymization blocklist violated — a stored corpus row must "
                f"contain none of {ANON_BLOCKLIST_FIELDS}; leaked: {leaked!r}")

        replaced = any(r.corpus_id == row.corpus_id for r in self.rows)
        self.add_row(row)
        if replaced:
            self.load_disclosures.append(
                f"corpus_id {row.corpus_id} already present — the existing row "
                "was REPLACED (dedup by corpus_id).")
        return row

    # -- percentile placement of the current project ----------------------
    def context_for(self, sched_or_sa, *, sector: Optional[str] = None
                    ) -> CorpusContext:
        """Place the current project's per-check values and health score against
        the corpus (filtered by ``sector`` when given).  Refuses percentiles
        below :data:`MIN_CONTEXT_N` peers (disclosed)."""
        peers = [r for r in self.rows if sector is None or r.sector == sector]
        n = len(peers)
        ctx = CorpusContext(sector=sector, n=n)
        if n < MIN_CONTEXT_N:
            ctx.refused = True
            ctx.disclosures.append(
                f"percentile placement refused: only {n} peer project(s) "
                f"{'in sector ' + repr(sector) if sector else 'in the corpus'} "
                f"(< {MIN_CONTEXT_N} required — small-n honesty, §6.9).")
            return ctx

        current = _current_metrics(sched_or_sa)
        for mid, val in sorted(current.items()):
            peer_vals = sorted(r.metric_values()[mid] for r in peers
                               if mid in r.metric_values())
            if not peer_vals:
                continue
            m = len(peer_vals)
            at_or_below = sum(1 for x in peer_vals if x <= val)
            ctx.metrics[mid] = MetricPlacement(
                metric_id=mid, value=float(val),
                corpus_p25=_percentile(peer_vals, 25.0),
                corpus_p50=_percentile(peer_vals, 50.0),
                corpus_p75=_percentile(peer_vals, 75.0),
                n=m, placement_pct=round(100.0 * at_or_below / m, 2))
        ctx.disclosures.append(
            f"placement computed against {n} peer project(s)"
            + (f" in sector {sector!r}" if sector else "") + ".")
        return ctx


# ===========================================================================
# harvest helpers
# ===========================================================================
def _unpack_sa(sa, evaluate):
    """Return (schedules, assessments, series_results, health_score) for either
    a SeriesAnalysis or a bare Schedule."""
    if hasattr(sa, "assessments") and hasattr(sa, "schedules"):
        assessments = list(sa.assessments)
        health = assessments[-1].health_score if assessments else None
        return list(sa.schedules), assessments, list(sa.series_results), health
    # a bare Schedule
    assessment = evaluate(sa)
    return [sa], [assessment], [], assessment.health_score


def _harvest_grades(sa) -> Optional[dict[str, Any]]:
    """Report-card grades if the scorecard module is importable (additive)."""
    try:
        from ..scorecard import score_series
        card = score_series(sa) if hasattr(sa, "assessments") else None
        if card is None:
            return None
        return {"overall": round(card.overall, 1), "letter": card.letter,
                "is_series": card.is_series}
    except Exception:                                    # pragma: no cover
        return None


def _harvest_censored(sched) -> list[float]:
    """Right-censored ``actual-so-far ÷ planned`` ratios for in-progress
    activities at the last update (RD > 0 = censored at the current ratio).
    Mirrors montecarlo.calibrate_from_series' completed-activity harvesting."""
    out: list[float] = []
    dd = sched.data_date
    if dd is None:
        return out
    for a in sched.real_activities:
        if a.is_milestone or not a.in_progress:
            continue
        if a.actual_start is None or a.remaining_duration_hours <= 0:
            continue
        cal = sched.cal_for(a)
        actual_wd = _count_workdays_inclusive(cal, a.actual_start.date(), dd.date())
        if a.baseline_start is not None and a.baseline_finish is not None:
            planned_wd = float(_count_workdays_inclusive(
                cal, a.baseline_start.date(), a.baseline_finish.date()))
        else:
            planned_wd = a.duration_days(cal)
        if actual_wd <= 0 or planned_wd <= 0:
            continue
        out.append(actual_wd / planned_wd)
    out.sort()
    return out


def _series_stats(schedules) -> dict[str, Any]:
    """Anonymized per-project series statistics (counts / cadence / float
    quantiles / logic density / percent-complete span)."""
    last = schedules[-1]
    reals = last.real_activities
    n_act = len(reals)
    n_rel = len(last.relationships)

    # update cadence (intervals between consecutive data dates, in days)
    dds = [s.data_date for s in schedules if s.data_date is not None]
    intervals = [(dds[i] - dds[i - 1]).days for i in range(1, len(dds))]
    cadence = {
        "n_updates": len(schedules),
        "intervals_days": intervals,
        "mean_interval_days": (round(sum(intervals) / len(intervals), 2)
                               if intervals else None),
        "median_interval_days": (_percentile(sorted(float(x) for x in intervals),
                                             50.0) if intervals else None),
    }

    # float distribution quantiles (working days, last update)
    floats = sorted(fd for fd in
                    (a.total_float_days(last.cal_for(a)) for a in reals)
                    if fd is not None)
    float_q = {"n": len(floats),
               "p25": _percentile(floats, 25.0), "p50": _percentile(floats, 50.0),
               "p75": _percentile(floats, 75.0),
               "min": floats[0] if floats else None,
               "max": floats[-1] if floats else None}

    # percent-complete span across the series (mean pct over real activities)
    def _mean_pct(s) -> Optional[float]:
        vals = [a.pct_complete for a in s.real_activities if not a.is_milestone]
        return round(sum(vals) / len(vals), 2) if vals else None

    first_pct, last_pct = _mean_pct(schedules[0]), _mean_pct(last)
    pct_span = {"first": first_pct, "last": last_pct,
                "delta": (round(last_pct - first_pct, 2)
                          if first_pct is not None and last_pct is not None
                          else None)}

    return {
        "activity_count": n_act,
        "relationship_count": n_rel,
        "logic_density": round(n_rel / n_act, 4) if n_act else None,
        "update_cadence": cadence,
        "float_quantiles_days": float_q,
        "percent_complete_span": pct_span,
    }


def _current_metrics(sched_or_sa) -> dict[str, float]:
    """Flat {metric_id: value} (+ ``health_score``) for the current project,
    accepting a SeriesAnalysis, a bare Schedule, or a pre-computed mapping."""
    if isinstance(sched_or_sa, Mapping):
        return {str(k): float(v) for k, v in sched_or_sa.items() if v is not None}
    from ..metrics.engine import evaluate
    schedules, assessments, series_results, health = _unpack_sa(sched_or_sa, evaluate)
    out: dict[str, float] = {}
    if assessments:
        for r in assessments[-1].results:
            if r.value is not None:
                out[r.check.id] = float(r.value)
    for r in series_results:
        if r.value is not None:
            out[r.check.id] = float(r.value)
    if health is not None:
        out["health_score"] = float(health)
    return out


# ===========================================================================
# anonymization leak scan
# ===========================================================================
def _anonymization_leaks(row: CorpusRow, schedules) -> list[str]:
    """Return the blocklist tokens (project name/id, source file, activity
    names) that leaked into the serialized row.  Empty list = clean."""
    forbidden: set[str] = set()
    for s in schedules:
        for tok in (s.project_name, s.project_id, s.source_file):
            if tok:
                forbidden.add(str(tok))
                base = os.path.basename(str(tok))
                if base:
                    forbidden.add(base)
        for a in s.activities.values():
            if a.name:
                forbidden.add(str(a.name))
    forbidden = {t for t in forbidden if len(t) >= _ANON_MIN_TOKEN}
    text = json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True, default=str)
    return sorted(t for t in forbidden if t in text)
