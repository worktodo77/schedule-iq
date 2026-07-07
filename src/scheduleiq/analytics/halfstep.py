"""MIP 3.4 half-step engine (backlog D9) — progress vs revision bifurcation with
NAMED revision attribution.

Forensic purpose
----------------
AACE 29R-03 MIP 3.4 (the observational / dynamic / contemporaneous split) asks,
for each update pair, how much of the milestone's movement was caused by
**performance** (progress recorded between the two updates) versus **revision**
(logic, duration, calendar, constraint, and scope edits the scheduler made).
This module answers that by re-scheduling update *n*'s network with update
*n+1*'s progress overlaid — the **half-step schedule** — and decomposing the
target's movement:

    progress_effect = EF_target(H)    − EF_target(E_n)
    revision_effect = EF_target(E_n1) − EF_target(H)
    total_movement  = EF_target(E_n1) − EF_target(E_n)   ==  progress + revision

where ``E_n`` is the engine run on ``earlier`` as imported, ``E_n1`` the run on
``later`` as imported, and ``H`` the run on the half-step.  The identity is
**exact by construction** (three engine dates on one target workday table) and is
asserted in code and in the tests.

Our differentiator over the market half-step (Fuse Forensics) is the **named
revision attribution**: the revision side is decomposed by re-applying each class
of edit from the change register (:mod:`scheduleiq.compare.diff`) ONE AT A TIME on
top of the half-step, giving a per-class target delta.  The class deltas do not
in general sum to ``revision_effect`` — the difference is reported honestly as an
``interaction/residual`` term (never forced to zero).  For the two largest
classes the individual named edits are re-applied (capped) to name the top
movers.

Every engine figure is a **diagnostic delta** in workdays of the target's own
calendar (ADR-0007 §4, presentation rule); the tool-of-record record dates are
carried alongside so the two are never confused.  Causation, entitlement, and
concurrency remain **PRELIMINARY**, reserved to the expert (CLAUDE.md §4).

Both files are gated through the ADR-0007 validation handshake before any engine
number is produced (``handshake="require"``; ``"skip"`` is the disclosed
test/analyst escape hatch).  A refused pair propagates :class:`HandshakeRefusal`
from :func:`run_halfstep`; the series API :func:`run_halfstep_series` converts a
refusal into a recorded stub result rather than raising.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from ..ingest.model import Activity, Relationship, Schedule
from ..compare.diff import ChangeSet, compare
from ..cpm.bridge import build_engine_inputs
from ..cpm.calendar_ops import build_workday_table, nearest_workday_index
from ..cpm.handshake import (HandshakeRefusal, require_valid_handshake,
                             run_handshake)
from ..cpm.results import AnalysisResult
# reuse impact.py's helpers so the two engine-side analytics modules share one
# target-resolution precedence, engine-run wrapper, and controlling-path walk.
from .impact import (_controlling_path, _finish_of, _hs_summary, _record_finish,
                     _resolve_target, _run)

# Cap on the number of named top-mover reruns per class (spec item 6).
_TOP_MOVERS_CAP = 10
# Cap on the listed progress contributors (spec item 7).
_PROGRESS_CONTRIB_CAP = 10

# Deterministic revision-class ordering (spec item 6).
_CLASS_ORDER = [
    "logic_added",
    "logic_deleted",
    "lag_type_changed",
    "duration_changed",
    "calendar_changed",
    "constraint_changed",
    "new_activities",
    "deleted_activities",
]

_PRELIMINARY = (
    "PRELIMINARY — the progress/revision bifurcation is a diagnostic "
    "decomposition of engine dates; causation, entitlement (EOT/compensation), "
    "concurrency, and quantum are reserved to the expert (AACE 29R-03; SCL "
    "Protocol 2nd ed.)."
)


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ClassAttribution:
    """One revision class re-applied alone on top of the half-step.

    ``delta_workdays`` is the target's movement (workdays of the target
    calendar) caused by applying JUST this class of edits to the half-step
    inputs — negative = the target moves earlier.  ``top_movers`` is populated
    only for the two largest classes (individual named edits, capped)."""
    cls: str
    n_edits: int
    target_finish_engine: Optional[date] = None
    delta_workdays: Optional[int] = None
    delta_calendar_days: Optional[int] = None
    computable: bool = True
    blocking: str = ""
    top_movers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": self.cls,
            "n_edits": self.n_edits,
            "target_finish_engine": (self.target_finish_engine.isoformat()
                                     if self.target_finish_engine else None),
            "delta_workdays": self.delta_workdays,
            "delta_calendar_days": self.delta_calendar_days,
            "computable": self.computable,
            "blocking": self.blocking,
            "top_movers": list(self.top_movers),
        }


@dataclass
class HalfStepResult:
    """The MIP 3.4 half-step decomposition for one update pair on one target."""
    earlier_label: str = ""
    later_label: str = ""
    earlier_data_date: Optional[date] = None
    later_data_date: Optional[date] = None

    target_uid: Optional[str] = None
    target_code: Optional[str] = None
    target_name: Optional[str] = None
    resolved_how: str = ""
    target_calendar: str = ""
    target_in_earlier: bool = True

    handshake_mode: str = "require"
    handshake_earlier: Optional[dict[str, Any]] = None
    handshake_later: Optional[dict[str, Any]] = None

    # engine baselines (diagnostic dates)
    en_target_ef: Optional[date] = None
    en1_target_ef: Optional[date] = None
    h_target_ef: Optional[date] = None

    progress_effect_workdays: Optional[int] = None
    revision_effect_workdays: Optional[int] = None
    total_movement_workdays: Optional[int] = None
    progress_effect_calendar_days: Optional[int] = None
    revision_effect_calendar_days: Optional[int] = None
    total_movement_calendar_days: Optional[int] = None
    identity_holds: Optional[bool] = None
    decomposition_computable: bool = True
    decomposition_blocking: str = ""

    # record-date (tool-of-record) movement, carried beside the engine numbers
    record_movement_calendar_days: Optional[int] = None
    record_movement_workdays: Optional[int] = None

    class_attributions: list[ClassAttribution] = field(default_factory=list)
    attribution_sum_workdays: Optional[int] = None
    residual_workdays: Optional[int] = None

    progress_contributors: list[dict[str, Any]] = field(default_factory=list)
    mip33_row: dict[str, Any] = field(default_factory=dict)

    disclosures: list[str] = field(default_factory=list)
    preliminary: str = _PRELIMINARY
    refused: bool = False
    refusal: str = ""

    def attribution(self, cls: str) -> Optional[ClassAttribution]:
        for c in self.class_attributions:
            if c.cls == cls:
                return c
        return None

    def decomposition(self) -> dict[str, Any]:
        return {
            "target": {"uid": self.target_uid, "code": self.target_code,
                       "calendar": self.target_calendar,
                       "resolved_how": self.resolved_how,
                       "present_in_earlier": self.target_in_earlier},
            "engine_dates": {
                "E_n_target_early_finish": (self.en_target_ef.isoformat()
                                            if self.en_target_ef else None),
                "half_step_target_early_finish": (self.h_target_ef.isoformat()
                                                  if self.h_target_ef else None),
                "E_n1_target_early_finish": (self.en1_target_ef.isoformat()
                                             if self.en1_target_ef else None),
            },
            "progress_effect_workdays": self.progress_effect_workdays,
            "revision_effect_workdays": self.revision_effect_workdays,
            "total_movement_workdays": self.total_movement_workdays,
            "progress_effect_calendar_days": self.progress_effect_calendar_days,
            "revision_effect_calendar_days": self.revision_effect_calendar_days,
            "total_movement_calendar_days": self.total_movement_calendar_days,
            "identity_holds": self.identity_holds,
            "identity": "total_movement == progress_effect + revision_effect",
            "record_movement_calendar_days": self.record_movement_calendar_days,
            "record_movement_workdays": self.record_movement_workdays,
            "computable": self.decomposition_computable,
            "blocking": self.decomposition_blocking,
            "convention": ("engine deltas are diagnostic (ADR-0007 §4); movement "
                           "is in WORKDAYS of the target's own calendar; the "
                           "tool-of-record record-date movement is carried "
                           "alongside, never merged."),
        }

    def attribution_block(self) -> dict[str, Any]:
        return {
            "revision_effect_workdays": self.revision_effect_workdays,
            "per_class": [c.to_dict() for c in self.class_attributions],
            "attribution_sum_workdays": self.attribution_sum_workdays,
            "interaction_residual_workdays": self.residual_workdays,
            "residual_note": (
                "sum(class deltas) does NOT in general equal revision_effect; the "
                "difference is the interaction between simultaneously-applied "
                "revisions and is reported here, never forced to zero (honesty "
                "requirement)."),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": {
                "earlier": self.earlier_label,
                "later": self.later_label,
                "earlier_data_date": (self.earlier_data_date.isoformat()
                                      if self.earlier_data_date else None),
                "later_data_date": (self.later_data_date.isoformat()
                                    if self.later_data_date else None),
            },
            "refused": self.refused,
            "refusal": self.refusal,
            "handshake": {
                "mode": self.handshake_mode,
                "earlier": self.handshake_earlier,
                "later": self.handshake_later,
            },
            "decomposition": self.decomposition(),
            "revision_attribution": self.attribution_block(),
            "progress_contributors": list(self.progress_contributors),
            "mip33_row": self.mip33_row,
            "disclosures": list(self.disclosures),
            "preliminary": self.preliminary,
        }


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _find_by_code(sched: Schedule, code: str) -> Optional[Activity]:
    for a in sched.activities.values():
        if a.code == code:
            return a
    return None


def _target_ef(res: Optional[AnalysisResult], uid: Optional[str]) -> Optional[date]:
    """Target early finish from an engine result: the named activity's EF, or —
    when the target is absent (fallback) — the project finish = max EF."""
    if res is None:
        return None
    if uid is not None:
        sa = res.scheduled.get(uid)
        if sa is not None:
            return sa.early_finish
    return _max_ef(res)


def _max_ef(res: Optional[AnalysisResult]) -> Optional[date]:
    if res is None or not res.scheduled:
        return None
    return max(sa.early_finish for sa in res.scheduled.values())


def _wd_delta(tbl: dict[date, int], base: Optional[date], scen: Optional[date]
              ) -> tuple[Optional[int], Optional[int]]:
    """(workday delta on the target calendar, calendar-day delta).  Uses a single
    unified target-calendar workday table so deltas across DIFFERENT engine runs
    are commensurable (and the decomposition identity is exact)."""
    if base is None or scen is None:
        return None, None
    cal_days = (scen - base).days
    try:
        return (nearest_workday_index(tbl, scen)
                - nearest_workday_index(tbl, base)), cal_days
    except KeyError:
        return None, cal_days


def _overlay_progress(hs: Schedule, later: Schedule, disclosures: list[str]) -> None:
    """Overlay ``later``'s progress onto the half-step schedule (a copy of the
    earlier network).  Matched by code, uid fallback.  Only the progress fields
    move; the earlier network (logic, durations, calendars, constraints,
    settings) is untouched.  New-in-later activities are NOT added (they are
    revisions); deleted-in-later activities keep the earlier state unprogressed.
    Unmatched activities on both sides are disclosed."""
    later_by_code = {a.code: a for a in later.activities.values()}
    later_by_uid = {a.uid: a for a in later.activities.values()}
    matched_later: set[str] = set()
    unmatched_earlier: list[str] = []
    for a in hs.activities.values():
        la = later_by_code.get(a.code) or later_by_uid.get(a.uid)
        if la is None:
            unmatched_earlier.append(a.code)
            continue
        matched_later.add(la.uid)
        # repin from later's actuals + set remaining duration + pct from later
        a.status = la.status
        a.actual_start = la.actual_start
        a.actual_finish = la.actual_finish
        a.remaining_duration_hours = la.remaining_duration_hours
        a.pct_complete = la.pct_complete
        a.physical_pct = la.physical_pct
    new_in_later = sorted(a.code for a in later.activities.values()
                          if a.uid not in matched_later)
    if new_in_later:
        disclosures.append(
            f"{len(new_in_later)} activity(ies) new in the later update were NOT "
            "overlaid onto the half-step (they are revisions, not progress): "
            + ", ".join(new_in_later) + ".")
    if unmatched_earlier:
        disclosures.append(
            f"{len(unmatched_earlier)} earlier activity(ies) absent from the "
            "later update kept their earlier (unprogressed) state in the "
            "half-step (their non-progress is a revision matter): "
            + ", ".join(sorted(unmatched_earlier)) + ".")


# ---------------------------------------------------------------------------
# revision-class edit builders (change register -> half-step mutations)
# ---------------------------------------------------------------------------
@dataclass
class _Edit:
    label: str
    apply: Callable[[Schedule], None]


def _ing_rel_from(later: Schedule, r: Relationship, code_to_uid: dict[str, str]
                  ) -> Optional[Relationship]:
    """Translate a ``later`` Relationship into a half-step Relationship, mapping
    endpoints by code onto the half-step's uids.  None when an endpoint is not
    present in the half-step."""
    p = later.activities.get(r.pred_uid)
    q = later.activities.get(r.succ_uid)
    if p is None or q is None:
        return None
    pu = code_to_uid.get(p.code)
    qu = code_to_uid.get(q.code)
    if pu is None or qu is None:
        return None
    return Relationship(pred_uid=pu, succ_uid=qu, rtype=r.rtype, lag_hours=r.lag_hours)


def _rels_by_codes(sched: Schedule) -> dict[tuple[str, str], list[Relationship]]:
    m: dict[tuple[str, str], list[Relationship]] = {}
    for r in sched.relationships:
        p = sched.activities.get(r.pred_uid)
        q = sched.activities.get(r.succ_uid)
        if p and q:
            m.setdefault((p.code, q.code), []).append(r)
    return m


def _build_edits(earlier: Schedule, later: Schedule, cs: ChangeSet
                 ) -> dict[str, list[_Edit]]:
    """Translate every revision class in the ChangeSet into a list of half-step
    mutations (one ``_Edit`` per named edit).  All mutations operate on a fresh
    copy of the half-step schedule passed in at apply time.

    Class boundaries (documented, to avoid double counting):
      * ``logic_added`` / ``logic_deleted`` / ``lag_type_changed`` cover only
        relationships whose BOTH endpoints exist in the earlier AND later network
        (genuine logic edits).  Relationships that appear/vanish because an
        activity was added/deleted are attributed to ``new_activities`` /
        ``deleted_activities`` instead.
    """
    e_codes = {a.code for a in earlier.activities.values()}
    l_codes = {a.code for a in later.activities.values()}
    both = e_codes & l_codes
    later_keyed = _rels_by_codes(later)
    earlier_keyed = _rels_by_codes(earlier)
    later_by_code = {a.code: a for a in later.activities.values()}

    edits: dict[str, list[_Edit]] = {c: [] for c in _CLASS_ORDER}

    # ---- logic changes (relationships between activities present in both) ----
    added_keys, deleted_keys, modified_keys = [], [], []
    for c in cs.logic_changes:
        key = (c.pred_code, c.succ_code)
        if c.pred_code not in both or c.succ_code not in both:
            continue  # touches an added/deleted activity -> handled by that class
        if c.kind == "added":
            added_keys.append(key)
        elif c.kind == "deleted":
            deleted_keys.append(key)
        elif c.kind == "modified":
            modified_keys.append(key)
    # dedupe, keep deterministic order
    added_keys = sorted(set(added_keys))
    deleted_keys = sorted(set(deleted_keys))
    modified_keys = sorted(set(modified_keys))

    def _mk_add(key):
        def _apply(hs: Schedule):
            code_to_uid = {a.code: a.uid for a in hs.activities.values()}
            for r in later_keyed.get(key, []):
                ir = _ing_rel_from(later, r, code_to_uid)
                if ir is not None:
                    hs.relationships.append(ir)
        return _apply

    def _mk_del(key):
        def _apply(hs: Schedule):
            uid_by_code = {a.code: a.uid for a in hs.activities.values()}
            pu, qu = uid_by_code.get(key[0]), uid_by_code.get(key[1])
            hs.relationships = [r for r in hs.relationships
                                if not (r.pred_uid == pu and r.succ_uid == qu)]
        return _apply

    def _mk_mod(key):
        def _apply(hs: Schedule):
            uid_by_code = {a.code: a.uid for a in hs.activities.values()}
            pu, qu = uid_by_code.get(key[0]), uid_by_code.get(key[1])
            hs.relationships = [r for r in hs.relationships
                                if not (r.pred_uid == pu and r.succ_uid == qu)]
            code_to_uid = uid_by_code
            for r in later_keyed.get(key, []):
                ir = _ing_rel_from(later, r, code_to_uid)
                if ir is not None:
                    hs.relationships.append(ir)
        return _apply

    for key in added_keys:
        edits["logic_added"].append(_Edit(f"add {key[0]}->{key[1]}", _mk_add(key)))
    for key in deleted_keys:
        edits["logic_deleted"].append(_Edit(f"delete {key[0]}->{key[1]}", _mk_del(key)))
    for key in modified_keys:
        edits["lag_type_changed"].append(
            _Edit(f"modify {key[0]}->{key[1]}", _mk_mod(key)))

    # ---- duration (OD) changes -------------------------------------------
    def _mk_od(code, new_hours):
        def _apply(hs: Schedule):
            for a in hs.activities.values():
                if a.code == code:
                    a.original_duration_hours = new_hours
        return _apply

    for fc in cs.duration_changes:
        if fc.code not in both:
            continue
        la = later_by_code.get(fc.code)
        if la is None:
            continue
        edits["duration_changed"].append(
            _Edit(f"OD {fc.code}: {fc.before}->{fc.after}",
                  _mk_od(fc.code, la.original_duration_hours)))

    # ---- calendar re-assignment ------------------------------------------
    def _mk_cal(code, new_cal_uid):
        def _apply(hs: Schedule):
            if new_cal_uid is not None and new_cal_uid not in hs.calendars \
                    and new_cal_uid in later.calendars:
                hs.calendars[new_cal_uid] = copy.deepcopy(later.calendars[new_cal_uid])
            for a in hs.activities.values():
                if a.code == code:
                    a.calendar_uid = new_cal_uid
        return _apply

    for fc in cs.calendar_changes:
        if fc.code not in both:
            continue
        la = later_by_code.get(fc.code)
        if la is None:
            continue
        edits["calendar_changed"].append(
            _Edit(f"calendar {fc.code}: {fc.before}->{fc.after}",
                  _mk_cal(fc.code, la.calendar_uid)))

    # ---- constraint changes ----------------------------------------------
    def _mk_con(code, la: Activity):
        def _apply(hs: Schedule):
            for a in hs.activities.values():
                if a.code == code:
                    a.constraint = la.constraint
                    a.constraint_date = la.constraint_date
                    a.constraint2 = la.constraint2
                    a.constraint2_date = la.constraint2_date
        return _apply

    for fc in cs.constraint_changes:
        if fc.code not in both:
            continue
        la = later_by_code.get(fc.code)
        if la is None:
            continue
        edits["constraint_changed"].append(
            _Edit(f"constraint {fc.code}: {fc.before}->{fc.after}",
                  _mk_con(fc.code, la)))

    # ---- new activities (added activity + its incident relationships) -----
    def _add_new_activity(hs: Schedule, la: Activity):
        if la.uid in hs.activities or _find_by_code(hs, la.code) is not None:
            return
        na = copy.deepcopy(la)
        if na.calendar_uid is not None and na.calendar_uid not in hs.calendars \
                and na.calendar_uid in later.calendars:
            hs.calendars[na.calendar_uid] = copy.deepcopy(later.calendars[na.calendar_uid])
        hs.activities[na.uid] = na
        # wire in later's relationships that touch this new activity, where the
        # OTHER endpoint already exists in the half-step.
        code_to_uid = {a.code: a.uid for a in hs.activities.values()}
        for r in later.relationships:
            p = later.activities.get(r.pred_uid)
            q = later.activities.get(r.succ_uid)
            if p is None or q is None:
                continue
            if la.code not in (p.code, q.code):
                continue
            if p.code in code_to_uid and q.code in code_to_uid:
                ir = _ing_rel_from(later, r, code_to_uid)
                if ir is not None and not any(
                        x.pred_uid == ir.pred_uid and x.succ_uid == ir.succ_uid
                        and x.rtype == ir.rtype for x in hs.relationships):
                    hs.relationships.append(ir)

    def _mk_newact(code):
        def _apply(hs: Schedule):
            la = later_by_code.get(code)
            if la is not None:
                _add_new_activity(hs, la)
        return _apply

    for a in sorted(cs.added, key=lambda x: x.code):
        edits["new_activities"].append(
            _Edit(f"add activity {a.code}", _mk_newact(a.code)))

    # ---- deleted activities (remove activity + its incident relationships) -
    def _mk_delact(code):
        def _apply(hs: Schedule):
            ea = _find_by_code(hs, code)
            if ea is None:
                return
            uid = ea.uid
            del hs.activities[uid]
            hs.relationships = [r for r in hs.relationships
                                if r.pred_uid != uid and r.succ_uid != uid]
        return _apply

    for a in sorted(cs.deleted, key=lambda x: x.code):
        edits["deleted_activities"].append(
            _Edit(f"delete activity {a.code}", _mk_delact(a.code)))

    return edits


# ---------------------------------------------------------------------------
# engine run of an ingest schedule -> (result, blocking)
# ---------------------------------------------------------------------------
def _run_schedule(sched: Schedule) -> tuple[Optional[AnalysisResult], str, Any]:
    """Build engine inputs from an ingest schedule and run one baseline engine
    pass (constraints on, the schedule's own statusing mode).  Returns
    ``(result|None, blocking, engine_inputs)``.  Never raises for an invalid
    network — degrades per-scenario like impact.py."""
    try:
        ei = build_engine_inputs(sched)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"engine inputs error: {exc}", None
    res, blk = _run(ei, ei.constraints, ei.statusing_mode)
    return res, blk, ei


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def run_halfstep(earlier: Schedule, later: Schedule, *,
                 target: Optional[str] = None, handshake: str = "require",
                 threshold_pct: float = 99.0) -> HalfStepResult:
    """Bifurcate the target's movement between ``earlier`` and ``later`` into
    progress and revision components with named revision attribution (MIP 3.4).

    ``handshake="require"`` gates BOTH files on the ADR-0007 validation handshake
    and re-raises :class:`HandshakeRefusal` when either file does not handshake.
    ``handshake="skip"`` bypasses the gate (disclosed) and degrades per-scenario.
    """
    if handshake not in ("require", "skip"):
        raise ValueError(f"handshake must be 'require' or 'skip', got {handshake!r}")

    out = HalfStepResult(handshake_mode=handshake)
    out.earlier_label = earlier.label()
    out.later_label = later.label()
    out.earlier_data_date = earlier.data_date.date() if earlier.data_date else None
    out.later_data_date = later.data_date.date() if later.data_date else None

    # -- handshake gate for BOTH files (ADR-0007) -----------------------------
    if handshake == "require":
        hs_e = require_valid_handshake(earlier, threshold_pct=threshold_pct)
        hs_l = require_valid_handshake(later, threshold_pct=threshold_pct)
        out.handshake_earlier = _hs_summary(hs_e)
        out.handshake_later = _hs_summary(hs_l)
    else:
        out.disclosures.append(
            "handshake='skip': the ADR-0007 validation gate was BYPASSED for both "
            "files (analyst/test escape hatch). Engine deltas are unvalidated "
            "against the record; invalid-network runs degrade to 'not computable'.")
        for label, sched in (("earlier", earlier), ("later", later)):
            try:
                summ = _hs_summary(run_handshake(sched, threshold_pct=threshold_pct))
            except Exception as exc:  # pragma: no cover - defensive
                summ = {"error": f"handshake summary unavailable: {exc}"}
            if label == "earlier":
                out.handshake_earlier = summ
            else:
                out.handshake_later = summ

    # -- target resolution (record dates; engine-independent) -----------------
    later_tgt, how = _resolve_target(later, target)
    out.resolved_how = how
    if later_tgt is None:
        out.disclosures.append(f"target could not be resolved on the later update: {how}")
        earlier_tgt = None
    else:
        out.target_uid, out.target_code, out.target_name = (
            later_tgt.uid, later_tgt.code, later_tgt.name)
        cal = later.cal_for(later_tgt)
        out.target_calendar = (cal.name or cal.uid) if cal else (later_tgt.calendar_uid or "")
        earlier_tgt = _find_by_code(earlier, later_tgt.code)
        if earlier_tgt is None:
            out.target_in_earlier = False
            out.disclosures.append(
                f"target {later_tgt.code!r} is absent from the earlier update; the "
                "decomposition target falls back to project finish (max early "
                "finish) in every run.")

    # uids used to read the target EF in each run (None -> project finish = max EF)
    t_uid_earlier = earlier_tgt.uid if (earlier_tgt is not None) else None
    t_uid_later = later_tgt.uid if (later_tgt is not None and out.target_in_earlier) else None
    if later_tgt is not None and not out.target_in_earlier:
        t_uid_later = None  # fall back consistently to project finish on both sides

    # -- change register (drives the named revision attribution) --------------
    cs = compare(earlier, later)

    # -- baseline engine runs: E_n (earlier), E_n1 (later) --------------------
    en, en_blk, _ = _run_schedule(earlier)
    en1, en1_blk, _ = _run_schedule(later)

    # -- half-step schedule: earlier network + later progress -----------------
    hs_sched = copy.deepcopy(earlier)
    hs_sched.data_date = later.data_date
    _overlay_progress(hs_sched, later, out.disclosures)
    h, h_blk, h_ei = _run_schedule(hs_sched)

    out.en_target_ef = _target_ef(en, t_uid_earlier)
    out.en1_target_ef = _target_ef(en1, t_uid_later)
    out.h_target_ef = _target_ef(h, t_uid_earlier)

    # -- MIP 3.3 as-is row (no bifurcation) -----------------------------------
    out.mip33_row = _mip33_row(earlier, later, cs, earlier_tgt, later_tgt,
                               out.en_target_ef, out.en1_target_ef)

    if en is None or en1 is None or h is None:
        out.decomposition_computable = False
        blk = "; ".join(b for b in (
            f"E_n invalid: {en_blk}" if en is None else "",
            f"E_n1 invalid: {en1_blk}" if en1 is None else "",
            f"half-step invalid: {h_blk}" if h is None else "") if b)
        out.decomposition_blocking = blk
        out.disclosures.append("decomposition not computable — " + blk)
        return out

    # -- unified target-calendar workday table (commensurable deltas) ---------
    tbl = _unified_target_table(h_ei, earlier_tgt, [en, en1, h])

    # -- decomposition --------------------------------------------------------
    prog_wd, prog_cal = _wd_delta(tbl, out.en_target_ef, out.h_target_ef)
    rev_wd, rev_cal = _wd_delta(tbl, out.h_target_ef, out.en1_target_ef)
    tot_wd, tot_cal = _wd_delta(tbl, out.en_target_ef, out.en1_target_ef)
    out.progress_effect_workdays, out.progress_effect_calendar_days = prog_wd, prog_cal
    out.revision_effect_workdays, out.revision_effect_calendar_days = rev_wd, rev_cal
    out.total_movement_workdays, out.total_movement_calendar_days = tot_wd, tot_cal
    if None not in (prog_wd, rev_wd, tot_wd):
        out.identity_holds = (prog_wd + rev_wd == tot_wd)
        # exact by construction (three dates on one table); assert loudly
        assert out.identity_holds, (
            f"half-step identity violated: {prog_wd} + {rev_wd} != {tot_wd}")

    # record-date movement carried beside the engine decomposition
    if earlier_tgt is not None and later_tgt is not None:
        e_rec, l_rec = _record_finish(earlier_tgt), _record_finish(later_tgt)
        if e_rec is not None and l_rec is not None:
            out.record_movement_calendar_days = (l_rec.date() - e_rec.date()).days
            r_wd, _ = _wd_delta(tbl, e_rec.date(), l_rec.date())
            out.record_movement_workdays = r_wd

    # -- named revision attribution (per class, on top of the half-step) ------
    edits = _build_edits(earlier, later, cs)
    out.class_attributions = _attribute_classes(
        hs_sched, edits, t_uid_earlier, out.h_target_ef, tbl)
    computable = [c for c in out.class_attributions
                  if c.computable and c.delta_workdays is not None]
    out.attribution_sum_workdays = sum(c.delta_workdays for c in computable)
    if out.revision_effect_workdays is not None:
        out.residual_workdays = (out.revision_effect_workdays
                                 - out.attribution_sum_workdays)

    # -- top movers for the two largest (by |delta|) computable classes -------
    ranked = sorted(
        [c for c in computable if c.delta_workdays != 0],
        key=lambda c: (-abs(c.delta_workdays), _CLASS_ORDER.index(c.cls)))
    for c in ranked[:2]:
        c.top_movers = _top_movers(hs_sched, edits[c.cls], t_uid_earlier,
                                   out.h_target_ef, tbl)

    # -- top progress contributors (controlling-path RD movers) ---------------
    out.progress_contributors = _progress_contributors(
        earlier, later, hs_sched, h_ei, h, t_uid_earlier, out.disclosures)

    return out


# ---------------------------------------------------------------------------
# attribution + contributors
# ---------------------------------------------------------------------------
def _unified_target_table(h_ei, earlier_tgt: Optional[Activity],
                          results: list[AnalysisResult]) -> dict[date, int]:
    """One workday table on the target's calendar wide enough to cover every EF
    in every run, so deltas taken across different engine runs are commensurable.
    """
    cal_uid = earlier_tgt.calendar_uid if earlier_tgt is not None else None
    cpm_cal = None
    if cal_uid is not None:
        cpm_cal = h_ei.calendar_registry.get(cal_uid)
    if cpm_cal is None:
        cpm_cal = h_ei.calendar
    starts = [r.project_start for r in results if r is not None]
    efs: list[date] = []
    for r in results:
        if r is None:
            continue
        for sa in r.scheduled.values():
            efs.append(sa.early_finish)
    lo = min(starts + efs) - timedelta(days=120)
    hi = max(efs) + timedelta(days=800)
    return build_workday_table(cpm_cal, lo, hi)


def _apply_all(hs_sched: Schedule, edits: list[_Edit]) -> Schedule:
    m = copy.deepcopy(hs_sched)
    for e in edits:
        e.apply(m)
    return m


def _attribute_classes(hs_sched: Schedule, edits: dict[str, list[_Edit]],
                       t_uid: Optional[str], h_ef: Optional[date],
                       tbl: dict[date, int]) -> list[ClassAttribution]:
    out: list[ClassAttribution] = []
    for cls in _CLASS_ORDER:
        class_edits = edits.get(cls, [])
        ca = ClassAttribution(cls=cls, n_edits=len(class_edits))
        if not class_edits:
            ca.target_finish_engine = h_ef
            ca.delta_workdays, ca.delta_calendar_days = 0, 0
            out.append(ca)
            continue
        mutated = _apply_all(hs_sched, class_edits)
        res, blk, _ = _run_schedule(mutated)
        if res is None:
            ca.computable, ca.blocking = False, blk
        else:
            ef = _target_ef(res, t_uid)
            ca.target_finish_engine = ef
            ca.delta_workdays, ca.delta_calendar_days = _wd_delta(tbl, h_ef, ef)
        out.append(ca)
    return out


def _top_movers(hs_sched: Schedule, class_edits: list[_Edit], t_uid: Optional[str],
                h_ef: Optional[date], tbl: dict[date, int]) -> list[dict[str, Any]]:
    """Re-apply each named edit in the class ALONE on top of the half-step (cap
    10) to name the top individual movers, sorted by |delta| then label."""
    movers: list[dict[str, Any]] = []
    for e in class_edits[:_TOP_MOVERS_CAP]:
        mutated = _apply_all(hs_sched, [e])
        res, blk, _ = _run_schedule(mutated)
        row: dict[str, Any] = {"edit": e.label}
        if res is None:
            row.update({"computable": False, "blocking": blk,
                        "delta_workdays": None, "delta_calendar_days": None,
                        "target_finish_engine": None})
        else:
            ef = _target_ef(res, t_uid)
            dwd, dcal = _wd_delta(tbl, h_ef, ef)
            row.update({"computable": True, "blocking": "",
                        "delta_workdays": dwd, "delta_calendar_days": dcal,
                        "target_finish_engine": ef.isoformat() if ef else None})
        movers.append(row)
    movers.sort(key=lambda r: (-(abs(r["delta_workdays"])
                                 if r["delta_workdays"] is not None else -1),
                               r["edit"]))
    if len(class_edits) > _TOP_MOVERS_CAP:
        movers.append({"edit": "__truncated__", "computable": False,
                       "blocking": f"{len(class_edits)} edits; capped at "
                                   f"{_TOP_MOVERS_CAP}",
                       "delta_workdays": None, "delta_calendar_days": None,
                       "target_finish_engine": None})
    return movers


def _progress_contributors(earlier: Schedule, later: Schedule, hs_sched: Schedule,
                           h_ei, h: AnalysisResult, t_uid: Optional[str],
                           disclosures: list[str]) -> list[dict[str, Any]]:
    """Rank matched activities on the half-step's controlling path to the target
    by |remaining-duration change in workdays| (earlier RD -> later RD).  A
    heuristic approximation of which progress overlays moved the target."""
    if t_uid is None:
        return []
    path = set(_controlling_path(h_ei, h, t_uid))
    e_by_code = {a.code: a for a in earlier.activities.values()}
    l_by_code = {a.code: a for a in later.activities.values()}
    rows: list[dict[str, Any]] = []
    for uid in path:
        a = hs_sched.activities.get(uid)
        if a is None:
            continue
        ea = e_by_code.get(a.code)
        la = l_by_code.get(a.code)
        if ea is None or la is None:
            continue
        if ea.not_started and la.not_started:
            # no progress was overlaid for this activity (an RD difference here
            # reflects an OD revision, not performance) — excluded from the
            # progress ranking.
            continue
        cal = later.cal_for(la) or earlier.cal_for(ea)
        hpd = cal.hours_per_day if (cal and cal.hours_per_day) else 8.0
        e_rd = ea.remaining_duration_hours / hpd
        l_rd = la.remaining_duration_hours / hpd
        d_rd = l_rd - e_rd
        rows.append({
            "code": a.code, "name": a.name,
            "rd_change_workdays": round(d_rd, 2),
            "earlier_remaining_workdays": round(e_rd, 2),
            "later_remaining_workdays": round(l_rd, 2),
            "later_status": la.status.value,
        })
    rows.sort(key=lambda r: (-abs(r["rd_change_workdays"]), r["code"]))
    disclosures.append(
        "progress contributors are a HEURISTIC: matched activities on the "
        "half-step's controlling path to the target, ranked by |remaining-"
        "duration change in workdays| (activities not started in BOTH updates "
        "are excluded — an RD difference there is an OD revision, not "
        "progress); they approximate (do not exactly attribute) the progress "
        "effect.")
    return rows[:_PROGRESS_CONTRIB_CAP]


def _mip33_row(earlier: Schedule, later: Schedule, cs: ChangeSet,
               earlier_tgt: Optional[Activity], later_tgt: Optional[Activity],
               en_ef: Optional[date], en1_ef: Optional[date]) -> dict[str, Any]:
    """MIP 3.3 observational row — per update pair WITHOUT bifurcation: record EF
    movement, engine EF movement, critical-path Jaccard, and the change counts."""
    rec_move = None
    if earlier_tgt is not None and later_tgt is not None:
        e_rec, l_rec = _record_finish(earlier_tgt), _record_finish(later_tgt)
        if e_rec is not None and l_rec is not None:
            rec_move = (l_rec.date() - e_rec.date()).days
    eng_move = None
    if en_ef is not None and en1_ef is not None:
        eng_move = (en1_ef - en_ef).days
    return {
        "method": "MIP 3.3 (observational; no bifurcation)",
        "target_code": later_tgt.code if later_tgt is not None else None,
        "record_finish_movement_calendar_days": rec_move,
        "engine_finish_movement_calendar_days": eng_move,
        "critical_path_jaccard": cs.critical_path_jaccard,
        "change_counts": cs.summary_counts(),
    }


# ---------------------------------------------------------------------------
# series API
# ---------------------------------------------------------------------------
def run_halfstep_series(schedules: list[Schedule], *,
                        target: Optional[str] = None, handshake: str = "require",
                        threshold_pct: float = 99.0) -> list[HalfStepResult]:
    """Run :func:`run_halfstep` over consecutive pairs.  Each pair degrades
    independently: a pair refused by the handshake yields a STUB result carrying
    the refusal (not an exception), so one bad update does not abort the series.
    """
    out: list[HalfStepResult] = []
    for earlier, later in zip(schedules, schedules[1:]):
        try:
            out.append(run_halfstep(earlier, later, target=target,
                                    handshake=handshake, threshold_pct=threshold_pct))
        except HandshakeRefusal as exc:
            stub = HalfStepResult(handshake_mode=handshake, refused=True,
                                  refusal=str(exc))
            stub.earlier_label = earlier.label()
            stub.later_label = later.label()
            stub.earlier_data_date = earlier.data_date.date() if earlier.data_date else None
            stub.later_data_date = later.data_date.date() if later.data_date else None
            stub.disclosures.append(
                "pair refused by the ADR-0007 handshake; recorded as a stub in the "
                "series (the other pairs are unaffected).")
            out.append(stub)
    return out
