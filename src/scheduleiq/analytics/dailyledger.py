"""Daily-resolution delay ledger — "continuous windows" (backlog N3;
ANALYTICS_PROPOSAL.md §8.3; ADR-0007 gate + presentation rule).

Forensic purpose
----------------
Between two consecutive schedule updates the per-update movement of a target
(milestone / completion) is one number.  This module interpolates the progress
state day by day between the two data dates and re-schedules the network at
each daily step, producing a day-by-day ledger of critical-path delay and
recovery whose daily deltas SUM EXACTLY to the movement between the two
endpoint states (a built-in arithmetic check, asserted in code).  It
eliminates window-boundary judgment calls and makes concurrency visible at the
resolution where it happens.  Everything here is a **diagnostic delta**
(ADR-0007 §4): tool-of-record dates remain the schedule; nothing is written
back.  The output is expressly PRELIMINARY / observational — concurrency,
causation, entitlement and quantum are reserved to the expert (CLAUDE.md §4).

Method (documented choices)
---------------------------
1.  **Handshake gate** (ADR-0007 §3): BOTH files must pass
    ``require_valid_handshake`` before any daily run; ``handshake="skip"`` is
    the documented analyst/test escape hatch, recorded in ``disclosures``.
2.  **Target resolution as in impact.py**: resolved on the LATER file
    (explicit uid/code, else latest-finishing finish milestone, else
    latest-finishing activity = the project-finish fallback), then located in
    the EARLIER file by code for the reconciliation block; misses disclosed.
3.  **Later-network framing**: every daily state is scheduled on the LATER
    file's network — its logic, durations, constraints, calendars and
    SCHEDOPTIONS (statusing mode, lag-calendar strategy).  Rationale: the
    ledger measures delay *as expressed against the current-network view* of
    the project — the network the parties were actually steering by at the end
    of the window.  The alternative earlier-network framing (apply later
    progress to the earlier network) is exactly the D9 MIP 3.4 half-step, and
    the N4 methodology-robustness sweep varies the framing; this module
    deliberately fixes it and says so.
4.  **State interpolation, day granularity.**  For each calendar day d from
    earlier.data_date to later.data_date inclusive, per activity (per the
    LATER file's actuals):
      * actual_finish <= d  → completed: pin AS and AF;
      * actual_start <= d < actual_finish (or no AF) → in-progress: pin AS;
        remaining duration = linear interpolation between the RD implied at
        the earlier data date (the earlier file's RD for the same code, by
        code; the later file's OD when the activity is not in the earlier
        file) and the RD at the later data date (later's RD; 0 when completed
        by then), over WORKDAYS of the activity's own calendar between the two
        data dates, evaluated at d; rounded half up to an integer, floored at
        0.  Milestones carry RD 0.
      * not yet started at d → unpinned; scheduled at the EARLIER file's
        remaining duration when the code exists there (not completed), else
        the later file's OD — a disclosed choice.
    The day state is then rescheduled with ``project_start = d`` (the data
    date) → EF_target(d).
5.  **Workday-index conventions.**  The interpolation clock w(d) uses the
    FORWARD-adjusted workday index (a non-workday d takes the next workday's
    index) — consistent with the engine's own project_start adjustment, so
    the day state is piecewise-constant across non-working days and weekend
    rows carry zero deltas rather than jitter.  The ledger's wd() subtraction
    of target EF dates uses ``nearest_workday_index`` semantics on the
    TARGET's calendar table (engine EFs land on the activity's own calendar
    workdays, which may be non-workdays of the target calendar in
    multi-calendar networks).  Both choices are fixed and documented here.
6.  **Ledger rows** (d0 is the baseline; rows start at d0+1):
    daily_delta_wd = wd(EF_target(d)) − wd(EF_target(d−1)); positive = slip,
    negative = recovery.  Each row carries the day's controlling activity —
    the target's IMMEDIATE binding predecessor (a one-step backward walk from
    the target, preferring the predecessor whose relationship-driven date
    lands exactly on the target's early date, ties broken by latest driven
    date then greatest predecessor id — same convention as impact.py's
    controlling-path walk, restricted to one step; documented choice) — plus
    the codes newly started / newly completed on that day.
7.  **Arithmetic check** (spec §8.3): Σ daily deltas == wd(EF_target(d_last))
    − wd(EF_target(d0)) EXACTLY — telescoping by construction, asserted in
    code, both sides exposed.  The RECONCILIATION block additionally reports
    the interpolated endpoints against the two AS-IMPORTED engine runs and
    the record dates: the endpoints will NOT exactly equal the as-imported
    runs whenever the later file's actuals/RDs disagree with linear
    interpolation (or the not-started duration choice differs) — disclosed,
    not hidden.
8.  **Annotation**: events (D6 ``EventMapResult``) whose window covers d are
    listed on the row; with a responsibility overlay (D7), each day's delta is
    attributed to the tag of that day's controlling activity → per-party
    subtotals, labelled an OBSERVATIONAL allocation (a screen, not an
    apportionment; concurrency/causation reserved to the expert).
9.  **Performance / cap**: one engine run per day; EngineInputs are built once
    and only pins/RDs are mutated per day.  Windows longer than
    ``_DAY_CAP`` (400) days are truncated at the cap with a disclosure (the
    arithmetic identity then covers the truncated span).
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..ingest.model import Activity as IngestActivity, Schedule
from ..cpm.bridge import EngineInputs, build_engine_inputs
from ..cpm.calendar_ops import build_workday_table, nearest_workday_index
from ..cpm.engine import run_analysis
from ..cpm.handshake import (HandshakeResult, require_valid_handshake,
                             run_handshake)
from ..cpm.relationship_logic import compute_relationship_constraint
from ..cpm.results import AnalysisResult
# Target resolution is deliberately shared with impact.py (same precedence,
# same wording) so the two engine-side analytics never disagree on "the target".
from .impact import _record_finish, _resolve_target

LABEL = ("PRELIMINARY — observational daily delay ledger; concurrency, "
         "causation, entitlement, and quantum are reserved to the expert")

PRESENTATION_RULE = ("Tool-of-record dates are the schedule; every engine "
                     "figure here is a diagnostic delta only (ADR-0007 §4).")

SIGN_CONVENTION = ("positive daily delta = the target slips later; "
                   "negative = recovery")

# Hard cap on the number of daily engine runs (spec item 7).
_DAY_CAP = 400


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class DayRow:
    """One ledger day (d0 itself is the baseline and carries no row)."""
    day: date
    ef_target: Optional[date] = None
    delta_workdays: int = 0
    cumulative_workdays: int = 0
    controlling_code: str = ""
    controlling_party: Optional[str] = None
    newly_started: list[str] = field(default_factory=list)
    newly_completed: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "ef_target": self.ef_target.isoformat() if self.ef_target else None,
            "delta_workdays": self.delta_workdays,
            "cumulative_workdays": self.cumulative_workdays,
            "controlling_code": self.controlling_code,
            "controlling_party": self.controlling_party,
            "newly_started": list(self.newly_started),
            "newly_completed": list(self.newly_completed),
            "event_ids": list(self.event_ids),
        }


@dataclass
class DailyLedger:
    """The full daily-resolution delay ledger for one update pair."""
    label: str = LABEL
    earlier_label: str = ""
    later_label: str = ""

    target_uid: Optional[str] = None
    target_code: Optional[str] = None
    target_name: Optional[str] = None
    resolved_how: str = ""
    target_calendar: str = ""
    earlier_target_uid: Optional[str] = None
    earlier_target_how: str = ""

    handshake_earlier: Optional[dict[str, Any]] = None
    handshake_later: Optional[dict[str, Any]] = None

    computable: bool = True
    blocking: str = ""

    window: dict[str, Any] = field(default_factory=dict)
    rows: list[DayRow] = field(default_factory=list)
    arithmetic_check: dict[str, Any] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    responsibility_subtotals: dict[str, Any] = field(default_factory=dict)
    disclosures: list[str] = field(default_factory=list)

    @property
    def cumulative_series(self) -> list[dict[str, Any]]:
        """The cumulative delay curve (for charting)."""
        return [{"day": r.day.isoformat(),
                 "cumulative_workdays": r.cumulative_workdays}
                for r in self.rows]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "presentation_rule": PRESENTATION_RULE,
            "sign_convention": SIGN_CONVENTION,
            "pair": {"earlier": self.earlier_label, "later": self.later_label},
            "target": {
                "uid": self.target_uid,
                "code": self.target_code,
                "name": self.target_name,
                "calendar": self.target_calendar,
                "resolved_how": self.resolved_how,
                "earlier_uid": self.earlier_target_uid,
                "earlier_located_how": self.earlier_target_how,
            },
            "handshake_earlier": self.handshake_earlier,
            "handshake_later": self.handshake_later,
            "computable": self.computable,
            "blocking": self.blocking,
            "window": dict(self.window),
            "rows": [r.to_dict() for r in self.rows],
            "cumulative_series": self.cumulative_series,
            "arithmetic_check": dict(self.arithmetic_check),
            "reconciliation": dict(self.reconciliation),
            "responsibility_subtotals": dict(self.responsibility_subtotals),
            "disclosures": list(self.disclosures),
        }


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _as_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def _hpd(sched: Schedule, a: IngestActivity) -> float:
    cal = sched.cal_for(a)
    return cal.hours_per_day if (cal and cal.hours_per_day) else 8.0


def _floor_wd(hours: float, hpd: float) -> int:
    if hpd <= 0:
        hpd = 8.0
    return int(math.floor(hours / hpd + 1e-9))


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def _fwd_index(tbl: dict[date, int], d: date) -> int:
    """Forward-adjusted workday index: a non-workday takes the NEXT workday's
    index (consistent with the engine's project_start adjustment) — the
    interpolation clock (module docstring item 5).  Falls back to the nearest
    index defensively at table edges."""
    v = tbl.get(d)
    if v is not None:
        return v
    for k in range(1, 15):
        v = tbl.get(d + timedelta(days=k))
        if v is not None:
            return v
    return nearest_workday_index(tbl, d)


def capped_day_range(d0: date, dn: date, cap: int = _DAY_CAP
                     ) -> tuple[list[date], bool]:
    """All calendar days d0..dn inclusive, truncated at ``cap`` days after d0.
    Returns (days, capped).  Separable so the cap logic is unit-testable
    without 400 engine runs."""
    total = (dn - d0).days
    n = min(total, cap)
    return [d0 + timedelta(days=k) for k in range(n + 1)], total > cap


def _hs_summary(hs: HandshakeResult) -> dict[str, Any]:
    return {
        "match_rate_pct": round(hs.match_rate_pct, 2),
        "threshold_pct": hs.threshold_pct,
        "passed": hs.passed,
        "engine_is_valid": hs.engine_is_valid,
        "statusing_mode": hs.statusing_mode,
        "lag_strategy": hs.lag_strategy,
        "constraint_applications": hs.constraint_applications,
    }


def _wd_delta(tbl: dict[date, int], a: Optional[date], b: Optional[date]
              ) -> Optional[int]:
    """wd(b) − wd(a) on ``tbl`` with nearest_workday_index semantics; None when
    either date is missing or off-table."""
    if a is None or b is None:
        return None
    try:
        return nearest_workday_index(tbl, b) - nearest_workday_index(tbl, a)
    except KeyError:
        return None


# ---------------------------------------------------------------------------
# per-activity day-state statics (built once; mutated per day)
# ---------------------------------------------------------------------------
@dataclass
class _ActStatics:
    base: Any                       # bridged CpmActivity (later file)
    code: str
    as_d: Optional[date]            # later's actual start (status-gated)
    af_d: Optional[date]            # later's actual finish (status-gated)
    rd0: int                        # RD implied at the earlier data date
    rd1: int                        # RD at the later data date
    od_ns: int                      # duration used while not yet started
    is_milestone: bool
    tbl: dict[date, int]            # the activity's own workday table
    idx0: int                       # fwd index of d0 on tbl
    span_w: int                     # fwd index of dN − idx0 (W)

    def rd_at(self, d: date) -> int:
        if self.is_milestone:
            return 0
        if self.span_w <= 0:
            return max(0, self.rd1)
        w = _fwd_index(self.tbl, d) - self.idx0
        r = self.rd0 + (self.rd1 - self.rd0) * (w / self.span_w)
        return max(0, _round_half_up(r))


def _build_statics(earlier: Schedule, later: Schedule, ei: EngineInputs,
                   d0: date, dn: date, disclosures: list[str]
                   ) -> list[_ActStatics]:
    later_by_uid = {a.uid: a for a in later.real_activities}
    earlier_by_code: dict[str, IngestActivity] = {}
    for a in sorted(earlier.real_activities, key=lambda x: x.uid):
        earlier_by_code.setdefault(a.code, a)

    statics: list[_ActStatics] = []
    n_ns_earlier = n_ns_later_od = n_missing_earlier = 0
    for base in ei.activities:
        ing = later_by_uid[base.act_id]
        hpd_l = _hpd(later, ing)
        # status-gated actuals from the LATER file (spec item 3)
        as_d = af_d = None
        if ing.completed:
            as_d = _as_date(ing.actual_start)
            af_d = _as_date(ing.actual_finish) or as_d
            as_d = as_d or af_d
        elif ing.in_progress:
            as_d = _as_date(ing.actual_start)
        # RD at the later data date
        if ing.completed:
            rd1 = 0
        elif ing.in_progress:
            rd1 = _floor_wd(ing.remaining_duration_hours, hpd_l)
        else:
            rd1 = int(base.original_duration or 0)
        # RD implied at the earlier data date (matched by code)
        e = earlier_by_code.get(ing.code)
        if e is None:
            rd0 = int(base.original_duration or 0)
            n_missing_earlier += 1
        elif e.completed:
            rd0 = 0
        else:
            rd0 = _floor_wd(e.remaining_duration_hours, _hpd(earlier, e))
        # duration while not yet started: earlier's RD when available (disclosed)
        if ing.is_milestone:
            od_ns = 0
        elif e is not None and not e.completed:
            od_ns = _floor_wd(e.remaining_duration_hours, _hpd(earlier, e))
            n_ns_earlier += 1
        else:
            od_ns = int(base.original_duration or 0)
            n_ns_later_od += 1
        tbl = None
        if ing.calendar_uid:
            tbl = ei.calendar_registry.get_workday_table(ing.calendar_uid)
        if tbl is None:
            tbl = ei.workday_table
        idx0 = _fwd_index(tbl, d0)
        span_w = _fwd_index(tbl, dn) - idx0
        statics.append(_ActStatics(
            base=base, code=ing.code, as_d=as_d, af_d=af_d, rd0=rd0, rd1=rd1,
            od_ns=od_ns, is_milestone=ing.is_milestone, tbl=tbl,
            idx0=idx0, span_w=span_w))
    disclosures.append(
        "not-yet-started activities are scheduled at the EARLIER file's "
        f"remaining duration when the code exists there ({n_ns_earlier} "
        f"activity(ies)), else at the later file's original duration "
        f"({n_ns_later_od}) — documented choice.")
    if n_missing_earlier:
        disclosures.append(
            f"{n_missing_earlier} later-file activity(ies) have no code match "
            "in the earlier file; their day-0 remaining duration falls back to "
            "the later file's original duration.")
    return statics


def _day_activities(statics: list[_ActStatics], d: date) -> list:
    """The interpolated day-d state: shallow copies of the bridged activities
    with pins/RD/OD mutated per the spec's three branches."""
    out = []
    for st in statics:
        a = copy.copy(st.base)
        if st.af_d is not None and st.af_d <= d:
            a.pinned_early_start = st.as_d or st.af_d
            a.pinned_early_finish = st.af_d
            a.remaining_duration = None
        elif st.as_d is not None and st.as_d <= d:
            a.pinned_early_start = st.as_d
            a.pinned_early_finish = None
            a.remaining_duration = st.rd_at(d)
        else:
            a.pinned_early_start = None
            a.pinned_early_finish = None
            a.remaining_duration = None
            a.original_duration = st.od_ns
        out.append(a)
    return out


# ---------------------------------------------------------------------------
# engine helpers
# ---------------------------------------------------------------------------
def _run_day(ei: EngineInputs, activities: list, project_start: date
             ) -> tuple[Optional[AnalysisResult], str]:
    try:
        res = run_analysis(
            activities=activities,
            relationships=ei.relationships,
            project_start=project_start,
            workday_table=ei.workday_table,
            calendar=ei.calendar,
            convention=ei.convention,
            calendar_registry=ei.calendar_registry,
            lag_strategy=ei.lag_strategy,
            constraints=ei.constraints or None,
            statusing_mode=ei.statusing_mode,
        )
    except Exception as exc:
        return None, f"engine error: {exc}"
    if not res.is_valid:
        issues = [f"{i.issue_code}: {i.message}"
                  for i in res.validation.issues if i.blocking]
        return None, "; ".join(issues) or "network invalid (no blocking detail)"
    return res, ""


def _binding_chainhead(ei: EngineInputs, res: AnalysisResult, target_uid: str,
                       preds: list, cal_by_uid: dict[str, Optional[str]]
                       ) -> Optional[str]:
    """One-step binding backward walk from the target: the predecessor whose
    relationship-driven date lands on the target's early date (ties: latest
    driven date, then greatest predecessor id) — impact.py's controlling-path
    convention restricted to the first step (module docstring item 6)."""
    sa = res.scheduled.get(target_uid)
    if sa is None:
        return None
    best = None
    for r in preds:
        pred = res.scheduled.get(r.pred_id)
        if pred is None:
            continue
        cid = cal_by_uid.get(r.pred_id)
        cal = (ei.calendar_registry.get(cid) if cid else None) or ei.calendar
        tbl = (ei.calendar_registry.get_workday_table(cid) if cid else None) \
            or ei.workday_table
        try:
            ctype, cdate = compute_relationship_constraint(
                r.rel_type, pred.early_start, pred.early_finish, r.lag,
                tbl, cal, ei.convention)
        except Exception:  # pragma: no cover - defensive
            continue
        succ_date = sa.early_start if ctype == "ES" else sa.early_finish
        key = (cdate == succ_date, cdate, r.pred_id)
        if best is None or key > best:
            best = key
    return best[2] if best else None


# ---------------------------------------------------------------------------
# annotation helpers
# ---------------------------------------------------------------------------
def _events_for_day(events: Any, d: date) -> list[str]:
    """Event ids (D6 EventMapResult / EventMapping list) whose window covers d."""
    if events is None:
        return []
    evs = getattr(events, "events", events)
    out = []
    for ev in evs:
        s = _as_date(getattr(ev, "start", None))
        f = _as_date(getattr(ev, "finish", None))
        if s is None and f is None:
            continue
        s = s or f
        f = f or s
        if s <= d <= f:
            out.append(getattr(ev, "event_id", "") or "")
    return sorted(out)


def _norm_responsibility(later: Schedule, responsibility: Any,
                         disclosures: list[str]) -> Optional[dict[str, str]]:
    """Normalize the D7 overlay to a code -> party map.  Accepts a
    ResponsibilityResult (uses ``tags_by_code``), a plain dict (code -> party),
    or an iterable of ResponsibilityRule (applied to the later schedule)."""
    if responsibility is None:
        return None
    tags = getattr(responsibility, "tags_by_code", None)
    if tags is not None:
        return dict(tags)
    if isinstance(responsibility, dict):
        return dict(responsibility)
    try:
        from ..intake.responsibility import tag_schedule
        by_uid = tag_schedule(later, list(responsibility))
        return {later.activities[u].code: p for u, p in by_uid.items()
                if u in later.activities}
    except Exception:
        disclosures.append(
            "responsibility overlay was not a recognized structure "
            "(ResponsibilityResult, code->party dict, or rule list); ignored.")
        return None


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def run_daily_ledger(earlier: Schedule, later: Schedule, *,
                     target: Optional[str] = None,
                     handshake: str = "require",
                     threshold_pct: float = 99.0,
                     events: Any = None,
                     responsibility: Any = None) -> DailyLedger:
    """Build the daily-resolution delay ledger for the update pair
    (``earlier`` -> ``later``).  See the module docstring for every method
    choice.  ``handshake="require"`` gates BOTH files on the ADR-0007
    validation handshake and re-raises :class:`HandshakeRefusal`;
    ``handshake="skip"`` bypasses the gate with a disclosure."""
    out = DailyLedger()
    out.earlier_label = earlier.label()
    out.later_label = later.label()
    out.disclosures.append(
        "framing: every daily state is rescheduled on the LATER file's network "
        "(logic, durations, constraints, calendars, SCHEDOPTIONS) — the ledger "
        "measures delay against the current-network view; the earlier-network "
        "framing is the D9 half-step and the N4 sweep varies it.")

    # -- handshake gate (ADR-0007), BOTH files ---------------------------------
    if handshake == "require":
        out.handshake_earlier = _hs_summary(
            require_valid_handshake(earlier, threshold_pct=threshold_pct))  # may raise
        out.handshake_later = _hs_summary(
            require_valid_handshake(later, threshold_pct=threshold_pct))    # may raise
    elif handshake == "skip":
        out.disclosures.append(
            "handshake='skip': the ADR-0007 validation gate was BYPASSED for "
            "both files (analyst/test escape hatch). Engine deltas are "
            "unvalidated against the record.")
        for name, s in (("handshake_earlier", earlier), ("handshake_later", later)):
            try:
                setattr(out, name, _hs_summary(
                    run_handshake(s, threshold_pct=threshold_pct)))
            except Exception as exc:  # pragma: no cover - defensive
                setattr(out, name, {"error": f"handshake summary unavailable: {exc}"})
    else:
        raise ValueError(f"handshake must be 'require' or 'skip', got {handshake!r}")

    # -- data-date window ------------------------------------------------------
    d0, dn = _as_date(earlier.data_date), _as_date(later.data_date)
    if d0 is None or dn is None:
        out.computable = False
        out.blocking = "both schedules need a data date for the daily window"
        out.disclosures.append(out.blocking)
        return out
    if d0 > dn:
        out.computable = False
        out.blocking = (f"earlier data date {d0.isoformat()} is after later "
                        f"data date {dn.isoformat()}; pair refused")
        out.disclosures.append(out.blocking)
        return out
    days, capped = capped_day_range(d0, dn)
    if capped:
        out.disclosures.append(
            f"window is {(dn - d0).days} calendar days; capped at {_DAY_CAP} "
            f"days after {d0.isoformat()} ({days[-1].isoformat()}) — the "
            "arithmetic identity covers the truncated span only.")
    out.window = {
        "start": d0.isoformat(), "end": dn.isoformat(),
        "end_effective": days[-1].isoformat(),
        "calendar_days_total": (dn - d0).days,
        "calendar_days_computed": len(days) - 1,
        "capped": capped, "day_cap": _DAY_CAP,
    }

    # -- target resolution (as impact.py; on the LATER file) -------------------
    tgt, how = _resolve_target(later, target)
    if tgt is None and target is not None:
        out.disclosures.append(
            f"{how}; falling back to the default target (project finish).")
        tgt, how = _resolve_target(later, None)
    out.resolved_how = how
    if tgt is None:
        out.computable = False
        out.blocking = f"target could not be resolved: {how}"
        out.disclosures.append(out.blocking)
        return out
    out.target_uid, out.target_code, out.target_name = tgt.uid, tgt.code, tgt.name
    tcal = later.cal_for(tgt)
    out.target_calendar = (tcal.name or tcal.uid) if tcal else (tgt.calendar_uid or "")
    # locate in the earlier file by code (for reconciliation)
    e_tgt = None
    for a in sorted(earlier.real_activities, key=lambda x: x.uid):
        if a.uid == tgt.uid or a.code == tgt.code:
            e_tgt = a
            break
    if e_tgt is not None:
        out.earlier_target_uid = e_tgt.uid
        out.earlier_target_how = "located in earlier file by code"
    else:
        out.earlier_target_how = "NOT found in earlier file (by uid or code)"
        out.disclosures.append(
            f"target {tgt.code} has no match in the earlier file; the "
            "reconciliation block cannot compare against the earlier "
            "as-imported run.")

    # -- engine inputs (built ONCE from the later file; tables extended) -------
    ei = build_engine_inputs(later)
    out.disclosures.extend(ei.disclosures)
    lo_needed = d0 - timedelta(days=60)
    if lo_needed < min(ei.workday_table):
        hi = max(ei.workday_table)
        ei.workday_table = build_workday_table(ei.calendar, lo_needed, hi)
        ei.calendar_registry.ensure_workday_tables(lo_needed, hi)
    tgt_tbl = None
    if tgt.calendar_uid:
        tgt_tbl = ei.calendar_registry.get_workday_table(tgt.calendar_uid)
    if tgt_tbl is None:
        tgt_tbl = ei.workday_table

    statics = _build_statics(earlier, later, ei, d0, days[-1], out.disclosures)
    cal_by_uid = {a.act_id: a.calendar_id for a in ei.activities}
    preds = [r for r in ei.relationships if r.succ_id == tgt.uid]
    started_on: dict[date, list[str]] = {}
    completed_on: dict[date, list[str]] = {}
    for st in statics:
        if st.as_d is not None:
            started_on.setdefault(st.as_d, []).append(st.code)
        if st.af_d is not None:
            completed_on.setdefault(st.af_d, []).append(st.code)

    resp_map = _norm_responsibility(later, responsibility, out.disclosures)

    # -- the daily runs ---------------------------------------------------------
    efs: list[Optional[date]] = []
    controlling: list[str] = []
    for d in days:
        res, blk = _run_day(ei, _day_activities(statics, d), d)
        if res is None:
            out.computable = False
            out.blocking = f"day {d.isoformat()}: {blk}"
            out.rows = []
            out.arithmetic_check = {"exact": None, "reason": out.blocking}
            out.reconciliation = {"reason": out.blocking}
            return out
        sa = res.scheduled.get(tgt.uid)
        efs.append(sa.early_finish if sa else None)
        head = _binding_chainhead(ei, res, tgt.uid, preds, cal_by_uid)
        controlling.append(ei.code_by_uid.get(head, head) if head else tgt.code)
    if any(ef is None for ef in efs):
        out.computable = False
        out.blocking = "target was not scheduled on at least one day state"
        return out

    # -- rows -------------------------------------------------------------------
    cum = 0
    for i in range(1, len(days)):
        d = days[i]
        delta = nearest_workday_index(tgt_tbl, efs[i]) \
            - nearest_workday_index(tgt_tbl, efs[i - 1])
        cum += delta
        party = None
        if resp_map is not None:
            party = resp_map.get(controlling[i]) or "Untagged"
        out.rows.append(DayRow(
            day=d, ef_target=efs[i], delta_workdays=delta,
            cumulative_workdays=cum,
            controlling_code=controlling[i], controlling_party=party,
            newly_started=sorted(started_on.get(d, [])),
            newly_completed=sorted(completed_on.get(d, [])),
            event_ids=_events_for_day(events, d)))

    # -- arithmetic check (spec §8.3: exact by telescoping; asserted) -----------
    sum_deltas = sum(r.delta_workdays for r in out.rows)
    endpoint = nearest_workday_index(tgt_tbl, efs[-1]) \
        - nearest_workday_index(tgt_tbl, efs[0])
    assert sum_deltas == endpoint, (
        f"daily-ledger arithmetic check failed: Σ deltas {sum_deltas} != "
        f"endpoint movement {endpoint}")
    out.arithmetic_check = {
        "sum_of_daily_deltas_wd": sum_deltas,
        "endpoint_delta_wd": endpoint,
        "exact": sum_deltas == endpoint,
        "ef_target_day0": efs[0].isoformat(),
        "ef_target_last": efs[-1].isoformat(),
        "note": ("Σ daily deltas equals wd(EF_target(d_last)) − "
                 "wd(EF_target(d0)) exactly (telescoping identity; asserted "
                 "in code; workdays of the target's calendar)."),
    }

    # -- reconciliation vs the as-imported runs and the record ------------------
    out.reconciliation = _reconciliation(
        earlier, ei, tgt, e_tgt, tgt_tbl, efs[0], efs[-1], out.disclosures)

    # -- responsibility subtotals (observational) -------------------------------
    if resp_map is not None:
        by_party: dict[str, dict[str, int]] = {}
        for r in out.rows:
            b = by_party.setdefault(r.controlling_party or "Untagged",
                                    {"delta_workdays": 0, "days": 0})
            b["delta_workdays"] += r.delta_workdays
            b["days"] += 1
        out.responsibility_subtotals = {
            "note": ("OBSERVATIONAL allocation only: each day's delta is "
                     "attributed to the responsibility tag of that day's "
                     "controlling activity. This is a screen, not an "
                     "apportionment — concurrency and causation are reserved "
                     "to the expert."),
            "by_party": {k: dict(v) for k, v in sorted(by_party.items())},
        }
    else:
        out.responsibility_subtotals = {"reason": "no responsibility overlay provided"}
    return out


def _reconciliation(earlier: Schedule, ei: EngineInputs, tgt: IngestActivity,
                    e_tgt: Optional[IngestActivity], tgt_tbl: dict[date, int],
                    interp_d0_ef: date, interp_dn_ef: date,
                    disclosures: list[str]) -> dict[str, Any]:
    """Interpolated endpoints vs the two AS-IMPORTED engine runs and the record
    dates.  The endpoints will not exactly match the as-imported runs whenever
    the later file's actuals/RDs disagree with linear interpolation (or the
    not-started duration choice differs) — disclosed, not hidden."""
    block: dict[str, Any] = {
        "interpolated_day0_ef": interp_d0_ef.isoformat(),
        "interpolated_last_ef": interp_dn_ef.isoformat(),
        "note": ("interpolation endpoints are interpolated-state runs on the "
                 "later network; they will not exactly equal the as-imported "
                 "runs when the later file's actuals/RDs disagree with linear "
                 "interpolation or when the not-started duration choice "
                 "differs — disclosed, not hidden."),
    }
    # later file, as imported (later's own pins/RDs at its data date)
    res, blk = _run_day(ei, ei.activities, ei.project_start)
    ef_later = None
    if res is not None:
        sa = res.scheduled.get(tgt.uid)
        ef_later = sa.early_finish if sa else None
    block["later_as_imported_ef"] = ef_later.isoformat() if ef_later else None
    block["later_as_imported_vs_interp_wd"] = _wd_delta(tgt_tbl, ef_later, interp_dn_ef)
    if res is None:
        block["later_as_imported_blocking"] = blk
    # earlier file, as imported
    ef_earlier = None
    if e_tgt is not None:
        try:
            eie = build_engine_inputs(earlier)
            res_e, blk_e = _run_day(eie, eie.activities, eie.project_start)
            if res_e is not None:
                sa = res_e.scheduled.get(e_tgt.uid)
                ef_earlier = sa.early_finish if sa else None
            else:
                block["earlier_as_imported_blocking"] = blk_e
        except Exception as exc:
            block["earlier_as_imported_blocking"] = f"engine inputs failed: {exc}"
    else:
        block["earlier_as_imported_blocking"] = "target not located in earlier file"
    block["earlier_as_imported_ef"] = ef_earlier.isoformat() if ef_earlier else None
    block["earlier_as_imported_vs_interp_wd"] = _wd_delta(tgt_tbl, ef_earlier, interp_d0_ef)
    # record dates (the schedule of record; presentation rule)
    rec_e = _record_finish(e_tgt) if e_tgt is not None else None
    rec_l = _record_finish(tgt)
    block["earlier_record_ef"] = rec_e.isoformat() if rec_e else None
    block["later_record_ef"] = rec_l.isoformat() if rec_l else None
    block["record_movement_wd"] = _wd_delta(tgt_tbl, _as_date(rec_e), _as_date(rec_l))
    if rec_e is None or rec_l is None:
        disclosures.append(
            "record finish dates missing on one or both files; the record-"
            "movement reconciliation figure is unavailable.")
    return block
