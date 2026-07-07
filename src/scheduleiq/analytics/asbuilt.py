"""As-built path reconstruction (retrospective) — ANALYTICS_PROPOSAL.md §2 item 6.

The forensic question this answers is *not* "what would the date be" but "what
actually drove what": the longest continuous chain of relationships whose ACTUAL
dates are consistent with each link having controlled its successor.  It is a
defensible starting point for as-built critical-path methods (AACE MIP 3.1/3.5),
with every link traceable to the two actual dates that anchor it.

Why the ADR-0007 handshake gate does NOT apply
-----------------------------------------------
The handshake (``scheduleiq.cpm.handshake``) gates *what-if* analytics: it
refuses to run a diagnostic reschedule until the ported engine reproduces the
tool-of-record dates.  This module runs no reschedule and forecasts nothing —
it is a purely retrospective reading of the ACTUAL start/finish dates the tool
already recorded, measuring the workday lag actually observed on each link.
There is no competing set of computed dates to reconcile, so the handshake gate
is inapplicable by construction.  (The lag arithmetic is the ported
``compute_actual_lag`` / ``run_lag_analysis``, honoring the file's SCHEDOPTIONS
lag-calendar mapping exactly as ``cpm.bridge`` does — see ``build_engine_inputs``.)

Everything here is an OBSERVATION, not an opinion: causation, concurrency, and
the choice of as-built method are reserved to the expert (CLAUDE.md §4).  The
result carries a standing PRELIMINARY label to that effect.

Link semantics (as implemented)
-------------------------------
For a relationship, let the two ANCHORING actual dates be, per type:
  FS: pred Actual Finish  -> succ Actual Start
  SS: pred Actual Start   -> succ Actual Start
  FF: pred Actual Finish  -> succ Actual Finish
  SF: pred Actual Start   -> succ Actual Finish
``actual_lag`` (workdays) is the ported workday-number subtraction of those two
dates, measured in the per-relationship lag calendar (predecessor-calendar
default, per the SCHEDOPTIONS strategy resolved by the bridge).  ``tightness`` =
``actual_lag - planned_lag`` (workdays).

  * tightness >= 0  -> the link is an as-built LINK candidate: the successor's
    anchor lands on or after the predecessor's anchor + planned lag, i.e. the
    actual dates are consistent with this link having controlled the successor.
    A link is the strongest driver when tightness is small (0 = perfectly
    tight); chains follow the tightest incoming link at each node.
  * tightness < 0   -> CONTRADICTED logic: the successor occurred before the
    link would allow.  These are out-of-sequence evidence, listed separately —
    never chain members.
  * required actual dates missing -> not actualized; the link provides no
    as-built evidence and cannot be traversed.

A link whose tightness exceeds ``gap_threshold_wd`` (default 5 wd) is still
traversable but FLAGGED as a gap: the expert must see unexplained as-built lag,
not have it hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from ..ingest.model import Activity, Schedule
from ..cpm.bridge import build_engine_inputs
from ..cpm.calendar_ops import date_to_workday
from ..cpm.destatusing import run_lag_analysis
from ..cpm.models import Activity as CpmActivity

LABEL = ("PRELIMINARY — as-built path reconstruction; causation and methodology "
         "selection reserved to the expert")

DEFAULT_GAP_THRESHOLD_WD = 5
PATH_CAP = 100

# anchoring-date roles per relationship type: (pred field, succ field)
_ANCHORS = {
    "FS": ("actual_finish", "actual_start"),
    "SS": ("actual_start", "actual_start"),
    "FF": ("actual_finish", "actual_finish"),
    "SF": ("actual_start", "actual_finish"),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _as_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def _started(a: Activity) -> bool:
    """Started/actualized-eligible: any actual date present.  Tasks normally
    carry an actual start; finish milestones (and DAT-05 corrupt rows) may carry
    only an actual finish — either makes the activity part of the as-built
    record, so both count (spec: "Milestones with actual dates count")."""
    return a.actual_start is not None or a.actual_finish is not None


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class AsBuiltLink:
    """One actualized (or contradicted) relationship, every field traceable to
    the two actual dates that anchor it."""
    pred_uid: str
    succ_uid: str
    pred_code: str
    succ_code: str
    rel_type: str
    planned_lag_wd: float
    actual_lag_wd: float
    tightness_wd: float
    pred_anchor_date: Optional[str]     # isoformat of the pred anchoring actual date
    succ_anchor_date: Optional[str]
    lag_calendar: Optional[str]         # the calendar the lag was measured in
    lag_calendar_fallback: bool
    contradicted: bool                  # tightness < 0 (OOS — succ before the link allows)
    is_gap: bool                        # tightness > gap threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "pred_uid": self.pred_uid,
            "succ_uid": self.succ_uid,
            "pred_code": self.pred_code,
            "succ_code": self.succ_code,
            "rel_type": self.rel_type,
            "planned_lag_wd": self.planned_lag_wd,
            "actual_lag_wd": self.actual_lag_wd,
            "tightness_wd": self.tightness_wd,
            "pred_anchor_date": self.pred_anchor_date,
            "succ_anchor_date": self.succ_anchor_date,
            "lag_calendar": self.lag_calendar,
            "lag_calendar_fallback": self.lag_calendar_fallback,
            "contradicted": self.contradicted,
            "is_gap": self.is_gap,
        }


@dataclass
class AsBuiltChain:
    rank: int
    activity_uids: list[str]            # ordered start -> end anchor
    activity_codes: list[str]
    links: list[AsBuiltLink]           # ordered start -> end anchor (len = len(activities)-1)
    span_workdays: Optional[float]     # end.AF - start.AS in the end anchor's calendar
    span_calendar: Optional[str]
    start_code: str
    end_code: str
    start_actual_start: Optional[str]
    end_actual_finish: Optional[str]
    break_reason: str                  # why the chain starts where it does
    gap_flags: list[str] = field(default_factory=list)
    contradicted_links: list[AsBuiltLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "activity_uids": list(self.activity_uids),
            "activity_codes": list(self.activity_codes),
            "links": [l.to_dict() for l in self.links],
            "span_workdays": self.span_workdays,
            "span_calendar": self.span_calendar,
            "start_code": self.start_code,
            "end_code": self.end_code,
            "start_actual_start": self.start_actual_start,
            "end_actual_finish": self.end_actual_finish,
            "break_reason": self.break_reason,
            "gap_flags": list(self.gap_flags),
            "contradicted_links": [l.to_dict() for l in self.contradicted_links],
        }


@dataclass
class AsBuiltReconstruction:
    label: str
    end_anchor_code: Optional[str]
    end_anchor_uid: Optional[str]
    end_anchor_resolution: str
    chains: list[AsBuiltChain]
    links: list[AsBuiltLink]           # every actualized (consistent) link
    contradicted_links: list[AsBuiltLink]
    summary: dict[str, int]
    disclosures: list[str]
    lag_strategy: Optional[str]
    gap_threshold_wd: float
    top_n: int
    span_convention: str = ("chain span = end-anchor Actual Finish minus chain-start "
                            "Actual Start, in workdays of the end anchor's calendar")
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "end_anchor_code": self.end_anchor_code,
            "end_anchor_uid": self.end_anchor_uid,
            "end_anchor_resolution": self.end_anchor_resolution,
            "chains": [c.to_dict() for c in self.chains],
            "links": [l.to_dict() for l in self.links],
            "contradicted_links": [l.to_dict() for l in self.contradicted_links],
            "summary": dict(self.summary),
            "disclosures": list(self.disclosures),
            "lag_strategy": self.lag_strategy,
            "gap_threshold_wd": self.gap_threshold_wd,
            "top_n": self.top_n,
            "span_convention": self.span_convention,
            "reason": self.reason,
        }


def _empty(reason: str, disclosures: Optional[list[str]] = None,
           top_n: int = 5, gap_threshold_wd: float = DEFAULT_GAP_THRESHOLD_WD
           ) -> AsBuiltReconstruction:
    return AsBuiltReconstruction(
        label=LABEL, end_anchor_code=None, end_anchor_uid=None,
        end_anchor_resolution="none", chains=[], links=[], contradicted_links=[],
        summary={"actualized_activities": 0, "actualized_relationships": 0,
                 "contradicted_relationships": 0, "unreached_started_activities": 0},
        disclosures=disclosures or [], lag_strategy=None,
        gap_threshold_wd=gap_threshold_wd, top_n=top_n, reason=reason)


# ---------------------------------------------------------------------------
# end-anchor resolution
# ---------------------------------------------------------------------------
def _auto_end(started: list[Activity]) -> Activity:
    """Latest actual_finish; tie -> latest actual_start; tie -> smallest uid.
    Deterministic: iterate uid-ascending with a strict '>' so the first
    (smallest-uid) activity wins on an exact date tie."""
    best: Optional[Activity] = None
    best_key: Optional[tuple] = None
    for a in sorted(started, key=lambda x: x.uid):
        af = _as_date(a.actual_finish) or date.min
        as_ = _as_date(a.actual_start) or date.min
        key = (af, as_)
        if best is None or key > best_key:   # type: ignore[operator]
            best, best_key = a, key
    return best                              # type: ignore[return-value]


def _resolve_end(sched: Schedule, started: list[Activity], end: Optional[str]
                 ) -> tuple[Activity, str]:
    started_uids = {a.uid for a in started}
    if end is not None:
        a = sched.activities.get(end)
        if a is None:
            for x in sched.activities.values():
                if x.code == end:
                    a = x
                    break
        if a is not None and a.uid in started_uids:
            return a, f"explicit end {a.code!r} (actualized)"
        return (_auto_end(started),
                f"latest actual finish (requested end {end!r} not found or not started)")
    return _auto_end(started), "latest actual finish"


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def reconstruct_asbuilt_paths(
    sched: Schedule,
    *,
    end: Optional[str] = None,
    top_n: int = 5,
    gap_threshold_wd: float = DEFAULT_GAP_THRESHOLD_WD,
) -> AsBuiltReconstruction:
    """Reconstruct the longest continuous chains through actualized relationships.

    Backward from the end anchor (explicit ``end`` uid/code if given and started,
    else the latest-finishing actualized activity), the walk steps to the
    tightest incoming as-built link at each node; ties branch (capped at 100
    paths).  Chains are ranked by total actualized working-duration span and the
    top ``top_n`` returned, each carrying its ordered links with full
    traceability, its start break-reason, its gap flags, and the contradicted
    (out-of-sequence) links found at its nodes.  Never raises: a schedule with no
    actuals returns an empty result carrying a ``reason``.
    """
    reals = sched.real_activities
    started = [a for a in reals if _started(a)]
    if not started:
        return _empty("no started activities — nothing to reconstruct as-built",
                      ["schedule carries no actual dates on real activities"],
                      top_n, gap_threshold_wd)

    try:
        ei = build_engine_inputs(sched)
    except Exception as exc:  # pragma: no cover - defensive; bridge is robust
        return _empty(f"could not build engine inputs: {exc}",
                      top_n=top_n, gap_threshold_wd=gap_threshold_wd)

    registry = ei.calendar_registry
    code_by_uid = ei.code_by_uid

    # CPM activities carrying ACTUAL dates (date granularity) for the ported lag
    # arithmetic.  The bridge pins actuals into early-date slots for its
    # reschedule; the lag functions need actual_start/actual_finish, so we build
    # a parallel activity set here (same uids, same calendar keys).
    lag_acts: dict[str, CpmActivity] = {}
    for a in reals:
        cid = a.calendar_uid if (a.calendar_uid is not None
                                 and registry.get(a.calendar_uid) is not None) else None
        lag_acts[a.uid] = CpmActivity(
            act_id=a.uid,
            calendar_id=cid,
            actual_start=_as_date(a.actual_start),
            actual_finish=_as_date(a.actual_finish),
        )

    lag_res = run_lag_analysis(
        ei.relationships, lag_acts, ei.workday_table, ei.calendar,
        calendar_registry=registry, lag_strategy=ei.lag_strategy)

    started_uids = {a.uid for a in started}
    ingest_by_uid = {a.uid: a for a in reals}

    def _code(uid: str) -> str:
        return code_by_uid.get(uid, ingest_by_uid[uid].code if uid in ingest_by_uid else uid)

    # Build link records from the lag results.
    all_links: list[AsBuiltLink] = []
    contradicted_all: list[AsBuiltLink] = []
    incoming_actualized: dict[str, list[AsBuiltLink]] = {}
    incoming_contradicted: dict[str, list[AsBuiltLink]] = {}
    incoming_rels: dict[str, list[tuple[str, str]]] = {}   # succ_uid -> [(pred_uid, rtype)]

    for lr in lag_res.relationship_results:
        incoming_rels.setdefault(lr.succ_id, []).append((lr.pred_id, lr.rel_type))
        if lr.actual_lag is None or lr.lag_variance is None:
            continue
        if lr.pred_id not in started_uids or lr.succ_id not in started_uids:
            continue
        pred = ingest_by_uid.get(lr.pred_id)
        succ = ingest_by_uid.get(lr.succ_id)
        if pred is None or succ is None:
            continue
        pred_field, succ_field = _ANCHORS[lr.rel_type]
        pred_anchor = _as_date(getattr(pred, pred_field))
        succ_anchor = _as_date(getattr(succ, succ_field))
        contradicted = lr.lag_variance < 0
        link = AsBuiltLink(
            pred_uid=lr.pred_id, succ_uid=lr.succ_id,
            pred_code=_code(lr.pred_id), succ_code=_code(lr.succ_id),
            rel_type=lr.rel_type,
            planned_lag_wd=lr.planned_lag,
            actual_lag_wd=lr.actual_lag,
            tightness_wd=lr.lag_variance,
            pred_anchor_date=pred_anchor.isoformat() if pred_anchor else None,
            succ_anchor_date=succ_anchor.isoformat() if succ_anchor else None,
            lag_calendar=lr.lag_calendar_id,
            lag_calendar_fallback=lr.lag_calendar_fallback,
            contradicted=contradicted,
            is_gap=(not contradicted) and lr.lag_variance > gap_threshold_wd,
        )
        if contradicted:
            contradicted_all.append(link)
            incoming_contradicted.setdefault(lr.succ_id, []).append(link)
        else:
            all_links.append(link)
            incoming_actualized.setdefault(lr.succ_id, []).append(link)

    # -- end anchor -------------------------------------------------------
    end_act, resolution = _resolve_end(sched, started, end)
    end_uid = end_act.uid

    # -- end-anchor calendar resources for span measurement ---------------
    end_cid = end_act.calendar_uid
    span_cal = registry.get(end_cid) if end_cid else None
    span_table = registry.get_workday_table(end_cid) if end_cid else None
    if span_cal is None or span_table is None:
        span_cal, span_table = ei.calendar, ei.workday_table

    def _span(start_act: Activity) -> Optional[float]:
        start_as = _as_date(start_act.actual_start) or _as_date(start_act.actual_finish)
        end_af = _as_date(end_act.actual_finish) or _as_date(end_act.actual_start)
        if start_as is None or end_af is None:
            return None
        try:
            end_n = date_to_workday(end_af, span_cal, span_table, is_start=False)
            start_n = date_to_workday(start_as, span_cal, span_table, is_start=True)
        except ValueError:
            return None
        return float(end_n - start_n)

    # -- backward branching walk -----------------------------------------
    def _break_reason(uid: str) -> str:
        incoming = incoming_rels.get(uid, [])
        if not incoming:
            return "no actualized predecessor link"
        # a real incoming exists but no actualized link was traversable
        if any(pred_uid not in started_uids for pred_uid, _ in incoming):
            return "predecessor not started"
        return "no actualized predecessor link"

    def _dedupe_by_pred(links: list[AsBuiltLink]) -> list[AsBuiltLink]:
        seen: set[str] = set()
        out: list[AsBuiltLink] = []
        for l in sorted(links, key=lambda x: (x.pred_code, x.rel_type)):
            if l.pred_uid in seen:
                continue
            seen.add(l.pred_uid)
            out.append(l)
        return out

    disclosures = list(ei.disclosures)
    cap_hit = False
    completed: list[dict] = []
    # path dicts hold end->start order; reversed at finalize time
    work: list[dict] = [{
        "nodes": [end_uid], "links": [], "gaps": [], "contra": [],
        "visited": {end_uid}, "break": "",
    }]
    guard = 0
    while work and guard < 200000:
        guard += 1
        path = work.pop()
        head = path["nodes"][-1]
        for cl in incoming_contradicted.get(head, []):
            path["contra"].append(cl)
        cands = [l for l in incoming_actualized.get(head, [])
                 if l.pred_uid not in path["visited"]]
        if not cands:
            path["break"] = _break_reason(head)
            completed.append(path)
            continue
        min_t = min(l.tightness_wd for l in cands)
        chosen = _dedupe_by_pred([l for l in cands if l.tightness_wd == min_t])
        if len(work) + len(completed) + len(chosen) > PATH_CAP:
            cap_hit = True
            path["break"] = f"combinatorial cap ({PATH_CAP} paths) reached"
            completed.append(path)
            continue
        for l in chosen:
            gaps = list(path["gaps"])
            if l.is_gap:
                gaps.append(
                    f"gap: link {l.pred_code}->{l.succ_code} ({l.rel_type}) has "
                    f"+{l.tightness_wd:g} wd of unexplained actual lag "
                    f"(threshold {gap_threshold_wd:g} wd)")
            work.append({
                "nodes": path["nodes"] + [l.pred_uid],
                "links": path["links"] + [l],
                "gaps": gaps,
                "contra": list(path["contra"]),
                "visited": path["visited"] | {l.pred_uid},
                "break": "",
            })
    if cap_hit:
        disclosures.append(
            f"as-built branching hit the {PATH_CAP}-path cap; some tied branches "
            "were not expanded (chains truncated at the cap are flagged in their "
            "break reason).")
    if guard >= 200000:  # pragma: no cover - defensive against pathological graphs
        disclosures.append("as-built walk hit its iteration guard; result may be partial.")

    # -- finalize chains --------------------------------------------------
    reached: set[str] = set()
    finals: list[AsBuiltChain] = []
    for path in completed:
        uids = list(reversed(path["nodes"]))          # start -> end
        links = list(reversed(path["links"]))          # start -> end
        reached.update(uids)
        start_act = ingest_by_uid[uids[0]]
        chain = AsBuiltChain(
            rank=0,
            activity_uids=uids,
            activity_codes=[_code(u) for u in uids],
            links=links,
            span_workdays=_span(start_act),
            span_calendar=(span_cal.name if span_cal else None),
            start_code=_code(uids[0]),
            end_code=_code(end_uid),
            start_actual_start=(_as_date(start_act.actual_start).isoformat()
                                if start_act.actual_start else None),
            end_actual_finish=(_as_date(end_act.actual_finish).isoformat()
                               if end_act.actual_finish else None),
            break_reason=path["break"],
            gap_flags=path["gaps"],
            contradicted_links=path["contra"],
        )
        finals.append(chain)

    # rank by span (longest first); None spans sort last; deterministic tiebreak.
    finals.sort(key=lambda c: (
        -(c.span_workdays if c.span_workdays is not None else -1e18),
        c.start_code, tuple(c.activity_codes)))
    top = finals[:max(1, top_n)]
    for i, c in enumerate(top, start=1):
        c.rank = i

    unreached = len(started_uids - (reached & started_uids))
    summary = {
        "actualized_activities": len(started),
        "actualized_relationships": len(all_links),
        "contradicted_relationships": len(contradicted_all),
        "unreached_started_activities": unreached,
    }

    all_links.sort(key=lambda l: (l.succ_code, l.pred_code, l.rel_type))
    contradicted_all.sort(key=lambda l: (l.succ_code, l.pred_code, l.rel_type))

    return AsBuiltReconstruction(
        label=LABEL,
        end_anchor_code=_code(end_uid),
        end_anchor_uid=end_uid,
        end_anchor_resolution=resolution,
        chains=top,
        links=all_links,
        contradicted_links=contradicted_all,
        summary=summary,
        disclosures=disclosures,
        lag_strategy=ei.lag_strategy.value,
        gap_threshold_wd=gap_threshold_wd,
        top_n=top_n,
    )
