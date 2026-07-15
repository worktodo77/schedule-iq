"""Methodology-robustness certificate (backlog N4; ANALYTICS_PROPOSAL.md §8.4).

Forensic purpose
----------------
Before an opinion is committed, the delay measurement is stress-tested: the same
target movement is re-measured under a GRID of defensible method variants —
perturbed window boundaries (±1 update), alternative statusing settings
(retained logic vs progress override), MIP 3.3 vs MIP 3.4 framing (and, where
the window is short enough, the N3 daily-ledger framing), and with/without the
analyst-nominated contested revisions.  The certificate reports how stable the
attribution is across the sweep ("Contractor-responsible delay ranges 15–27 wd
across 6 method variants").  A conclusion that survives the sweep is armored
against the "you cherry-picked your windows" cross-examination; one that does
not is a warning the expert wants *before* signing.

This module is a **stability screen of the METHOD**, not an apportionment
opinion.  Everything it emits is expressly ``PRELIMINARY`` and ``OBSERVATIONAL``
(CLAUDE.md §4): causation, concurrency, entitlement (EOT/compensation) and
quantum are reserved to the expert.  The per-party numbers are produced by the
DISCLOSED allocation heuristics below — they exist to test the *sensitivity of
the answer to method choices*, and must never be quoted as an apportionment.

It reuses, without modifying, the D9 half-step engine
(:mod:`scheduleiq.analytics.halfstep`) and the N3 daily ledger
(:mod:`scheduleiq.analytics.dailyledger`); the MIP 3.3 framing is read off D9's
``mip33_row`` and needs no extra engine run.

The variant grid (combinatorial, capped)
-----------------------------------------
Four dimensions are swept.  For a series of ``k`` schedules with ``pairs`` the
consecutive update pairs:

* **Framing** (up to 3):
    - ``mip34_halfstep`` — the D9 progress/revision bifurcation (E_n1 − E_n
      split into performance and revision components).
    - ``mip33_asis`` — the observational whole-window movement (E_n1 − E_n) with
      NO bifurcation, read from D9's ``mip33_row`` (no extra engine run).
    - ``n3_daily`` — the N3 daily-ledger cumulative movement (later-network
      framing), included only when ``include_daily`` and the window spans
      ≤ ``_DAILY_SPAN_CAP`` (120) calendar days; longer windows record the
      daily variant as not-computable.
* **Statusing** (2): ``retained_logic`` vs ``progress_override``.  The D9/N3
  modules take the mode from each file's SCHEDOPTIONS via the bridge
  (:mod:`scheduleiq.cpm.bridge`), so a variant is applied by DEEP-COPYING the
  schedule and flipping ``settings.progress_override``; the resolved mode is
  read back from the bridge's own disclosure and recorded on the row (evidence
  the flip took effect).  A schedule already in the requested mode is used
  as-is (no copy) so the primary variant reproduces a direct D9 run exactly.
* **Window boundaries** (±1 update): for ≥3 updates the interior boundaries are
  dropped one at a time, merging the adjacent windows — for ``[S1,S2,S3]`` the
  boundary set ``{S1→S2, S2→S3}`` (``full``) vs ``{S1→S3}`` (``drop:S2``).  With
  only 2 schedules this dimension collapses (disclosed).
* **Contested revisions**: when ``contested_revisions`` is given (edit
  identifiers matching D9's named-edit format, e.g. ``"add activity HD10"`` /
  ``"add HB20->HA50"``; a case-insensitive substring/prefix match is accepted),
  the half-step variants are re-measured with those edits excluded from the
  revision overlay — an arithmetic ``with``/``without`` pair that subtracts the
  matched edits' D9-attributed deltas from the revision effect (no re-run).
  Without ``contested_revisions`` this dimension collapses (disclosed).  It
  applies to the ``mip34_halfstep`` framing only.

The combinatorial product is enumerated deterministically and capped at
``max_variants`` (default 24); the truncated tail is disclosed in enumeration
order.

The measured quantity (comparable across variants)
--------------------------------------------------
One number per variant, summed over the windows in the variant's boundary set:

* **With a responsibility overlay** — total delay at the target attributed per
  party.  Allocation heuristics (DISCLOSED, OBSERVATIONAL):
    - ``mip34_halfstep``: the **progress effect** is split across the
      controlling-path activities by ``|remaining-duration change|`` (D9's
      progress contributors) and mapped to their parties; the **revision
      effect** is allocated to the parties of D9's **named top movers** (the
      activity a relationship edit binds — its successor — or the edited
      activity), with the un-named remainder to ``"Unallocated"``.
    - ``mip33_asis``: the whole-window movement is allocated to the party of the
      window's single controlling activity (D9's top progress contributor, else
      the largest named mover).
    - ``n3_daily``: N3's per-party subtotals are used directly (its ``Untagged``
      bucket is folded into ``"Unallocated"``).
* **Without an overlay** — total target movement (engine workdays) summed over
  the windows.  Still a valid stability sweep.

Verdict banding
---------------
Per measured series (each party, or ``TOTAL``) the min/max/range/median and a
spread% are computed across the computable variants, and a verdict band is
assigned (thresholds are module constants, disclosed in the output):
``STABLE`` (range ≤ 10% of |median| or ≤ 2 wd), ``MODERATE`` (≤ 25% or ≤ 5 wd),
``UNSTABLE`` (else).

Degradation & refusal
---------------------
A variant whose engine run, daily span, or handshake fails is recorded
``computable=False`` with a reason; the certificate NEVER raises for a
variant-level failure.  A :class:`HandshakeRefusal` on the PRIMARY
(unperturbed: ``mip34_halfstep`` / the files' own statusing / ``full`` /
``with_revisions``) variant propagates unless ``handshake="skip"``.
"""
from __future__ import annotations

import copy
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from ..ingest.model import Schedule
from ..cpm.bridge import build_engine_inputs
from ..cpm.handshake import HandshakeRefusal
from .halfstep import HalfStepResult, run_halfstep
from .dailyledger import DailyLedger, run_daily_ledger

# --------------------------------------------------------------------------
# module constants (verdict thresholds + caps; disclosed in the output)
# --------------------------------------------------------------------------
# Rationale: a delay measurement that moves by no more than a couple of workdays
# (or a tenth of its own magnitude) across every defensible method choice is, for
# forensic purposes, method-independent.  The wider MODERATE band flags a
# conclusion the expert should be able to explain but that is not overturned by
# method choice; UNSTABLE says the answer is substantially a methodology artifact.
STABLE_RANGE_PCT = 10.0     # range ≤ 10% of |median| -> STABLE
STABLE_RANGE_WD = 2.0       # ...or range ≤ 2 workdays -> STABLE
MODERATE_RANGE_PCT = 25.0   # range ≤ 25% of |median| -> MODERATE
MODERATE_RANGE_WD = 5.0     # ...or range ≤ 5 workdays -> MODERATE

# Daily framing is only offered on windows this short (calendar days); longer
# windows would require a very long daily engine sweep and the technique's value
# (eliminating boundary judgement) is aimed at contemporaneous-length windows.
_DAILY_SPAN_CAP = 120

# Default cap on the enumerated variant grid.
_DEFAULT_MAX_VARIANTS = 24

_FRAMING_LABELS = {
    "mip34_halfstep": "MIP 3.4 half-step bifurcation (D9)",
    "mip33_asis": "MIP 3.3 as-is observational (D9 mip33_row)",
    "n3_daily": "N3 daily-ledger cumulative (later-network framing)",
}

_PRELIMINARY = (
    "PRELIMINARY — this certificate stress-tests the METHOD, not the schedule. "
    "The per-variant numbers are produced by disclosed OBSERVATIONAL allocation "
    "heuristics and exist only to screen the sensitivity of the answer to method "
    "choices; causation, concurrency, entitlement (EOT/compensation) and quantum "
    "are reserved to the expert (AACE 29R-03; SCL Protocol 2nd ed.). Nothing here "
    "is an apportionment opinion.")

_ALLOCATION_NOTE = (
    "Allocation heuristics (OBSERVATIONAL, disclosed): mip34_halfstep splits the "
    "progress effect across the controlling-path activities by |remaining-"
    "duration change| and the revision effect across the D9 named top movers "
    "(relationship edits map to the bound successor; residual to 'Unallocated'); "
    "mip33_asis allocates the whole-window movement to the window's controlling "
    "activity's party; n3_daily uses the N3 per-party subtotals directly. These "
    "are a stability screen, never an apportionment.")

_UNALLOCATED = "Unallocated"


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class VariantRow:
    """One cell of the method grid — the measurement under one set of coordinates."""
    variant_id: str
    framing: str
    statusing: str
    boundary: str
    contested: str
    is_primary: bool = False
    statusing_mode_resolved: str = ""       # read back from the bridge disclosure
    computable: bool = True
    reason: str = ""
    total_workdays: Optional[float] = None  # the measured quantity (Σ over windows)
    per_party: dict[str, float] = field(default_factory=dict)   # overlay only
    windows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "coordinates": {
                "framing": self.framing,
                "framing_label": _FRAMING_LABELS.get(self.framing, self.framing),
                "statusing": self.statusing,
                "statusing_mode_resolved": self.statusing_mode_resolved,
                "boundary": self.boundary,
                "contested": self.contested,
            },
            "is_primary": self.is_primary,
            "computable": self.computable,
            "reason": self.reason,
            "total_workdays": _round(self.total_workdays),
            "per_party": {k: _round(v) for k, v in sorted(self.per_party.items())},
            "windows": list(self.windows),
        }


@dataclass
class StabilityStat:
    """Min/max/range/median/spread and verdict for one measured series across the
    computable variants."""
    series: str                 # party name, or "TOTAL" (no-overlay sweep)
    n_variants: int
    values: list[float]
    minimum: float
    maximum: float
    range: float
    median: float
    spread_pct: Optional[float]
    verdict: str
    sentence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": self.series,
            "n_variants": self.n_variants,
            "values": [_round(v) for v in self.values],
            "min": _round(self.minimum),
            "max": _round(self.maximum),
            "range": _round(self.range),
            "median": _round(self.median),
            "spread_pct": _round(self.spread_pct),
            "verdict": self.verdict,
            "sentence": self.sentence,
        }


@dataclass
class RobustnessCertificate:
    """The methodology-robustness certificate for one target across one series."""
    target: Optional[str] = None
    target_resolved_how: str = ""
    n_schedules: int = 0
    overlay: bool = False
    handshake_mode: str = "require"
    handshake_primary_earlier: Optional[dict[str, Any]] = None
    handshake_primary_later: Optional[dict[str, Any]] = None

    dimensions: dict[str, Any] = field(default_factory=dict)
    variants: list[VariantRow] = field(default_factory=list)
    stability: list[StabilityStat] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)
    verdict_thresholds: dict[str, Any] = field(default_factory=dict)

    disclosures: list[str] = field(default_factory=list)
    preliminary: str = _PRELIMINARY
    allocation_note: str = _ALLOCATION_NOTE

    @property
    def computable_variants(self) -> int:
        return sum(1 for v in self.variants if v.computable)

    def variant(self, variant_id: str) -> Optional[VariantRow]:
        for v in self.variants:
            if v.variant_id == variant_id:
                return v
        return None

    def primary(self) -> Optional[VariantRow]:
        for v in self.variants:
            if v.is_primary:
                return v
        return None

    def series(self, name: str) -> Optional[StabilityStat]:
        for s in self.stability:
            if s.series == name:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": ("methodology-robustness certificate (N4; ANALYTICS_PROPOSAL "
                      "§8.4) — a stability screen of the METHOD"),
            "target": self.target,
            "target_resolved_how": self.target_resolved_how,
            "n_schedules": self.n_schedules,
            "overlay": self.overlay,
            "handshake": {
                "mode": self.handshake_mode,
                "primary_earlier": self.handshake_primary_earlier,
                "primary_later": self.handshake_primary_later,
            },
            "dimensions": self.dimensions,
            "verdict_thresholds": self.verdict_thresholds,
            "variants": [v.to_dict() for v in self.variants],
            "computable_variant_count": self.computable_variants,
            "total_variant_count": len(self.variants),
            "stability": [s.to_dict() for s in self.stability],
            "sentences": list(self.sentences),
            "disclosures": list(self.disclosures),
            "allocation_note": self.allocation_note,
            "preliminary": self.preliminary,
        }


class _VariantSkip(Exception):
    """A non-handshake reason a variant is not computable (bad span, blocked
    decomposition, invalid network under skip)."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _round(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    r = round(float(x) + 0.0, 3)
    return int(r) if r == int(r) else r


def _own_mode(sched: Schedule) -> str:
    return ("progress_override" if sched.settings.progress_override
            else "retained_logic")


def _id_match(identifier: str, edit_label: str) -> bool:
    """Case-insensitive substring/prefix match either direction (documented)."""
    a = identifier.strip().lower()
    b = edit_label.strip().lower()
    return bool(a) and (a in b or b in a)


def _party_code_from_edit(label: str) -> str:
    """Extract the activity code a named D9 edit is anchored to, for a party
    lookup.  Relationship edits ("add A->B", "delete A->B", "modify A->B") anchor
    on the bound SUCCESSOR (B); activity edits ("add activity C", "delete
    activity C") and field edits ("OD C: ...", "calendar C: ...", "constraint C:
    ...") anchor on the named activity C."""
    parts = label.split()
    if not parts:
        return ""
    head = parts[0]
    if head in ("OD", "calendar", "constraint") and len(parts) >= 2:
        return parts[1].rstrip(":")
    if head in ("add", "delete", "modify"):
        if len(parts) >= 3 and parts[1] == "activity":
            return parts[2]
        seg = parts[-1]
        if "->" in seg:
            return seg.split("->")[-1]
    return parts[-1].rstrip(":")


def _fmt_wd(x: float) -> str:
    r = _round(x)
    return str(r)


def _norm_responsibility(sched: Schedule, responsibility: Any,
                         disclosures: list[str]) -> Optional[dict[str, str]]:
    """Normalize responsibility to a UID -> party map, with legacy fallback.

    Codes remain accepted at this boundary for old callers, but every activity
    carrying a UID is converted to that UID before the N4 sweep allocates a
    progress/revision component.  This keeps a stable activity identity through
    a code change instead of silently moving its delay to ``Unallocated``.
    """
    if responsibility is None:
        return None
    tags = getattr(responsibility, "tags_by_code", None)
    if tags is not None:
        return {a.uid or a.code: tags[a.code]
                for a in sched.activities.values() if a.code in tags}
    if isinstance(responsibility, dict):
        if any(k in sched.activities for k in responsibility):
            return dict(responsibility)
        return {a.uid or a.code: responsibility[a.code]
                for a in sched.activities.values() if a.code in responsibility}
    try:
        from ..intake.responsibility import tag_schedule
        by_uid = tag_schedule(sched, list(responsibility))
        return {u or sched.activities[u].code: p for u, p in by_uid.items()
                if u in sched.activities}
    except Exception:
        disclosures.append(
            "responsibility overlay was not a recognized structure "
            "(ResponsibilityResult, code->party dict, or rule list); ignored — "
            "the sweep runs on totals only.")
        return None


# --------------------------------------------------------------------------
# verdict banding + stability stats (exported, unit-testable)
# --------------------------------------------------------------------------
def band_verdict(range_wd: float, median: float) -> str:
    """Assign a stability band to one measured series from its range and median.

    STABLE   : range ≤ STABLE_RANGE_WD workdays, OR ≤ STABLE_RANGE_PCT% of |median|.
    MODERATE : range ≤ MODERATE_RANGE_WD workdays, OR ≤ MODERATE_RANGE_PCT% of |median|.
    UNSTABLE : otherwise.
    """
    a = abs(median)
    if range_wd <= STABLE_RANGE_WD or (a and range_wd <= STABLE_RANGE_PCT / 100.0 * a):
        return "STABLE"
    if range_wd <= MODERATE_RANGE_WD or (a and range_wd <= MODERATE_RANGE_PCT / 100.0 * a):
        return "MODERATE"
    return "UNSTABLE"


def compute_stability_stats(rows: list[VariantRow]) -> list[StabilityStat]:
    """Stability statistics per measured series across the COMPUTABLE variants in
    ``rows``.  Overlay mode (per-party series) is used when any computable row
    carries a ``per_party`` mapping; otherwise a single ``TOTAL`` series is built
    from ``total_workdays``.  Exported so the arithmetic can be unit-tested on
    hand-built rows."""
    comp = [r for r in rows if r.computable]
    overlay = any(r.per_party for r in comp)
    if overlay:
        series_keys = sorted({k for r in comp for k in r.per_party})
    else:
        series_keys = ["TOTAL"]

    out: list[StabilityStat] = []
    for key in series_keys:
        values: list[float] = []
        for r in comp:
            if overlay:
                values.append(float(r.per_party.get(key, 0.0)))
            elif r.total_workdays is not None:
                values.append(float(r.total_workdays))
        if not values:
            continue
        mn, mx = min(values), max(values)
        rng = mx - mn
        med = statistics.median(values)
        spread = (rng / abs(med) * 100.0) if med else None
        verdict = band_verdict(rng, med)
        if overlay:
            sentence = (f"{key}-responsible delay ranges {_fmt_wd(mn)}–{_fmt_wd(mx)} "
                        f"wd across {len(values)} method variants ({verdict}).")
        else:
            sentence = (f"Total target movement ranges {_fmt_wd(mn)}–{_fmt_wd(mx)} "
                        f"wd across {len(values)} method variants ({verdict}).")
        out.append(StabilityStat(
            series=key, n_variants=len(values), values=list(values),
            minimum=mn, maximum=mx, range=rng, median=med,
            spread_pct=spread, verdict=verdict, sentence=sentence))
    return out


# --------------------------------------------------------------------------
# the sweep engine
# --------------------------------------------------------------------------
class _Sweep:
    """Holds the schedules + caches and computes one variant's measured quantity.
    Caching: run_halfstep is memoized per (i, j, statusing) — MIP 3.3 reads the
    same result, and the contested-revision exclusion is arithmetic post-
    processing, so neither needs an extra engine run.  run_daily_ledger is
    memoized per (i, j, statusing).  Flipped schedule copies are memoized per
    (index, statusing)."""

    def __init__(self, schedules, *, target, resp_map, contested, handshake,
                 threshold_pct):
        self.schedules = schedules
        self.target = target
        self.resp_map = resp_map
        self.overlay = resp_map is not None
        self.contested = list(contested or [])
        self.handshake = handshake
        self.threshold_pct = threshold_pct
        self._flip_cache: dict[tuple[int, str], Schedule] = {}
        self._hs_cache: dict[tuple[int, int, str], Any] = {}
        self._daily_cache: dict[tuple[int, int, str], Any] = {}
        self._mode_cache: dict[tuple[int, str], tuple[str, str]] = {}

    # -- statusing application (deep-copy + flip) --------------------------
    def _flip(self, i: int, statusing: str) -> Schedule:
        if _own_mode(self.schedules[i]) == statusing:
            return self.schedules[i]           # already in mode -> reproduce direct run
        key = (i, statusing)
        s = self._flip_cache.get(key)
        if s is None:
            s = copy.deepcopy(self.schedules[i])
            s.settings.progress_override = (statusing == "progress_override")
            self._flip_cache[key] = s
        return s

    def resolved_mode(self, i: int, statusing: str) -> tuple[str, str]:
        """(engine statusing_mode value, the bridge's own disclosure) for the
        flipped schedule — evidence the bridge picked the flip up."""
        key = (i, statusing)
        if key not in self._mode_cache:
            ei = build_engine_inputs(self._flip(i, statusing))
            disc = next((d for d in ei.disclosures
                         if d.startswith("statusing mode:")), "")
            self._mode_cache[key] = (ei.statusing_mode.value, disc)
        return self._mode_cache[key]

    # -- cached engine runs ------------------------------------------------
    def _get_halfstep(self, i: int, j: int, statusing: str) -> HalfStepResult:
        key = (i, j, statusing)
        cached = self._hs_cache.get(key)
        if cached is not None:
            if isinstance(cached, HandshakeRefusal):
                raise cached
            return cached
        try:
            r = run_halfstep(self._flip(i, statusing), self._flip(j, statusing),
                             target=self.target, handshake=self.handshake,
                             threshold_pct=self.threshold_pct)
        except HandshakeRefusal as exc:
            self._hs_cache[key] = exc
            raise
        self._hs_cache[key] = r
        return r

    def _get_daily(self, i: int, j: int, statusing: str) -> DailyLedger:
        key = (i, j, statusing)
        cached = self._daily_cache.get(key)
        if cached is not None:
            if isinstance(cached, HandshakeRefusal):
                raise cached
            return cached
        try:
            r = run_daily_ledger(self._flip(i, statusing), self._flip(j, statusing),
                                 target=self.target, handshake=self.handshake,
                                 threshold_pct=self.threshold_pct,
                                 responsibility=self.resp_map)
        except HandshakeRefusal as exc:
            self._daily_cache[key] = exc
            raise
        self._daily_cache[key] = r
        return r

    def _span_days(self, i: int, j: int) -> Optional[int]:
        de = self.schedules[i].data_date
        dl = self.schedules[j].data_date
        if de is None or dl is None:
            return None
        de = de.date() if isinstance(de, datetime) else de
        dl = dl.date() if isinstance(dl, datetime) else dl
        return (dl - de).days

    # -- per-pair measurement ----------------------------------------------
    def measure_pair(self, framing: str, statusing: str, i: int, j: int,
                     contested: str, disclosures: list[str]) -> dict[str, Any]:
        if framing == "n3_daily":
            span = self._span_days(i, j)
            if span is not None and span > _DAILY_SPAN_CAP:
                raise _VariantSkip(
                    f"daily framing skipped: window {self.schedules[i].label()}->"
                    f"{self.schedules[j].label()} spans {span} calendar days > "
                    f"{_DAILY_SPAN_CAP}")
            dl = self._get_daily(i, j, statusing)      # may raise HandshakeRefusal
            return self._measure_daily(dl)
        hs = self._get_halfstep(i, j, statusing)       # may raise HandshakeRefusal
        if framing == "mip33_asis":
            return self._measure_mip33(hs)
        return self._measure_mip34(hs, contested, disclosures)

    def _measure_mip34(self, hs: HalfStepResult, contested: str,
                       disclosures: list[str]) -> dict[str, Any]:
        if hs.total_movement_workdays is None:
            raise _VariantSkip(hs.decomposition_blocking
                               or "half-step decomposition not computable")
        prog = hs.progress_effect_workdays or 0
        rev = hs.revision_effect_workdays or 0

        # contested-revision exclusion (arithmetic; matched top-mover deltas)
        excluded: set[str] = set()
        matched_total = 0
        if contested == "without_contested":
            for m in self._named_movers(hs):
                if any(_id_match(idf, m["edit"]) for idf in self.contested):
                    excluded.add(m["edit"])
                    matched_total += m["delta_workdays"]
            if not excluded:
                disclosures.append(
                    f"contested revisions {self.contested!r} matched no named "
                    f"top-mover edit in window {hs.earlier_label}->{hs.later_label}; "
                    "no exclusion applied (the without-contested variant equals the "
                    "with-contested variant for this window).")
        rev_adj = rev - matched_total
        total = prog + rev_adj

        per_party: Optional[dict[str, float]] = None
        if self.overlay:
            per_party = {}
            self._allocate_progress(per_party, hs, prog)
            self._allocate_revision(per_party, hs, rev_adj, excluded)
        return {
            "total": float(total), "per_party": per_party,
            "detail": {
                "framing": "mip34_halfstep",
                "pair": f"{hs.earlier_label}->{hs.later_label}",
                "progress_effect_workdays": prog,
                "revision_effect_workdays": rev,
                "revision_effect_after_exclusion": rev_adj,
                "total_movement_workdays": hs.total_movement_workdays,
                "excluded_edits": sorted(excluded),
                "excluded_delta_workdays": matched_total,
            },
        }

    def _measure_mip33(self, hs: HalfStepResult) -> dict[str, Any]:
        total = hs.total_movement_workdays
        if total is None:
            raise _VariantSkip(hs.decomposition_blocking
                               or "MIP 3.3 movement not computable")
        per_party: Optional[dict[str, float]] = None
        if self.overlay:
            uid, code = self._controlling_ref(hs)
            party = self._party_for_ref(uid, code)
            per_party = {party: float(total)}
        return {
            "total": float(total), "per_party": per_party,
            "detail": {
                "framing": "mip33_asis",
                "pair": f"{hs.earlier_label}->{hs.later_label}",
                "whole_window_movement_workdays": total,
                "controlling_code": self._controlling_code(hs),
                "mip33_row": hs.mip33_row,
            },
        }

    def _measure_daily(self, dl: DailyLedger) -> dict[str, Any]:
        if not dl.computable:
            raise _VariantSkip(dl.blocking or "daily ledger not computable")
        total = dl.arithmetic_check.get("endpoint_delta_wd")
        if total is None:
            total = sum(r.delta_workdays for r in dl.rows)
        per_party: Optional[dict[str, float]] = None
        if self.overlay:
            per_party = {}
            by = dl.responsibility_subtotals.get("by_party", {})
            for pk, v in by.items():
                key = _UNALLOCATED if pk in ("Untagged", _UNALLOCATED) else pk
                per_party[key] = per_party.get(key, 0.0) + float(v["delta_workdays"])
        return {
            "total": float(total), "per_party": per_party,
            "detail": {
                "framing": "n3_daily",
                "pair": f"{dl.earlier_label}->{dl.later_label}",
                "endpoint_delta_workdays": total,
            },
        }

    # -- allocation helpers ------------------------------------------------
    def _party_for_ref(self, uid: Optional[str] = None,
                       code: Optional[str] = None) -> str:
        """Resolve an N4 contributor UID first, with legacy code fallback."""
        if uid and uid in self.resp_map:
            return self.resp_map[uid]
        if code and code in self.resp_map:
            return self.resp_map[code]
        return _UNALLOCATED

    @staticmethod
    def _named_movers(hs: HalfStepResult) -> list[dict[str, Any]]:
        movers: list[dict[str, Any]] = []
        for ca in hs.class_attributions:
            for m in ca.top_movers:
                if m.get("edit") == "__truncated__" or not m.get("computable"):
                    continue
                if m.get("delta_workdays") is None:
                    continue
                movers.append(m)
        return movers

    def _allocate_progress(self, per_party: dict[str, float],
                           hs: HalfStepResult, prog: float) -> None:
        contribs = hs.progress_contributors or []
        weights = [(c.get("uid"), c["code"],
                    abs(c.get("rd_change_workdays") or 0.0))
                   for c in contribs]
        wsum = sum(w for _, _, w in weights)
        if wsum > 0:
            for uid, code, w in weights:
                p = self._party_for_ref(uid, code)
                per_party[p] = per_party.get(p, 0.0) + prog * w / wsum
        else:
            per_party[_UNALLOCATED] = per_party.get(_UNALLOCATED, 0.0) + prog

    def _allocate_revision(self, per_party: dict[str, float], hs: HalfStepResult,
                           rev_adj: float, excluded: set[str]) -> None:
        named_sum = 0.0
        for m in self._named_movers(hs):
            if m["edit"] in excluded:
                continue
            code = _party_code_from_edit(m["edit"])
            p = self._party_for_ref(m.get("uid"), code)
            per_party[p] = per_party.get(p, 0.0) + m["delta_workdays"]
            named_sum += m["delta_workdays"]
        residual = rev_adj - named_sum
        per_party[_UNALLOCATED] = per_party.get(_UNALLOCATED, 0.0) + residual

    def _controlling_ref(self, hs: HalfStepResult) -> tuple[Optional[str], Optional[str]]:
        if hs.progress_contributors:
            top = hs.progress_contributors[0]
            return top.get("uid"), top.get("code")
        best = None
        for m in self._named_movers(hs):
            d = m["delta_workdays"]
            if d and (best is None or abs(d) > abs(best[1])):
                best = (m["edit"], d)
        if best:
            mover = next((m for m in self._named_movers(hs)
                          if m.get("edit") == best[0]), None)
            return (mover.get("uid") if mover else None,
                    _party_code_from_edit(best[0]))
        return None, None

    def _controlling_code(self, hs: HalfStepResult) -> Optional[str]:
        """Display-only controlling code retained for certificate provenance."""
        return self._controlling_ref(hs)[1]


# --------------------------------------------------------------------------
# grid enumeration
# --------------------------------------------------------------------------
def _boundary_sets(schedules) -> list[tuple[str, list[tuple[int, int]]]]:
    """The boundary-perturbation coordinates: the full consecutive segmentation,
    plus one segmentation per interior boundary dropped (adjacent windows
    merged).  Each is a list of (earlier_index, later_index) pairs."""
    n = len(schedules)
    idx = list(range(n))
    sets: list[tuple[str, list[tuple[int, int]]]] = [
        ("full", [(idx[k], idx[k + 1]) for k in range(n - 1)])]
    for k in range(1, n - 1):        # interior boundaries only
        reduced = [x for x in idx if x != k]
        pairs = [(reduced[t], reduced[t + 1]) for t in range(len(reduced) - 1)]
        sets.append((f"drop:{schedules[k].label()}", pairs))
    return sets


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------
def run_robustness_certificate(schedules: list[Schedule], *,
                               target: Optional[str] = None,
                               contested_revisions: Optional[list[str]] = None,
                               responsibility: Any = None,
                               handshake: str = "require",
                               threshold_pct: float = 99.0,
                               include_daily: bool = True,
                               max_variants: int = _DEFAULT_MAX_VARIANTS
                               ) -> RobustnessCertificate:
    """Build the methodology-robustness certificate for ``target`` across the
    update ``schedules`` (see the module docstring for every method choice).

    ``handshake="require"`` gates each variant on the ADR-0007 handshake and
    RE-RAISES :class:`HandshakeRefusal` from the PRIMARY (unperturbed) variant;
    every other variant degrades to not-computable on refusal.  ``handshake=
    "skip"`` bypasses the gate for every variant (disclosed) so no refusal can
    propagate."""
    if handshake not in ("require", "skip"):
        raise ValueError(f"handshake must be 'require' or 'skip', got {handshake!r}")
    if len(schedules) < 2:
        raise ValueError("run_robustness_certificate needs at least 2 schedules")

    cert = RobustnessCertificate(target=target, n_schedules=len(schedules),
                                 handshake_mode=handshake)
    cert.verdict_thresholds = {
        "STABLE": (f"range ≤ {STABLE_RANGE_PCT:g}% of |median| or ≤ "
                   f"{STABLE_RANGE_WD:g} wd"),
        "MODERATE": (f"range ≤ {MODERATE_RANGE_PCT:g}% of |median| or ≤ "
                     f"{MODERATE_RANGE_WD:g} wd"),
        "UNSTABLE": "otherwise",
        "rationale": ("a measurement that moves ≤ a couple of workdays (or a "
                      "tenth of its magnitude) across every defensible method "
                      "choice is, forensically, method-independent."),
    }

    resp_map = _norm_responsibility(schedules[-1], responsibility, cert.disclosures)
    cert.overlay = resp_map is not None

    sweep = _Sweep(schedules, target=target, resp_map=resp_map,
                   contested=contested_revisions, handshake=handshake,
                   threshold_pct=threshold_pct)

    # -- dimension coordinate lists ---------------------------------------
    framings = ["mip34_halfstep", "mip33_asis"]
    if include_daily:
        framings.append("n3_daily")
    statusings = ["retained_logic", "progress_override"]
    boundary_sets = _boundary_sets(schedules)
    contested_coords = ["with_revisions"]
    if contested_revisions:
        contested_coords.append("without_contested")

    own = _own_mode(schedules[0])
    if _own_mode(schedules[-1]) != own:
        cert.disclosures.append(
            "the series' files disagree on the SCHEDOPTIONS statusing mode; the "
            f"primary variant uses the first file's own mode ({own}).")

    # collapsed-dimension disclosures
    if len(schedules) < 3:
        cert.disclosures.append(
            "window-boundary dimension COLLAPSED: with 2 schedules there is no "
            "interior boundary to drop, so only the single window is measured.")
    if not contested_revisions:
        cert.disclosures.append(
            "contested-revision dimension COLLAPSED: no contested_revisions were "
            "given, so no with/without-contested pair is swept.")
    if not include_daily:
        cert.disclosures.append(
            "N3 daily framing DISABLED (include_daily=False); only the MIP 3.4 and "
            "MIP 3.3 framings are swept.")
    cert.disclosures.append(
        "statusing variants are applied by DEEP-COPYING the schedule and flipping "
        "settings.progress_override; the resolved engine mode is read back from "
        "the bridge's own disclosure and recorded per variant (statusing_mode_"
        "resolved).")

    # -- enumerate the combinatorial grid (deterministic order) -----------
    combos: list[tuple[str, str, str, list[tuple[int, int]], str]] = []
    for b_label, pairs in boundary_sets:
        for framing in framings:
            for st in statusings:
                for cc in contested_coords:
                    # the contested dimension only expands the half-step framing
                    if cc == "without_contested" and framing != "mip34_halfstep":
                        continue
                    combos.append((framing, st, b_label, pairs, cc))

    truncated: list[tuple] = []
    if len(combos) > max_variants:
        truncated = combos[max_variants:]
        combos = combos[:max_variants]
        cert.disclosures.append(
            f"variant grid capped at max_variants={max_variants}: "
            f"{len(truncated)} variant(s) truncated in enumeration order "
            "(boundary -> framing -> statusing -> contested). Truncated: "
            + "; ".join(f"{f}|{s}|{b}|{c}" for f, s, b, _p, c in truncated) + ".")

    cert.dimensions = {
        "framings": [{"key": f, "label": _FRAMING_LABELS[f]} for f in framings],
        "statusings": statusings,
        "boundary_sets": [{"label": lbl,
                           "windows": [f"{schedules[i].label()}->{schedules[j].label()}"
                                       for i, j in prs]}
                          for lbl, prs in boundary_sets],
        "contested_coords": contested_coords,
        "contested_revisions": list(contested_revisions or []),
        "include_daily": include_daily,
        "daily_span_cap_days": _DAILY_SPAN_CAP,
        "max_variants": max_variants,
        "enumerated": len(combos) + len(truncated),
        "run": len(combos),
        "truncated": len(truncated),
    }

    primary_coord = ("mip34_halfstep", own, boundary_sets[0][0], "with_revisions")

    # -- run each variant --------------------------------------------------
    for framing, st, b_label, pairs, cc in combos:
        vid = f"{framing}|{st}|{b_label}|{cc}"
        is_primary = (framing, st, b_label, cc) == primary_coord
        row = VariantRow(variant_id=vid, framing=framing, statusing=st,
                         boundary=b_label, contested=cc, is_primary=is_primary)
        # record the resolved statusing mode (evidence the bridge took the flip)
        try:
            mode_val, mode_disc = sweep.resolved_mode(pairs[-1][1], st)
            row.statusing_mode_resolved = mode_val
            if mode_disc and mode_disc not in cert.disclosures:
                cert.disclosures.append("bridge: " + mode_disc)
        except Exception:  # pragma: no cover - defensive
            pass

        try:
            total = 0.0
            per_party: dict[str, float] = {}
            windows: list[dict[str, Any]] = []
            for i, j in pairs:
                m = sweep.measure_pair(framing, st, i, j, cc, cert.disclosures)
                total += m["total"]
                if sweep.overlay and m["per_party"] is not None:
                    for p, v in m["per_party"].items():
                        per_party[p] = per_party.get(p, 0.0) + v
                windows.append({
                    "window": f"{schedules[i].label()}->{schedules[j].label()}",
                    "total_workdays": _round(m["total"]),
                    "per_party": ({k: _round(v) for k, v in sorted(m["per_party"].items())}
                                  if (sweep.overlay and m["per_party"] is not None) else None),
                    "detail": m["detail"],
                })
            row.total_workdays = total
            row.per_party = per_party if sweep.overlay else {}
            row.windows = windows

            # capture the primary handshake summaries for the certificate header
            if is_primary and framing == "mip34_halfstep":
                hs = sweep._get_halfstep(pairs[0][0], pairs[0][1], st)
                cert.handshake_primary_earlier = hs.handshake_earlier
                cert.handshake_primary_later = hs.handshake_later
                cert.target_resolved_how = hs.resolved_how
        except HandshakeRefusal as exc:
            if is_primary and handshake == "require":
                raise
            row.computable = False
            row.reason = f"handshake refused: {exc}"
        except _VariantSkip as exc:
            row.computable = False
            row.reason = str(exc)

        cert.variants.append(row)

    # a target-resolution note even when the primary refused/none captured
    if not cert.target_resolved_how:
        for v in sweep._hs_cache.values():
            if isinstance(v, HalfStepResult):
                cert.target_resolved_how = v.resolved_how
                break

    # -- stability stats + §8.4 sentences ---------------------------------
    cert.stability = compute_stability_stats(cert.variants)
    cert.sentences = [s.sentence for s in cert.stability]
    return cert
