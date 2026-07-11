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

# -- FCBI v0.5 (LI-01 governed revision) constants --------------------------
FCBI_PATHS_N0 = 25            # initial enumeration depth for the adaptive
                              # convergence rule (ruling O7.3): enumerate deeper
                              # until the MAX POSSIBLE OMITTED WEIGHT < tolerance,
                              # doubling each round.  Activities on no enumerated
                              # path are DISTANCE UNRESOLVED -> quarantine (O6),
                              # never assigned their own total float (O1).
FCBI_CONV_TOL = 0.01         # convergence tolerance on the omitted weight: once
                              # the next (unenumerated) path could contribute at
                              # most this weight, deeper paths are immaterial.
FCBI_PATHS_MAX = 512         # hard safety ceiling; reaching it WITHOUT meeting the
                              # tolerance sets depth_capped (window is provisional).
REFERENCE_HPD = 8.0           # fixed reference hours/day for the calendar-neutral
                              # hour->day conversion (ruling O7.7); supersedes any
                              # per-activity or "dominant calendar" basis for FCBI.
TIER1_TOL_HOURS = 0.5         # Tier-1 numerical tolerance in HOURS, applied before
                              # the hour->day conversion (ruling O4). Absorbs storage
                              # precision / exporter rounding / repeated conversions
                              # only; it is NOT an empirical noise filter and NOT a
                              # per-activity epsilon deadband (Tier 2, not implemented).


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


def relative_float_map(schedule: Schedule,
                       paths: list[FloatPath]) -> dict[str, float]:
    """Per-activity relative float RF, keyed by activity code.

    Formula
    -------
        RF(a) = min over the top-N float paths containing ``a`` of that path's
                relative float (``FloatPath.rel_float_days``);
        activities on no extracted path fall back to their own total float in
        working days on their own calendar.

    Activities with neither a path membership nor a stored total float are
    omitted (their weight is undefined).
    """
    rf: dict[str, float] = {}
    for p in paths:
        for a in p.activities:
            cur = rf.get(a.code)
            if cur is None or p.rel_float_days < cur:
                rf[a.code] = p.rel_float_days
    for a in schedule.activities.values():
        if a.code in rf:
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
    paths = float_paths(schedule, n=KERNEL_PATHS_N, band_days=None)
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
# -- FCBI v0.5 result model (LI-01 governed revision, rulings O1-O7) ---------
@dataclass
class Burner:
    """One activity's target-specific float movement in a window.

    ``distance_days`` is the v0.5 nonnegative target-specific distance d_i
    (ruling O1) — 0 on the driving path, never negative; ``weight`` is
    w = 2^(-d/lambda) in (0, 1].  ``contribution`` = consumption_days * weight
    feeds the derived diagnostic W and the burn-weighted mean proximity C; it
    is NOT the primary output (that is the unweighted gross B, ruling O2)."""
    code: str
    name: str
    consumption_days: float          # c_i, unweighted working-day float movement
    distance_days: float             # d_i >= 0 (target-specific distance, O1)
    weight: float                    # w_i = 2^(-d_i/lambda) in (0, 1]
    contribution: float              # c_i * w_i (weighted; feeds W and C only)


@dataclass
class QuarantineEntry:
    """A contribution EXCLUDED from the primary target-specific result and
    reported in the quarantine subtotal (ruling O6), never merely flagged."""
    code: str
    name: str
    consumption_days: float
    reason: str


@dataclass
class CompletionOmission:
    """An activity completed within the window (ruling O5 diagnostic): it
    leaves the remaining-work population, so its float movement does not enter
    B — disclosed here so a heavy-completion month is never silently benign."""
    code: str
    name: str
    prior_pos_float_days: Optional[float]   # prior TF if >= 0
    prior_neg_float_days: Optional[float]   # depth of prior negative float (>= 0)
    prior_weight: Optional[float]           # w(d) at the prior update, if resolvable
    consumption_days: float                 # float it moved before completing


@dataclass
class TimingSet:
    """Endpoint-timing sensitivity set (ruling O3) for the weighted burn W.
    NOT a band and NOT bounds: the true within-window value is not bracketed
    by these (distance can dip below both endpoints mid-window)."""
    start: Optional[float]           # PRIMARY: w evaluated at start-of-window d
    end: Optional[float]             # w at end-of-window d
    min_endpoint: Optional[float]    # w at min(d_start, d_end) (superseded min-RF)


@dataclass
class FcbiWindow:
    earlier_label: str
    later_label: str
    working_days: Optional[float]           # window length (O7.10)

    # -- primary outputs, burn side (ruling O2, activity basis) --------------
    burn_gross: float                       # B_u = sum c_i (gross activity-day burn)
    burn_proximity: Optional[float]         # C_u = sum(c*w)/sum(c); None => N/A
    burn_proximity_reason: str              # labelled reason when C_u is N/A
    burn_weighted: float                    # W_u = B_u * C_u (derived diagnostic)
    burn_rate: Optional[float]              # B_u / working days in window (O7.10)

    # -- recovery side mirror (tracked separately, never netted) -------------
    recov_gross: float                      # B-_u
    recov_proximity: Optional[float]        # C-_u
    recov_proximity_reason: str
    recov_weighted: float                   # W-_u

    # -- endpoint-timing sensitivity set on the weighted burn (O3) -----------
    timing: TimingSet

    # -- negative-float severity, beside B and C, never in the kernel --------
    n_severity: Optional[float]             # N_u = max(0, -F_target)
    n_deepening: Optional[float]            # dN+ = max(0, N_u - N_{u-1})

    # -- target governance and coverage (ruling O6) --------------------------
    target_code: Optional[str]
    coverage: Optional[float]               # ELIGIBLE-BURN coverage: eligible c /
                                            # (eligible c + quarantined c) — a burn
                                            # measure, NOT data completeness
    coverage_reason: str                    # labelled reason when coverage is N/A
    quarantine_burn: float                  # sum of quarantined c
    quarantine: list[QuarantineEntry] = field(default_factory=list)
    recov_quarantine: float = 0.0           # quarantined recovery (mirror, REV-15)

    # -- population coverage (Q6 settled by principal): over the whole burn-
    # candidate population (incomplete, non-LOE, non-target, discrete TASK
    # activities present at both endpoints), NOT just movers — so eligible-burn
    # coverage is never mistaken for data completeness or population eligibility
    candidate_pop: int = 0
    pop_tf_evaluable: int = 0               # candidates with float at both endpoints
    pop_eligible: int = 0                   # candidates eligible (resolved, ungoverned)
    pop_exclusions: dict = field(default_factory=dict)   # reason -> count

    # -- completion-omission diagnostic (ruling O5) --------------------------
    completed_in_window: int = 0
    completed_prior_pos: float = 0.0        # sum prior positive float of completers
    completed_prior_neg: float = 0.0        # sum prior negative-float depth
    completed_prior_share: Optional[float] = None   # share of prior live-work pop
    completion_omission: list[CompletionOmission] = field(default_factory=list)

    # -- population evaluability (REV-11): incomplete population members whose
    # float could not be measured at both endpoints — coverage above is
    # eligible-BURN coverage, NOT data completeness, so this is disclosed beside it
    unmeasurable_count: int = 0

    # -- non-target milestone margin movement, disclosed separately (REV-17):
    # zero-duration milestones are schedule markers, not remaining WORK, so their
    # float movement is NOT in B/C; it is reported here as milestone-margin change
    milestone_margin_changes: list = field(default_factory=list)

    # -- basis-change segmentation (ruling O7.9) -----------------------------
    basis_change: bool = False
    basis_change_reasons: list[str] = field(default_factory=list)
    requirement_margin_change: Optional[float] = None   # observed target-margin change

    # enumeration hit the path cap with burn still unresolved (ruling O7.3; REV-08)
    depth_capped: bool = False
    top_burners: list[Burner] = field(default_factory=list)

    @property
    def tf_evaluability(self) -> Optional[float]:
        """Share of the candidate population whose float is measurable at both
        endpoints — a data-completeness diagnostic, distinct from burn coverage."""
        return (self.pop_tf_evaluable / self.candidate_pop
                if self.candidate_pop else None)

    @property
    def population_eligibility(self) -> Optional[float]:
        """Share of the candidate population eligible for the target basis
        (resolved distance, ungoverned) — distinct from eligible-BURN coverage."""
        return (self.pop_eligible / self.candidate_pop
                if self.candidate_pop else None)


@dataclass
class FcbiResult:
    windows: list[FcbiWindow] = field(default_factory=list)
    # cumulative GROSS burn B over OPERATIONAL windows only (basis-change
    # windows excluded and the series restarted after them, ruling O7.9)
    cumulative_burn: list[Optional[float]] = field(default_factory=list)
    cumulative_weighted: list[Optional[float]] = field(default_factory=list)
    top_burners: list[Burner] = field(default_factory=list)   # aggregated, operational
    lam: float = DEFAULT_LAMBDA
    target_code: Optional[str] = None
    target_auto_resolved: bool = False       # True => analyst did not select m (O7.1)
    depth_capped: bool = False               # any window hit the path cap (REV-08)
    interpretation: str = ""
    reason: str = ""
    scope_note: str = (
        "Within-network trend instrument on a continuously maintained schedule. "
        "B is a gross activity-day aggregate containing replicated path float — "
        "NOT project float consumed or a stock; the (B, C) pair is an interpretive "
        "decomposition that makes network-size dominance visible but does NOT cure "
        "granularity or network-size dependence. No cross-project or "
        "cross-granularity comparison. Structural churn is disclosed alongside.")


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


@dataclass
class LiIndicesResult:
    fcbi: FcbiResult
    pci: PciResult
    cdi: CdiResult
    rdi: RdiResult
    bwi: BwiResult


# ==========================================================================
# 1. FCBI — Float Criticality Burn Index  (§9.1, N6; LI-01 v0.5 governed)
#
# v0.5 governed revision (rulings O1-O7).  Self-contained: it does NOT use the
# shared RF/weight kernel (which retains the v0.4 basis for PCI/CDI/RDI/BWI).
# The FCBI distance is target-specific and nonnegative (O1); the own-total-float
# fallback and the w>1 over-critical premium are abolished; FCBI% is retired.
# ==========================================================================
def _dstr(x: Optional[datetime]) -> str:
    return x.strftime("%Y-%m-%d") if x else "—"


def _target_distance(schedule: Schedule, target_code: Optional[str],
                     lam: float = DEFAULT_LAMBDA
                     ) -> tuple[dict[str, float], Optional[float], Optional[float], bool]:
    """Per-activity nonnegative target-specific distance d_i (ruling O1):

        d_i = min over enumerated float paths containing i of
              (that path's margin to m  -  the driving path's margin to m)

    The reference is the DRIVING path's margin (``paths[0]``, the tool-of-record
    rank-1 float walk — ruling O1 "the driving path's margin," a fixed reference,
    not the global minimum; the ``max(0.0, ...)`` clamp keeps d >= 0 for an
    off-path feeder more negative than the spine, so both mandatory O1
    consequences hold: driving-path d = 0 AND d >= 0 always).  Margins are taken
    on a **fixed reference hours/day basis** over **discrete members only**
    (``FloatPath.rel_float_hours``): a calendar-neutral distance that is not
    repriced by native calendar length (ruling O7.7; REV-02) and cannot be set
    by a level-of-effort node (ruling O7.3; REV-07).

    **Adaptive convergence (ruling O7.3; REV-08).**  Enumeration depth starts at
    ``FCBI_PATHS_N0`` and DOUBLES until the *max possible omitted weight* — the
    weight the next, unenumerated path could carry (paths come out least-float
    first, so the next margin is at least the current maximum) — falls below
    ``FCBI_CONV_TOL``, or the network is exhausted.  Reaching ``FCBI_PATHS_MAX``
    without meeting the tolerance sets ``depth_capped`` (the window is
    provisional, not implied converged).  Returns
    ``(dist_by_code, driving_margin_ref_days, target_margin_ref_days, depth_capped)``.
    NOTE (disclosed limitation): the driving-path *identity* still follows the
    tool-of-record native-calendar float walk (ADR-0004); on a mixed-calendar
    merge the reference-basis rank-2 path could be marginally more critical, in
    which case the clamp treats it as co-critical (d = 0)."""
    if target_code is None:
        return {}, None, None, False
    n = FCBI_PATHS_N0
    paths: list = []
    converged = False
    while True:
        paths = float_paths(schedule, target_uid=target_code, n=n, band_days=None)
        if not paths:
            return {}, None, None, False
        driving_h0 = paths[0].rel_float_hours
        margins = [p.rel_float_hours for p in paths if p.rel_float_hours is not None]
        if len(paths) < n or driving_h0 is None or not margins:
            converged = True                      # network exhausted / nothing to refine
            break
        d_next = max(0.0, (max(margins) - driving_h0) / REFERENCE_HPD)
        if kernel_weight(d_next, lam) < FCBI_CONV_TOL:
            converged = True                      # omitted weight immaterial (O7.3)
            break
        if n >= FCBI_PATHS_MAX:
            break                                 # ceiling hit WITHOUT converging
        n = min(n * 2, FCBI_PATHS_MAX)
    depth_capped = not converged
    driving_h = paths[0].rel_float_hours
    if driving_h is None:                          # no discrete member on the spine
        return {}, None, None, depth_capped
    driving_margin = driving_h / REFERENCE_HPD
    dist: dict[str, float] = {}
    for p in paths:
        if p.rel_float_hours is None:              # branch has no discrete float
            continue
        d = max(0.0, p.rel_float_hours / REFERENCE_HPD - driving_margin)
        for a in p.activities:
            if a.is_loe_or_summary:
                continue
            cur = dist.get(a.code)
            if cur is None or d < cur:
                dist[a.code] = d
    tgt = _find_by_code(schedule, target_code)
    tmargin = (tgt.total_float_hours / REFERENCE_HPD
               if tgt is not None and tgt.total_float_hours is not None else None)
    return dist, driving_margin, tmargin, depth_capped


def _governed_codes(schedule: Schedule, target_code: Optional[str]) -> dict[str, str]:
    """Codes whose LATE dates are governed by a NON-target basis, traced THROUGH
    the network (ruling O6 predicates 3 and 5 — propagated governance).  Returns
    ``{code: reason}``.

    A late-type constraint OR an expected finish on node K caps K's late finish
    and therefore the late dates of every activity that must precede K.  So K and
    all of K's ancestors are governed.  A field-level check on the activity alone
    is insufficient (the A->M->completion case, probe P7).  Both the primary and
    secondary constraint are considered (via ``_late_type``); expected-finish
    governance is propagated the same way (REV-04), not only checked on the
    activity itself."""
    tgt_uid = None
    for a in schedule.activities.values():
        if a.code == target_code:
            tgt_uid = a.uid
            break
    sources: list[tuple[str, str]] = []           # (uid, reason)
    for a in schedule.activities.values():
        if a.uid == tgt_uid or a.is_loe_or_summary:
            continue
        if _late_type(a):
            sources.append((a.uid, "late dates governed by a non-target constraint, "
                                   "propagated through the network"))
        elif a.expected_finish is not None:
            sources.append((a.uid, "late dates governed by a non-target expected "
                                   "finish, propagated through the network"))
    governed: dict[str, str] = {}
    for k, reason in sources:
        seen, stack = {k}, [k]
        while stack:                              # reverse BFS over predecessors
            cur = stack.pop()
            for r in schedule.predecessors_of(cur):
                if r.pred_uid not in seen:
                    seen.add(r.pred_uid)
                    stack.append(r.pred_uid)
        for uid in seen:
            a = schedule.activities.get(uid)
            if a is not None and a.code not in governed:
                governed[a.code] = reason
    return governed


def _resolve_fcbi_target(scheds: list[Schedule],
                         explicit: Optional[str]) -> tuple[Optional[str], bool]:
    """Resolve the single terminal completion milestone m (ruling O6 v1 scope).

    An explicit analyst-selected code always wins (returns auto_resolved=False).
    Otherwise resolve a **terminal FINISH MILESTONE** — one with no directed path
    to any *other* finish milestone (i.e. genuinely at the end of the network) —
    preferring the latest-finishing such milestone, from the latest schedule that
    has one.  Unlike the BWI heuristic this NEVER selects a constrained
    intermediate milestone or a task (REV-01).  Returns
    ``(code, auto_resolved)``; ``auto_resolved=True`` is a signal that the run
    should carry a provenance note and the analyst should confirm m (ruling
    O7.1)."""
    if explicit is not None:
        return explicit, False
    for s in reversed(scheds):
        fmiles = [a for a in s.activities.values()
                  if a.atype == ActivityType.FINISH_MILESTONE]
        if not fmiles:
            continue
        fmile_uids = {a.uid for a in fmiles}

        def reaches_other_finish(a) -> bool:
            seen, stack = {a.uid}, [a.uid]
            while stack:
                cur = stack.pop()
                for r in s.successors_of(cur):
                    if r.succ_uid in seen:
                        continue
                    if r.succ_uid in fmile_uids and r.succ_uid != a.uid:
                        return True
                    seen.add(r.succ_uid)
                    stack.append(r.succ_uid)
            return False

        terminal = [a for a in fmiles if not reaches_other_finish(a)]
        pool = terminal or fmiles
        chosen = max(pool, key=lambda a: (a.finish or datetime.min, a.code))
        return chosen.code, True
    return None, True


def _eligibility(code: str, ea, d_start: Optional[float],
                 governed: dict[str, str]) -> tuple[bool, str]:
    """Ruling O6 eligibility predicate.  Ineligible contributions are EXCLUDED
    from the primary result and reported in the quarantine subtotal.  ``governed``
    is the UNION of the propagated-governance maps at both window endpoints
    (REV-04), so a constraint or expected finish ADDED mid-window still
    quarantines the activities it governs."""
    if d_start is None:
        return False, ("distance unresolved — activity is on no enumerated float "
                       "path to the target (never assigned its own total float)")
    if code in governed:
        return False, governed[code] + " (ADR-0004: unresolved -> quarantine)"
    return True, ""


def _basis_change_reasons(cs, target_code: Optional[str]) -> list[str]:
    """A window is a BASIS-CHANGE WINDOW (ruling O7.9) when the target date, a
    scheduling option, or a calendar definition changed — requirement-induced
    margin change, not execution erosion.  Such windows are excluded from the
    continuous operational-burn trend and the cumulative series restarts."""
    reasons: list[str] = []
    e_by = {a.code: a for a in cs.earlier.activities.values()}
    l_by = {a.code: a for a in cs.later.activities.values()}
    te, tl = e_by.get(target_code), l_by.get(target_code)
    if te is not None and tl is not None:
        # REQUIREMENT basis only — NEVER the forecast early_finish/finish (a moving
        # forecast on an unconstrained target is execution erosion, ruling O7.9).
        # A stale constraint_date is ignored when the constraint type is NONE
        # (REV-06 false positive); a change of constraint TYPE (added/removed/
        # retyped, primary or secondary) is itself a requirement-basis change even
        # at an unchanged nominal date.
        def _req(a):
            cd = a.constraint_date if a.constraint != ConstraintType.NONE else None
            cd2 = a.constraint2_date if a.constraint2 != ConstraintType.NONE else None
            return (a.constraint.value, cd, a.constraint2.value, cd2, a.baseline_finish)
        if _req(te) != _req(tl):
            reasons.append(f"target requirement basis changed "
                           f"({te.constraint.value}/{_dstr(te.constraint_date)} -> "
                           f"{tl.constraint.value}/{_dstr(tl.constraint_date)})")
    elif (te is None) != (tl is None):
        reasons.append("target milestone present in only one update of the pair")
    # project-level requirement dates (REV-06)
    if cs.earlier.must_finish_by != cs.later.must_finish_by:
        reasons.append(f"project must-finish-by moved {_dstr(cs.earlier.must_finish_by)} "
                       f"-> {_dstr(cs.later.must_finish_by)}")
    if cs.earlier.baseline_finish != cs.later.baseline_finish:
        reasons.append("project baseline completion changed (rebaseline)")
    es, ls = cs.earlier.settings, cs.later.settings
    for fld in ("retained_logic", "progress_override", "make_open_ends_critical",
                "use_expected_finish", "critical_float_threshold_hours",
                "relationship_lag_calendar", "critical_definition", "actual_dates"):
        if getattr(es, fld, None) != getattr(ls, fld, None):
            reasons.append(f"scheduling-option change: {fld}")
    ncal = len(getattr(cs, "calendar_def_changes", []) or [])
    if ncal:
        reasons.append(f"{ncal} calendar-definition change(s)")
    return reasons


def _fcbi(sa, lam: float = DEFAULT_LAMBDA, target: Optional[str] = None,
          tier1_tol_hours: float = TIER1_TOL_HOURS) -> FcbiResult:
    scheds = getattr(sa, "schedules", [])
    changesets = getattr(sa, "changesets", [])
    if not changesets:
        return FcbiResult(reason="series has fewer than two updates", lam=lam)
    if not (math.isfinite(lam) and lam > 0):          # ruling never-raises (REV-12)
        return FcbiResult(lam=lam, reason=f"invalid lambda {lam!r}: the half-weight "
                          "constant must be a finite positive number of working days")

    target_code, auto_resolved = _resolve_fcbi_target(scheds, target)
    if target_code is None:
        return FcbiResult(lam=lam, reason="no terminal completion finish milestone "
                          "could be resolved as the FCBI target (ruling O6 v1 scope "
                          "requires one selected completion milestone m — select it "
                          "explicitly, ruling O7.1)")

    dist_cache = {id(s): _target_distance(s, target_code, lam) for s in scheds}
    gov_cache = {id(s): _governed_codes(s, target_code) for s in scheds}

    windows: list[FcbiWindow] = []
    cumulative_burn: list[Optional[float]] = []
    cumulative_weighted: list[Optional[float]] = []
    running_b = running_w = 0.0
    agg: dict[str, dict] = {}                          # code -> summed burn record
    basis_resolved = False        # target/path basis resolved for >=1 activity
    any_depth_capped = False

    for cs in changesets:
        earlier, later = cs.earlier, cs.later
        e_by_code = {a.code: a for a in earlier.activities.values()}
        l_by_code = {a.code: a for a in later.activities.values()}
        # defensive .get: endpoints absent from sa.schedules recompute, not raise
        dist_e, _dmarg_e, tmarg_e, cap_e = dist_cache.get(id(earlier)) or \
            _target_distance(earlier, target_code, lam)
        dist_l, _dmarg_l, tmarg_l, _cap_l = dist_cache.get(id(later)) or \
            _target_distance(later, target_code, lam)
        # UNION governance over BOTH endpoints so a constraint/expected-finish
        # ADDED mid-window still quarantines what it governs (ruling O6; REV-04)
        gov_e = gov_cache.get(id(earlier))
        if gov_e is None:
            gov_e = _governed_codes(earlier, target_code)
        gov_l = gov_cache.get(id(later))
        if gov_l is None:
            gov_l = _governed_codes(later, target_code)
        governed = {**gov_e, **gov_l}
        if dist_e or dist_l:
            basis_resolved = True
        if cap_e:
            any_depth_capped = True
        bc_reasons = _basis_change_reasons(cs, target_code)
        basis_change = bool(bc_reasons)

        burners: list[Burner] = []
        quarantine: list[QuarantineEntry] = []
        completion: list[CompletionOmission] = []
        milestone_changes: list = []
        b_gross = r_gross = 0.0
        sum_cw = sum_cw_end = sum_cw_min = 0.0
        r_cw = q_burn = rq_burn = 0.0
        comp_pos = comp_neg = 0.0
        comp_n = unmeasurable = 0
        candidate_pop = pop_tf_evaluable = pop_eligible = 0
        pop_exclusions: dict = {}

        for code, ea in e_by_code.items():
            la = l_by_code.get(code)
            if ea.is_loe_or_summary or code == target_code or la is None:
                continue
            # completion-omission diagnostic (ruling O5): ALWAYS record a completer
            if la.completed and not ea.completed:
                pos = neg = w_prior = None
                moved = 0.0
                if ea.total_float_hours is not None:
                    d_prior = dist_e.get(code)
                    w_prior = kernel_weight(d_prior, lam) if d_prior is not None else None
                    tf_prior = ea.total_float_hours / REFERENCE_HPD
                    pos = tf_prior if tf_prior >= 0 else None
                    neg = -tf_prior if tf_prior < 0 else None
                    if la.total_float_hours is not None:
                        dh = la.total_float_hours - ea.total_float_hours
                        if abs(dh) <= tier1_tol_hours:
                            dh = 0.0
                        moved = max(0.0, -dh / REFERENCE_HPD)
                completion.append(CompletionOmission(code, ea.name, pos, neg, w_prior, moved))
                comp_n += 1
                comp_pos += pos or 0.0
                comp_neg += neg or 0.0
                continue
            if la.completed:                          # complete at both -> out of pop
                continue

            # non-target zero-duration milestones are markers, not remaining WORK
            # (REV-17): excluded from B/C AND from the candidate population;
            # their margin movement is disclosed separately
            if ea.is_milestone:
                if (ea.total_float_hours is not None
                        and la.total_float_hours is not None):
                    dh = la.total_float_hours - ea.total_float_hours
                    if abs(dh) <= tier1_tol_hours:
                        dh = 0.0
                    mv = dh / REFERENCE_HPD
                    if mv != 0.0:
                        milestone_changes.append(QuarantineEntry(
                            code, ea.name, abs(mv),
                            "milestone margin change (excluded from B — not remaining work)"))
                continue

            # ---- burn-candidate task: population coverage (Q6, settled) -------
            candidate_pop += 1
            d_start = dist_e.get(code)
            both_floats = (ea.total_float_hours is not None
                           and la.total_float_hours is not None)
            if not both_floats:                       # not weight-resolvable (REV-11)
                unmeasurable += 1
                pop_exclusions["float unmeasurable at an endpoint"] = \
                    pop_exclusions.get("float unmeasurable at an endpoint", 0) + 1
                continue
            pop_tf_evaluable += 1
            if d_start is None:
                pop_exclusions["distance unresolved"] = \
                    pop_exclusions.get("distance unresolved", 0) + 1
            elif code in governed:
                pop_exclusions["governed (non-target basis)"] = \
                    pop_exclusions.get("governed (non-target basis)", 0) + 1
            else:
                pop_eligible += 1

            # Tier-1 tolerance applied in HOURS before the hour->day conversion (O4)
            delta_h = la.total_float_hours - ea.total_float_hours
            if abs(delta_h) <= tier1_tol_hours:
                delta_h = 0.0
            delta_days = delta_h / REFERENCE_HPD
            c = -delta_days if delta_days < 0 else 0.0
            rec = delta_days if delta_days > 0 else 0.0
            if c <= 0 and rec <= 0:
                continue

            eligible, reason = _eligibility(code, ea, d_start, governed)
            if not eligible:
                if c > 0:
                    q_burn += c
                    quarantine.append(QuarantineEntry(code, ea.name, c, reason))
                elif rec > 0:                          # mirror: quarantined recovery
                    rq_burn += rec
                continue

            d_end = dist_l.get(code)                   # None => unresolved at end
            w_start = kernel_weight(d_start, lam)
            if d_end is None:                          # do NOT fabricate end (REV-14)
                w_end = w_min = w_start
            else:
                w_end = kernel_weight(d_end, lam)
                w_min = kernel_weight(min(d_start, d_end), lam)
            if rec > 0:
                r_gross += rec
                r_cw += rec * w_start
            if c > 0:
                b_gross += c
                sum_cw += c * w_start
                sum_cw_end += c * w_end
                sum_cw_min += c * w_min
                burners.append(Burner(code, ea.name, c, d_start, w_start, c * w_start))
                # aggregate across OPERATIONAL windows only (REV-03), summing
                # consumption and contribution; a single distance is not
                # meaningful across windows so it is derived at the end (REV-09)
                if not basis_change:
                    a = agg.setdefault(code, {"name": ea.name, "c": 0.0, "cw": 0.0})
                    a["c"] += c
                    a["cw"] += c * w_start

        # -- primary decomposition (ruling O2) -------------------------------
        C = (sum_cw / b_gross) if b_gross > 0 else None
        C_reason = "" if b_gross > 0 else "NOT APPLICABLE — no eligible burn (B_u = 0)"
        Cr = (r_cw / r_gross) if r_gross > 0 else None
        Cr_reason = "" if r_gross > 0 else "NOT APPLICABLE — no eligible recovery (B-_u = 0)"
        cover_denom = b_gross + q_burn
        coverage = (b_gross / cover_denom) if cover_denom > 0 else None
        cover_reason = "" if cover_denom > 0 else "NOT APPLICABLE — no eligible or quarantined burn"
        wd = _working_days_5d(earlier.data_date, later.data_date)
        wd = wd if wd > 0 else None
        rate = (b_gross / wd) if wd else None

        n_e = max(0.0, -tmarg_e) if tmarg_e is not None else None
        n_l = max(0.0, -tmarg_l) if tmarg_l is not None else None
        dN = (max(0.0, n_l - n_e) if (n_l is not None and n_e is not None) else None)
        req_margin = ((tmarg_e - tmarg_l) if (basis_change and tmarg_e is not None
                                              and tmarg_l is not None) else None)

        burners.sort(key=lambda x: (-x.contribution, -x.consumption_days, x.code))
        completion.sort(key=lambda x: (-(x.prior_neg_float_days or 0.0),
                                       -x.consumption_days, x.code))
        quarantine.sort(key=lambda x: (-x.consumption_days, x.code))
        prior_pop = sum(1 for a in earlier.activities.values()
                        if not a.is_loe_or_summary and not a.completed
                        and a.code != target_code)
        comp_share = (comp_n / prior_pop) if prior_pop > 0 else None

        windows.append(FcbiWindow(
            earlier_label=earlier.label(), later_label=later.label(), working_days=wd,
            burn_gross=b_gross, burn_proximity=C, burn_proximity_reason=C_reason,
            burn_weighted=sum_cw, burn_rate=rate,
            recov_gross=r_gross, recov_proximity=Cr, recov_proximity_reason=Cr_reason,
            recov_weighted=r_cw,
            timing=TimingSet(start=(sum_cw if b_gross > 0 else None),
                             end=(sum_cw_end if b_gross > 0 else None),
                             min_endpoint=(sum_cw_min if b_gross > 0 else None)),
            n_severity=n_l, n_deepening=dN,
            target_code=target_code, coverage=coverage, coverage_reason=cover_reason,
            quarantine_burn=q_burn, quarantine=quarantine[:25],
            recov_quarantine=rq_burn,
            candidate_pop=candidate_pop, pop_tf_evaluable=pop_tf_evaluable,
            pop_eligible=pop_eligible, pop_exclusions=pop_exclusions,
            completed_in_window=comp_n, completed_prior_pos=comp_pos,
            completed_prior_neg=comp_neg, completed_prior_share=comp_share,
            completion_omission=completion,          # full list (REV-10)
            unmeasurable_count=unmeasurable,
            milestone_margin_changes=milestone_changes,
            basis_change=basis_change, basis_change_reasons=bc_reasons,
            requirement_margin_change=req_margin, depth_capped=cap_e,
            top_burners=burners[:10]))

        if basis_change:                              # segment out; restart (O7.9)
            running_b = running_w = 0.0
            cumulative_burn.append(None)
            cumulative_weighted.append(None)
        else:
            running_b += b_gross
            running_w += sum_cw
            cumulative_burn.append(running_b)
            cumulative_weighted.append(running_w)

    if not basis_resolved:
        return FcbiResult(windows=windows, cumulative_burn=cumulative_burn,
                          cumulative_weighted=cumulative_weighted, lam=lam,
                          target_code=target_code, target_auto_resolved=auto_resolved,
                          depth_capped=any_depth_capped,
                          reason=f"no target-specific distance to {target_code} could "
                                 "be resolved from enumerated float paths in any "
                                 "window (no float-path basis)")

    # aggregate burners across OPERATIONAL windows; effective weight = cw/c so the
    # printed (c, w, c*w) reconcile even across mixed-distance windows (REV-09)
    top = []
    for code, a in agg.items():
        c, cw = a["c"], a["cw"]
        w_eff = (cw / c) if c > 0 else 0.0
        d_eff = -lam * math.log2(w_eff) if 0 < w_eff <= 1 else 0.0
        top.append(Burner(code, a["name"], c, d_eff, w_eff, cw))
    top.sort(key=lambda x: (-x.contribution, -x.consumption_days, x.code))
    top = top[:15]

    # current-segment cumulative B: the last window's value (None if the latest
    # window is a basis-change restart — do NOT revive a prior segment, REV-03)
    total_b = cumulative_burn[-1] if cumulative_burn else 0.0
    total_w = cumulative_weighted[-1] if cumulative_weighted else 0.0
    last_c = next((w.burn_proximity for w in reversed(windows)
                   if not w.basis_change and w.burn_proximity is not None), None)
    n_op = sum(1 for w in windows if not w.basis_change)
    n_bc = len(windows) - n_op
    lead = top[0].code if top else "n/a"
    # headline = the (B, C) pair (Q1 settled); W is the derived diagnostic
    if total_b is not None:
        seg_txt = (f"current operational segment B = {total_b:.1f} gross activity-days"
                   + (f", latest C = {last_c:.2f} burn-weighted proximity"
                      if last_c is not None else "")
                   + (f" (W = B·C = {total_w:.1f})" if total_w else ""))
    else:
        seg_txt = ("latest window is a basis-change restart (current-segment B not "
                   "yet accumulated)")
    interp = (f"Operational float burn to {target_code}: {seg_txt} across {n_op} "
              f"operational window(s)"
              + (f" ({n_bc} basis-change window(s) segmented out)" if n_bc else "")
              + (f"; largest single burner {lead}." if top else ".")
              + (" PROVISIONAL: target auto-resolved — the analyst must confirm m "
                 "before this is expert work product (O7.1)." if auto_resolved else "")
              + (" PROVISIONAL: float-path enumeration hit the depth ceiling without "
                 "converging (O7.3)." if any_depth_capped else "")
              + " Headline is the (B, C) pair — B is a gross activity-day aggregate "
              "(not project float consumed); C carries proximity; W = B·C is the "
              "derived single-number diagnostic.")
    return FcbiResult(windows=windows, cumulative_burn=cumulative_burn,
                      cumulative_weighted=cumulative_weighted, top_burners=top,
                      lam=lam, target_code=target_code,
                      target_auto_resolved=auto_resolved, depth_capped=any_depth_capped,
                      interpretation=interp)


# -- lambda sensitivity set (Q4/Q2 settled): recompute C and W at multiple lambda
# so a conclusion is not an artifact of one half-weight constant (analogous to the
# endpoint-timing sensitivity set).  B is lambda-invariant and reported once.
@dataclass
class LambdaPoint:
    lam: float
    cumulative_c: Optional[float]     # latest operational-window C at this lambda
    cumulative_w: Optional[float]     # current-segment cumulative W at this lambda


@dataclass
class LambdaSensitivity:
    cumulative_b: Optional[float]     # lambda-invariant gross burn (reported once)
    points: list = field(default_factory=list)      # list[LambdaPoint]
    reason: str = ""


def fcbi_lambda_sensitivity(sa, target: Optional[str] = None,
                            lams=(3.0, 5.0, 10.0)) -> LambdaSensitivity:
    """Recompute FCBI C and W across ``lams`` (default 3/5/10 working days).  B is
    lambda-invariant so it is reported once; C and W move with lambda, exposing
    whether a near-critical-burn conclusion is robust to the half-weight constant
    (Q2/Q4).  Never raises; a per-lambda failure is skipped with the reason kept
    on the result when nothing computed."""
    base = _fcbi(sa, DEFAULT_LAMBDA, target)
    if base.reason and not base.windows:
        return LambdaSensitivity(cumulative_b=None, reason=base.reason)
    cb = base.cumulative_burn[-1] if base.cumulative_burn else None
    points: list[LambdaPoint] = []
    for lam in lams:
        f = _fcbi(sa, lam, target)
        cw = f.cumulative_weighted[-1] if f.cumulative_weighted else None
        c = next((w.burn_proximity for w in reversed(f.windows)
                  if not w.basis_change and w.burn_proximity is not None), None)
        points.append(LambdaPoint(lam=lam, cumulative_c=c, cumulative_w=cw))
    return LambdaSensitivity(cumulative_b=cb, points=points)


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
                                f"band (RF <= {band_days:g}d)")

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
                     allocations=allocated, interpretation=interp)


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
                                "finish span to compute a required pace")
    interp = (f"Recovery debt stands at {cumulative:.1f} working days — the "
              "portion of the current completion forecast resting on a pace the "
              "Project has not demonstrated"
              + (" (debt has accrued: the forecast requires acceleration beyond "
                 "the best window achieved)." if cumulative > 0
                 else "; no window required more than the best pace demonstrated."))
    return RdiResult(rows=rows, rdi_days=cumulative, interpretation=interp)


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

    densities: list[Optional[float]] = []
    for s in scheds:
        tgt = _find_by_code(s, target)
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

    base = densities[0]
    if base is None:
        return BwiResult(target_code=target,
                         rows=[BwiRow(scheds[i].label(), densities[i], None)
                               for i in range(len(scheds))],
                         reason=f"target {target} has no usable forecast finish / "
                                "near-critical work at the first update")
    if base == 0:
        return BwiResult(target_code=target,
                         rows=[BwiRow(scheds[i].label(), densities[i], None)
                               for i in range(len(scheds))],
                         reason=f"baseline near-critical density ahead of {target} "
                                "is zero — BWI is undefined (nothing to normalize)")

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
    interp = (f"Work packed ahead of {target} is "
              f"{last_bwi:.2f}x the baseline density"
              if last_bwi is not None else
              f"Bow-wave density ahead of {target} could not be tracked")
    if break_label:
        interp += (f"; required density first outruns the demonstrated pace at "
                   f"{break_label} (projected break).")
    else:
        interp += "; required density stays within the demonstrated pace."
    return BwiResult(target_code=target, rows=rows,
                     projected_break_label=break_label, interpretation=interp)


# ==========================================================================
# public entry point
# ==========================================================================
def run_li_indices(sa, lam: float = DEFAULT_LAMBDA,
                   band_days: float = DEFAULT_BAND_DAYS,
                   bwi_target: Optional[str] = None,
                   fcbi_target: Optional[str] = None) -> LiIndicesResult:
    """Compute all five LI indices over the ordered series ``sa``.

    Float paths (the expensive step) are extracted once per schedule and shared
    across PCI/CDI (the v0.4 RF kernel); FCBI (LI-01, v0.5 governed) computes its
    own nonnegative target-specific distance basis (ruling O1) and does not use
    that kernel.  Every sub-result carries a ``reason`` when it could not be
    computed; this function never raises.

    Parameters
    ----------
    sa : SeriesAnalysis
        Ordered schedules with change-register changesets (``sa.schedules`` and
        ``sa.changesets``).
    lam : float
        Half-weight constant λ (default 5 working days): FCBI weight
        w = 2^(-d/λ), and the v0.4 kernel for PCI/CDI/RDI/BWI.
    band_days : float
        Near-critical band (RF <= band_days) for CDI/RDI/BWI (default 10 wd).
    bwi_target : str | None
        Activity code for the Bow-Wave milestone; default resolves to the latest
        late-type-constrained finish milestone, else the last finish milestone.
    fcbi_target : str | None
        The single selected TERMINAL completion finish milestone m for FCBI
        (ruling O6 v1 scope).  When omitted, FCBI auto-resolves a terminal finish
        milestone and flags ``target_auto_resolved`` — the analyst SHOULD select m
        explicitly (ruling O7.1).
    """
    scheds = getattr(sa, "schedules", [])
    # the shared v0.4 kernel (PCI/CDI/RDI/BWI) cannot divide by a non-positive λ;
    # fall back to the default there while FCBI reports the invalid-λ reason itself
    kern_lam = lam if (math.isfinite(lam) and lam > 0) else DEFAULT_LAMBDA
    kernels = {id(s): _build_kernel(s, kern_lam) for s in scheds}
    return LiIndicesResult(
        fcbi=_fcbi(sa, lam, fcbi_target),        # raw λ: FCBI reports invalid-λ itself
        pci=_pci(sa, kernels, kern_lam),
        cdi=_cdi(sa, kernels, kern_lam, band_days),
        rdi=_rdi(sa, kernels, band_days),
        bwi=_bwi(sa, kernels, band_days, bwi_target),
    )
