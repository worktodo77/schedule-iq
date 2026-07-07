"""Push-button TIA workbench (backlog S6; ANALYTICS_PROPOSAL.md §6.5).

Forensic purpose
----------------
This module assembles a Time-Impact-Analysis *skeleton* on top of the ported CPM
engine (ADR-0007) and the D6 delay-event mapper.  It runs the two families of
forensic method a TIA can take, side by side, from one set of mapped delay
events:

* **Additive / prospective (MIP 3.6/3.7).**  For each mapped delay event an
  engine *fragnet* is auto-built at the mapped insertion point (a new activity
  whose duration is the event's workday span, tied predecessor-side from the
  mapped activity's predecessors and successor-side into the mapped activity),
  and the target's movement is measured on the update whose window contains the
  event (D4-style data-date bracketing).  Events landing on the same update are
  batched into one table; the table is the *stepped cumulative insertion* — the
  events inserted one at a time in event-date order — with each event's marginal
  contribution and the running cumulative (the classic "order matters" TIA).

* **Subtractive / collapsed as-built (MIP 3.8/3.9).**  From the LAST (most
  as-built) schedule, each event becomes a :class:`~scheduleiq.cpm.collapse.Delay`
  on its mapped activity and the ported collapse engine is run GLOBAL and STEPPED
  per responsible party.  The collapse engine's own guardrails ride through
  untouched: the calibration gate (``calibration_ok``), and the out-of-sequence
  precondition (``is_blocked`` / ``oos_clean``) — when a collapse is BLOCKED it is
  reported blocked and the OOS is NOT auto-acknowledged (that acknowledgment is
  the expert's, per the collapse engine's Step-2 contract).

Presentation discipline (ADR-0007 §4): the tool-of-record dates remain the only
dates reported as *the schedule*.  Every engine figure here — every fragnet
impact and every collapse delta — is a diagnostic delta; the baseline record
dates are carried alongside so the two are never confused.  Method selection
(additive vs subtractive) and event causation are **PRELIMINARY**, reserved to
the expert (CLAUDE.md §4; AACE 29R-03; SCL Protocol 2nd ed.).

Both engine families are gated through the ADR-0007 validation handshake before
any engine number is produced (``handshake="require"``; ``"skip"`` is the
disclosed test/analyst escape hatch).  A refused update propagates
:class:`~scheduleiq.cpm.handshake.HandshakeRefusal` from :func:`run_tia`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..ingest.model import Schedule
from ..intake.events import EventMapResult, map_events
from ..trend.series import SeriesAnalysis
from ..cpm.bridge import EngineInputs, build_engine_inputs
from ..cpm.calendar_ops import build_workday_table
from ..cpm.collapse import CollapseInput, CollapseResult, Delay, ExtractionMode, run_collapse
from ..cpm.engine import run_analysis
from ..cpm.handshake import (HandshakeRefusal, require_valid_handshake,
                             run_handshake)
from ..cpm.models import Activity as CpmActivity, Relationship as CpmRelationship
from ..cpm.results import AnalysisResult
# Reuse impact.py's target-resolution precedence, engine-run wrapper, handshake
# summary, and delta helper so the engine-side analytics modules stay consistent.
from .impact import (_delta, _finish_of, _hs_summary, _record_finish,
                     _resolve_target, _target_wd_table)

# One fragnet / delay per mapped activity, capped (a multi-activity event is a
# candidate list, not a determination — the cap keeps the auto-build honest).
_MAX_MAPPED_PER_EVENT = 3

_PRELIMINARY = (
    "PRELIMINARY — this is a TIA SKELETON: event→fragnet auto-build, per-update "
    "impact, and collapsed as-built variants are diagnostic engine computations. "
    "Method selection (MIP 3.6/3.7 additive vs MIP 3.8/3.9 subtractive) and event "
    "causation/entitlement (EOT, concurrency, quantum) are reserved to the expert "
    "(AACE 29R-03; SCL Protocol 2nd ed.)."
)

_FRAMING = (
    "§6.5 push-button TIA: mapped delay events drive an additive fragnet impact on "
    "each contemporaneous update AND a subtractive collapsed-as-built extraction "
    "from the most as-built schedule. The two are presented side by side for the "
    "expert to select and defend a method; neither is a finding."
)

_PRESENTATION_RULE = (
    "Tool-of-record dates are the schedule; every fragnet impact and collapse "
    "delta below is a diagnostic engine figure only (ADR-0007 §4)."
)


# ---------------------------------------------------------------------------
# party normalization (event responsibility -> collapse party vocabulary)
# ---------------------------------------------------------------------------
_PARTY_SYNONYMS = {
    "OWNER": "OWNER", "EMPLOYER": "OWNER", "CLIENT": "OWNER",
    "CONTRACTOR": "CONTRACTOR",
    "EXCUSABLE": "EXCUSABLE",
    "THIRD PARTY": "THIRD_PARTY", "THIRD_PARTY": "THIRD_PARTY",
    "NEUTRAL": "NEUTRAL",
}


def _norm_party(raw: str) -> str:
    """Map an event's free-text responsibility to the collapse party vocabulary
    (OWNER/CONTRACTOR/EXCUSABLE/THIRD_PARTY); unknown values pass through
    upper-cased so the collapse still filters on them deterministically."""
    key = (raw or "").strip().upper()
    return _PARTY_SYNONYMS.get(key, key or "UNSPECIFIED")


# ---------------------------------------------------------------------------
# result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class FragnetDef:
    """One auto-built fragnet: full traceability from the delay event to the
    engine activity + ties inserted at the mapped insertion point."""
    event_id: str
    event_title: str
    schedule_label: str
    mapped_activity_code: str
    mapped_activity_uid: str
    fragnet_id: str
    duration_workdays: int
    calendar_uid: Optional[str]
    predecessor_ties: list[str]           # pred uids tied into the fragnet
    successor_tie: str                    # the mapped activity uid
    rel_type: str
    responsibility: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_title": self.event_title,
            "schedule_label": self.schedule_label,
            "mapped_activity_code": self.mapped_activity_code,
            "mapped_activity_uid": self.mapped_activity_uid,
            "fragnet_id": self.fragnet_id,
            "duration_workdays": self.duration_workdays,
            "calendar_uid": self.calendar_uid,
            "predecessor_ties": list(self.predecessor_ties),
            "successor_tie": self.successor_tie,
            "rel_type": self.rel_type,
            "responsibility": self.responsibility,
            "note": self.note,
        }


@dataclass
class EventImpactRow:
    """One event's row in an update's stepped cumulative-insertion table.

    ``isolated_delta_workdays`` is the target's movement from inserting THIS
    event's fragnet(s) alone on the baseline; ``marginal_delta_workdays`` is the
    additional movement when this event is inserted on top of the earlier events
    (event-date order); ``cumulative_delta_workdays`` is the running total.  All
    positive = the target moves LATER (the delay pushes it out)."""
    event_id: str
    event_title: str
    isolated_delta_workdays: Optional[int] = None
    marginal_delta_workdays: Optional[int] = None
    cumulative_delta_workdays: Optional[int] = None
    engine_target_finish: Optional[date] = None
    computable: bool = True
    blocking: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_title": self.event_title,
            "isolated_delta_workdays": self.isolated_delta_workdays,
            "marginal_delta_workdays": self.marginal_delta_workdays,
            "cumulative_delta_workdays": self.cumulative_delta_workdays,
            "engine_target_finish": (self.engine_target_finish.isoformat()
                                     if self.engine_target_finish else None),
            "computable": self.computable,
            "blocking": self.blocking,
        }


@dataclass
class UpdateImpact:
    """The additive fragnet impact table for one contemporaneous update."""
    schedule_label: str
    data_date: Optional[date] = None
    target_uid: Optional[str] = None
    target_code: Optional[str] = None
    handshake: Optional[dict[str, Any]] = None
    baseline_engine_target_finish: Optional[date] = None
    record_target_finish: Optional[date] = None
    baseline_computable: bool = True
    baseline_blocking: str = ""
    rows: list[EventImpactRow] = field(default_factory=list)
    cumulative_total_workdays: Optional[int] = None
    identity_holds: Optional[bool] = None
    disclosures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_label": self.schedule_label,
            "data_date": self.data_date.isoformat() if self.data_date else None,
            "target": {"uid": self.target_uid, "code": self.target_code},
            "handshake": self.handshake,
            "baseline_engine_target_finish": (
                self.baseline_engine_target_finish.isoformat()
                if self.baseline_engine_target_finish else None),
            "record_target_finish": (self.record_target_finish.isoformat()
                                     if self.record_target_finish else None),
            "baseline_computable": self.baseline_computable,
            "baseline_blocking": self.baseline_blocking,
            "rows": [r.to_dict() for r in self.rows],
            "cumulative_total_workdays": self.cumulative_total_workdays,
            "identity_holds": self.identity_holds,
            "identity": "sum(marginal_delta_workdays) == cumulative_total_workdays",
            "disclosures": list(self.disclosures),
        }


@dataclass
class TiaResult:
    """The full push-button TIA: fragnet definitions, per-update additive impact
    tables, and the subtractive collapsed-as-built variants."""
    mode: str = "prospective"
    target_uid: Optional[str] = None
    target_code: Optional[str] = None
    target_name: Optional[str] = None
    as_built_schedule_label: str = ""

    handshakes: dict[str, Any] = field(default_factory=dict)
    fragnets: list[FragnetDef] = field(default_factory=list)
    updates: list[UpdateImpact] = field(default_factory=list)
    # {party: {"global": CollapseResult.to_dict(), "stepped": CollapseResult.to_dict()}}
    collapse: dict[str, dict[str, Any]] = field(default_factory=dict)
    disclosures: list[str] = field(default_factory=list)
    preliminary: str = _PRELIMINARY
    framing: str = _FRAMING

    def update(self, label: str) -> Optional[UpdateImpact]:
        for u in self.updates:
            if u.schedule_label == label:
                return u
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": ("MIP 3.6/3.7 additive fragnet TIA + MIP 3.8/3.9 collapsed "
                       "as-built (subtractive)"),
            "mode": self.mode,
            "presentation_rule": _PRESENTATION_RULE,
            "target": {"uid": self.target_uid, "code": self.target_code,
                       "name": self.target_name},
            "as_built_schedule_label": self.as_built_schedule_label,
            "handshakes": {k: self.handshakes[k] for k in sorted(self.handshakes)},
            "fragnets": [f.to_dict() for f in self.fragnets],
            "updates": [u.to_dict() for u in self.updates],
            "collapse": {p: self.collapse[p] for p in sorted(self.collapse)},
            "disclosures": list(self.disclosures),
            "preliminary": self.preliminary,
            "framing": self.framing,
        }


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _as_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def _order_key(s: Schedule):
    return (s.data_date or s.export_date or s.start_date or datetime.max)


def _event_workdays(cal, start: Optional[date], finish: Optional[date]) -> int:
    """Inclusive count of the insertion activity's own working days spanned by the
    event [start, finish].  Returns 0 when dates are missing or inverted."""
    if start is None or finish is None or finish < start:
        return 0
    n, d = 0, start
    guard = 0
    while d <= finish and guard < 4000:
        if cal is None or cal.is_workday(d):
            n += 1
        d += timedelta(days=1)
        guard += 1
    return n


def _run_engine(ei: EngineInputs, extra_acts: list[CpmActivity],
                extra_rels: list[CpmRelationship]
                ) -> tuple[Optional[AnalysisResult], str]:
    """Run the baseline engine (constraints on, the file's statusing mode) with the
    fragnet activities/relationships appended.  Degrades per-scenario (records the
    blocking issue instead of raising), matching impact.py."""
    try:
        res = run_analysis(
            activities=ei.activities + extra_acts,
            relationships=ei.relationships + extra_rels,
            project_start=ei.project_start,
            workday_table=ei.workday_table,
            calendar=ei.calendar,
            convention=ei.convention,
            calendar_registry=ei.calendar_registry,
            lag_strategy=ei.lag_strategy,
            constraints=ei.constraints or None,
            statusing_mode=ei.statusing_mode,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"engine error: {exc}"
    if not res.is_valid:
        issues = [f"{i.issue_code}: {i.message}"
                  for i in res.validation.issues if i.blocking]
        return None, "; ".join(issues) or "network invalid (no blocking detail)"
    return res, ""


def _build_fragnet(ev, mapped_uid: str, mapped_code: str, dur_wd: int,
                   ei: EngineInputs, sched_label: str, party: str,
                   cpm_by_uid: dict[str, CpmActivity]
                   ) -> tuple[CpmActivity, list[CpmRelationship], FragnetDef]:
    """Build one fragnet ahead of the mapped activity: a new activity (event id,
    duration = event workdays) tied predecessor-side from the mapped activity's
    predecessors and successor-side into the mapped activity (FS default)."""
    preds = [r for r in ei.relationships if r.succ_id == mapped_uid]
    frag_id = f"FRAG::{ev.event_id}::{mapped_uid}"
    cal_id = cpm_by_uid[mapped_uid].calendar_id
    frag_act = CpmActivity(act_id=frag_id, original_duration=dur_wd, calendar_id=cal_id)
    rels = [CpmRelationship(r.pred_id, frag_id, "FS", 0) for r in preds]
    rels.append(CpmRelationship(frag_id, mapped_uid, "FS", 0))
    note = ("fragnet inserted ahead of the mapped activity (FS): the mapped "
            "activity's predecessors drive the fragnet, and the fragnet drives the "
            "mapped activity — the additive/prospective insertion (MIP 3.6/3.7)")
    if not preds:
        note += "; mapped activity had no predecessor — fragnet roots at project start"
    fdef = FragnetDef(
        event_id=ev.event_id, event_title=ev.title, schedule_label=sched_label,
        mapped_activity_code=mapped_code, mapped_activity_uid=mapped_uid,
        fragnet_id=frag_id, duration_workdays=dur_wd, calendar_uid=cal_id,
        predecessor_ties=[r.pred_id for r in preds], successor_tie=mapped_uid,
        rel_type="FS", responsibility=party, note=note,
    )
    return frag_act, rels, fdef


def _mapped_activities(ev, sched: Schedule) -> list:
    """The mapped activities (capped) for an event on its window schedule, resolved
    from the mapping's matched codes to the schedule's activities."""
    by_code = {a.code: a for a in sched.real_activities}
    out, seen = [], set()
    for m in ev.matches:
        a = by_code.get(m.activity_code)
        if a is not None and a.uid not in seen:
            out.append(a)
            seen.add(a.uid)
        if len(out) >= _MAX_MAPPED_PER_EVENT:
            break
    return out


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def run_tia(schedules: list[Schedule], events_csv_or_mappings, *,
            target: Optional[str] = None, mode: str = "prospective",
            handshake: str = "require", threshold_pct: float = 99.0) -> TiaResult:
    """Assemble the push-button TIA for ``schedules`` and a set of mapped delay
    events (a CSV path or a pre-built :class:`EventMapResult`).

    ``handshake="require"`` gates every schedule used on the ADR-0007 validation
    handshake and re-raises :class:`HandshakeRefusal` from the first update that
    does not handshake (the caller handles it).  ``handshake="skip"`` bypasses the
    gate (disclosed) and degrades per-scenario.
    """
    if handshake not in ("require", "skip"):
        raise ValueError(f"handshake must be 'require' or 'skip', got {handshake!r}")
    if mode not in ("prospective", "retrospective"):
        raise ValueError(f"mode must be 'prospective' or 'retrospective', got {mode!r}")

    out = TiaResult(mode=mode)
    if not schedules:
        out.disclosures.append("no schedules provided; nothing to analyze.")
        return out

    ordered = sorted(schedules, key=_order_key)
    last = ordered[-1]
    out.as_built_schedule_label = last.label()
    by_label = {s.label(): s for s in ordered}
    if len(by_label) < len(ordered):
        out.disclosures.append(
            "two or more schedules share a label (same project + data date); "
            "events are mapped to the first schedule carrying that label.")

    # -- event mapping (accept a CSV path or a pre-built EventMapResult) --------
    if isinstance(events_csv_or_mappings, EventMapResult):
        emr = events_csv_or_mappings
    else:
        emr = map_events(SeriesAnalysis(schedules=ordered), events_csv_or_mappings)
    if emr.reason:
        out.disclosures.append(f"event mapping: {emr.reason}")

    # -- headline target (record dates) from the most as-built schedule --------
    tgt, how = _resolve_target(last, target)
    if tgt is not None:
        out.target_uid, out.target_code, out.target_name = tgt.uid, tgt.code, tgt.name
    else:
        out.disclosures.append(f"headline target unresolved on the as-built schedule: {how}")

    # -- handshake gate: every schedule used (propagates from the first refusal) -
    if len(ordered) == 1:
        out.disclosures.append(
            "single schedule provided (MIP 3.6): the additive impact runs against "
            "that one baseline; the collapsed-as-built variant uses the same file.")
    for s in ordered:
        if handshake == "require":
            hs = require_valid_handshake(s, threshold_pct=threshold_pct)  # may raise
            out.handshakes[s.label()] = _hs_summary(hs)
        else:
            try:
                out.handshakes[s.label()] = _hs_summary(
                    run_handshake(s, threshold_pct=threshold_pct))
            except Exception as exc:  # pragma: no cover - defensive
                out.handshakes[s.label()] = {"error": f"handshake unavailable: {exc}"}
    if handshake == "skip":
        out.disclosures.append(
            "handshake='skip': the ADR-0007 validation gate was BYPASSED (analyst/"
            "test escape hatch). Engine deltas are unvalidated against the record; "
            "invalid-network scenarios degrade to 'not computable'.")

    # -- group events by the update whose window they map to -------------------
    events_by_label: dict[str, list] = {}
    for ev in emr.events:
        s = by_label.get(ev.schedule_label)
        if s is None:
            out.disclosures.append(
                f"event {ev.event_id!r} mapped to schedule {ev.schedule_label!r}, "
                "which is not among the provided schedules; skipped.")
            continue
        if not ev.matches:
            out.disclosures.append(
                f"event {ev.event_id!r} ({ev.title}) mapped to no activity on "
                f"{ev.schedule_label!r} (no date overlap / keyword hit); no fragnet built.")
            continue
        events_by_label.setdefault(ev.schedule_label, []).append(ev)

    # -- additive fragnet impact per update ------------------------------------
    for s in ordered:
        evs = events_by_label.get(s.label())
        if not evs:
            continue
        out.updates.append(
            _impact_update(s, evs, target, out.handshakes.get(s.label()), out))

    # -- subtractive collapsed as-built variants (MIP 3.8/3.9) -----------------
    out.collapse = _collapse_variants(last, emr, out)

    return out


# ---------------------------------------------------------------------------
# additive impact of one update
# ---------------------------------------------------------------------------
def _impact_update(sched: Schedule, evs: list, target: Optional[str],
                   hs_summary: Optional[dict[str, Any]], out: TiaResult
                   ) -> UpdateImpact:
    ui = UpdateImpact(schedule_label=sched.label(),
                      data_date=_as_date(sched.data_date), handshake=hs_summary)
    ei = build_engine_inputs(sched)
    cpm_by_uid = {a.act_id: a for a in ei.activities}

    tgt, how = _resolve_target(sched, target)
    if tgt is None:
        ui.baseline_computable = False
        ui.baseline_blocking = f"target unresolved: {how}"
        ui.disclosures.append(ui.baseline_blocking)
        return ui
    ui.target_uid, ui.target_code = tgt.uid, tgt.code
    ui.record_target_finish = _as_date(_record_finish(tgt))
    wd_tbl = _target_wd_table(ei, tgt)

    base, base_blk = _run_engine(ei, [], [])
    if base is None:
        ui.baseline_computable = False
        ui.baseline_blocking = base_blk
        ui.disclosures.append(f"baseline engine run not computable: {base_blk}")
        return ui
    base_ef = _finish_of(base, tgt.uid)
    ui.baseline_engine_target_finish = base_ef

    # event-date order (start, then finish, then id) — the stepped-insertion order
    def _ev_key(ev):
        d = _as_date(ev.start) or _as_date(ev.finish) or date.max
        return (d, ev.event_id)
    evs_ordered = sorted(evs, key=_ev_key)

    ui.disclosures.append(
        "the impact table is the STEPPED cumulative insertion (events in event-date "
        "order); order matters — each row's marginal is its contribution GIVEN the "
        "earlier insertions, and the isolated column is its standalone effect.")

    cum_acts: list[CpmActivity] = []
    cum_rels: list[CpmRelationship] = []
    prev_cum = 0
    marginal_sum = 0
    all_computable = True
    for ev in evs_ordered:
        mapped = _mapped_activities(ev, sched)
        party = _norm_party(ev.responsibility)
        row = EventImpactRow(event_id=ev.event_id, event_title=ev.title)
        if len(ev.matches) > _MAX_MAPPED_PER_EVENT:
            ui.disclosures.append(
                f"event {ev.event_id!r} mapped to {len(ev.matches)} activities; "
                f"capped at {_MAX_MAPPED_PER_EVENT} fragnets (candidate list, not a "
                "determination).")

        ev_acts: list[CpmActivity] = []
        ev_rels: list[CpmRelationship] = []
        for a in mapped:
            cal = (ei.calendar_registry.get(cpm_by_uid[a.uid].calendar_id)
                   or ei.calendar)
            dur = _event_workdays(cal, _as_date(ev.start), _as_date(ev.finish))
            if dur <= 0:
                ui.disclosures.append(
                    f"event {ev.event_id!r} on {a.code}: non-positive workday "
                    "duration (missing/inverted dates); fragnet skipped.")
                continue
            fa, fr, fdef = _build_fragnet(ev, a.uid, a.code, dur, ei, sched.label(),
                                          party, cpm_by_uid)
            ev_acts.append(fa)
            ev_rels.extend(fr)
            out.fragnets.append(fdef)

        if not ev_acts:
            row.computable, row.blocking = False, "no fragnet built for this event"
            row.isolated_delta_workdays = 0
            row.marginal_delta_workdays = 0
            row.cumulative_delta_workdays = prev_cum
            ui.rows.append(row)
            continue

        # isolated: this event's fragnet(s) alone on the baseline
        iso, iso_blk = _run_engine(ei, ev_acts, ev_rels)
        if iso is not None:
            iso_wd, _ = _delta(wd_tbl, base_ef, _finish_of(iso, tgt.uid))
            row.isolated_delta_workdays = iso_wd

        # cumulative: this event on top of the earlier events (stepped insertion)
        cum_acts = cum_acts + ev_acts
        cum_rels = cum_rels + ev_rels
        cum, cum_blk = _run_engine(ei, cum_acts, cum_rels)
        if cum is None:
            row.computable, row.blocking = False, cum_blk
            all_computable = False
            ui.rows.append(row)
            continue
        cum_ef = _finish_of(cum, tgt.uid)
        cum_wd, _ = _delta(wd_tbl, base_ef, cum_ef)
        row.engine_target_finish = cum_ef
        row.cumulative_delta_workdays = cum_wd
        if cum_wd is not None:
            row.marginal_delta_workdays = cum_wd - prev_cum
            marginal_sum += row.marginal_delta_workdays
            prev_cum = cum_wd
        ui.rows.append(row)

    ui.cumulative_total_workdays = prev_cum
    if all_computable:
        # exact by construction (telescoping marginals) — assert loudly
        ui.identity_holds = (marginal_sum == prev_cum)
        assert ui.identity_holds, (
            f"cumulative identity violated: Σmarginal {marginal_sum} != "
            f"cumulative {prev_cum}")
    else:
        ui.disclosures.append(
            "one or more cumulative steps were not computable; the Σmarginal == "
            "cumulative identity is asserted only over the computable rows.")
    return ui


# ---------------------------------------------------------------------------
# subtractive collapsed as-built variants
# ---------------------------------------------------------------------------
def _collapse_variants(last: Schedule, emr: EventMapResult, out: TiaResult
                       ) -> dict[str, dict[str, Any]]:
    """From the LAST (most as-built) schedule, turn each event into a Delay on its
    mapped activity and run the ported collapse GLOBAL + STEPPED per party.  The
    collapse engine's calibration gate + OOS block ride through untouched."""
    ei = build_engine_inputs(last)
    cpm_by_uid = {a.act_id: a for a in ei.activities}
    code_to_uid = {a.code: a.uid for a in last.real_activities}

    all_delays: list[Delay] = []
    parties: set[str] = set()
    for ev in emr.events:
        party = _norm_party(ev.responsibility)
        codes = [m.activity_code for m in ev.matches][:_MAX_MAPPED_PER_EVENT]
        for code in codes:
            uid = code_to_uid.get(code)
            if uid is None:
                out.disclosures.append(
                    f"collapse: event {ev.event_id!r} activity {code!r} is not in the "
                    f"as-built schedule {last.label()!r}; delay dropped.")
                continue
            cal = ei.calendar_registry.get(cpm_by_uid[uid].calendar_id) or ei.calendar
            dur = _event_workdays(cal, _as_date(ev.start), _as_date(ev.finish))
            if dur <= 0:
                out.disclosures.append(
                    f"collapse: event {ev.event_id!r} on {code}: non-positive workday "
                    "duration; delay dropped.")
                continue
            all_delays.append(Delay(uid, party, dur, ev.title))
            parties.add(party)

    if not all_delays:
        out.disclosures.append(
            "collapse: no delays resolved against the as-built schedule; the "
            "collapsed-as-built variant was not run.")
        return {}

    out.disclosures.append(
        "collapse: the subtractive but-for rebuilds a clean planning network from "
        "the as-built ORIGINAL DURATIONS (unstatused) and re-runs CPM; its finish is "
        "the pure-logic finish, distinct from the additive impact's statused baseline. "
        "The engine's calibration gate and OOS block are carried through — a BLOCKED "
        "collapse is reported blocked and the OOS is NOT auto-acknowledged (that "
        "acknowledgment is the expert's).")

    variants: dict[str, dict[str, Any]] = {}
    for party in sorted(parties):
        variants[party] = {}
        for mode_name, mode in (("global", ExtractionMode.GLOBAL),
                                ("stepped", ExtractionMode.STEPPED)):
            inp = CollapseInput(
                activities=ei.activities, relationships=ei.relationships,
                project_start=ei.project_start, workday_table=ei.workday_table,
                calendar=ei.calendar, calendar_registry=ei.calendar_registry,
                convention=ei.convention, delays=all_delays, party=party, mode=mode,
            )
            res: CollapseResult = run_collapse(inp)
            variants[party][mode_name] = res.to_dict()
            if res.is_blocked:
                out.disclosures.append(
                    f"collapse ({party}, {mode_name}): BLOCKED — schedule is out of "
                    "sequence and not acknowledged; no but-for computed (§3.9.E.5).")
            elif not res.calibration_ok:
                out.disclosures.append(
                    f"collapse ({party}, {mode_name}): calibration mismatch — the "
                    "but-for delta is measured in the CPM model and flagged.")
    return variants
