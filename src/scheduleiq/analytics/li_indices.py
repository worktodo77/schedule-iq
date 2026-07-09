"""LI-proprietary schedule indices (backlog N6/N9/N10/N12/N14).

Five bespoke Long International metrics computed over an ordered update series,
each a single defensible number per update/window, decomposable to named
activities and trackable as a curve across the Project:

* **FCBI** — Float Criticality Burn Index (§9.1): float consumption weighted
  by how critical the consumed float was.
* **PCI** — Path Concentration Index (§9.4): Herfindahl concentration of the
  near-critical float paths' criticality weights.
* **RDI** — Recovery Debt Index (§9.5): cumulative gap between the pace a
  forecast requires and the pace the Project has actually demonstrated.
* **CDI** — Criticality Dwell Index (§10.2): each activity's share of the
  Project's total criticality-time.
* **BWI** — Bow-Wave Index (§10.4): near-critical work packed against a
  (typically constrained) milestone, per remaining working period, normalized
  to the first update.

Design duties (CLAUDE.md):
  * Perspective governs emphasis, never the facts — every number is reproducible
    from the parsed .xer via the shared float-path module.
  * Causation/entitlement/concurrency/quantum stay reserved to the expert; the
    interpretation strings below are descriptive triage language only.

Everything degrades gracefully: a series with no float or no dates yields empty
sub-results carrying a ``reason``; nothing here raises.  The float-path
extraction (the expensive step) is computed once per schedule and shared across
the three indices that use the criticality kernel (FCBI/PCI/CDI).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..ingest.model import ActivityType, ConstraintType, Schedule
from .paths import FloatPath, float_paths

DEFAULT_LAMBDA = 5.0          # half-weight constant, working days
DEFAULT_BAND_DAYS = 10.0      # near-critical band, working days
KERNEL_PATHS_N = 10           # top-N float paths feeding the criticality kernel


# ==========================================================================
# Shared criticality kernel  (published for the scoring spec to cite)
# ==========================================================================
def kernel_weight(rf_days: float, lam: float = DEFAULT_LAMBDA) -> float:
    """Exponential criticality weight of an activity/path.

    Formula
    -------
        weight = 2 ** (-RF / lam)

    where ``RF`` is the relative float in working days and ``lam`` the
    half-weight constant.  Driving-path float (RF = 0) weighs 1.0; float one
    half-weight constant off the path (RF = lam) weighs 0.5; two off
    (RF = 2*lam) weighs 0.25.  Negative RF (paths in negative float) weighs
    above 1.0, so genuinely over-critical work is never under-counted.
    """
    return 2.0 ** (-rf_days / lam)


# --------------------------------------------------------------------------
# Methodology rule (approved 2026-07-08; RDI/BWI/CDI audit, ruling C1/X1):
# LOE, WBS-summary, hammock, and other summary activities are not discrete
# executable work and therefore SHALL NOT contribute to the proprietary LI
# indices that measure criticality, float consumption, recovery, or
# criticality-time.  They are excluded here, at the shared criticality kernel,
# so every kernel/RF-map consumer (FCBI, CDI) inherits the exclusion; PCI
# additionally drops paths with no discrete-work member (see _build_kernel).
# RDI and BWI already exclude summary activities at their own loops.
# Milestones are NOT summary activities and are retained (a finish milestone
# is a legitimate criticality reference); they are excluded only from PCI's
# discrete-work path test below, where they are markers rather than work.
# --------------------------------------------------------------------------
def _is_discrete_work(a) -> bool:
    """A discrete executable activity: not LOE/summary/hammock and not a
    zero-duration milestone marker.  Used to decide whether a float path
    carries real work for PCI (a pure LOE/milestone path is not a genuine
    near-critical path)."""
    return not a.is_loe_or_summary and not a.is_milestone


def relative_float_map(schedule: Schedule,
                       paths: list[FloatPath]) -> dict[str, float]:
    """Per-activity relative float RF, keyed by activity code.

    Formula
    -------
        RF(a) = min over the top-N float paths containing ``a`` of that path's
                relative float (``FloatPath.rel_float_days``);
        activities on no extracted path fall back to their own total float in
        working days on their own calendar.

    LOE/summary activities are excluded (methodology rule above): they receive
    no relative float and therefore no criticality weight.  Activities with
    neither a path membership nor a stored total float are omitted (their
    weight is undefined).
    """
    rf: dict[str, float] = {}
    for p in paths:
        for a in p.activities:
            if a.is_loe_or_summary:          # summary work carries no criticality
                continue
            cur = rf.get(a.code)
            if cur is None or p.rel_float_days < cur:
                rf[a.code] = p.rel_float_days
    for a in schedule.activities.values():
        if a.is_loe_or_summary or a.code in rf:
            continue
        own = a.total_float_days(schedule.cal_for(a))
        if own is not None:
            rf[a.code] = own
    return rf


def activity_weights(schedule: Schedule, paths: list[FloatPath],
                     lam: float = DEFAULT_LAMBDA) -> dict[str, float]:
    """Per-activity criticality weight, keyed by code:
    ``weight(a) = kernel_weight(RF(a), lam)`` over :func:`relative_float_map`.
    """
    return {code: kernel_weight(rf, lam)
            for code, rf in relative_float_map(schedule, paths).items()}


@dataclass
class _Kernel:
    """Cached per-schedule criticality bundle (float paths + RF/weight maps)."""
    paths: list[FloatPath]
    rf: dict[str, float]
    weight: dict[str, float]


def _build_kernel(schedule: Schedule, lam: float) -> _Kernel:
    # float_paths() itself is unchanged (it feeds the tool-of-record driving-path
    # analytics and must not shift).  For the LI-index kernel we drop paths with
    # no discrete-work member — a path that exists only because logic routes
    # through an LOE/summary (or is a bare milestone chain) is not a genuine
    # near-critical path and would otherwise inflate PCI's path count.
    all_paths = float_paths(schedule, n=KERNEL_PATHS_N, band_days=None)
    paths = [p for p in all_paths if any(_is_discrete_work(a) for a in p.activities)]
    rf = relative_float_map(schedule, paths)
    return _Kernel(paths=paths, rf=rf,
                   weight={c: kernel_weight(v, lam) for c, v in rf.items()})


# ==========================================================================
# small date helpers  (5-day / 8-hour standard calendar walk)
# ==========================================================================
def _working_days_5d(start: Optional[datetime], end: Optional[datetime]) -> float:
    """Standard-calendar (Mon-Fri) working days in ``[start, end)``; 0 if the
    span is empty or either bound is missing.  Defensively capped at 20 years."""
    if start is None or end is None or start >= end:
        return 0.0
    d, e = start.date(), end.date()
    cap = d + timedelta(days=20 * 365)
    n = 0
    while d < e and d < cap:
        if d.isoweekday() <= 5:
            n += 1
        d += timedelta(days=1)
    return float(n)


def _late_type(a) -> bool:
    return bool(a.constraint.is_late_type or a.constraint2.is_late_type)


# ==========================================================================
# result dataclasses
# ==========================================================================
@dataclass
class Burner:
    code: str
    name: str
    consumption_days: float
    weight: float
    contribution: float          # consumption_days * weight
    constraint_flagged: bool     # criticality is late-type-constraint-manufactured


@dataclass
class FcbiWindow:
    earlier_label: str
    later_label: str
    fcbi: float
    fcbi_recovery: float
    fcbi_pct: Optional[float]
    top_burners: list[Burner] = field(default_factory=list)
    # item 2: when the criticality-weighted float stock is <= 0 the normalized
    # form is undefined; carry the labelled reason rather than a bare None.
    pct_undefined_reason: Optional[str] = None


@dataclass
class FcbiResult:
    windows: list[FcbiWindow] = field(default_factory=list)
    cumulative: list[float] = field(default_factory=list)   # cumulative FCBI per window
    top_burners: list[Burner] = field(default_factory=list)  # aggregated across series
    interpretation: str = ""
    reason: str = ""
    # items 1/1b/3/4/5: standing methodology disclosures for every output.
    disclosures: list[str] = field(default_factory=list)


def _fcbi_disclosures(lam: float) -> list[str]:
    """The standing FCBI methodology disclosures (§9.1; audit rev 3 rulings)."""
    return [
        "Completed activities are excluded from both burn (FCBI+) and recovery "
        "(FCBI-): the index measures float consumed by *in-flight* work, so an "
        "activity's float ending at completion is not counted as burn.  This "
        "aligns FCBI with RDI and BWI (live-work indices); CDI intentionally "
        "retains completed activities as retrospective criticality dwell.",
        f"Criticality weight = 2^(-RF/{lam:g}) with RF sampled as "
        "min(RF_(u-1), RF_u) across the window, so float that was near-critical "
        "at *either* end of the interval is weighted at that criticality.",
        f"RF = the minimum relative float over the top-{KERNEL_PATHS_N} float "
        "paths containing the activity (its own total float when it is on no "
        "enumerated path); the driving path is chosen by minimum total float "
        "from the tool-of-record, not a CPM pass, so RF is independent of the "
        "diagnostic engine's statusing mode.",
        "FCBI+ is windowing-dependent and not additive across merged windows "
        "(max(0, -dTF) is a total-variation measure); compare only like-for-"
        "like update cadences.",
        "Normalized FCBI% is undefined (reported as such, not 0) when the "
        "criticality-weighted live float stock at the window start is <= 0.",
    ]


_LOE_EXCLUSION_NOTE = (
    "LOE, WBS-summary, hammock, and other summary activities are excluded: "
    "they are not discrete executable work and carry no project criticality "
    "(approved methodology, 2026-07-08)."
)


def _rdi_disclosures(scheds) -> list[str]:
    notes = [
        _LOE_EXCLUSION_NOTE,
        "Completed activities are excluded from the required-pace side and "
        "counted on the demonstrated-pace side (they are the achievement).",
        "RDI depends on each update's remaining durations and project finish "
        "date; if the project finish is absent, required pace is not computed "
        "for that update, and if remaining duration is left unmaintained (0) on "
        "incomplete near-critical work, required pace is understated.",
    ]
    missing = [s.label() for s in scheds if getattr(s, "finish_date", None) is None]
    if missing:
        notes.append("DATA QUALITY: no project finish date on update(s): "
                     + ", ".join(missing) + " — required pace omitted there.")
    return notes


def _bwi_disclosures(target_code, densities, labels) -> list[str]:
    notes = [
        _LOE_EXCLUSION_NOTE,
        "BWI depends on remaining durations of near-critical work and the "
        "target milestone's finish; where the target has no usable finish in an "
        "update, that update's density is omitted.",
    ]
    missing = [labels[i] for i, d in enumerate(densities) if d is None]
    if missing:
        notes.append(f"DATA QUALITY: target {target_code} had no usable forecast "
                     "finish / near-critical density on update(s): "
                     + ", ".join(missing) + ".")
    return notes


def _cdi_disclosures() -> list[str]:
    return [
        _LOE_EXCLUSION_NOTE,
        "Completed activities are RETAINED in CDI: it measures retrospective "
        "criticality-time (where risk dwelt over the project's life, including "
        "on now-finished work), unlike the forward-looking FCBI/RDI/BWI.",
    ]


@dataclass
class PciResult:
    labels: list[str] = field(default_factory=list)
    per_update: list[Optional[float]] = field(default_factory=list)
    interpretation: str = ""
    reason: str = ""


@dataclass
class CdiEntry:
    code: str
    name: str
    dwell_share: float
    windows_present: int


@dataclass
class CdiResult:
    leaderboard: list[CdiEntry] = field(default_factory=list)
    top_decile_share: Optional[float] = None
    allocations: int = 0             # number of updates that allocated a unit
    interpretation: str = ""
    reason: str = ""
    disclosures: list[str] = field(default_factory=list)


@dataclass
class RdiRow:
    label: str
    required_pace: Optional[float]      # R_u, work-days per working day
    demonstrated_pace: Optional[float]  # D_w for the window ending at this update
    accrual_days: float
    cumulative_days: float


@dataclass
class RdiResult:
    rows: list[RdiRow] = field(default_factory=list)
    rdi_days: float = 0.0              # final cumulative recovery debt, days
    interpretation: str = ""
    reason: str = ""
    disclosures: list[str] = field(default_factory=list)


@dataclass
class BwiRow:
    label: str
    density: Optional[float]
    bwi: Optional[float]


@dataclass
class BwiResult:
    target_code: Optional[str] = None
    rows: list[BwiRow] = field(default_factory=list)
    projected_break_label: Optional[str] = None
    interpretation: str = ""
    reason: str = ""
    disclosures: list[str] = field(default_factory=list)


@dataclass
class LiIndicesResult:
    fcbi: FcbiResult
    pci: PciResult
    cdi: CdiResult
    rdi: RdiResult
    bwi: BwiResult


# ==========================================================================
# 1. FCBI — Float Criticality Burn Index  (§9.1, N6)
# ==========================================================================
def _fcbi(sa, kernels: dict[int, _Kernel], lam: float) -> FcbiResult:
    changesets = getattr(sa, "changesets", [])
    if not changesets:
        return FcbiResult(reason="series has fewer than two updates",
                          disclosures=_fcbi_disclosures(lam))

    windows: list[FcbiWindow] = []
    cumulative: list[float] = []
    running = 0.0
    agg: dict[str, Burner] = {}
    any_delta = False

    for cs in changesets:
        earlier = cs.earlier
        later = cs.later
        ek = kernels[id(earlier)]
        lk = kernels[id(later)]
        e_by_code = {a.code: a for a in earlier.activities.values()}
        l_by_code = {a.code: a for a in later.activities.values()}

        def _win_weight(code: str) -> Optional[float]:
            """Item 3 — weight from min(RF_(u-1), RF_u): float that was
            near-critical at *either* end of the window is weighted at that
            criticality.  ``None`` when the activity has no RF at either end."""
            rfs = [r for r in (ek.rf.get(code), lk.rf.get(code)) if r is not None]
            if not rfs:
                return None
            return kernel_weight(min(rfs), lam)

        burn = 0.0
        recov = 0.0
        burners: list[Burner] = []
        for code, delta in cs.float_deltas.items():
            # methodology rule (C1): LOE/summary activities are not discrete work
            # and never contribute burn or recovery.  (The shared kernel already
            # denies them a weight; this explicit guard is the visible contract
            # at FCBI and is robust to any future kernel refactor.)
            ea0, la0 = e_by_code.get(code), l_by_code.get(code)
            if (la0 is not None and la0.is_loe_or_summary) or \
               (ea0 is not None and ea0.is_loe_or_summary):
                continue
            # item 1 — completed activities are out of scope for BOTH burn and
            # recovery: an activity's float ending at completion is not a burn.
            la = l_by_code.get(code)
            if la is not None and la.completed:
                continue
            any_delta = True
            w = _win_weight(code)
            if w is None:
                continue
            if delta > 0:                       # regained float, tracked separately
                recov += delta * w
                continue
            c = -delta                          # consumption in working days (>= 0)
            if c <= 0:
                continue
            contrib = c * w
            burn += contrib
            ea = e_by_code.get(code)
            flagged = _late_type(ea) if ea is not None else False
            b = Burner(code=code, name=ea.name if ea else "",
                       consumption_days=c, weight=w, contribution=contrib,
                       constraint_flagged=flagged)
            burners.append(b)
            a = agg.get(code)
            if a is None:
                agg[code] = Burner(code, b.name, c, w, contrib, flagged)
            else:
                a.consumption_days += c
                a.contribution += contrib
                a.constraint_flagged = a.constraint_flagged or flagged

        # normalized: share of the criticality-weighted *live* float stock burned.
        # Completed and LOE/summary activities are excluded (item 1 / rule C1) and
        # the same min(RF) weight is used, so numerator and denominator share one
        # basis.
        denom = 0.0
        for a in earlier.activities.values():
            if a.completed or a.is_loe_or_summary:
                continue
            tf = a.total_float_days(earlier.cal_for(a))
            if tf is not None and tf > 0:
                w = _win_weight(a.code)
                if w is not None:
                    denom += tf * w
        if denom > 0:
            pct = 100.0 * burn / denom
            pct_reason = None
        else:
            pct = None
            pct_reason = ("criticality-weighted live float stock exhausted; "
                          "normalized FCBI undefined — interpret absolute FCBI+")

        burners.sort(key=lambda x: x.contribution, reverse=True)
        windows.append(FcbiWindow(
            earlier_label=earlier.label(), later_label=cs.later.label(),
            fcbi=burn, fcbi_recovery=recov, fcbi_pct=pct,
            top_burners=burners[:10], pct_undefined_reason=pct_reason))
        running += burn
        cumulative.append(running)

    if not any_delta:
        return FcbiResult(windows=windows, cumulative=cumulative,
                          reason="no incomplete activity carried total float in "
                                 "both updates of any pair",
                          disclosures=_fcbi_disclosures(lam))

    top = sorted(agg.values(), key=lambda x: x.contribution, reverse=True)[:15]
    total = cumulative[-1] if cumulative else 0.0
    flagged_n = sum(1 for b in top if b.constraint_flagged)
    interp = (f"Criticality-weighted float burn totals {total:.1f} weighted "
              f"working-day-units across {len(windows)} window(s); "
              f"{top[0].code if top else 'n/a'} is the largest single burner"
              + (f" ({flagged_n} of the top burners are flagged as "
                 "constraint-manufactured criticality)." if flagged_n
                 else "."))
    return FcbiResult(windows=windows, cumulative=cumulative,
                      top_burners=top, interpretation=interp,
                      disclosures=_fcbi_disclosures(lam))


# ==========================================================================
# 2. PCI — Path Concentration Index  (§9.4, N9)
# ==========================================================================
def _pci(sa, kernels: dict[int, _Kernel], lam: float) -> PciResult:
    scheds = getattr(sa, "schedules", [])
    if not scheds:
        return PciResult(reason="no schedules")
    labels = [s.label() for s in scheds]
    per: list[Optional[float]] = []
    computed = False
    for s in scheds:
        paths = kernels[id(s)].paths
        weights = [kernel_weight(p.rel_float_days, lam) for p in paths]
        tot = sum(weights)
        if not paths or tot <= 0:
            per.append(None)
            continue
        shares = [w / tot for w in weights]
        per.append(sum(sh * sh for sh in shares))     # Herfindahl, 1/N .. 1
        computed = True
    if not computed:
        return PciResult(labels=labels, per_update=per,
                         reason="no float paths could be extracted for any update")

    vals = [(i, v) for i, v in enumerate(per) if v is not None]
    first_v, last_v = vals[0][1], vals[-1][1]
    if last_v < first_v - 1e-9:
        interp = (f"PCI falls {first_v:.2f} -> {last_v:.2f}: criticality is "
                  "diffusing across more near-critical paths — a path-flip / "
                  "concurrency warning ahead of TRD-02.")
    elif last_v > first_v + 1e-9:
        interp = (f"PCI rises {first_v:.2f} -> {last_v:.2f}: criticality is "
                  "consolidating onto fewer paths (cleaner attribution; check "
                  "whether logic churn engineered the consolidation).")
    else:
        interp = (f"PCI is stable near {last_v:.2f} (1.0 = single-threaded, "
                  "1/N = fully diffuse near-criticality).")
    return PciResult(labels=labels, per_update=per, interpretation=interp)


# ==========================================================================
# 3. CDI — Criticality Dwell Index  (§10.2, N12)
# ==========================================================================
def _cdi(sa, kernels: dict[int, _Kernel], lam: float,
         band_days: float) -> CdiResult:
    scheds = getattr(sa, "schedules", [])
    if not scheds:
        return CdiResult(reason="no schedules")
    dwell: dict[str, float] = {}
    windows_present: dict[str, int] = {}
    names: dict[str, str] = {}
    allocated = 0
    for s in scheds:
        k = kernels[id(s)]
        # LOE/summary activities were already excluded from the kernel RF map
        # (rule C1), so ``k.rf`` contains only discrete work; the band selection
        # below therefore never allocates dwell to a summary activity.
        near = {code: k.weight[code] for code, rf in k.rf.items()
                if rf <= band_days and code in k.weight}
        wsum = sum(near.values())
        if wsum <= 0:
            continue
        allocated += 1                            # one unit of criticality this update
        for code, w in near.items():
            dwell[code] = dwell.get(code, 0.0) + w / wsum
            windows_present[code] = windows_present.get(code, 0) + 1
            if code not in names:
                a = _find_by_code(s, code)
                if a is not None:
                    names[code] = a.name
    if allocated == 0:
        return CdiResult(reason="no update had activities inside the near-critical "
                                f"band (RF <= {band_days:g}d)",
                         disclosures=_cdi_disclosures())

    board = [CdiEntry(code=c, name=names.get(c, ""),
                      dwell_share=v / allocated,
                      windows_present=windows_present.get(c, 0))
             for c, v in dwell.items()]
    board.sort(key=lambda e: e.dwell_share, reverse=True)
    n = len(board)
    k_top = max(1, math.ceil(n * 0.10))
    top_decile = sum(e.dwell_share for e in board[:k_top])
    lead = board[0]
    interp = (f"{lead.code} carried the most criticality-time "
              f"({lead.dwell_share:.0%} of the Project's dwell); the top decile "
              f"({k_top} of {n} activities) holds {top_decile:.0%}.")
    return CdiResult(leaderboard=board, top_decile_share=top_decile,
                     allocations=allocated, interpretation=interp,
                     disclosures=_cdi_disclosures())


# ==========================================================================
# demonstrated-pace series (shared by RDI and BWI's projected break)
# ==========================================================================
def _demonstrated_series(sa, kernels: dict[int, _Kernel],
                         band_days: float) -> list[Optional[float]]:
    """Per window (n-1), the pace actually demonstrated: total duration (days,
    own calendar) of near-critical activities *completed within the window*
    divided by the window's standard working days.  ``None`` when the window
    length is non-positive."""
    scheds = getattr(sa, "schedules", [])
    out: list[Optional[float]] = []
    for i in range(len(scheds) - 1):
        e, l = scheds[i], scheds[i + 1]
        wd = _working_days_5d(e.data_date, l.data_date)
        if wd <= 0:
            out.append(None)
            continue
        lk = kernels[id(l)]
        done = 0.0
        for a in l.activities.values():
            if a.is_loe_or_summary or not a.completed:
                continue
            rf = lk.rf.get(a.code)
            if rf is None or rf > band_days:
                continue
            af = a.actual_finish
            if af is None:
                continue
            if e.data_date is not None and l.data_date is not None \
                    and e.data_date < af <= l.data_date:
                done += a.duration_days(l.cal_for(a))
        out.append(done / wd)
    return out


# ==========================================================================
# 4. RDI — Recovery Debt Index  (§9.5, N10)
# ==========================================================================
def _rdi(sa, kernels: dict[int, _Kernel], band_days: float) -> RdiResult:
    scheds = getattr(sa, "schedules", [])
    if len(scheds) < 2:
        return RdiResult(reason="series has fewer than two updates")

    # required pace R_u per update
    required: list[Optional[float]] = []
    for s in scheds:
        k = kernels[id(s)]
        wd = _working_days_5d(s.data_date, s.finish_date)
        if wd <= 0:
            required.append(None)
            continue
        rem = 0.0
        for a in s.activities.values():
            if a.is_loe_or_summary or a.completed:
                continue
            rf = k.rf.get(a.code)
            if rf is None or rf > band_days:
                continue
            rem += a.remaining_days(s.cal_for(a))
        required.append(rem / wd)

    demonstrated = _demonstrated_series(sa, kernels, band_days)

    rows: list[RdiRow] = []
    cumulative = 0.0
    max_demo = 0.0
    rows.append(RdiRow(label=scheds[0].label(), required_pace=required[0],
                       demonstrated_pace=None, accrual_days=0.0,
                       cumulative_days=0.0))
    for i in range(len(scheds) - 1):
        d = demonstrated[i]
        if d is not None:
            max_demo = max(max_demo, d)
        r_prev = required[i]
        win_wd = _working_days_5d(scheds[i].data_date, scheds[i + 1].data_date)
        accrual = 0.0
        if r_prev is not None and win_wd > 0:
            accrual = max(0.0, r_prev - max_demo) * win_wd
        cumulative += accrual
        rows.append(RdiRow(label=scheds[i + 1].label(),
                           required_pace=required[i + 1],
                           demonstrated_pace=d, accrual_days=accrual,
                           cumulative_days=cumulative))

    if all(r is None for r in required):
        return RdiResult(rows=rows, rdi_days=0.0,
                         reason="no update had a usable data date -> forecast "
                                "finish span to compute a required pace",
                         disclosures=_rdi_disclosures(scheds))
    interp = (f"Recovery debt stands at {cumulative:.1f} working days — the "
              "portion of the current completion forecast resting on a pace the "
              "Project has not demonstrated"
              + (" (debt has accrued: the forecast requires acceleration beyond "
                 "the best window achieved)." if cumulative > 0
                 else "; no window required more than the best pace demonstrated."))
    return RdiResult(rows=rows, rdi_days=cumulative, interpretation=interp,
                     disclosures=_rdi_disclosures(scheds))


# ==========================================================================
# 5. BWI — Bow-Wave Index  (§10.4, N14)
# ==========================================================================
def _resolve_bwi_target(scheds: list[Schedule],
                        bwi_target: Optional[str]) -> Optional[str]:
    if bwi_target is not None:
        return bwi_target
    ref = scheds[0]
    fmiles = [a for a in ref.activities.values()
              if a.atype == ActivityType.FINISH_MILESTONE]
    if not fmiles:
        # no finish milestone anywhere: fall back to the latest-finishing activity
        cands = [a for a in ref.real_activities if a.finish is not None]
        if not cands:
            return None
        return max(cands, key=lambda a: a.finish).code
    late = [a for a in fmiles if _late_type(a)]
    pool = late if late else fmiles
    return max(pool, key=lambda a: a.finish or datetime.min).code


def _find_by_code(s: Schedule, code: str):
    for a in s.activities.values():
        if a.code == code:
            return a
    return None


def _bwi(sa, kernels: dict[int, _Kernel], band_days: float,
         bwi_target: Optional[str]) -> BwiResult:
    scheds = getattr(sa, "schedules", [])
    if not scheds:
        return BwiResult(reason="no schedules")
    target = _resolve_bwi_target(scheds, bwi_target)
    if target is None:
        return BwiResult(reason="no target milestone could be resolved")

    # B2 target-resolution robustness (audit ruling): pin the target's PERSISTENT
    # UID from the first update (matching by code, then by uid if the caller
    # passed a uid), then locate it in each later update by UID first and fall
    # back to code.  This survives an activity being re-coded/renamed between
    # updates.  BWI mathematics are unchanged.
    anchor = _find_by_code(scheds[0], target) or scheds[0].activities.get(target)
    anchor_uid = anchor.uid if anchor is not None else None
    target_code = anchor.code if anchor is not None else target

    densities: list[Optional[float]] = []
    for s in scheds:
        tgt = (s.activities.get(anchor_uid) if anchor_uid else None) \
            or _find_by_code(s, target_code)
        if tgt is None or tgt.finish is None:
            densities.append(None)
            continue
        wd = _working_days_5d(s.data_date, tgt.finish)
        if wd <= 0:
            densities.append(None)
            continue
        k = kernels[id(s)]
        vol = 0.0
        for a in s.activities.values():
            if a.is_loe_or_summary or a.completed:
                continue
            rf = k.rf.get(a.code)
            if rf is None or rf > band_days:
                continue
            fin = a.finish
            if fin is None or fin > tgt.finish:
                continue
            vol += a.remaining_days(s.cal_for(a))
        densities.append(vol / wd)

    labels = [s.label() for s in scheds]
    base = densities[0]
    if base is None:
        return BwiResult(target_code=target_code,
                         rows=[BwiRow(labels[i], densities[i], None)
                               for i in range(len(scheds))],
                         reason=f"target {target_code} has no usable forecast finish "
                                "/ near-critical work at the first update",
                         disclosures=_bwi_disclosures(target_code, densities, labels))
    if base == 0:
        return BwiResult(target_code=target_code,
                         rows=[BwiRow(labels[i], densities[i], None)
                               for i in range(len(scheds))],
                         reason=f"baseline near-critical density ahead of "
                                f"{target_code} is zero — BWI is undefined "
                                "(nothing to normalize)",
                         disclosures=_bwi_disclosures(target_code, densities, labels))

    rows = [BwiRow(label=scheds[i].label(), density=densities[i],
                   bwi=(densities[i] / base if densities[i] is not None else None))
            for i in range(len(scheds))]

    # projected break: first update whose required density exceeds the best
    # pace ever demonstrated up to that point (RDI's demonstrated D series).
    demo = _demonstrated_series(sa, kernels, band_days)
    break_label: Optional[str] = None
    max_demo = 0.0
    for i in range(1, len(scheds)):
        d = demo[i - 1]
        if d is not None:
            max_demo = max(max_demo, d)
        di = densities[i]
        if di is not None and di > max_demo:
            break_label = scheds[i].label()
            break

    last_bwi = next((r.bwi for r in reversed(rows) if r.bwi is not None), None)
    interp = (f"Work packed ahead of {target_code} is "
              f"{last_bwi:.2f}x the baseline density"
              if last_bwi is not None else
              f"Bow-wave density ahead of {target_code} could not be tracked")
    if break_label:
        interp += (f"; required density first outruns the demonstrated pace at "
                   f"{break_label} (projected break).")
    else:
        interp += "; required density stays within the demonstrated pace."
    return BwiResult(target_code=target_code, rows=rows,
                     projected_break_label=break_label, interpretation=interp,
                     disclosures=_bwi_disclosures(target_code, densities, labels))


# ==========================================================================
# public entry point
# ==========================================================================
def run_li_indices(sa, lam: float = DEFAULT_LAMBDA,
                   band_days: float = DEFAULT_BAND_DAYS,
                   bwi_target: Optional[str] = None) -> LiIndicesResult:
    """Compute all five LI indices over the ordered series ``sa``.

    Float paths (the expensive step) are extracted once per schedule and shared
    across FCBI/PCI/CDI.  Every sub-result carries a ``reason`` when it could not
    be computed; this function never raises.

    Parameters
    ----------
    sa : SeriesAnalysis
        Ordered schedules with change-register changesets (``sa.schedules`` and
        ``sa.changesets``).
    lam : float
        Half-weight constant λ for the criticality kernel (default 5 working
        days).
    band_days : float
        Near-critical band (RF <= band_days) for CDI/RDI/BWI (default 10 wd).
    bwi_target : str | None
        Activity code for the Bow-Wave milestone; default resolves to the latest
        late-type-constrained finish milestone, else the last finish milestone.
    """
    scheds = getattr(sa, "schedules", [])
    kernels = {id(s): _build_kernel(s, lam) for s in scheds}
    return LiIndicesResult(
        fcbi=_fcbi(sa, kernels, lam),
        pci=_pci(sa, kernels, lam),
        cdi=_cdi(sa, kernels, lam, band_days),
        rdi=_rdi(sa, kernels, band_days),
        bwi=_bwi(sa, kernels, band_days, bwi_target),
    )
