"""Driving-path and multi-path analytics over a parsed Schedule.

Forensic purpose
----------------
When an expert asks "what is doing this to my completion date?", the answer is
the *driving path*: the chain of activities whose relationships are satisfied
(predecessor's controlling date + lag lands, within tolerance, on the
successor's controlling date) all the way back from the target.  ScheduleIQ
recovers this from the tool-of-record dates and floats without running its own
CPM pass, so the result cannot disagree with the schedule of record (ADR-0004).
Around that spine we enumerate near-critical alternates (P1), profile how many
paths crowd the target (P2 — a volatility tell), rank the true merge points
where the date is most fragile (P3), and track how the driving path flips
across updates and *why* (P4 — the skeleton of a windows analysis).

All functions degrade gracefully: a schedule with no logic, no dates, or no
floats yields an empty result carrying a ``reason``, never an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..ingest.model import (Activity, Calendar, ConstraintType, RelType,
                            Relationship, Schedule)

DEFAULT_TOL_HOURS = 1.0


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class PathStep:
    """One activity on a path plus the relationship that drives the *next*
    step toward the target (None on the target itself)."""
    activity: Activity
    driving_rel: Optional[Relationship]     # this activity -> next-toward-target
    lag_hours: float
    calendar_name: str
    constraint: str
    total_float_days: Optional[float]
    pct_complete: float
    date_satisfied: bool = True             # rel met the date tolerance (vs float-picked)

    @property
    def code(self) -> str:
        return self.activity.code


@dataclass
class DrivingPath:
    target: Optional[Activity] = None
    steps: list[PathStep] = field(default_factory=list)   # ordered start -> target
    tolerance_hours: float = DEFAULT_TOL_HOURS
    flag_agreement_pct: Optional[float] = None            # vs Activity.is_longest_path
    flag_disagreements: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def codes(self) -> list[str]:
        return [s.code for s in self.steps]

    @property
    def activity_uids(self) -> list[str]:
        return [s.activity.uid for s in self.steps]


@dataclass
class FloatPath:
    rank: int
    steps: list[PathStep]
    min_float_days: Optional[float]
    max_float_days: Optional[float]
    calendars: list[str]
    constraints: list[str]
    pct_complete: float                     # length-weighted mean % complete
    rel_float_days: float = 0.0             # near-criticality of this path's own branch
    # Branch-unique min total float in raw HOURS over DISCRETE members only
    # (LOE/summary excluded).  None when the branch has no discrete member with a
    # stored float.  FCBI (LI-01 v0.5) uses this for a calendar-neutral,
    # discrete-members-only path margin (rulings O1/O7.3/O7.7); it divides by a
    # fixed reference hours/day rather than each activity's native calendar, so a
    # driver is not repriced by calendar length (never used by the v0.4 kernel).
    rel_float_hours: Optional[float] = None

    @property
    def codes(self) -> list[str]:
        return [s.code for s in self.steps]

    @property
    def activities(self) -> list[Activity]:
        return [s.activity for s in self.steps]


@dataclass
class MergePoint:
    activity: Activity
    converging_chains: int                  # distinct near-critical predecessor chains
    tightness_days: Optional[float]         # min float among the converging chains
    predecessor_codes: list[str] = field(default_factory=list)

    @property
    def code(self) -> str:
        return self.activity.code


@dataclass
class PathStabilityPair:
    earlier_label: str
    later_label: str
    jaccard: Optional[float]
    joined: list[str] = field(default_factory=list)     # on later path, not earlier
    left: list[str] = field(default_factory=list)       # on earlier path, not later
    causes: list[str] = field(default_factory=list)     # human-readable attributions
    progress_driven: list[str] = field(default_factory=list)
    revision_driven: list[str] = field(default_factory=list)
    reason: str = ""


# --------------------------------------------------------------------------
# date / calendar helpers
# --------------------------------------------------------------------------
def _ctrl_start(a: Activity) -> Optional[datetime]:
    """Controlling start: actuals win for started work, else early, else plan."""
    return a.actual_start or a.early_start or a.planned_start


def _ctrl_finish(a: Activity) -> Optional[datetime]:
    return a.actual_finish or a.early_finish or a.planned_finish


def _add_working_hours(cal: Optional[Calendar], t: datetime, hours: float) -> datetime:
    """Shift ``t`` by a (signed) lag expressed in working hours.

    Zero lag is exact (the common case on a driving chain).  For non-zero lags
    we advance in whole working days on the given calendar (hours converted via
    hours_per_day), which matches P6 closely enough for a ±tolerance test; a lag
    that still fails to align simply falls out of the satisfied set and the walk
    selects by float instead — it is never fatal.
    """
    if not hours:
        return t
    hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
    days = hours / hpd
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    cur = t
    guard = 0
    while remaining > 1e-9 and guard < 5000:
        guard += 1
        cur = cur + timedelta(days=step)
        if cal is None or cal.is_workday(cur.date()):
            remaining -= 1
    # sub-day remainder carried as raw hours (keeps small lags meaningful)
    frac = (abs(days) - int(abs(days)))
    if frac and cal:
        cur = cur + timedelta(hours=step * frac * hpd)
    return cur


def _pred_drive_date(pred: Activity, rtype: RelType) -> Optional[datetime]:
    """The predecessor date that a relationship of ``rtype`` keys off."""
    if rtype in (RelType.FS, RelType.FF):
        return _ctrl_finish(pred)
    return _ctrl_start(pred)            # SS, SF key off predecessor start


def _succ_key_date(succ: Activity, rtype: RelType) -> Optional[datetime]:
    """The successor date a relationship of ``rtype`` lands on.

    FS/SS constrain the successor start; FF/SF constrain the successor finish.
    For FF/SF the finish is the driven date and the implied start is
    finish − duration on the successor's calendar (used by the impact math);
    for membership we only need the driven date itself.
    """
    if rtype in (RelType.FS, RelType.SS):
        return _ctrl_start(succ)
    return _ctrl_finish(succ)           # FF, SF land on successor finish


def _is_satisfied(sched: Schedule, pred: Activity, succ: Activity,
                  rel: Relationship, tol_hours: float) -> bool:
    """A relationship is satisfied/driving when the predecessor's keyed date
    plus lag lands within ``tol_hours`` of the successor's keyed date."""
    pd = _pred_drive_date(pred, rel.rtype)
    sd = _succ_key_date(succ, rel.rtype)
    if pd is None or sd is None:
        return False
    cal = sched.cal_for(pred)
    driven = _add_working_hours(cal, pd, rel.lag_hours)
    return abs((sd - driven).total_seconds()) <= tol_hours * 3600.0 + 1.0


def _tf_days(sched: Schedule, a: Activity) -> Optional[float]:
    return a.total_float_days(sched.cal_for(a))


def _constraint_label(a: Activity) -> str:
    if a.constraint and a.constraint != ConstraintType.NONE:
        return a.constraint.value
    if a.constraint2 and a.constraint2 != ConstraintType.NONE:
        return a.constraint2.value
    return ""


def _make_step(sched: Schedule, a: Activity, rel: Optional[Relationship],
               satisfied: bool = True) -> PathStep:
    cal = sched.cal_for(a)
    return PathStep(
        activity=a,
        driving_rel=rel,
        lag_hours=rel.lag_hours if rel else 0.0,
        calendar_name=(cal.name or cal.uid) if cal else (a.calendar_uid or ""),
        constraint=_constraint_label(a),
        total_float_days=_tf_days(sched, a),
        pct_complete=a.pct_complete,
        date_satisfied=satisfied,
    )


# --------------------------------------------------------------------------
# target selection
# --------------------------------------------------------------------------
def _default_target(sched: Schedule) -> Optional[Activity]:
    """The project-completion target: the latest-finishing incomplete activity,
    preferring finish milestones and, among ties, the least-float (most
    critical) one — i.e. the substantial-completion milestone, not a parallel
    constrained one."""
    cands = [a for a in sched.real_activities if _ctrl_finish(a) is not None]
    if not cands:
        return None
    latest = max(_ctrl_finish(a) for a in cands)
    tol = timedelta(hours=DEFAULT_TOL_HOURS)
    at_end = [a for a in cands if abs(_ctrl_finish(a) - latest) <= tol]

    def rank(a: Activity):
        is_mile = 0 if a.atype.name == "FINISH_MILESTONE" else 1
        incomplete = 0 if not a.completed else 1
        fl = _tf_days(sched, a)
        fl = fl if fl is not None else 1e9
        return (incomplete, is_mile, fl, a.code)

    return sorted(at_end, key=rank)[0]


def _resolve_target(sched: Schedule, target_uid: Optional[str]) -> Optional[Activity]:
    if target_uid is not None:
        if target_uid in sched.activities:
            return sched.activities[target_uid]
        for a in sched.activities.values():        # allow target by code
            if a.code == target_uid:
                return a
        return None
    return _default_target(sched)


# --------------------------------------------------------------------------
# core backward walk
# --------------------------------------------------------------------------
FLOAT_TIE_BAND_DAYS = 0.1     # floats this close are a tie; satisfaction breaks it


def _walk(sched: Schedule, target: Activity, tol_hours: float,
          allowed: Optional[set[str]] = None) -> list[PathStep]:
    """Backward walk from ``target`` choosing, at each node, the driving
    predecessor by minimum total float FIRST (ties banded within
    ~FLOAT_TIE_BAND_DAYS), with date-satisfaction used only as the tiebreak
    inside that band.  Float is the tool-of-record's own criticality statement
    and must govern: on real files the satisfaction test can miss (lag
    calendars, calendar nuances), and a claimed driving path carrying floaty
    activities while a zero-float chain exists would be indefensible.  The
    chosen step keeps its date_satisfied flag as an annotation so satisfaction
    mismatches stay visible in every output.  ``allowed`` restricts the usable
    predecessor uids (for float-path extraction)."""
    rev: list[tuple[Activity, Optional[Relationship], bool]] = [(target, None, True)]
    visited = {target.uid}
    cur = target
    guard = 0
    while guard < len(sched.activities) + 2:
        guard += 1
        cands = []
        for r in sched.predecessors_of(cur.uid):
            p = sched.activities.get(r.pred_uid)
            if p is None or p.uid in visited:
                continue
            if allowed is not None and p.uid not in allowed:
                continue
            sat = _is_satisfied(sched, p, cur, r, tol_hours)
            fl = _tf_days(sched, p)
            cands.append((r, p, sat, fl if fl is not None else 1e9))
        if not cands:
            break
        # minimum float first; within the tie band prefer date-satisfied rels
        min_fl = min(c[3] for c in cands)
        band = [c for c in cands if c[3] <= min_fl + FLOAT_TIE_BAND_DAYS]
        r, p, sat, _ = min(band, key=lambda c: (not c[2], c[3], c[1].code))
        rev.append((p, r, sat))
        visited.add(p.uid)
        cur = p
    # reverse to start->target.  In backward order each node stored the rel that
    # runs from it into the node one step closer to the target, so after
    # reversal that same rel is the one driving this step's *next* hop; the
    # target itself stored None.
    steps: list[PathStep] = []
    for a, rel_toward_target, sat in reversed(rev):
        steps.append(_make_step(sched, a, rel_toward_target, sat))
    return steps


def _flag_agreement(sched: Schedule, member_uids: set[str]) -> tuple[Optional[float], list[str]]:
    """Cross-check the recovered path against the tool's own longest-path flag
    (P6 driving_path_flag, model field is_longest_path) where present."""
    flagged = [a for a in sched.real_activities if a.is_longest_path is not None]
    if not flagged:
        return None, []
    agree, dis = 0, []
    for a in flagged:
        on_path = a.uid in member_uids
        if bool(a.is_longest_path) == on_path:
            agree += 1
        else:
            dis.append(a.code)
    return 100.0 * agree / len(flagged), dis


# --------------------------------------------------------------------------
# A1: driving path
# --------------------------------------------------------------------------
def driving_path(schedule: Schedule, target_uid: Optional[str] = None,
                 tolerance_hours: float = DEFAULT_TOL_HOURS) -> DrivingPath:
    """Extract the driving path to ``target_uid`` (default: completion target).

    Backward walk through satisfied relationships; the returned steps run
    start -> target, each carrying the relationship that drives the next step,
    its lag, calendar, constraint, total float (days on the activity's own
    calendar), and % complete.  Metadata records the tolerance and the
    agreement rate against the tool's longest-path flag (P6 crosscheck)."""
    if not schedule.relationships:
        return DrivingPath(reason="schedule has no relationships")
    target = _resolve_target(schedule, target_uid)
    if target is None:
        return DrivingPath(reason="no target activity could be resolved "
                                  "(missing finish dates?)")
    steps = _walk(schedule, target, tolerance_hours)
    if not steps:
        return DrivingPath(target=target, tolerance_hours=tolerance_hours,
                           reason="target has no predecessors to walk")
    member_uids = {s.activity.uid for s in steps}
    pct, dis = _flag_agreement(schedule, member_uids)
    return DrivingPath(target=target, steps=steps,
                       tolerance_hours=tolerance_hours,
                       flag_agreement_pct=pct, flag_disagreements=dis)


# --------------------------------------------------------------------------
# P1: top-N float paths
# --------------------------------------------------------------------------
def _path_floats(steps: list[PathStep]) -> tuple[Optional[float], Optional[float]]:
    vals = [s.total_float_days for s in steps if s.total_float_days is not None]
    if not vals:
        return None, None
    return min(vals), max(vals)


def _finalize_path(schedule: Schedule, rank: int, steps: list[PathStep],
                   unique_uids: set[str]) -> FloatPath:
    mn, mx = _path_floats(steps)
    cals, cons = [], []
    for s in steps:
        if s.calendar_name and s.calendar_name not in cals:
            cals.append(s.calendar_name)
        if s.constraint and s.constraint not in cons:
            cons.append(s.constraint)
    pcs = [s.pct_complete for s in steps]
    pc = sum(pcs) / len(pcs) if pcs else 0.0
    # relative float = near-criticality of the branch unique to this path
    uvals = [s.total_float_days for s in steps
             if s.activity.uid in unique_uids and s.total_float_days is not None]
    rel = min(uvals) if uvals else (mn if mn is not None else 0.0)
    # calendar-neutral, DISCRETE-members-only branch margin in raw hours (FCBI):
    # LOE/summary excluded so a level-of-effort node can never set the margin
    # (ruling O7.3 discrete-members; REV-07).
    uvals_h = [s.activity.total_float_hours for s in steps
               if s.activity.uid in unique_uids
               and not s.activity.is_loe_or_summary
               and s.activity.total_float_hours is not None]
    rel_h = min(uvals_h) if uvals_h else None
    return FloatPath(rank=rank, steps=steps, min_float_days=mn, max_float_days=mx,
                     calendars=cals, constraints=cons, pct_complete=pc,
                     rel_float_days=rel if rel is not None else 0.0,
                     rel_float_hours=rel_h)


def float_paths(schedule: Schedule, target_uid: Optional[str] = None,
                n: int = 10, band_days: Optional[float] = None,
                tolerance_hours: float = DEFAULT_TOL_HOURS) -> list[FloatPath]:
    """Enumerate the top-N distinct paths to the target ranked by path relative
    float (P6 "multiple float paths").

    Path 1 is the driving path (least float).  Each subsequent path is the
    least-float *feeder*: a chain of not-yet-used activities that drives into an
    already-found path at a merge point, spliced onto that path's tail so every
    reported path still runs start -> target.  Feeder activities are then
    removed from the walkable set, so each path is a genuinely distinct,
    progressively higher-float alternate.  ``band_days`` caps output to paths
    whose relative float is within that many working days of the driving path.
    """
    if not schedule.relationships:
        return []
    target = _resolve_target(schedule, target_uid)
    if target is None:
        return []
    n = max(1, n)
    all_uids = {a.uid for a in schedule.activities.values()}
    steps1 = _walk(schedule, target, tolerance_hours, allowed=all_uids)
    if len(steps1) < 2:
        return []
    used = {s.activity.uid for s in steps1}
    # each found path kept as its ordered steps for splicing feeders onto tails
    found: list[list[PathStep]] = [steps1]
    out: list[FloatPath] = [_finalize_path(schedule, 1, steps1, used.copy())]

    while len(out) < n:
        best = None                         # (rel_float, feeder_steps, tail, feeder_uids)
        for fp in found:
            for idx, step in enumerate(fp):
                X = step.activity
                for r in schedule.predecessors_of(X.uid):
                    p = schedule.activities.get(r.pred_uid)
                    if p is None or p.uid in used:
                        continue
                    allowed = (all_uids - used) | {p.uid}
                    feeder = _walk(schedule, p, tolerance_hours, allowed=allowed)
                    if not feeder:
                        continue
                    # attach the connecting relationship p -> X to the feeder head
                    sat = _is_satisfied(schedule, p, X, r, tolerance_hours)
                    feeder[-1] = _make_step(schedule, p, r, sat)
                    fvals = [s.total_float_days for s in feeder
                             if s.total_float_days is not None]
                    rel = min(fvals) if fvals else 1e9
                    key = (rel, p.code)
                    if best is None or key < best[0]:
                        best = (key, feeder, fp[idx:], {s.activity.uid for s in feeder})
        if best is None:
            break
        _key, feeder, tail, feeder_uids = best
        rel = _key[0]
        if band_days is not None and rel > band_days + 1e-9:
            break
        full = feeder + tail
        out.append(_finalize_path(schedule, len(out) + 1, full, feeder_uids))
        found.append(full)
        used |= feeder_uids
    return out


_MISS = object()        # sentinel distinguishing "unwalked" from a cached None


def iter_float_paths(schedule: Schedule, target_uid: Optional[str] = None,
                     tolerance_hours: float = DEFAULT_TOL_HOURS):
    """Lazy generator yielding EXACTLY the paths of :func:`float_paths` — the same
    ``FloatPath`` objects in the same order — one at a time and unbounded.  It runs
    ``float_paths``'s own round structure VERBATIM: each round re-scans every found
    path and recomputes every feeder under the CURRENT ``used`` set, then selects
    the global minimum ``(native rel float, pred code)`` with the same first-found
    tie-break.  It is therefore the reference algorithm restructured to stream,
    not an approximation of it.

    A prior best-first/priority-queue variant (v0.5.4) was WITHDRAWN in wave-4: it
    cached each feeder against the ``used`` set current at push time and only
    re-pushed when a revalidated feeder's rel ROSE.  But consuming an activity can
    reroute a feeder's backward walk so its rel FALLS and its node sequence changes
    entirely (``float_paths``'s native-rel order is genuinely non-monotone — a
    later path can expose a lower-float branch hidden behind a since-consumed
    activity).  That broke exact equivalence: divergent path sequences and, through
    them, wrong per-activity distances and a frontier certificate computed on a
    corrupted ``used`` set (wave-4 W4-01/W4-02).  Correctness over performance
    (governed constraint): enumeration cost is bounded by the callers — the SOUND
    convergence frontier and ``FCBI_PATHS_MAX`` cap in
    :func:`li_indices._target_distance` — not by weakening the enumeration here.

    Two per-round optimisations keep the selection and its tie-break IDENTICAL to
    ``float_paths`` (verified byte-for-byte on a 500-DAG corpus, W4-03) while
    removing its redundant work:

    * the feeder walk from a predecessor ``p`` is MEMOISED by ``p.uid`` — it depends
      only on ``used`` (fixed within the round), identical for every attachment; and
    * an attachment activity is examined at most ONCE per round (``seen_attach``).
      ``float_paths`` keys a candidate by ``(feeder rel, p.code)`` — INDEPENDENT of
      which found path the attachment sits on — and keeps the first-seen among equal
      keys.  A shared merge activity (e.g. the target) recurs as a step on many found
      paths; re-examining it from a later found path only regenerates equal-key
      candidates that the first-seen tie-break already discards, so skipping them
      cannot change the winner.  This turns an O(paths·merge-degree) re-scan of a
      wide near-critical fan into O(activities) per round.

    Yields ``(native_rel_float_days, FloatPath, frozenset_of_used_uids)``.  The
    used-set snapshot is ``float_paths``'s OWN cumulative used set AFTER the yielded
    path; every not-yet-yielded path's unique members are a subset of the unused
    activities, so a caller can derive a sound lower bound on every future path's
    margin from ``reachable − used`` (used by the FCBI convergence frontier)."""
    if not schedule.relationships:
        return
    target = _resolve_target(schedule, target_uid)
    if target is None:
        return
    all_uids = {a.uid for a in schedule.activities.values()}
    steps1 = _walk(schedule, target, tolerance_hours, allowed=all_uids)
    if len(steps1) < 2:
        return
    used = {s.activity.uid for s in steps1}
    found: list[list[PathStep]] = [steps1]
    fp1 = _finalize_path(schedule, 1, steps1, used.copy())
    yield fp1.rel_float_days, fp1, frozenset(used)
    rank = 1

    while True:
        # per-round memo: p.uid -> (native_rel, feeder_steps) or None.  The walk
        # from p depends only on ``used`` (fixed within a round), so it is identical
        # across every attachment X — computing it once cannot change the selection.
        memo: dict = {}
        # ``float_paths`` walks each feeder with allowed = (all_uids - used) | {p.uid};
        # every candidate ``p`` here is already unused (checked below), so that set is
        # exactly ``all_uids - used`` for the whole round — build it once (read-only).
        allowed_round = all_uids - used

        def _feeder(p):
            cached = memo.get(p.uid, _MISS)
            if cached is not _MISS:
                return cached
            feeder = _walk(schedule, p, tolerance_hours, allowed=allowed_round)
            if not feeder:
                memo[p.uid] = None
                return None
            fvals = [s.total_float_days for s in feeder if s.total_float_days is not None]
            res = (min(fvals) if fvals else 1e9, feeder)
            memo[p.uid] = res
            return res

        best = None                          # (key, feeder, tail, feeder_uids)
        seen_attach: set[str] = set()        # attachment activities handled this round
        for fp in found:
            for idx, step in enumerate(fp):
                X = step.activity
                if X.uid in seen_attach:     # first-seen (found, idx) already covers X;
                    continue                 # later occurrences only re-tie, never win
                seen_attach.add(X.uid)
                for r in schedule.predecessors_of(X.uid):
                    p = schedule.activities.get(r.pred_uid)
                    if p is None or p.uid in used:
                        continue
                    fr = _feeder(p)
                    if fr is None:
                        continue
                    rel, feeder0 = fr
                    key = (rel, p.code)
                    if best is None or key < best[0]:
                        # attach the connecting rel p->X to a COPY of the head (the
                        # memoised feeder is shared across attachments; the head's
                        # float — hence ``rel`` — is unchanged by this annotation)
                        feeder = list(feeder0)
                        sat = _is_satisfied(schedule, p, X, r, tolerance_hours)
                        feeder[-1] = _make_step(schedule, p, r, sat)
                        best = (key, feeder, fp[idx:],
                                {s.activity.uid for s in feeder})
        if best is None:
            break
        _key, feeder, tail, feeder_uids = best
        rank += 1
        full = feeder + tail
        fp = _finalize_path(schedule, rank, full, feeder_uids)
        found.append(full)
        used |= feeder_uids
        yield fp.rel_float_days, fp, frozenset(used)


# --------------------------------------------------------------------------
# P2: proximity profile
# --------------------------------------------------------------------------
def proximity_profile(schedule: Schedule, target_uid: Optional[str] = None,
                      bands=(5, 10, 20),
                      tolerance_hours: float = DEFAULT_TOL_HOURS) -> dict:
    """Distribution of near-critical crowding around the target.

    For each band (working days) report how many distinct paths and how many
    distinct activities sit within that much *relative* float of the target's
    driving path.  A schedule with many paths inside a tight band is a
    volatility warning for any windows analysis (proposal §2.2)."""
    dp = driving_path(schedule, target_uid, tolerance_hours)
    result = {"target": dp.target.code if dp.target else None,
              "bands": {}, "reason": dp.reason}
    if not dp.steps:
        return result
    target_float = dp.target.total_float_days(schedule.cal_for(dp.target)) \
        if dp.target else 0.0
    target_float = target_float if target_float is not None else 0.0
    # enumerate a generous set of paths once, then bucket by band
    paths = float_paths(schedule, target_uid, n=50, band_days=None,
                        tolerance_hours=tolerance_hours)
    for band in bands:
        npaths, acts = 0, set()
        for p in paths:
            rel = p.rel_float_days - target_float
            if rel <= band + 1e-9:
                npaths += 1
                for s in p.steps:
                    if s.total_float_days is not None \
                            and (s.total_float_days - target_float) <= band + 1e-9:
                        acts.add(s.activity.uid)
        result["bands"][band] = {"paths": npaths, "activities": len(acts)}
    return result


# --------------------------------------------------------------------------
# P3: true merge-point ranking
# --------------------------------------------------------------------------
def merge_ranking(schedule: Schedule, near_days: float = 10.0,
                  top: int = 15) -> list[MergePoint]:
    """Rank merge nodes by the number of DISTINCT converging near-critical
    chains (not raw predecessor counts, as Fuse's Merge Hotspot does).

    A merge node's fragility is the number of predecessor chains whose head is
    within ``near_days`` of critical converging on it, and its tightness is the
    minimum float among those converging chains — where the completion date is
    most exposed (proposal §2.3)."""
    if not schedule.relationships:
        return []
    merges: list[MergePoint] = []
    for a in schedule.real_activities:
        preds = schedule.predecessors_of(a.uid)
        if len(preds) < 2:
            continue
        near = []
        seen = set()
        for r in preds:
            p = schedule.activities.get(r.pred_uid)
            if p is None or p.uid in seen:
                continue
            seen.add(p.uid)
            fl = _tf_days(schedule, p)
            if fl is not None and fl <= near_days:
                near.append((p.code, fl))
        if len(near) >= 2:
            merges.append(MergePoint(
                activity=a, converging_chains=len(near),
                tightness_days=min(f for _, f in near),
                predecessor_codes=[c for c, _ in near]))
    merges.sort(key=lambda m: (-m.converging_chains,
                               m.tightness_days if m.tightness_days is not None else 1e9,
                               m.code))
    return merges[:top]


# --------------------------------------------------------------------------
# P4: path stability across updates
# --------------------------------------------------------------------------
def _changeset_index(cs) -> dict:
    """Map activity code -> the set of change categories touching it in a
    ChangeSet, split into progress-side and revision-side edits."""
    progress: dict[str, list[str]] = {}
    revision: dict[str, list[str]] = {}

    def add(bucket, code, label):
        bucket.setdefault(code, [])
        if label not in bucket[code]:
            bucket[code].append(label)

    for ch in cs.status_changes:
        add(progress, ch.code, f"status {ch.before}->{ch.after}")
    for ch in cs.actual_date_changes:
        add(progress, ch.code, f"{ch.field} {ch.before}->{ch.after}")
    for ch in cs.planned_date_changes:
        add(progress, ch.code, f"{ch.field} {ch.before}->{ch.after}")
    for ch in cs.duration_changes:
        add(revision, ch.code, f"duration {ch.before}->{ch.after}")
    for ch in cs.constraint_changes:
        add(revision, ch.code, f"constraint {ch.before}->{ch.after}")
    for ch in cs.calendar_changes:
        add(revision, ch.code, f"calendar {ch.before}->{ch.after}")
    for lc in cs.logic_changes:
        lbl = f"logic {lc.kind} {lc.pred_code}->{lc.succ_code}"
        add(revision, lc.pred_code, lbl)
        add(revision, lc.succ_code, lbl)
    return {"progress": progress, "revision": revision}


def path_stability(series_analysis, target_code: Optional[str] = None,
                   tolerance_hours: float = DEFAULT_TOL_HOURS
                   ) -> list[PathStabilityPair]:
    """Per consecutive update pair, compare driving-path membership (by code)
    and attribute each flip.

    A code joining or leaving the driving path is classified progress-driven
    (its status / actual / forecast dates moved in the change register) or
    revision-driven (it — or a relationship on it — appears in the logic /
    constraint / duration / calendar edits), with the specific named edits
    recorded so every attribution is traceable (proposal §2.4)."""
    scheds = getattr(series_analysis, "schedules", [])
    changesets = getattr(series_analysis, "changesets", [])
    out: list[PathStabilityPair] = []
    if len(scheds) < 2:
        return out
    # resolve a stable target code across the series (first schedule's default)
    if target_code is None:
        dp0 = driving_path(scheds[0], None, tolerance_hours)
        target_code = dp0.target.code if dp0.target else None

    def path_codes(s: Schedule) -> set[str]:
        dp = driving_path(s, target_code, tolerance_hours)
        return set(dp.codes)

    for i in range(len(scheds) - 1):
        e, l = scheds[i], scheds[i + 1]
        ce, cl = path_codes(e), path_codes(l)
        pair = PathStabilityPair(earlier_label=e.label(), later_label=l.label(),
                                 jaccard=None)
        union = ce | cl
        pair.jaccard = len(ce & cl) / len(union) if union else None
        pair.joined = sorted(cl - ce)
        pair.left = sorted(ce - cl)
        flips = set(pair.joined) | set(pair.left)
        if not flips:
            pair.causes.append("driving path unchanged")
            out.append(pair)
            continue
        cs = changesets[i] if i < len(changesets) else None
        idx = _changeset_index(cs) if cs is not None else {"progress": {}, "revision": {}}
        for code in sorted(flips):
            prog = idx["progress"].get(code)
            rev = idx["revision"].get(code)
            if prog:
                pair.progress_driven.append(code)
                pair.causes.append(f"{code}: progress-driven ({'; '.join(prog)})")
            if rev:
                pair.revision_driven.append(code)
                pair.causes.append(f"{code}: revision-driven ({'; '.join(rev)})")
            if not prog and not rev:
                pair.causes.append(f"{code}: reflowed (no direct edit; driven by "
                                   "an upstream change)")
        out.append(pair)
    return out


# --------------------------------------------------------------------------
# convenience bundle for the report/excel writers
# --------------------------------------------------------------------------
def run_path_analytics(series_analysis, target_code: Optional[str] = None,
                       n: int = 10, near_days: float = 10.0,
                       tolerance_hours: float = DEFAULT_TOL_HOURS) -> dict:
    """Compute the full multi-path bundle for a series in one call, targeting
    the latest update's completion (or ``target_code``).  Returns a dict the
    Excel and Word writers consume; never raises."""
    scheds = getattr(series_analysis, "schedules", [])
    if not scheds:
        return {"target_code": target_code, "driving": DrivingPath(reason="no schedules"),
                "float_paths": [], "proximity": {"bands": {}}, "merges": [],
                "stability": [], "per_update_driving": []}
    latest = scheds[-1]
    if target_code is None:
        dp0 = driving_path(latest, None, tolerance_hours)
        target_code = dp0.target.code if dp0.target else None
    return {
        "target_code": target_code,
        "driving": driving_path(latest, target_code, tolerance_hours),
        "float_paths": float_paths(latest, target_code, n=n,
                                   tolerance_hours=tolerance_hours),
        "proximity": proximity_profile(latest, target_code,
                                       tolerance_hours=tolerance_hours),
        "merges": merge_ranking(latest, near_days=near_days),
        "stability": path_stability(series_analysis, target_code, tolerance_hours),
        "per_update_driving": [(s.label(), driving_path(s, target_code, tolerance_hours))
                               for s in scheds],
    }
