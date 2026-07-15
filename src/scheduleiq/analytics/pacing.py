"""S2 — pacing and constructive-acceleration screens (ANALYTICS_PROPOSAL.md §6.3).

Both screens are *preliminary triage instruments*, not opinions.  The pacing
defense in particular turns on contemporaneous intent (did the contractor
consciously slow non-critical work, aware of a concurrent excusable/critical
delay, while retaining the ability to recover) — something no schedule-data
screen can establish on its own.  Everything here surfaces the *pattern* in
the data (float, deceleration, timing, resource retention) and leaves intent
to the expert, per CLAUDE.md rule 4.

Pacing candidates (``pacing_candidates``)
------------------------------------------
For each consecutive update pair, non-critical chains (activities with more
than 5 working days of total float in the *earlier* update, connected to one
another via relationships) are screened for deceleration — remaining
duration growth, a progress-rate collapse relative to the prior window, or an
unexplained rightward forecast push — occurring while a parallel critical
delay ran (the project's forecast finish slipped, or the minimum float among
currently-critical activities worsened).  Every candidate carries the full
evidence bundle a pacing analysis needs to start from: the chain, the float
available when the deceleration began, the measured deceleration, the
concurrent critical slip, whether an events entry evidences contemporaneous
awareness, and a reversibility read from resource retention.

Constructive-acceleration candidates (``acceleration_candidates``)
--------------------------------------------------------------------
For each update pair, counts how many of five independent signals fired
(duration compression on incomplete work, calendar upgrades, resource
increases on incomplete work, an out-of-sequence spike, and a DUR-04
remaining-duration-compression finding); two or more make the window a
candidate, strengthened when it follows an event tagged
``responsibility=Owner`` (a denied/late EOT signal is the classic predicate).

Both functions accept ``events`` as the list of dicts produced by
``scheduleiq.intake.events.load_events_csv`` (not a path) so callers who have
already loaded the events list once can reuse it; ``run_pacing`` loads the
CSV itself.  Every function degrades gracefully: on missing/short series or
malformed inputs the result is an empty list (or a ``PacingResult`` carrying
a ``reason``), never an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..intake._util import working_days_between
from ..intake.events import load_events_csv
from ..compare.diff import match_activity

NONCRIT_FLOAT_THRESHOLD_DAYS = 5.0
DECEL_FORECAST_PUSH_DAYS = 5.0
DECEL_RATE_DROP_FRACTION = 0.5
RESOURCE_RETENTION_FRACTION = 0.9
OWNER_EVENT_LOOKBACK_DAYS = 90

PACING_CAPTION = ("pacing candidates — preliminary screening; the pacing "
                  "defense requires contemporaneous intent evidence — "
                  "reserved to the expert.")
ACCELERATION_CAPTION = PACING_CAPTION   # same preliminary framing, per spec


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class PacingCandidate:
    window_label: str
    chain_codes: list = field(default_factory=list)
    float_at_start_days: Optional[float] = None
    deceleration_measure: str = ""
    concurrent_critical_slip: str = ""
    contemporaneous_awareness: bool = False
    contemporaneous_events: list = field(default_factory=list)
    reversibility: str = ""


@dataclass
class AccelerationCandidate:
    window_label: str
    signals: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    following_owner_event: bool = False
    owner_event_titles: list = field(default_factory=list)


@dataclass
class PacingResult:
    pacing: list = field(default_factory=list)          # list[PacingCandidate]
    acceleration: list = field(default_factory=list)     # list[AccelerationCandidate]
    caption: str = PACING_CAPTION
    reason: str = ""


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _critical_delay_signal(cs) -> tuple[bool, str]:
    """Was there a parallel critical delay in this window: the project
    forecast finish slipped, or the minimum float among currently-critical
    activities worsened?"""
    e, l = cs.earlier, cs.later
    parts = []
    slipped = False
    if e.finish_date and l.finish_date:
        slip = (l.finish_date - e.finish_date).days
        if slip > 0:
            slipped = True
            parts.append(f"project forecast finish slipped {slip}d "
                         f"({e.finish_date.date()} -> {l.finish_date.date()})")
    crit_codes = cs.critical_before | cs.critical_after
    if crit_codes:
        deltas = [cs.float_deltas[c] for c in crit_codes if c in cs.float_deltas]
        if deltas:
            min_delta = min(deltas)
            if min_delta < 0:
                slipped = True
                parts.append("minimum total float among critical-path "
                             f"activities worsened {min_delta:+.1f}d")
    return slipped, ("; ".join(parts) if parts else "no concurrent critical slip detected")


def _noncritical_chains(sched, threshold_days: float = NONCRIT_FLOAT_THRESHOLD_DAYS
                        ) -> list:
    """Connected components (via relationships) among incomplete real
    activities whose total float exceeds ``threshold_days`` — the
    non-critical chain population pacing screens for deceleration."""
    pop = [a for a in sched.real_activities if not a.completed]
    tf = {a.uid: a.total_float_days(sched.cal_for(a)) for a in pop}
    noncrit = {uid for uid, fl in tf.items() if fl is not None and fl > threshold_days}
    if not noncrit:
        return []
    adj: dict = {uid: set() for uid in noncrit}
    for r in sched.relationships:
        if r.pred_uid in noncrit and r.succ_uid in noncrit:
            adj[r.pred_uid].add(r.succ_uid)
            adj[r.succ_uid].add(r.pred_uid)
    seen: set = set()
    chains = []
    for uid in noncrit:
        if uid in seen:
            continue
        stack, comp = [uid], []
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            comp.append(u)
            stack.extend(adj[u] - seen)
        chains.append(comp)
    return chains


def _touched_by_logic_or_def_change(cs, activity) -> bool:
    """Return whether a revision touched ``activity`` using UID-first identity.

    Change-register codes remain useful display labels, but a stable UID re-code
    must not turn an otherwise unexplained forecast push into a false negative.
    Legacy rows without UIDs retain the old unambiguous code fallback.
    """
    uid = getattr(activity, "uid", None)
    code = getattr(activity, "code", "")
    for fc in list(cs.duration_changes) + list(cs.constraint_changes) + list(cs.calendar_changes):
        if uid and getattr(fc, "uid", None):
            if fc.uid == uid:
                return True
        elif fc.code == code:
            return True
    for lc in cs.logic_changes:
        if uid and (getattr(lc, "pred_uid", None) or getattr(lc, "succ_uid", None)):
            if lc.pred_uid == uid or lc.succ_uid == uid:
                return True
        elif lc.pred_code == code or lc.succ_code == code:
            return True
    return False


def _overlap(events, start: Optional[datetime], finish: Optional[datetime]
            ) -> tuple[bool, list]:
    """Events whose window overlaps [start, finish] — contemporaneous
    awareness evidence for a pacing candidate."""
    if not events or not start or not finish:
        return False, []
    hits = []
    for ev in events:
        es, ef = ev.get("start"), ev.get("finish")
        if es and ef and es <= finish and start <= ef:
            hits.append(ev.get("title") or ev.get("event_id") or "")
        elif es and start <= es <= finish:
            hits.append(ev.get("title") or ev.get("event_id") or "")
        elif ef and start <= ef <= finish:
            hits.append(ev.get("title") or ev.get("event_id") or "")
    return (len(hits) > 0), hits


def _following_owner_event(events, start: Optional[datetime], finish: Optional[datetime]
                           ) -> tuple[bool, list]:
    """An Owner-tagged event that fell on/before this window (i.e. could have
    prompted acceleration) within a bounded lookback."""
    if not events or not finish:
        return False, []
    hits = []
    for ev in events:
        if (ev.get("responsibility") or "").strip().lower() != "owner":
            continue
        ref = ev.get("finish") or ev.get("start")
        if ref is None or ref > finish:
            continue
        if start is not None and ref < start - timedelta(days=OWNER_EVENT_LOOKBACK_DAYS):
            continue
        hits.append(ev.get("title") or ev.get("event_id") or "")
    return (len(hits) > 0), hits


def _reversibility(chain_acts: list, later_acts: list) -> str:
    """Read resource retention across a chain with UID-first pair matching."""
    tot_e = sum(sum(r.budget_units for r in a.resources) for a in chain_acts)
    matched_l = [a for a in later_acts if a is not None]
    if not matched_l:
        return "no later-update data for this chain"
    tot_l = sum(sum(r.budget_units for r in a.resources) for a in matched_l)
    if tot_e == 0 and tot_l == 0:
        return "no resource data available"
    if tot_l >= tot_e * RESOURCE_RETENTION_FRACTION:
        return (f"resources retained ({tot_e:.0f} -> {tot_l:.0f} budget units) "
                "— consistent with reversibility")
    return (f"resources reduced/removed ({tot_e:.0f} -> {tot_l:.0f} budget units) "
            "— reduces reversibility")


# --------------------------------------------------------------------------
# pacing_candidates
# --------------------------------------------------------------------------
def pacing_candidates(sa, events: Optional[list] = None) -> list:
    """Screen every update pair for textbook pacing patterns.  See module
    docstring for the deceleration/concurrency criteria.  Never raises: a
    malformed changeset or missing data simply yields no candidate for that
    window."""
    changesets = getattr(sa, "changesets", [])
    out: list = []
    for i, cs in enumerate(changesets):
        try:
            e, l = cs.earlier, cs.later
            delayed, crit_desc = _critical_delay_signal(cs)
            if not delayed:
                continue
            chains = _noncritical_chains(e)
            if not chains:
                continue
            prev_cs = changesets[i - 1] if i > 0 else None
            for chain_uids in chains:
                chain_acts_e = [e.activities[u] for u in chain_uids]
                chain_acts_l = [match_activity(l, a) for a in chain_acts_e]
                codes = sorted(a.code for a in chain_acts_e)
                measures = []

                # (a) remaining-duration growth
                rd_e = sum(a.remaining_duration_hours for a in chain_acts_e)
                matched_l = [a for a in chain_acts_l if a is not None]
                rd_l = sum(a.remaining_duration_hours for a in matched_l)
                if matched_l and rd_l > rd_e + 1e-6:
                    measures.append(f"remaining duration grew {rd_e:.0f}h -> {rd_l:.0f}h "
                                    "across the chain")

                # (b) progress-rate collapse vs the prior window (>= 50% drop)
                if prev_cs is not None:
                    prev_acts = [match_activity(prev_cs.earlier, a)
                                 for a in chain_acts_e]
                    if all(a is not None for a in prev_acts) and matched_l:
                        rd_prev = sum(a.remaining_duration_hours for a in prev_acts)
                        days_prev = working_days_between(None, prev_cs.earlier.data_date,
                                                         e.data_date)
                        days_cur = working_days_between(None, e.data_date, l.data_date)
                        if days_prev and days_cur and days_prev > 0 and days_cur > 0:
                            rate_prev = (rd_prev - rd_e) / days_prev
                            rate_cur = (rd_e - rd_l) / days_cur
                            if rate_prev > 0 and rate_cur <= DECEL_RATE_DROP_FRACTION * rate_prev:
                                measures.append(
                                    f"chain progress rate dropped from {rate_prev:.1f}h/wd "
                                    f"to {rate_cur:.1f}h/wd (>= 50% reduction vs the prior "
                                    "window)")

                # (c) unexplained rightward forecast push
                for ea, la in zip(chain_acts_e, chain_acts_l):
                    code = ea.code
                    fc_e = ea.early_finish or ea.planned_finish
                    fc_l = (la.early_finish or la.planned_finish) if la else None
                    if fc_e and fc_l:
                        cal = l.cal_for(la) if la else None
                        push = working_days_between(cal, fc_e, fc_l)
                        if push is not None and push > DECEL_FORECAST_PUSH_DAYS \
                                and not _touched_by_logic_or_def_change(cs, ea):
                            measures.append(
                                f"{code} forecast finish pushed right {push:.1f} working "
                                "days with no logic/duration/constraint/calendar change")

                if not measures:
                    continue

                floats = [a.total_float_days(e.cal_for(a)) for a in chain_acts_e]
                floats = [f for f in floats if f is not None]
                float_start = min(floats) if floats else None
                awareness, ev_titles = _overlap(events, e.data_date, l.data_date)
                reversibility = _reversibility(chain_acts_e, chain_acts_l)

                out.append(PacingCandidate(
                    window_label=f"{e.label()} -> {l.label()}",
                    chain_codes=codes,
                    float_at_start_days=float_start,
                    deceleration_measure="; ".join(measures),
                    concurrent_critical_slip=crit_desc,
                    contemporaneous_awareness=awareness,
                    contemporaneous_events=ev_titles,
                    reversibility=reversibility,
                ))
        except Exception:                # a broken window must never sink the screen
            continue
    return out


# --------------------------------------------------------------------------
# acceleration_candidates
# --------------------------------------------------------------------------
def _log07_value(assessments, sched) -> Optional[float]:
    for a in assessments:
        if getattr(a, "schedule", None) is sched:
            r = a.result("LOG-07") if hasattr(a, "result") else None
            return r.value if r else None
    return None


def acceleration_candidates(sa, events: Optional[list] = None) -> list:
    """Screen every update pair for >= 2 of the five constructive-
    acceleration signals.  Carries the same preliminary caption as
    ``pacing_candidates`` (``PACING_CAPTION`` / ``ACCELERATION_CAPTION``).
    Never raises."""
    changesets = getattr(sa, "changesets", [])
    assessments = getattr(sa, "assessments", [])
    series_results = getattr(sa, "series_results", [])
    dur04 = next((r for r in series_results if getattr(r.check, "id", None) == "DUR-04"), None)

    out: list = []
    for cs in changesets:
        try:
            e, l = cs.earlier, cs.later
            e_by_code = {a.code: a for a in e.activities.values()}
            l_by_code = {a.code: a for a in l.activities.values()}
            signals, evidence = [], []

            # 1: duration compression on incomplete work
            comp = []
            for ch in cs.duration_changes:
                la = l_by_code.get(ch.code)
                if la is None or la.completed:
                    continue
                try:
                    before = float(str(ch.before).rstrip("h"))
                    after = float(str(ch.after).rstrip("h"))
                except ValueError:
                    continue
                if after < before:
                    comp.append(ch.code)
            if comp:
                signals.append("duration compression on incomplete work")
                evidence.extend(comp)

            # 2: calendar upgrades (definition edits, or activity moved to a
            #    calendar with more weekly hours)
            upgrades = []
            for fc in cs.calendar_def_changes:
                if fc.field in ("hours per day", "workdays per week"):
                    try:
                        if float(fc.after) > float(fc.before):
                            upgrades.append(f"{fc.code}: {fc.field} {fc.before} -> {fc.after}")
                    except (ValueError, TypeError):
                        pass
            cal_by_name = {}
            for c in list(e.calendars.values()) + list(l.calendars.values()):
                if c.name:
                    cal_by_name.setdefault(c.name, c)
            for fc in cs.calendar_changes:
                cb, ca = cal_by_name.get(fc.before), cal_by_name.get(fc.after)
                if cb and ca and ca.hours_per_week > cb.hours_per_week:
                    upgrades.append(f"{fc.code}: calendar {fc.before} -> {fc.after} "
                                    "(longer calendar)")
            if upgrades:
                signals.append("calendar upgrade(s)")
                evidence.extend(upgrades)

            # 3: resource increases on incomplete work
            res_inc = []
            for code, la in l_by_code.items():
                if la.completed:
                    continue
                ea = e_by_code.get(code)
                if ea is None:
                    continue
                bu_e = sum(r.budget_units for r in ea.resources)
                bu_l = sum(r.budget_units for r in la.resources)
                if bu_l > bu_e + 1e-6:
                    res_inc.append(code)
            if res_inc:
                signals.append("resource increase on incomplete work")
                evidence.extend(res_inc)

            # 4: out-of-sequence spike (LOG-07 count up vs the prior update)
            oos_e, oos_l = _log07_value(assessments, e), _log07_value(assessments, l)
            if oos_e is not None and oos_l is not None and oos_l > oos_e:
                signals.append(f"out-of-sequence finding count rose ({oos_e:.0f} -> {oos_l:.0f})")

            # 5: remaining-duration compression (DUR-04 branch findings, this window)
            if dur04 is not None:
                hits = [f.object_id for f in dur04.findings
                       if str(f.detail).endswith(f"({l.label()})")]
                if hits:
                    signals.append("DUR-04 remaining-duration compression finding(s)")
                    evidence.extend(hits)

            if len(signals) < 2:
                continue

            owner_flag, owner_titles = _following_owner_event(events, e.data_date, l.data_date)
            out.append(AccelerationCandidate(
                window_label=f"{e.label()} -> {l.label()}",
                signals=signals,
                evidence=sorted(set(evidence)),
                following_owner_event=owner_flag,
                owner_event_titles=owner_titles,
            ))
        except Exception:                 # a broken window must never sink the screen
            continue
    return out


# --------------------------------------------------------------------------
# convenience bundle
# --------------------------------------------------------------------------
def run_pacing(sa, events_csv: Optional[str] = None) -> PacingResult:
    """Compute both screens for a series in one call.  Never raises."""
    result = PacingResult()
    events = None
    if events_csv:
        try:
            events = load_events_csv(events_csv)
        except OSError as e:
            result.reason = f"events CSV not loaded: {e}"
    try:
        result.pacing = pacing_candidates(sa, events)
    except Exception as e:                # pragma: no cover - defensive
        result.reason = (result.reason + "; " if result.reason else "") + \
            f"pacing screen error: {e}"
    try:
        result.acceleration = acceleration_candidates(sa, events)
    except Exception as e:                # pragma: no cover - defensive
        result.reason = (result.reason + "; " if result.reason else "") + \
            f"acceleration screen error: {e}"
    return result
