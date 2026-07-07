"""Collapsed As-Built / But-For extraction engine (MIP 3.9 Step 8).

Ported from the LI MIP 3.9 tool (mip39.collapse.engine) per ADR-0007 — port-and-validate.

AACE 29R-03 §3.9 "Modeled / Subtractive / Multiple Base" (Collapsed As-Built
Windows). The collapse answers *but-for*: "what would the as-built finish have
been but for party X's delays?" by **subtracting** those delays from a clean
copy of the as-built logic network and re-running the validated Retained-Logic
CPM (``mip39.engine.run_analysis``).

Design constraints enforced here (the prototype core got these wrong — see
``methodology_requirements_matrix.md`` §7):

* **Calibration gate (M-QNT-01 / §3.9.E):** before extracting anything, a pure
  CPM run on the *full* as-built durations must reproduce the as-built (ABCS)
  finish. If it doesn't (``calibration_ok=False``), the network does not behave
  as a clean retained-logic model — typically out-of-sequence work — and the
  collapse delta is flagged as unreliable.

* **Out-of-sequence precondition (Alex's decision, 2026-06; refined A3/
  T2-oos-unblock, 2026-06-15):** the collapse requires an OOS-clean schedule
  *unless the analyst has acknowledged the OOS in Step 2*. ``run_collapse``
  returns ``is_blocked=True`` with the conflicts when ``oos_acknowledged`` is
  False; once acknowledged it proceeds over the OOS under retained logic and
  stamps the conflicts on the result as a disclosed anomaly (``oos_clean=False``,
  ``oos_conflicts`` populated). Resolve Step 2 (OOS), or acknowledge it there.

* **No un-tabulated mutation (M-EXT-02 / §3.9.E.5):** the but-for run rebuilds a
  clean planning network from the *tabulated* logic + durations and re-runs CPM.
  It never strips or rewrites downstream successor state to force an earlier
  finish (that was the prototype's defect that let the collapse finish *later*
  than as-built).

* **Earlier-or-equal clamp (§3.9.E):** removing a delay can only pull the finish
  earlier or leave it unchanged. A but-for finish later than as-built is clamped
  and recorded as an anomaly. Compensable days are ``max(0, …)`` — never
  negative (the prototype's "-2 CD" bug).

Modes:
* **GLOBAL** — remove all of the party's delays at once; one but-for finish.
* **STEPPED** — remove delays one at a time, *latest-first* (§3.9.H), recording
  each delay's marginal contribution and the running cumulative.

This module reuses the validated CPM; it implements no scheduling math itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from typing import Any, Optional

from .conventions import EFConvention
from .models import Activity, Calendar, Relationship

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class ExtractionMode(str, Enum):
    """How the party's delays are removed from the as-built."""

    GLOBAL = "GLOBAL"
    STEPPED = "STEPPED"


@dataclass(frozen=True)
class Delay:
    """A delay tagged to an activity and attributed to a responsible party.

    Fields:
        activity_id: Activity the delay sits on.
        party:       Responsible party ("OWNER" | "CONTRACTOR" | "EXCUSABLE" |
                     "THIRD_PARTY" | …). The collapse extracts one party at a time.
        delay_days:  Whole workdays of delay embedded in this activity's
                     as-built duration (the amount subtracted in the but-for).
        description: Free-text label (provenance only; not used in math).
    """

    activity_id: str
    party: str
    delay_days: int
    description: str = ""


@dataclass(frozen=True)
class LagDelay:
    """A delay embedded in a relationship LAG, attributed to a party.

    Some delays live in the logic ties rather than in an activity's duration —
    e.g. an owner-directed hold modeled as added lag between two activities. The
    collapse subtracts ``delay_days`` from the lag of the (pred → succ)
    relationship when extracting ``party`` (clamped so a positive lag does not go
    below 0). This is the "subtract … and lag" half of the But-For.

    Fields:
        pred_id / succ_id / rel_type: identify the relationship.
        party:      Responsible party (extracted one at a time).
        delay_days: Whole workdays of lag attributable to the party.
        description: Free-text label (provenance only).
    """

    pred_id: str
    succ_id: str
    party: str
    delay_days: int
    rel_type: str = "FS"
    description: str = ""


@dataclass
class CollapseInput:
    """Everything ``run_collapse`` needs.

    Fields:
        activities:        As-built activity set (the corrected window XER).
        relationships:     As-built relationships (tabulated logic).
        project_start:     Anchor for the CPM forward pass.
        workday_table:     Prebuilt workday lookup covering the network span.
        calendar:          Project-default calendar.
        delays:            All tagged delays (all parties).
        party:             Party to extract in this run.
        mode:              GLOBAL or STEPPED.
        as_built_finish:   The validated ABCS finish to calibrate against. When
                           None, the calibration run defines it (calibration
                           trivially holds).
        calendar_registry: Optional multi-calendar registry (passed through).
        convention:        EF convention; defaults to P6_COMPATIBILITY to match
                           the anchored ABCS (``AS_BUILT_ANCHORED``).
        driving_overrides: A1/F-03 — analyst overrides of the driving predecessor,
                           {succ_id: chosen_pred_id}. They NEVER move the primary
                           CPM-derived headline; they drive a DISCLOSED "analyst-
                           driver" SHADOW (edge-substitution, self-calibrated).
    """

    activities: list[Activity]
    relationships: list[Relationship]
    project_start: date
    workday_table: dict[date, int]
    calendar: Calendar
    delays: list[Delay] = field(default_factory=list)
    lag_delays: list[LagDelay] = field(default_factory=list)
    party: str = "OWNER"
    mode: ExtractionMode = ExtractionMode.GLOBAL
    as_built_finish: Optional[date] = None
    calendar_registry: Optional[Any] = None
    convention: EFConvention = EFConvention.P6_COMPATIBILITY
    driving_overrides: dict[str, str] = field(default_factory=dict)
    # A3/T2-oos-unblock — when the analyst has ACKNOWLEDGED the out-of-sequence
    # logic in Step 2, the collapse proceeds over it with a disclosed anomaly (the
    # conflicts are stamped on the result) instead of hard-blocking. Default False
    # keeps the OOS-clean precondition byte-for-byte for every existing caller.
    oos_acknowledged: bool = False
    # ADR-027 §C — when the basis IS the rectified ABCS (logic rectification has
    # produced the clean as-built), the detect→block→acknowledge OOS gate DEMOTES
    # to a safety-net: any OOS that *survived* rectification is a disclosed
    # RESIDUAL warning, not a hard block. Default False keeps the gate unchanged;
    # 4.4a opts in when it feeds the rectified relationships to the collapse.
    rectified_basis: bool = False


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass
class PerDelayMarginal:
    """One stepped-extraction step (latest-first)."""

    activity_id: str
    delay_days: int
    marginal_days: int
    cumulative_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "delay_days": self.delay_days,
            "marginal_days": self.marginal_days,
            "cumulative_days": self.cumulative_days,
        }


@dataclass
class DiagnosticRow:
    """Per-activity diagnostic of how a delay claim behaved in the collapse."""

    activity_id: str
    original_duration: int
    claim_days: int
    effective_save_wd: int
    on_pre_cp: bool
    on_post_cp: bool
    capped: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "original_duration": self.original_duration,
            "claim_days": self.claim_days,
            "effective_save_wd": self.effective_save_wd,
            "on_pre_cp": self.on_pre_cp,
            "on_post_cp": self.on_post_cp,
            "capped": self.capped,
        }


@dataclass
class CollapseResult:
    """Result of a but-for extraction for one party."""

    mode: ExtractionMode
    party: str
    n_delays_processed: int
    original_finish: Optional[date]
    collapsed_finish: Optional[date]
    compensable_days: int               # WORKDAYS (primary; comparable to claim)
    compensable_calendar_days: int      # calendar days (contract-time view)
    pre_collapse_cp: list[str]
    post_collapse_cp: list[str]
    per_delay_marginal: list[PerDelayMarginal]
    diagnostic: list[DiagnosticRow]
    calibration_ok: bool
    calibration_finish: Optional[date]
    oos_clean: bool
    oos_conflicts: list[dict[str, Any]]
    anomalies: list[str]
    is_blocked: bool
    # A1/F-03 — DISCLOSED "analyst-driver" sensitivity (driving-override shadow).
    # The shadow is self-calibrated against the substituted network's own as-built;
    # `shadow_calibration_ok` discloses whether that still reproduces the PRIMARY
    # as-built finish (edge-substitution can break it). Never the headline.
    shadow_compensable_days: int = 0
    shadow_compensable_calendar_days: int = 0
    shadow_collapsed_finish: Optional[date] = None
    shadow_calibration_finish: Optional[date] = None
    shadow_calibration_ok: bool = True
    shadow_post_collapse_cp: list[str] = field(default_factory=list)
    shadow_anomalies: list[str] = field(default_factory=list)
    # Structured edge edits (forensic record; E7-serializable): per override
    # {succ_id, analyst_pred_id, dropped_edges:[{pred_id,rel_type,lag}], applied, reason?}.
    driving_overrides_applied: list[dict[str, Any]] = field(default_factory=list)
    # E7/F-23 — §3.9.E.5 change-log of the bypass structural edits the primary
    # collapse made: per fully-removed (0-duration) node, the reconnect edges
    # synthesized across it {dropped_activity, reason, reconnects:[{pred_id,
    # succ_id, rel_type, lag}]}.
    bypass_change_log: list[dict[str, Any]] = field(default_factory=list)
    # Phase I — per-activity collapsed (but-for) span for the schedule overlay,
    # {act_id: {"start": iso, "finish": iso}} from the final but-for CPM run.
    # Activities bypassed in the but-for network (fully-removed delays) are absent
    # — the overlay renders no ghost for them and discloses the gap.
    collapsed_dates: dict[str, dict[str, str]] = field(default_factory=dict)

    def _acp_reconciliation(self) -> dict[str, Any]:
        """E5/F-08 — Analogous Critical Path reconciliation (CALC-021 / 29R-03
        §3.9.K.3/.5/.6). The ACP is the collapsed schedule's critical path
        (``post_collapse_cp``) transferred onto the as-built logic. The §3.9.K
        self-check cross-foots the delays LOCATED ON THE ACP against the
        as-built−collapsed delta: Σ(delay quantity on the ACP) should equal the
        compensable workdays.

        "On the ACP" is exactly what ``DiagnosticRow.on_post_cp`` encodes — for a
        duration delay, its activity is on the collapsed CP; for a lag delay, its
        relationship's endpoints are both on it. The cross-foot is computed in BOTH
        global and stepped modes (Codex E5). A non-zero residual flags delay days
        that did not control on the ACP (e.g. parallelism / concurrency) and
        warrants analyst review — it is surfaced, not hidden."""
        acp = list(self.post_collapse_cp)
        total = self.compensable_days
        # Σ delays located on the analogous critical path (duration delays whose
        # activity is on the ACP + lag delays whose relationship lies on it).
        acp_delay_sum = sum(
            int(d.claim_days) for d in self.diagnostic if d.on_post_cp
        )
        reconciled = acp_delay_sum == total
        return {
            "acp": acp,
            "total_delta_wd": total,
            "mode": self.mode.value,
            "acp_delay_sum_wd": acp_delay_sum,
            "reconciled": reconciled,
            "residual_wd": total - acp_delay_sum,
            "note": (
                "§3.9.K.5/.6 self-check: the delays located on the analogous "
                "critical path (collapsed CP transferred to the as-built logic) "
                "should sum to the as-built−collapsed delta. A non-zero residual "
                "flags delay days that did not control on the ACP (parallelism / "
                "concurrency) and warrants review."
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        party = self.party.upper()
        ecd_cd = self.compensable_calendar_days if party == "OWNER" else None
        ecd_wd = self.compensable_days if party == "OWNER" else None
        nnd_cd = self.compensable_calendar_days if party == "CONTRACTOR" else None
        nnd_wd = self.compensable_days if party == "CONTRACTOR" else None
        end_cd = (
            self.compensable_calendar_days
            if party in {"EXCUSABLE", "THIRD_PARTY"}
            else None
        )
        end_wd = (
            self.compensable_days
            if party in {"EXCUSABLE", "THIRD_PARTY"}
            else None
        )
        return {
            "mode": self.mode.value,
            "party_extracted": self.party,
            "delay_quantity": (
                "ECD" if party == "OWNER"
                else "NND" if party == "CONTRACTOR"
                else "END" if party in {"EXCUSABLE", "THIRD_PARTY"}
                else None
            ),
            "ecd_calendar_days": ecd_cd,
            "ecd_workdays": ecd_wd,
            "nnd_calendar_days": nnd_cd,
            "nnd_workdays": nnd_wd,
            "end_calendar_days": end_cd,
            "end_workdays": end_wd,
            # E4 interim floor (F-07/FU-2) — END here is the EXCUSABLE/THIRD_PARTY
            # collapse *extraction*, NOT the 29R-03 §3.9.I.3 net-excusable-non-
            # compensable *reconciliation* (which nets excusable delay against the
            # compensable analysis). Labelled so it is never read as a true END.
            "end_basis": "party_extraction",
            "end_is_reconciled": False,
            "end_disclosure": (
                "END here is the EXCUSABLE/THIRD_PARTY collapse extraction, NOT a "
                "§3.9.I.3 net-excusable-non-compensable reconciliation. The "
                "reconciliation (netting excusable delay against the compensable "
                "analysis) is a separate computation, not performed here."
                if party in {"EXCUSABLE", "THIRD_PARTY"} else None
            ),
            "adjustments": {
                "owner_paid_acceleration_credit_cd": None,
                "contractor_unreimbursed_mitigation_credit_cd": None,
                "status": "not_captured",
                # E4 interim floor — None means UNCOMPUTED, explicitly NOT zero.
                # M-QNT-02 acceleration/mitigation credit is scaffolded but not yet
                # computed; the but-for figure nets no such credit.
                "is_zero": False,
                "disclosure": (
                    "Acceleration / unreimbursed-mitigation credit is not computed "
                    "(§3.9.I). The but-for figure nets no such credit — treat as "
                    "uncomputed, NOT zero."
                ),
            },
            "n_delays_processed": self.n_delays_processed,
            "original_finish": (
                self.original_finish.isoformat() if self.original_finish else None
            ),
            "collapsed_finish": (
                self.collapsed_finish.isoformat() if self.collapsed_finish else None
            ),
            "compensable_days": self.compensable_days,
            "compensable_calendar_days": self.compensable_calendar_days,
            "pre_collapse_cp": list(self.pre_collapse_cp),
            "post_collapse_cp": list(self.post_collapse_cp),
            # Phase I — per-activity collapsed (but-for) span for the schedule overlay.
            "collapsed_dates": dict(self.collapsed_dates),
            # E5/F-08 — Analogous Critical Path reconciliation self-check (CALC-021).
            "acp_reconciliation": self._acp_reconciliation(),
            # E7/F-23 — §3.9.E.5 bypass change-log (dropped nodes + reconnects).
            "bypass_change_log": list(self.bypass_change_log),
            "per_delay_marginal": [m.to_dict() for m in self.per_delay_marginal],
            "diagnostic": [d.to_dict() for d in self.diagnostic],
            "calibration_ok": self.calibration_ok,
            "calibration_finish": (
                self.calibration_finish.isoformat()
                if self.calibration_finish
                else None
            ),
            "oos_clean": self.oos_clean,
            "oos_conflicts": list(self.oos_conflicts),
            "anomalies": list(self.anomalies),
            "is_blocked": self.is_blocked,
            # A1/F-03 — disclosed analyst-driver sensitivity (never the headline).
            "driving_override_shadow": (
                {
                    "compensable_days": self.shadow_compensable_days,
                    "compensable_calendar_days": self.shadow_compensable_calendar_days,
                    "collapsed_finish": (
                        self.shadow_collapsed_finish.isoformat()
                        if self.shadow_collapsed_finish else None
                    ),
                    "calibration_finish": (
                        self.shadow_calibration_finish.isoformat()
                        if self.shadow_calibration_finish else None
                    ),
                    "calibration_ok": self.shadow_calibration_ok,
                    "post_collapse_cp": list(self.shadow_post_collapse_cp),
                    "anomalies": list(self.shadow_anomalies),
                }
                if any(a.get("applied") for a in self.driving_overrides_applied) else None
            ),
            "driving_overrides_applied": list(self.driving_overrides_applied),
        }


# ---------------------------------------------------------------------------
# Out-of-sequence detection (retained-logic precondition)
# ---------------------------------------------------------------------------


def detect_out_of_sequence(
    activities: list[Activity], relationships: list[Relationship]
) -> list[dict[str, Any]]:
    """Find relationships whose *actuals* violate retained logic.

    Retained-Logic OOS = the as-built shows a successor having started/finished
    before its predecessor allowed it. These must be resolved before a collapse,
    because a pure CPM rebuild cannot reproduce an as-built that broke its own
    logic (the collapse would be measured against an un-reproducible baseline).

    Checks (using actual dates only; activities without the relevant actuals are
    skipped — they cannot be out of sequence yet):
        FS: successor actual_start < predecessor actual_finish.
        SS: successor actual_start < predecessor actual_start.
        FF: successor actual_finish < predecessor actual_finish.
    """
    by_id = {a.act_id: a for a in activities}
    conflicts: list[dict[str, Any]] = []
    for r in relationships:
        p = by_id.get(r.pred_id)
        s = by_id.get(r.succ_id)
        if p is None or s is None:
            continue
        conflict: Optional[tuple[date, date]] = None
        if r.rel_type == "FS":
            if s.actual_start is not None and p.actual_finish is not None:
                if s.actual_start < p.actual_finish:
                    conflict = (s.actual_start, p.actual_finish)
        elif r.rel_type == "SS":
            if s.actual_start is not None and p.actual_start is not None:
                if s.actual_start < p.actual_start:
                    conflict = (s.actual_start, p.actual_start)
        elif r.rel_type == "FF":
            if s.actual_finish is not None and p.actual_finish is not None:
                if s.actual_finish < p.actual_finish:
                    conflict = (s.actual_finish, p.actual_finish)
        if conflict is not None:
            conflicts.append(
                {
                    "pred_id": r.pred_id,
                    "succ_id": r.succ_id,
                    "rel_type": r.rel_type,
                    "successor_date": conflict[0].isoformat(),
                    "predecessor_date": conflict[1].isoformat(),
                }
            )
    return conflicts


# ---------------------------------------------------------------------------
# Internal CPM helpers
# ---------------------------------------------------------------------------


def _planning_network(
    activities: list[Activity], subtract: dict[str, int]
) -> list[Activity]:
    """Clean subtractive network: as-built durations minus the removed delays.

    Builds fresh planning activities carrying ONLY tabulated inputs (duration,
    calendar, existing constraints) — no actuals, no pins, no %C — so the CPM
    forward pass schedules purely from logic + (reduced) duration. This is the
    §3.9.E.5-compliant rebuild: nothing downstream is stripped or mutated.
    """
    out: list[Activity] = []
    for a in activities:
        od = int(a.original_duration or 0)
        od = max(0, od - int(subtract.get(a.act_id, 0)))
        out.append(
            Activity(
                act_id=a.act_id,
                original_duration=od,
                calendar_id=a.calendar_id,
                constraint_type=a.constraint_type,
                constraint_date=a.constraint_date,
            )
        )
    return out


def _adjust_relationships(
    relationships: list[Relationship], lag_subtract: dict[tuple[str, str], int]
) -> list[Relationship]:
    """Return relationships with party lag-delays subtracted (positive lags only).

    A lag-delay removes added lag; it never turns a positive lag into a negative
    lead (clamped at 0) and never touches an already-negative (lead) lag.
    """
    if not lag_subtract:
        return list(relationships)
    out: list[Relationship] = []
    for r in relationships:
        days = lag_subtract.get((r.pred_id, r.succ_id), 0)
        lag = r.lag
        if days and lag > 0:
            lag = max(0, lag - days)
        out.append(Relationship(r.pred_id, r.succ_id, r.rel_type, lag))
    return out


def _bypass(
    activities: list[Activity],
    relationships: list[Relationship],
    removed: set[str],
) -> tuple[list[Activity], list[Relationship]]:
    """Drop fully-removed activities and reconnect their predecessors to their
    successors (transitive bypass), so a delay equal to an activity's whole
    duration collapses exactly instead of leaving a 0-day milestone that still
    costs ~1 WD under the P6 FS convention.

    The bypass relationship carries the successor link's type and the summed lag
    (the removed node has 0 duration, so start == finish). Multi-node adjacent
    removals are handled per-node (a chain of removed nodes may not fully
    short-circuit; rare in practice — one delay activity at a time).
    """
    if not removed:
        return activities, relationships
    acts = [a for a in activities if a.act_id not in removed]
    preds_of: dict[str, list[Relationship]] = {}
    succs_of: dict[str, list[Relationship]] = {}
    for r in relationships:
        preds_of.setdefault(r.succ_id, []).append(r)
        succs_of.setdefault(r.pred_id, []).append(r)
    rels = [
        r
        for r in relationships
        if r.pred_id not in removed and r.succ_id not in removed
    ]
    for x in removed:
        for rp in preds_of.get(x, []):
            if rp.pred_id in removed:
                continue
            for rs in succs_of.get(x, []):
                if rs.succ_id in removed:
                    continue
                rels.append(
                    Relationship(
                        rp.pred_id, rs.succ_id, rs.rel_type, rp.lag + rs.lag
                    )
                )
    return acts, rels


def _bypass_change_log(
    inp: "CollapseInput",
    subtract: dict[str, int],
    lag_subtract: Optional[dict[tuple[str, str], int]] = None,
) -> list[dict[str, Any]]:
    """E7/F-23 — the §3.9.E.5 change-log for the bypass structural edits a collapse
    run made. Re-derives ``_run_cpm``'s removed set (activities reduced to 0
    duration) and ``_bypass``'s synthesized reconnect edges deterministically from
    the same inputs — read-only, no CPM run, so the hot path is untouched. One
    record per dropped node lists the reconnects {pred_id, succ_id, rel_type, lag}.
    """
    removed = {
        a.act_id
        for a in inp.activities
        if int(a.original_duration or 0) > 0
        and int(a.original_duration or 0) - int(subtract.get(a.act_id, 0)) <= 0
    }
    if not removed:
        return []
    rels = _adjust_relationships(inp.relationships, lag_subtract or {})
    preds_of: dict[str, list[Relationship]] = {}
    succs_of: dict[str, list[Relationship]] = {}
    for r in rels:
        preds_of.setdefault(r.succ_id, []).append(r)
        succs_of.setdefault(r.pred_id, []).append(r)
    log: list[dict[str, Any]] = []
    for x in sorted(removed):
        reconnects: list[dict[str, Any]] = []
        for rp in preds_of.get(x, []):
            if rp.pred_id in removed:
                continue
            for rs in succs_of.get(x, []):
                if rs.succ_id in removed:
                    continue
                reconnects.append({
                    "pred_id": rp.pred_id,
                    "succ_id": rs.succ_id,
                    "rel_type": rs.rel_type,
                    "lag": rp.lag + rs.lag,
                })
        log.append({
            "dropped_activity": x,
            "reason": "duration fully removed (0-day) — transitive bypass (§3.9.E.5)",
            "reconnects": reconnects,
        })
    return log


def _run_cpm(
    inp: CollapseInput,
    subtract: dict[str, int],
    lag_subtract: Optional[dict[tuple[str, str], int]] = None,
) -> Any:
    """Run the validated Retained-Logic CPM on the subtractive network.

    Applies duration subtraction (``subtract``), lag subtraction
    (``lag_subtract``), and bypass of any activity reduced to 0 duration.
    """
    from .engine import run_analysis  # lazy: avoid import cycles

    acts = _planning_network(inp.activities, subtract)
    rels = _adjust_relationships(inp.relationships, lag_subtract or {})
    removed = {
        a.act_id
        for a in inp.activities
        if int(a.original_duration or 0) > 0
        and int(a.original_duration or 0) - int(subtract.get(a.act_id, 0)) <= 0
    }
    if removed:
        acts, rels = _bypass(acts, rels, removed)
    return run_analysis(
        activities=acts,
        relationships=rels,
        project_start=inp.project_start,
        workday_table=inp.workday_table,
        calendar=inp.calendar,
        convention=inp.convention,
        calendar_registry=inp.calendar_registry,
    )


def _cp_ids(result: Any) -> list[str]:
    if result is not None and result.critical_path is not None:
        return list(result.critical_path.activity_ids)
    return []


def _collapsed_dates(run: Any) -> dict[str, dict[str, str]]:
    """Per-activity early-start/finish from a CPM run's schedule — the but-for
    span the Phase-I schedule overlay ghosts under the as-built bars. Activities
    bypassed (fully-removed delays) are absent from the run's schedule and so are
    omitted, which the overlay discloses rather than drawing a misleading bar."""
    out: dict[str, dict[str, str]] = {}
    sched = getattr(run, "scheduled", None) or {}
    for act_id, sa in sched.items():
        es = getattr(sa, "early_start", None)
        ef = getattr(sa, "early_finish", None)
        if es is not None and ef is not None:
            out[act_id] = {"start": es.isoformat(), "finish": ef.isoformat()}
    return out


def _cd(later: Optional[date], earlier: Optional[date]) -> int:
    """Non-negative calendar-day difference (later − earlier), clamped at 0."""
    if later is None or earlier is None:
        return 0
    return max(0, (later - earlier).days)


def _wd(
    table: dict[date, int], later: Optional[date], earlier: Optional[date]
) -> int:
    """Non-negative WORKDAY difference via the workday table, clamped at 0.

    Finish movement is measured in workdays so it is directly comparable to the
    delay claim (workdays) and the critical-path duration (workdays) — a 10-WD
    claim that fully drives the finish reads as a 10-WD save, not 14 CD. Falls
    back to calendar days only if a finish date is outside the table.
    """
    if later is None or earlier is None:
        return 0
    if later in table and earlier in table:
        return max(0, table[later] - table[earlier])
    return max(0, (later - earlier).days)


def _dur(result: Any) -> Optional[int]:
    """Project duration in workdays (inclusive span) from a CPM run.

    This is the convention-safe way to measure finish movement: differencing two
    *durations* avoids the inclusive-day off-by-one that differencing two finish
    *dates* introduces. ``critical_path.project_duration`` is the engine's own
    inclusive workday span.
    """
    if result is not None and result.critical_path is not None:
        return result.critical_path.project_duration
    return None


def _apply_driving_overrides(
    relationships: list[Relationship], overrides: dict[str, str]
) -> tuple[list[Relationship], list[dict[str, Any]]]:
    """A1/F-03 — edge-substitution for the analyst-driver SHADOW: force each chosen
    predecessor to bind its successor by dropping the successor's OTHER predecessor
    edges. Records each edit (forensic; E7-serializable). Never deletes a node; an
    override whose pred is not an existing predecessor of the successor is recorded
    ``applied=False`` and changes nothing."""
    preds_by_succ: dict[str, list[Relationship]] = {}
    for r in relationships:
        preds_by_succ.setdefault(r.succ_id, []).append(r)
    drop: set[int] = set()
    applied: list[dict[str, Any]] = []
    for succ_id, pred_id in overrides.items():
        succ_preds = preds_by_succ.get(succ_id, [])
        if not any(r.pred_id == pred_id for r in succ_preds):
            applied.append({
                "succ_id": succ_id, "analyst_pred_id": pred_id, "dropped_edges": [],
                "applied": False,
                "reason": "analyst predecessor is not an existing predecessor of the successor",
            })
            continue
        dropped = [r for r in succ_preds if r.pred_id != pred_id]
        for r in dropped:
            drop.add(id(r))
        applied.append({
            "succ_id": succ_id, "analyst_pred_id": pred_id,
            "dropped_edges": [
                {"pred_id": r.pred_id, "rel_type": r.rel_type, "lag": r.lag}
                for r in dropped
            ],
            "applied": True,
        })
    subst = [r for r in relationships if id(r) not in drop]
    return subst, applied


def _shadow_metrics(
    inp: CollapseInput, subst_rels: list[Relationship],
    claim_by_act: dict[str, int], lag_claim: dict[tuple[str, str], int],
    primary_ref_finish: Optional[date],
) -> dict[str, Any]:
    """A1/F-03 — the disclosed analyst-driver SHADOW. Re-runs the calibration +
    global but-for on the edge-substituted network, SELF-calibrated (savings
    measured against the substituted network's OWN as-built). ``calibration_ok``
    discloses whether that network still reproduces the PRIMARY as-built finish —
    edge-substitution can break it, in which case the shadow is an uncalibrated
    sensitivity, NOT a comparable entitlement quantity (§3.9.E)."""
    sinp = replace(inp, relationships=subst_rels, driving_overrides={})
    cal = _run_cpm(sinp, {}, {})
    cal_finish = cal.project_finish
    ref_dur = _dur(cal)
    bf = (
        _run_cpm(sinp, claim_by_act, lag_claim)
        if (claim_by_act or lag_claim) else cal
    )
    bf_dur = _dur(bf)
    collapsed_raw = bf.project_finish
    anomalies: list[str] = []
    collapsed_finish = collapsed_raw
    if collapsed_raw is not None and cal_finish is not None and collapsed_raw > cal_finish:
        collapsed_finish = cal_finish
        anomalies.append("Shadow collapsed finish exceeded the substituted as-built; clamped.")
    save_wd = max(0, ref_dur - bf_dur) if (ref_dur is not None and bf_dur is not None) else 0
    cal_ok = (
        cal_finish is not None and primary_ref_finish is not None
        and cal_finish == primary_ref_finish
    )
    if not cal_ok:
        anomalies.append(
            "The analyst-driver (edge-substituted) network does not reproduce the "
            "as-built finish; this shadow is a DISCLOSED SENSITIVITY only, not a "
            "comparable entitlement quantity."
        )
    return {
        "compensable_days": save_wd,
        "compensable_calendar_days": _cd(cal_finish, collapsed_finish),
        "collapsed_finish": collapsed_finish,
        "calibration_finish": cal_finish,
        "calibration_ok": cal_ok,
        "post_collapse_cp": _cp_ids(bf),
        "anomalies": anomalies,
    }


# ---------------------------------------------------------------------------
# The collapse
# ---------------------------------------------------------------------------


def run_collapse(inp: CollapseInput) -> CollapseResult:
    """Run a but-for extraction for ``inp.party``.

    Returns a blocked result (``is_blocked=True``) if the schedule is not
    out-of-sequence-clean; otherwise the collapsed finish + compensable days +
    per-delay marginals + diagnostics, all measured against a calibrated CPM
    baseline.
    """
    anomalies: list[str] = []
    party_delays = [d for d in inp.delays if d.party == inp.party]
    party_lags = [l for l in inp.lag_delays if l.party == inp.party]
    n_processed = len(party_delays) + len(party_lags)

    # --- 1. OOS precondition -------------------------------------------------
    oos = detect_out_of_sequence(inp.activities, inp.relationships)
    # The gate blocks ONLY when OOS is present and neither the analyst has
    # acknowledged it (A3) nor the rectified ABCS is the basis (ADR-027 §C —
    # rectification is itself the resolution; any survivor is a disclosed
    # residual, not a block).
    proceed_over_oos = inp.oos_acknowledged or inp.rectified_basis
    if oos and not proceed_over_oos:
        return CollapseResult(
            mode=inp.mode,
            party=inp.party,
            n_delays_processed=n_processed,
            original_finish=inp.as_built_finish,
            collapsed_finish=None,
            compensable_days=0,
            compensable_calendar_days=0,
            pre_collapse_cp=[],
            post_collapse_cp=[],
            per_delay_marginal=[],
            diagnostic=[],
            calibration_ok=False,
            calibration_finish=None,
            oos_clean=False,
            oos_conflicts=oos,
            anomalies=[
                "Schedule is out of sequence; resolve Step 2 (OOS) before "
                "collapsing. The collapse is blocked (no un-tabulated logic "
                "adjustment is performed; §3.9.E.5)."
            ],
            is_blocked=True,
        )
    if oos:
        if inp.rectified_basis:
            # ADR-027 §C — the rectified ABCS is the basis, so the gate is a
            # safety-net: these conflicts SURVIVED rectification (a residual the
            # rectification did not resolve). Proceed, but disclose them as a
            # residual warning for the analyst to review — not a block.
            anomalies.append(
                f"Collapse proceeded over {len(oos)} RESIDUAL out-of-sequence "
                "conflict(s) that survived logic rectification (ADR-027 §C): the "
                "rectified ABCS is the basis. These residuals are disclosed for "
                "review/cross-examination (safety-net warning, not a block)."
            )
        else:
            # A3/T2-oos-unblock — OOS present but ACKNOWLEDGED in Step 2: proceed
            # over it and stamp the conflicts on the result as a disclosed anomaly
            # (the acknowledgement must deliver the unblock it implies; the prior
            # un-overridable 409 was a contradiction). oos_clean stays False and
            # the conflicts ride on the result, so the deliverable shows what was
            # accepted.
            anomalies.append(
                f"Collapse proceeded over {len(oos)} ACKNOWLEDGED out-of-sequence "
                "conflict(s) (analyst accepted in Step 2): retained-logic CPM applied "
                "with no un-tabulated adjustment (§3.9.E.5). The conflicts are "
                "disclosed on this result for cross-examination."
            )

    # --- 2. Calibration run (full as-built durations + lags) ----------------
    cal = _run_cpm(inp, {}, {})
    if not cal.is_valid or cal.project_finish is None:
        anomalies.append("Calibration CPM run was invalid; collapse unreliable.")
    calibration_finish = cal.project_finish
    pre_cp = _cp_ids(cal)
    as_built_finish = inp.as_built_finish or calibration_finish
    calibration_ok = (
        calibration_finish is not None
        and as_built_finish is not None
        and calibration_finish == as_built_finish
    )
    if not calibration_ok and inp.as_built_finish is not None:
        anomalies.append(
            "Calibration mismatch: pure CPM finish "
            f"{calibration_finish} != as-built/ABCS finish {as_built_finish}. "
            "The collapse delta is measured in the CPM model and flagged."
        )

    # Reference the collapse is measured FROM: finish date (display + calendar
    # days) and project DURATION in workdays (the convention-safe save measure).
    ref_finish = calibration_finish
    ref_dur = _dur(cal)

    def _save_wd(run: Any) -> int:
        """Workdays the finish moved earlier vs as-built = duration shortening."""
        d = _dur(run)
        if ref_dur is None or d is None:
            return 0
        return max(0, ref_dur - d)

    # --- 3. Claim maps (duration delays on activities; lag delays on links) --
    claim_by_act: dict[str, int] = {}
    od_by_act: dict[str, int] = {a.act_id: int(a.original_duration or 0) for a in inp.activities}
    for d in party_delays:
        claim_by_act[d.activity_id] = claim_by_act.get(d.activity_id, 0) + int(d.delay_days)
    lag_claim: dict[tuple[str, str], int] = {}
    for lg in party_lags:
        k = (lg.pred_id, lg.succ_id)
        lag_claim[k] = lag_claim.get(k, 0) + int(lg.delay_days)
    rel_lag = {(r.pred_id, r.succ_id): r.lag for r in inp.relationships}

    sched = cal.scheduled if cal.is_valid else {}

    def _ef(act_id: str) -> date:
        sa = sched.get(act_id)
        return sa.early_finish if sa is not None else (ref_finish or date.min)

    # --- 4. But-for extraction ----------------------------------------------
    per_delay: list[PerDelayMarginal] = []

    if inp.mode == ExtractionMode.STEPPED:
        # Unify duration + lag delays; remove latest-first (§3.9.H stepped).
        # Each item: (kind, ref_key, days, ordering_ef, display_label).
        items: list[tuple[str, Any, int, date, str]] = []
        for d in party_delays:
            items.append(
                ("dur", d.activity_id, int(d.delay_days), _ef(d.activity_id), d.activity_id)
            )
        for lg in party_lags:
            items.append(
                ("lag", (lg.pred_id, lg.succ_id), int(lg.delay_days),
                 _ef(lg.succ_id), f"{lg.pred_id}→{lg.succ_id}")
            )
        items.sort(key=lambda it: it[3], reverse=True)
        dur_removed: dict[str, int] = {}
        lag_removed: dict[tuple[str, str], int] = {}
        prev_save = 0
        final = cal
        for kind, ref_key, days, _ef_d, label in items:
            if kind == "dur":
                dur_removed[ref_key] = dur_removed.get(ref_key, 0) + days
            else:
                lag_removed[ref_key] = lag_removed.get(ref_key, 0) + days
            step = _run_cpm(inp, dict(dur_removed), dict(lag_removed))
            cumulative = _save_wd(step)
            marginal = max(0, cumulative - prev_save)
            per_delay.append(
                PerDelayMarginal(
                    activity_id=label,
                    delay_days=days,
                    marginal_days=marginal,
                    cumulative_days=cumulative,
                )
            )
            prev_save = cumulative
            final = step
        post_cp = _cp_ids(final)
        collapsed_raw = final.project_finish
        collapsed_save = _save_wd(final)
        collapsed_dates = _collapsed_dates(final)
        # E7/F-23 — §3.9.E.5 change-log for the final stepped network's bypasses.
        bypass_log = _bypass_change_log(inp, dict(dur_removed), dict(lag_removed))
    else:
        # GLOBAL: remove all party delays (duration + lag) at once.
        bf = (
            _run_cpm(inp, claim_by_act, lag_claim)
            if (claim_by_act or lag_claim)
            else cal
        )
        collapsed_raw = bf.project_finish
        collapsed_save = _save_wd(bf)
        post_cp = _cp_ids(bf)
        collapsed_dates = _collapsed_dates(bf)
        # E7/F-23 — §3.9.E.5 change-log for the global but-for network's bypasses.
        bypass_log = _bypass_change_log(inp, claim_by_act, lag_claim)

    # earlier-or-equal clamp on the final collapsed finish (display)
    collapsed_finish = collapsed_raw
    if (
        collapsed_raw is not None
        and ref_finish is not None
        and collapsed_raw > ref_finish
    ):
        collapsed_finish = ref_finish
        anomalies.append("Collapsed finish exceeded as-built; clamped to as-built.")
    # Primary measure is WORKDAYS (duration delta — comparable to the claim + CP);
    # calendar days from the finish dates are also reported (contract-time view).
    compensable_days = collapsed_save
    compensable_calendar_days = _cd(ref_finish, collapsed_finish)

    # --- 5. Diagnostics (duration rows + lag rows) --------------------------
    diagnostic: list[DiagnosticRow] = []
    pre_set, post_set = set(pre_cp), set(post_cp)
    for act_id in sorted(claim_by_act):
        claim = claim_by_act[act_id]
        standalone = _run_cpm(inp, {act_id: claim}, {})
        effective = _save_wd(standalone)
        diagnostic.append(
            DiagnosticRow(
                activity_id=act_id,
                original_duration=od_by_act.get(act_id, 0),
                claim_days=claim,
                effective_save_wd=effective,
                on_pre_cp=act_id in pre_set,
                on_post_cp=act_id in post_set,
                capped=effective < claim,
            )
        )
    for key in sorted(lag_claim):
        claim = lag_claim[key]
        standalone = _run_cpm(inp, {}, {key: claim})
        effective = _save_wd(standalone)
        pred, succ = key
        diagnostic.append(
            DiagnosticRow(
                activity_id=f"{pred}→{succ}",
                original_duration=int(rel_lag.get(key, 0)),
                claim_days=claim,
                effective_save_wd=effective,
                on_pre_cp=(pred in pre_set and succ in pre_set),
                on_post_cp=(pred in post_set and succ in post_set),
                capped=effective < claim,
            )
        )

    # --- 6. A1/F-03 — disclosed analyst-driver SHADOW (driving-override) ------
    # Additive only: the primary result above is untouched, so an empty (or fully
    # unapplied) override set leaves the headline byte-for-byte identical.
    shadow_kwargs: dict[str, Any] = {}
    if inp.driving_overrides:
        subst_rels, applied = _apply_driving_overrides(
            inp.relationships, inp.driving_overrides
        )
        if any(a["applied"] for a in applied):
            sm = _shadow_metrics(inp, subst_rels, claim_by_act, lag_claim, as_built_finish)
            shadow_kwargs = {
                "shadow_compensable_days": sm["compensable_days"],
                "shadow_compensable_calendar_days": sm["compensable_calendar_days"],
                "shadow_collapsed_finish": sm["collapsed_finish"],
                "shadow_calibration_finish": sm["calibration_finish"],
                "shadow_calibration_ok": sm["calibration_ok"],
                "shadow_post_collapse_cp": sm["post_collapse_cp"],
                "shadow_anomalies": sm["anomalies"],
            }
        shadow_kwargs["driving_overrides_applied"] = applied

    return CollapseResult(
        mode=inp.mode,
        party=inp.party,
        n_delays_processed=n_processed,
        original_finish=as_built_finish,
        collapsed_finish=collapsed_finish,
        compensable_days=compensable_days,
        compensable_calendar_days=compensable_calendar_days,
        pre_collapse_cp=pre_cp,
        post_collapse_cp=post_cp,
        per_delay_marginal=per_delay,
        diagnostic=diagnostic,
        calibration_ok=calibration_ok,
        calibration_finish=calibration_finish,
        # A3/T2-oos-unblock — clean unless we proceeded over acknowledged OOS, in
        # which case the conflicts ride on the result as a disclosed stamp.
        oos_clean=not oos,
        oos_conflicts=list(oos),
        anomalies=anomalies,
        is_blocked=False,
        bypass_change_log=bypass_log,
        collapsed_dates=collapsed_dates,
        **shadow_kwargs,
    )
