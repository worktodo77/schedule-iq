"""Issue-impact overlay, OOS statusing delta, and constraint-free criticality
(backlog A2 / A4 / P5) — the engine-side impact analytics on top of the ported
CPM engine (ADR-0007).

Forensic purpose
----------------
For a selected target (a completion milestone or any activity), this module
answers "what is doing this to my date, and by how much?".  It re-schedules the
file's network under a series of counterfactuals — each an INDEPENDENT engine
run compared to the as-imported baseline — and reports the movement of the
target as a **diagnostic delta**, never as a competing schedule (ADR-0007 §4,
presentation rule).  The tool-of-record dates remain the schedule; every engine
number here is a labelled delta, and the baseline record dates are carried
alongside the engine dates so the two are never confused.

Scenarios (each yields an :class:`ImpactDelta`; sign convention: **negative
delta = the target improves / moves earlier**):

* ``constraints_released_all`` — drop every date constraint; also the
  per-constrained-activity "float absorbed" = TF(unconstrained) − TF(constrained).
* ``constraint_released:<code>/<type>`` — drop one constraint at a time (the
  waterfall attribution table; capped, driving-path-nearest first).
* ``leads_zeroed`` — set every negative lag (lead) to zero; plus Σ lead-hours on
  the controlling path.
* ``lags_visibility`` — NO engine rerun: Σ positive lag hours on the controlling
  path and as a share of path working duration ("invisible scope").
* ``oos_statusing_delta`` (A4) — re-run under Progress Override; the retained-vs-
  override target delta, plus the count of relationships the override drops.
* ``expected_finish_released`` — drop only EXPECTED_FINISH (XF) constraints.
* ``calendar_neutral_restatement`` — NO engine rerun: restate each controlling-
  path activity's total float in hours vs day-float on its own calendar hours/day
  vs the project-default hours/day (§1.2 row 2 / CAL-05 concept), flagging where
  hour-float and day-float diverge at the target.
* ``open_ends`` — graph reachability: real incomplete activities with no forward
  path to the target (their slippage is invisible to the target).

P5 (``constraint_free_criticality``): the baseline vs constraints-released
per-activity criticality flip table — "manufactured-critical" (critical only WITH
constraints) vs "masked-critical" (critical only WITHOUT), with the target's own
float change.  Criticality here is **total float ≤ 0** (the float-based
criticality of proposal §2.5, "recompute float with constraints released"); the
engine's longest-path ``is_critical`` is degenerate under heavy constraint
distortion (a mandatory-finish can pull a mid-network node's early finish past
the target), so total-float criticality is the defensible signal for this
feature and is stated as such.

Every delta is expressed in WORKDAYS of the target's own calendar (with a
calendar-day figure carried for readability).  A scenario whose engine run fails
network validation is recorded as "not computable — <blocking issue>"; the module
degrades per-scenario and never raises out of a scenario.  Half-step attribution
(§1.2 row 6) is deferred to backlog D9 (a placeholder note is emitted, not
implemented).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from ..ingest.model import Activity, Schedule
from ..cpm.bridge import EngineInputs, build_engine_inputs
from ..cpm.constraints import SchedulingConstraint, StatusingMode
from ..cpm.engine import _is_in_progress, run_analysis
from ..cpm.handshake import (HandshakeResult, require_valid_handshake,
                             run_handshake)
from ..cpm.relationship_logic import compute_relationship_constraint
from ..cpm.results import AnalysisResult

# Cap on the number of per-constraint attribution reruns (spec A2 item 2).
_CONSTRAINT_ATTRIBUTION_CAP = 20
# Cap on the listed open-end activities (count is always exact).
_OPEN_ENDS_CAP = 50


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ImpactDelta:
    """One scenario's diagnostic effect on the target.

    ``delta_workdays`` is the target's movement in WORKDAYS of the target's own
    calendar (negative = earlier / improves).  ``delta_calendar_days`` carries
    the same movement in raw calendar days for readability.  A scenario with no
    engine rerun (``lags_visibility``, ``calendar_neutral_restatement``) leaves
    the deltas ``None`` and carries its numbers in ``details``.  A scenario whose
    engine run was invalid sets ``computable=False`` and ``blocking``.
    """
    scenario: str
    target_finish_engine: Optional[date] = None
    delta_workdays: Optional[int] = None
    delta_calendar_days: Optional[int] = None
    computable: bool = True
    blocking: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    sign_convention: str = "negative delta = target moves earlier (improves)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "target_finish_engine": (self.target_finish_engine.isoformat()
                                     if self.target_finish_engine else None),
            "delta_workdays": self.delta_workdays,
            "delta_calendar_days": self.delta_calendar_days,
            "computable": self.computable,
            "blocking": self.blocking,
            "sign_convention": self.sign_convention,
            "details": self.details,
        }


@dataclass
class ImpactAnalysis:
    """The full issue-impact overlay for one target on one schedule."""
    target_uid: Optional[str] = None
    target_code: Optional[str] = None
    target_name: Optional[str] = None
    resolved_how: str = ""
    target_calendar: str = ""

    # presentation rule: engine dates are diagnostic; record dates are the schedule
    baseline_engine_es: Optional[date] = None
    baseline_engine_ef: Optional[date] = None
    baseline_engine_tf_workdays: Optional[int] = None
    baseline_record_es: Optional[datetime] = None
    baseline_record_ef: Optional[datetime] = None
    baseline_computable: bool = True

    handshake: Optional[dict[str, Any]] = None

    deltas: list[ImpactDelta] = field(default_factory=list)             # waterfall
    constraint_attribution: list[ImpactDelta] = field(default_factory=list)
    constraint_free_criticality: dict[str, Any] = field(default_factory=dict)
    calendar_restatement: dict[str, Any] = field(default_factory=dict)
    open_ends: dict[str, Any] = field(default_factory=dict)
    disclosures: list[str] = field(default_factory=list)

    def delta(self, scenario: str) -> Optional[ImpactDelta]:
        for d in self.deltas:
            if d.scenario == scenario:
                return d
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": {
                "uid": self.target_uid,
                "code": self.target_code,
                "name": self.target_name,
                "calendar": self.target_calendar,
                "resolved_how": self.resolved_how,
            },
            "presentation_rule": (
                "Tool-of-record dates are the schedule; every engine figure below "
                "is a diagnostic delta only (ADR-0007 §4)."
            ),
            "baseline": {
                "engine_early_start": (self.baseline_engine_es.isoformat()
                                       if self.baseline_engine_es else None),
                "engine_early_finish": (self.baseline_engine_ef.isoformat()
                                        if self.baseline_engine_ef else None),
                "engine_total_float_workdays": self.baseline_engine_tf_workdays,
                "record_early_start": (self.baseline_record_es.isoformat()
                                       if self.baseline_record_es else None),
                "record_early_finish": (self.baseline_record_ef.isoformat()
                                        if self.baseline_record_ef else None),
                "computable": self.baseline_computable,
            },
            "handshake": self.handshake,
            "waterfall": [d.to_dict() for d in self.deltas],
            "constraint_attribution": [d.to_dict() for d in self.constraint_attribution],
            "constraint_free_criticality": self.constraint_free_criticality,
            "calendar_restatement": self.calendar_restatement,
            "open_ends": self.open_ends,
            "disclosures": list(self.disclosures),
            "deferred": [
                "Half-step progress-vs-revision attribution (§1.2 row 6) is "
                "deferred to backlog D9 — not implemented here."
            ],
        }


# ---------------------------------------------------------------------------
# target resolution
# ---------------------------------------------------------------------------
def _record_finish(a: Activity) -> Optional[datetime]:
    return a.actual_finish or a.early_finish or a.planned_finish


def _resolve_target(sched: Schedule, target: Optional[str]) -> tuple[Optional[Activity], str]:
    """Resolve the target activity and describe how (spec precedence).

    Explicit ``target`` matches an activity uid, else a code.  Default: the
    latest-finishing real FINISH MILESTONE (tie -> least tool-of-record float,
    then code); failing that, the latest-finishing real activity by early/planned
    finish.
    """
    if target is not None:
        if target in sched.activities:
            return sched.activities[target], f"explicit target by uid ({target})"
        for a in sched.activities.values():
            if a.code == target:
                return a, f"explicit target by code ({target})"
        return None, f"explicit target {target!r} not found"

    reals = sched.real_activities
    mrs = [a for a in reals
           if a.atype.name == "FINISH_MILESTONE" and _record_finish(a) is not None]
    pool, how = mrs, "default: latest-finishing finish milestone"
    if not pool:
        pool = [a for a in reals if _record_finish(a) is not None]
        how = "default: latest-finishing activity (no finish milestone present)"
    if not pool:
        return None, "no target resolvable (no finish dates)"
    latest = max(_record_finish(a) for a in pool)

    def _tf(a: Activity) -> float:
        cal = sched.cal_for(a)
        d = a.total_float_days(cal)
        return d if d is not None else 1e9

    at_end = [a for a in pool if _record_finish(a) == latest]
    at_end.sort(key=lambda a: (_tf(a), a.code))
    return at_end[0], how


# ---------------------------------------------------------------------------
# engine helpers
# ---------------------------------------------------------------------------
def _run(ei: EngineInputs, constraints, statusing_mode, relationships=None
         ) -> tuple[Optional[AnalysisResult], str]:
    """Run one engine scenario; return (result|None, blocking).  Never raises for
    an invalid network — records the blocking issues instead (per-scenario
    degradation)."""
    try:
        res = run_analysis(
            activities=ei.activities,
            relationships=relationships if relationships is not None else ei.relationships,
            project_start=ei.project_start,
            workday_table=ei.workday_table,
            calendar=ei.calendar,
            convention=ei.convention,
            calendar_registry=ei.calendar_registry,
            lag_strategy=ei.lag_strategy,
            constraints=constraints or None,
            statusing_mode=statusing_mode,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"engine error: {exc}"
    if not res.is_valid:
        issues = [f"{i.issue_code}: {i.message}"
                  for i in res.validation.issues if i.blocking]
        return None, "; ".join(issues) or "network invalid (no blocking detail)"
    return res, ""


def _finish_of(res: Optional[AnalysisResult], uid: str) -> Optional[date]:
    if res is None:
        return None
    sa = res.scheduled.get(uid)
    return sa.early_finish if sa else None


def _target_wd_table(ei: EngineInputs, target: Activity) -> dict[date, int]:
    tbl = None
    if target.calendar_uid:
        tbl = ei.calendar_registry.get_workday_table(target.calendar_uid)
    return tbl if tbl is not None else ei.workday_table


def _delta(tbl: dict[date, int], base_ef: Optional[date], scen_ef: Optional[date]
           ) -> tuple[Optional[int], Optional[int]]:
    """(workday delta on the target calendar, calendar-day delta)."""
    if base_ef is None or scen_ef is None:
        return None, None
    cal_days = (scen_ef - base_ef).days
    b, s = tbl.get(base_ef), tbl.get(scen_ef)
    if b is None or s is None:
        return None, cal_days
    return s - b, cal_days


# ---------------------------------------------------------------------------
# controlling path to the target (engine early dates)
# ---------------------------------------------------------------------------
def _controlling_path(ei: EngineInputs, res: AnalysisResult, target_uid: str
                      ) -> list[str]:
    """Backward walk from the target through the BINDING predecessor at each node
    (the one whose relationship-driven early date lands on the successor's early
    start/finish), using the baseline engine dates.  This recovers the true
    controlling path to the target even when constraint distortion has broken the
    engine's global longest path (proposal §1.1, restricted to the binding link).

    Returns activity uids ordered start -> target.
    """
    cpm_by_succ: dict[str, list] = {}
    for r in ei.relationships:
        cpm_by_succ.setdefault(r.succ_id, []).append(r)

    order: list[str] = [target_uid]
    seen = {target_uid}
    cur = target_uid
    guard = 0
    while guard < len(ei.activities) + 2:
        guard += 1
        sa = res.scheduled.get(cur)
        if sa is None:
            break
        best = None  # (is_bound, driven_date, pred_id)
        for r in cpm_by_succ.get(cur, []):
            pred = res.scheduled.get(r.pred_id)
            if pred is None or r.pred_id in seen:
                continue
            cal = (ei.calendar_registry.get(
                _cal_uid_of(ei, r.pred_id)) or ei.calendar)
            tbl = (ei.calendar_registry.get_workday_table(
                _cal_uid_of(ei, r.pred_id)) or ei.workday_table)
            try:
                ctype, cdate = compute_relationship_constraint(
                    r.rel_type, pred.early_start, pred.early_finish, r.lag,
                    tbl, cal, ei.convention)
            except Exception:  # pragma: no cover - defensive
                continue
            succ_date = sa.early_start if ctype == "ES" else sa.early_finish
            bound = (cdate == succ_date)
            key = (bound, cdate, r.pred_id)
            if best is None or key > best:
                best = key
        if best is None:
            break
        pred_id = best[2]
        order.append(pred_id)
        seen.add(pred_id)
        cur = pred_id
    order.reverse()
    return order


def _cal_uid_of(ei: EngineInputs, uid: str) -> Optional[str]:
    for a in ei.activities:
        if a.act_id == uid:
            return a.calendar_id
    return None


# ---------------------------------------------------------------------------
# open ends: reachability to the target
# ---------------------------------------------------------------------------
def _reaches_target(sched: Schedule, target_uid: str) -> set[str]:
    """Set of activity uids with a forward path to the target (target included)."""
    succ: dict[str, list[str]] = {}
    for r in sched.relationships:
        succ.setdefault(r.pred_uid, []).append(r.succ_uid)
    reach = {target_uid}
    # reverse-reachability: BFS on predecessors of the target
    preds: dict[str, list[str]] = {}
    for r in sched.relationships:
        preds.setdefault(r.succ_uid, []).append(r.pred_uid)
    stack = [target_uid]
    while stack:
        cur = stack.pop()
        for p in preds.get(cur, []):
            if p not in reach:
                reach.add(p)
                stack.append(p)
    return reach


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def run_impact_analysis(sched: Schedule, target: Optional[str] = None, *,
                        handshake: str = "require",
                        threshold_pct: float = 99.0) -> ImpactAnalysis:
    """Run the issue-impact overlay (A2), the OOS statusing delta (A4), and
    constraint-free criticality (P5) for ``target`` on ``sched``.

    ``handshake="require"`` gates on the ADR-0007 validation handshake and
    re-raises :class:`HandshakeRefusal` when the file does not handshake (callers
    / the runner handle it).  ``handshake="skip"`` is the documented test/analyst
    escape hatch: the gate is bypassed, recorded in ``disclosures``, and any
    scenario whose engine run is invalid degrades to "not computable".
    """
    out = ImpactAnalysis()

    # -- target resolution (uses tool-of-record dates; engine-independent) ----
    tgt, how = _resolve_target(sched, target)
    out.resolved_how = how
    if tgt is None:
        out.disclosures.append(f"target could not be resolved: {how}")
        return out
    out.target_uid, out.target_code, out.target_name = tgt.uid, tgt.code, tgt.name
    cal = sched.cal_for(tgt)
    out.target_calendar = (cal.name or cal.uid) if cal else (tgt.calendar_uid or "")
    out.baseline_record_es = tgt.early_start
    out.baseline_record_ef = _record_finish(tgt)

    # -- handshake gate (ADR-0007) --------------------------------------------
    if handshake == "require":
        hs = require_valid_handshake(sched, threshold_pct=threshold_pct)  # may raise
        out.handshake = _hs_summary(hs)
    elif handshake == "skip":
        out.disclosures.append(
            "handshake='skip': the ADR-0007 validation gate was BYPASSED (analyst/"
            "test escape hatch). Engine deltas are unvalidated against the record; "
            "invalid-network scenarios degrade to 'not computable'.")
        try:
            out.handshake = _hs_summary(run_handshake(sched, threshold_pct=threshold_pct))
        except Exception as exc:  # pragma: no cover - defensive
            out.handshake = {"error": f"handshake summary unavailable: {exc}"}
    else:
        raise ValueError(f"handshake must be 'require' or 'skip', got {handshake!r}")

    # -- build inputs + baseline run ------------------------------------------
    ei = build_engine_inputs(sched)
    out.disclosures.extend(ei.disclosures)
    wd_tbl = _target_wd_table(ei, tgt)

    base, base_block = _run(ei, ei.constraints, ei.statusing_mode)
    if base is None:
        out.baseline_computable = False
        out.disclosures.append(f"baseline engine run not computable: {base_block}")
        # every scenario is not-computable without a baseline target finish
        for name in ("constraints_released_all", "expected_finish_released",
                     "leads_zeroed", "lags_visibility", "oos_statusing_delta"):
            out.deltas.append(ImpactDelta(scenario=name, computable=False,
                                          blocking=f"baseline invalid: {base_block}"))
        out.open_ends = _open_ends_block(sched, tgt.uid)
        out.calendar_restatement = {"reason": "baseline engine run not computable"}
        out.constraint_free_criticality = {"reason": "baseline engine run not computable"}
        return out

    base_ef = _finish_of(base, tgt.uid)
    base_sa = base.scheduled.get(tgt.uid)
    out.baseline_engine_es = base_sa.early_start if base_sa else None
    out.baseline_engine_ef = base_ef
    out.baseline_engine_tf_workdays = base_sa.total_float if base_sa else None

    # controlling path to the target (for leads/lags/calendar scenarios)
    path = _controlling_path(ei, base, tgt.uid)

    # -- scenario 1: constraints_released_all + float absorbed ----------------
    all_off, blk = _run(ei, None, ei.statusing_mode)
    d1 = ImpactDelta(scenario="constraints_released_all")
    if all_off is None:
        d1.computable, d1.blocking = False, blk
    else:
        ef = _finish_of(all_off, tgt.uid)
        d1.target_finish_engine = ef
        d1.delta_workdays, d1.delta_calendar_days = _delta(wd_tbl, base_ef, ef)
        d1.details["float_absorbed_workdays"] = _float_absorbed(ei, base, all_off)
        d1.details["note"] = ("all date constraints dropped; float absorbed = "
                              "TF(unconstrained) - TF(constrained) per constrained "
                              "activity")
    out.deltas.append(d1)

    # -- scenario: expected_finish_released -----------------------------------
    xf = [c for c in ei.constraints if c.ctype.name == "EXPECTED_FINISH"]
    non_xf = [c for c in ei.constraints if c.ctype.name != "EXPECTED_FINISH"]
    dx = ImpactDelta(scenario="expected_finish_released")
    dx.details["expected_finish_count"] = len(xf)
    if not xf:
        dx.details["note"] = "no EXPECTED_FINISH constraints in the file"
        dx.target_finish_engine = base_ef
        dx.delta_workdays, dx.delta_calendar_days = 0, 0
    else:
        r_xf, blk = _run(ei, non_xf, ei.statusing_mode)
        if r_xf is None:
            dx.computable, dx.blocking = False, blk
        else:
            ef = _finish_of(r_xf, tgt.uid)
            dx.target_finish_engine = ef
            dx.delta_workdays, dx.delta_calendar_days = _delta(wd_tbl, base_ef, ef)
    out.deltas.append(dx)

    # -- scenario: leads_zeroed -----------------------------------------------
    rels0 = [copy.copy(r) for r in ei.relationships]
    lead_hours = 0.0
    for r in rels0:
        if r.lag < 0:
            r.lag = 0
    dl = ImpactDelta(scenario="leads_zeroed")
    lead_hours = _sum_path_lag_hours(sched, path, negative=True)
    dl.details["lead_hours_on_controlling_path"] = lead_hours
    r_l, blk = _run(ei, ei.constraints, ei.statusing_mode, relationships=rels0)
    if r_l is None:
        dl.computable, dl.blocking = False, blk
    else:
        ef = _finish_of(r_l, tgt.uid)
        dl.target_finish_engine = ef
        dl.delta_workdays, dl.delta_calendar_days = _delta(wd_tbl, base_ef, ef)
    out.deltas.append(dl)

    # -- scenario: lags_visibility (no rerun) ---------------------------------
    dlag = ImpactDelta(scenario="lags_visibility",
                       sign_convention="no engine rerun; visibility metric only")
    lag_hours = _sum_path_lag_hours(sched, path, negative=False)
    path_dur_h = _path_working_hours(sched, path)
    dlag.details = {
        "positive_lag_hours_on_controlling_path": lag_hours,
        "path_working_hours": path_dur_h,
        "lag_share_pct_of_path": (round(100.0 * lag_hours / path_dur_h, 2)
                                  if path_dur_h else None),
        "note": ("invisible scope: positive lags on the controlling path are "
                 "durationless time no activity is accountable for"),
    }
    out.deltas.append(dlag)

    # -- scenario: oos_statusing_delta (A4) -----------------------------------
    dropped = _override_dropped_rels(ei)
    d_oos = ImpactDelta(scenario="oos_statusing_delta")
    d_oos.details["baseline_statusing_mode"] = ei.statusing_mode.value
    d_oos.details["override_dropped_relationships"] = len(dropped)
    d_oos.details["dropped_pairs"] = dropped
    if not any(_is_in_progress(a) for a in ei.activities):
        d_oos.target_finish_engine = base_ef
        d_oos.delta_workdays, d_oos.delta_calendar_days = 0, 0
        d_oos.details["note"] = ("no in-progress activities; retained-vs-override "
                                 "delta is 0 by construction")
    else:
        r_ov, blk = _run(ei, ei.constraints, StatusingMode.PROGRESS_OVERRIDE)
        if r_ov is None:
            d_oos.computable, d_oos.blocking = False, blk
        else:
            ef = _finish_of(r_ov, tgt.uid)
            d_oos.target_finish_engine = ef
            d_oos.delta_workdays, d_oos.delta_calendar_days = _delta(wd_tbl, base_ef, ef)
            d_oos.details["note"] = ("retained-logic baseline vs progress-override; "
                                     "the classic OOS dispute number")
    out.deltas.append(d_oos)

    # -- constraint attribution table (per-constraint rerun) ------------------
    out.constraint_attribution = _constraint_attribution(
        ei, tgt.uid, base_ef, wd_tbl, path)

    # -- constraint-free criticality (P5) -------------------------------------
    out.constraint_free_criticality = _criticality_block(
        sched, ei, base, all_off, tgt.uid)

    # -- calendar-neutral restatement -----------------------------------------
    out.calendar_restatement = _calendar_block(sched, path, tgt.uid)

    # -- open ends ------------------------------------------------------------
    out.open_ends = _open_ends_block(sched, tgt.uid)

    return out


# ---------------------------------------------------------------------------
# scenario sub-computations
# ---------------------------------------------------------------------------
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


def _float_absorbed(ei: EngineInputs, base: AnalysisResult,
                    unconstrained: AnalysisResult) -> list[dict[str, Any]]:
    """Per constrained activity: TF(unconstrained) − TF(constrained), in workdays.
    Deterministic (sorted by code)."""
    code = ei.code_by_uid
    rows = []
    seen: set[str] = set()
    for con in ei.constraints:
        uid = con.act_id
        if uid in seen:
            continue
        seen.add(uid)
        b = base.scheduled.get(uid)
        u = unconstrained.scheduled.get(uid)
        if b is None or u is None:
            continue
        rows.append({
            "uid": uid,
            "code": code.get(uid, uid),
            "tf_constrained_workdays": b.total_float,
            "tf_unconstrained_workdays": u.total_float,
            "float_absorbed_workdays": u.total_float - b.total_float,
        })
    rows.sort(key=lambda r: r["code"])
    return rows


def _constraint_attribution(ei: EngineInputs, target_uid: str,
                            base_ef: Optional[date], wd_tbl: dict[date, int],
                            path: list[str]) -> list[ImpactDelta]:
    """Drop each distinct constraint alone (capped, driving-path-nearest first)
    and record the per-constraint target delta — the waterfall attribution."""
    code = ei.code_by_uid
    on_path = set(path)
    # distinct by (act_id, ctype); rank path-nearest (on the controlling path)
    # first, then by code for determinism.
    distinct: list[SchedulingConstraint] = []
    seen: set[tuple[str, str]] = set()
    for c in ei.constraints:
        key = (c.act_id, c.ctype.name)
        if key in seen:
            continue
        seen.add(key)
        distinct.append(c)
    distinct.sort(key=lambda c: (0 if c.act_id in on_path else 1,
                                 code.get(c.act_id, c.act_id), c.ctype.name))
    capped = distinct[:_CONSTRAINT_ATTRIBUTION_CAP]
    out: list[ImpactDelta] = []
    for con in capped:
        others = [c for c in ei.constraints
                  if not (c.act_id == con.act_id and c.ctype is con.ctype
                          and c.cdate == con.cdate)]
        res, blk = _run(ei, others, ei.statusing_mode)
        label = f"constraint_released:{code.get(con.act_id, con.act_id)}/{con.ctype.value}"
        d = ImpactDelta(scenario=label)
        d.details["on_controlling_path"] = con.act_id in on_path
        if res is None:
            d.computable, d.blocking = False, blk
        else:
            ef = _finish_of(res, target_uid)
            d.target_finish_engine = ef
            d.delta_workdays, d.delta_calendar_days = _delta(wd_tbl, base_ef, ef)
        out.append(d)
    if len(distinct) > _CONSTRAINT_ATTRIBUTION_CAP:
        out.append(ImpactDelta(
            scenario="constraint_released:__truncated__",
            computable=False,
            blocking=f"{len(distinct)} distinct constraints; capped at "
                     f"{_CONSTRAINT_ATTRIBUTION_CAP}"))
    return out


def _override_dropped_rels(ei: EngineInputs) -> list[list[str]]:
    """Relationships an OOS progress-override drops: from an in-progress
    predecessor to a not-fully-pinned successor.  Named by code, sorted."""
    by_uid = {a.act_id: a for a in ei.activities}
    inprog = {a.act_id for a in ei.activities if _is_in_progress(a)}
    code = ei.code_by_uid
    out = []
    for r in ei.relationships:
        if r.pred_id not in inprog:
            continue
        succ = by_uid.get(r.succ_id)
        fully_pinned = (succ is not None
                        and succ.pinned_early_start is not None
                        and succ.pinned_early_finish is not None)
        if fully_pinned:
            continue
        out.append([code.get(r.pred_id, r.pred_id), code.get(r.succ_id, r.succ_id)])
    out.sort()
    return out


def _sum_path_lag_hours(sched: Schedule, path: list[str], *, negative: bool) -> float:
    """Sum lag hours (tool-of-record ingest lags) over the relationships that lie
    consecutively on ``path``.  ``negative`` selects leads (lags < 0, returned as
    a magnitude); otherwise positive lags."""
    edges = set(zip(path, path[1:]))
    total = 0.0
    for r in sched.relationships:
        if (r.pred_uid, r.succ_uid) not in edges:
            continue
        if negative and r.lag_hours < 0:
            total += -r.lag_hours
        elif not negative and r.lag_hours > 0:
            total += r.lag_hours
    return total


def _path_working_hours(sched: Schedule, path: list[str]) -> float:
    total = 0.0
    for uid in path:
        a = sched.activities.get(uid)
        if a is not None and not a.is_milestone:
            total += a.original_duration_hours
    return total


def _criticality_block(sched: Schedule, ei: EngineInputs, base: AnalysisResult,
                       unconstrained: Optional[AnalysisResult], target_uid: str
                       ) -> dict[str, Any]:
    """P5: baseline-vs-unconstrained criticality flip table.  Criticality =
    total float <= 0 (float-based, proposal §2.5).  Manufactured-critical =
    critical only WITH constraints; masked-critical = critical only WITHOUT."""
    if unconstrained is None:
        return {"reason": "constraints_released_all run not computable"}
    code = ei.code_by_uid
    incomplete = {a.uid for a in sched.real_activities if not a.completed}

    def crit(res: AnalysisResult, uid: str) -> Optional[bool]:
        sa = res.scheduled.get(uid)
        return (sa.total_float <= 0) if sa else None

    flips = []
    manufactured, masked = [], []
    base_crit = uncon_crit = 0
    for uid in sorted(incomplete, key=lambda u: code.get(u, u)):
        cb, cu = crit(base, uid), crit(unconstrained, uid)
        if cb:
            base_crit += 1
        if cu:
            uncon_crit += 1
        if cb == cu or cb is None or cu is None:
            continue
        row = {"uid": uid, "code": code.get(uid, uid),
               "critical_with_constraints": cb, "critical_without": cu}
        flips.append(row)
        if cb and not cu:
            manufactured.append(code.get(uid, uid))
        elif cu and not cb:
            masked.append(code.get(uid, uid))

    n_inc = max(1, len(incomplete))
    tsa_b = base.scheduled.get(target_uid)
    tsa_u = unconstrained.scheduled.get(target_uid)
    return {
        "criticality_definition": "total_float <= 0 (float-based; proposal §2.5)",
        "incomplete_activities": len(incomplete),
        "pct_critical_with_constraints": round(100.0 * base_crit / n_inc, 1),
        "pct_critical_without": round(100.0 * uncon_crit / n_inc, 1),
        "manufactured_critical": sorted(manufactured),
        "masked_critical": sorted(masked),
        "n_manufactured": len(manufactured),
        "n_masked": len(masked),
        "flip_table": flips,
        "target_total_float_workdays": {
            "with_constraints": tsa_b.total_float if tsa_b else None,
            "without": tsa_u.total_float if tsa_u else None,
        },
    }


def _calendar_block(sched: Schedule, path: list[str], target_uid: str
                    ) -> dict[str, Any]:
    """Calendar-neutral restatement of each controlling-path activity's total
    float: hours vs day-float on its own calendar hours/day vs the project-default
    hours/day (§1.2 row 2 / CAL-05 concept).  Flags where they diverge."""
    # project-default calendar (most-assigned real-activity calendar)
    counts: dict[str, list] = {}
    for a in sched.real_activities:
        c = sched.cal_for(a)
        if c:
            counts.setdefault(c.uid, [c, 0])
            counts[c.uid][1] += 1
    if not counts:
        return {"reason": "no calendars resolved"}
    default_cal = max(counts.values(), key=lambda t: t[1])[0]
    dom_hpd = default_cal.hours_per_day or 8.0

    rows, max_div, target_div = [], 0.0, None
    for uid in path:
        a = sched.activities.get(uid)
        if a is None or a.total_float_hours is None:
            continue
        own_cal = sched.cal_for(a)
        own_hpd = (own_cal.hours_per_day if own_cal and own_cal.hours_per_day else 8.0)
        own_days = a.total_float_hours / own_hpd
        dom_days = a.total_float_hours / dom_hpd
        div = abs(own_days - dom_days)
        max_div = max(max_div, div)
        diverges = div > 0.5
        row = {
            "uid": uid, "code": a.code,
            "own_hours_per_day": own_hpd,
            "total_float_hours": a.total_float_hours,
            "day_float_own_calendar": round(own_days, 2),
            "day_float_default_calendar": round(dom_days, 2),
            "divergence_days": round(div, 2),
            "diverges": diverges,
        }
        if uid == target_uid:
            target_div = round(div, 2)
        if diverges:
            rows.append(row)
    return {
        "default_calendar": default_cal.name or default_cal.uid,
        "default_hours_per_day": dom_hpd,
        "max_divergence_days_on_path": round(max_div, 2),
        "target_divergence_days": target_div,
        "diverging_activities": rows,
        "note": ("float shown in 'days' is not calendar-neutral: an activity on a "
                 "10h/day calendar reports fewer 'days' of float than the same "
                 "hours on the project's 8h/day calendar"),
    }


def _open_ends_block(sched: Schedule, target_uid: str) -> dict[str, Any]:
    """Real incomplete activities with no forward path to the target — their
    slippage is invisible to the target date."""
    reach = _reaches_target(sched, target_uid)
    dangling = []
    for a in sched.real_activities:
        if a.completed or a.uid == target_uid:
            continue
        if a.uid not in reach:
            dangling.append({"uid": a.uid, "code": a.code, "name": a.name,
                             "status": a.status.value})
    dangling.sort(key=lambda r: r["code"])
    return {
        "count": len(dangling),
        "activities": dangling[:_OPEN_ENDS_CAP],
        "truncated": len(dangling) > _OPEN_ENDS_CAP,
        "note": ("incomplete activities with no relationship path forward to the "
                 "target; any slippage on them does not move the target date"),
    }
