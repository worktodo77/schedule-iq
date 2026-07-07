"""
Ported from the LI MIP 3.9 tool (mip39.engine) per ADR-0007 — port-and-validate.

W1a port severance (this port only — see ADR-0007): the optional normalization
pipeline hook (normalization_policy / data_date) and the optional simulation
(ABCS) hook (simulation_input) are REMOVED from run_analysis() in this port.
Neither mip39.normalization nor mip39.simulation is ported in this wave.
The destatusing hook (destatusing_input) is KEPT, but its import is now lazy
(deferred until destatusing_input is actually provided) since mip39.destatusing
is being ported separately, in parallel, and must not be a hard import-time
dependency of this module. Forward pass, backward pass, float, longest-path,
and multi-calendar logic are unchanged from the source.

INFRA-007/008: Phase 3/4 CPM Analytical Engine.

Implements a full Precedence Diagramming Method (PDM) critical path analysis
under Retained Logic scheduling (ADR-002):

  Forward pass  — Early Start (ES) and Early Finish (EF) for all activities.
                  Supports all four PDM relationship types: FS, SS, FF, SF.
  Backward pass — Late Start (LS) and Late Finish (LF) for all activities.
                  Supports all four PDM relationship types: FS, SS, FF, SF.
  Float         — Total Float (TF) and Free Float (FF) for all activities.
  Critical path — Phase 4 (INFRA-008): actual longest-path (controlling-path)
                  tracing per AACE 49R-06 §4.2. Resolves LIM-029.
                  ScheduledActivity.is_critical reflects longest-path membership.
                  TF=0 is retained as a secondary diagnostic in
                  CriticalPathInfo.tf_zero_activities.
                  Divergence flags CP-001 through CP-004 identify differences
                  between the TF=0 set and the longest-path set, tied paths,
                  multiple controlling finish nodes, and LP activities with
                  positive total float.

Pre-analysis gate: NetworkValidator (INFRA-002) runs on raw lists before
scheduling. Blocking issues prevent scheduling and return is_valid=False in
the result envelope.

Multi-calendar scheduling (V1-B.1 — ADR-012): optional CalendarRegistry
enables per-activity workday tables and configurable lag calendar strategies
(PREDECESSOR_CALENDAR, SUCCESSOR_CALENDAR, PROJECT_DEFAULT, CONTINUOUS_24H).
When calendar_registry is None, single-calendar behavior is preserved exactly.

Normalization pipeline (V1-C — ADR-013) and simulation schedule generation
(V1-E — ADR-015): both hooks are SEVERED in this port (see the port-severance
note above) — mip39.normalization and mip39.simulation are not ported in this
wave. run_analysis() no longer accepts normalization_policy, data_date, or
simulation_input.

XER/Primavera import is handled by the mip39.xer ingestion layer
(INFRA-011 through INFRA-014; ADR-007, ADR-008). The engine operates on
Activity, Relationship, and Calendar objects regardless of their origin.

Entry point: run_analysis(activities, relationships, project_start,
                          workday_table, calendar, [optional parameters])

Source:
  ADR-002 — Retained Logic; forensic scheduling mode.
  ADR-005 — Forensic defensibility; determinism; traceability.
  ADR-012 — V1-B.1 multi-calendar architecture.
  ADR-013 — V1-C normalization workflow governance.
  ADR-014 — V1-D destatusing and auto-drive governance.
  ADR-015 — V1-E simulation schedule generation governance.
  CPW-P6 Manual pp. 40-42 — Forward/backward pass; lag arithmetic.
  AACE 29R-03/52R-06 — CPM principles; float analysis.

Interpretation flags (recorded in AnalysisContext for analyst review):
  - FS lag=0: constrained ES = predecessor EF (same workday; P6 convention).
  - Multiple finish nodes: each receives LF = project_finish (max EF).
  - Longest-path tracing (INFRA-008): controlling predecessors identified from
    forward-pass constraints; all four PDM relationship types supported.

Date constraints (LIM-028 — CLOSED in this port):
  Optional P6-style date constraints (SNET/SNLT/FNET/FNLT/SO/FO/MS/MF/ALAP/XF)
  are applied in the forward and backward passes at day granularity when the
  caller passes ``constraints=`` to run_analysis(). See scheduleiq.cpm.constraints.
  Every applied constraint is disclosed in a ConstraintApplication log
  (P6-compatible analytical convention; not exact P6 emulation — ADR-006).

Progress Override statusing mode (net-new — the source implements Retained
Logic only, per ADR-002):
  run_analysis() accepts ``statusing_mode=StatusingMode.PROGRESS_OVERRIDE`` to
  drop the retained-logic tie from an in-progress (started-but-incomplete)
  predecessor to its successor's remaining work. The default,
  StatusingMode.RETAINED_LOGIC, is bit-identical to prior behavior.

Explicitly excluded (LIM references):
  - Resource constraints
  - Hour-level lag precision (fractional workday lags truncated to integer)
  - Exact P6 constraint/statusing emulation (day-granularity approximation only).
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any, Optional

from .calendar_ops import _adjust_nonworkday, nearest_workday_index as _wd_index
from .calendar_registry import CalendarRegistry, LagCalendarStrategy
from .constraints import (
    ConstraintApplication,
    ConstraintType,
    SchedulingConstraint,
    StatusingMode,
    apply_backward_constraint,
    apply_forward_constraint,
    constraint_is_start_anchored,
)
from .context import AnalysisContext, CalculationMode, ScheduleMetadata
from .conventions import EFConvention, fs_forward_offset
from .lag_analysis import apply_lag
from .models import Activity, Calendar, Relationship
from .network import ActivityNetwork, topological_sort
# destatusing.DestatusingInput/run_destatusing imported lazily in run_analysis()
# (inside the `if destatusing_input is not None` block): mip39.destatusing is
# being ported separately, in parallel, and must not be a hard import-time
# dependency of this module (W1a port severance).
# normalization and simulation hooks are not ported in this wave (W1a port
# severance) — see the module docstring.
from .relationship_logic import compute_relationship_constraint
from .longest_path import trace_longest_paths
from .results import AnalysisResult, CriticalPathInfo, ScheduledActivity
from .validation import NetworkValidator
from .warnings import AnalysisWarning, WarningCategory, WarningLog


# ---------------------------------------------------------------------------
# Documented interpretation flags, assumptions, exclusions
# ---------------------------------------------------------------------------

_INTERPRETATION_FLAGS: list[str] = [
    "FS lag=0 convention: constrained ES = predecessor EF (same workday; "
    "P6 day-granularity). Requires analyst confirmation for project-specific "
    "calendar settings.",
    "Multiple finish nodes: all receive LF = project_finish (max EF across "
    "all activities). Standard backward-pass convention for open-end networks.",
    "Critical path: longest-path tracing (INFRA-008; AACE 49R-06). Controlling "
    "predecessors identified from forward-pass constraints. TF=0 reported as "
    "secondary diagnostic for comparison. Divergence flags (CP-001 to CP-004) "
    "raised when TF=0 set and longest-path set differ.",
    "Total float: TF = workday_table[LF] - workday_table[EF]. Integer workday "
    "count. Equivalent to LS_workday - ES_workday under Retained Logic.",
]

_ASSUMPTIONS: list[str] = [
    "Activities with no predecessors start at project_start.",
    "Integer workday durations only; fractional durations are rejected.",
    "EF = ES + (OD - 1) workdays for OD >= 1; EF = ES for OD = 0 (milestone).",
    "FS lag=0: successor ES = predecessor EF (same workday; P6 convention).",
    "Retained Logic scheduling throughout; no Progress Override (ADR-002).",
    "Multiple finish nodes each receive LF = project_finish.",
    "Longest-path tracing uses forward-pass ES/EF; controlling predecessor is "
    "the predecessor whose constraint equals the activity's scheduled ES (FS/SS) "
    "or EF (FF/SF). Ties produce multiple controlling paths.",
]

_EXCLUDED: list[str] = [
    "Date constraints (START_ON, FINISH_ON, etc.) — scheduling behavior "
    "deferred (LIM-028).",
    "Resource constraints.",
    "Hour-level lag precision (integer workday lags only).",
    "Progress Override calculation mode (ADR-002).",
    "Exact P6 calendar emulation (exception dates, fiscal periods).",
    "Per-relationship lag calendar assignment (deferred post-V1-D).",
    "XER/Primavera import is handled by mip39.xer, not engine.py "
    "(INFRA-011 through INFRA-014; ADR-007, ADR-008).",
]


# ---------------------------------------------------------------------------
# INFRA-007: CPM engine — internal helpers
# ---------------------------------------------------------------------------

def _validate_duration(act_id: str, od: object) -> int:
    """
    Validate and return original_duration as a non-negative integer.

    Raises ValueError for None, fractional, or negative durations.
    """
    if od is None:
        raise ValueError(
            f"run_analysis: activity {act_id!r} has original_duration=None. "
            "All activities require a duration."
        )
    if od != int(od):  # type: ignore[operator]
        raise ValueError(
            f"run_analysis: activity {act_id!r} has fractional "
            f"original_duration={od}. Integer workday durations required."
        )
    od_int = int(od)  # type: ignore[arg-type]
    if od_int < 0:
        raise ValueError(
            f"run_analysis: activity {act_id!r} has negative "
            f"original_duration={od_int}."
        )
    return od_int


def _build_context(
    activities: list[Activity],
    relationships: list[Relationship],
    project_start: date,
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
) -> AnalysisContext:
    """Build and configure an AnalysisContext for this run."""
    metadata = ScheduleMetadata(
        project_start=project_start.isoformat(),
        activity_count=len(activities),
        relationship_count=len(relationships),
    )
    ctx = AnalysisContext(
        schedule_metadata=metadata,
        calendar_name=calendar.name,
        hours_per_day=calendar.hours_per_day,
        ef_convention=convention.value,
    )
    for flag in _INTERPRETATION_FLAGS:
        ctx.add_interpretation_flag(flag)
    for assumption in _ASSUMPTIONS:
        ctx.add_assumption(assumption)
    for cap in _EXCLUDED:
        ctx.add_excluded_capability(cap)
    # Record convention-specific assumption
    fs_offset = fs_forward_offset(convention)
    ctx.convention_assumptions = [
        f"EF convention: {convention.value}. FS forward offset = {fs_offset} workday(s). "
        f"{'Same-workday FS (P3-tradition; backward-compatible).' if fs_offset == 0 else 'Next-workday FS (P6 analytical approximation; not exact P6 emulation).'}"
    ]
    if convention == EFConvention.P6_COMPATIBILITY:
        ctx.convention_warnings = [
            "P6_COMPATIBILITY convention is an analytical approximation of P6 "
            "day-level behavior. It is NOT exact P6 emulation. Results require "
            "analyst confirmation before use in forensic analysis (ADR-006)."
        ]
    return ctx


def _run_forward_pass(
    network: ActivityNetwork,
    project_start: date,
    workday_table: dict[date, int],
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
    act_workday_tables: Optional[dict[str, dict[date, int]]] = None,
    act_calendars: Optional[dict[str, Calendar]] = None,
    lag_workday_table: Optional[dict[date, int]] = None,
    lag_calendar: Optional[Calendar] = None,
    lag_resources: Optional[dict] = None,
) -> tuple[dict[str, Activity], list[str]]:
    """
    Extended forward pass supporting all four PDM relationship types.

    Returns: (scheduled, topological_order)
    scheduled maps activity_id → Activity copy with early_start and early_finish set.

    FF/SF constraint resolution: compute candidate EF from EF-type constraints,
    then derive ES = apply_lag(candidate_EF, -(OD-1), ...). Final ES is the max
    over all ES-type constraints and ES values derived from EF-type constraints.

    V1-B.1: act_workday_tables and act_calendars provide per-activity workday
    resources. lag_workday_table and lag_calendar override lag arithmetic for all
    relationships (resolved from LagCalendarStrategy by the caller). When not
    provided, single-calendar behavior is preserved exactly.
    """
    topo_order = topological_sort(network)
    scheduled: dict[str, Activity] = {}

    _default_lag_wt = lag_workday_table if lag_workday_table is not None else workday_table
    _default_lag_cal = lag_calendar if lag_calendar is not None else calendar

    for act_id in topo_order:
        activity = network.activities[act_id]
        od_int = _validate_duration(act_id, activity.original_duration)
        span = max(0, od_int - 1)

        # Per-activity workday resources (fall back to project default)
        _act_wt = (act_workday_tables or {}).get(act_id, workday_table)
        _act_cal = (act_calendars or {}).get(act_id, calendar)

        es_constraints: list[date] = []
        ef_constraints: list[date] = []

        # V2-A: a fully-pinned (completed) activity ignores predecessor logic
        # entirely (brief §4.2/§4.3). Skip the predecessor loop: its incoming
        # edges were dropped from the topological order, so a predecessor may
        # not yet be in `scheduled` (e.g. inside a tolerated all-pinned cycle).
        # Building constraints would be both unused and a potential KeyError.
        _fully_pinned = (
            activity.pinned_early_start is not None
            and activity.pinned_early_finish is not None
        )
        pred_rels = [] if _fully_pinned else network.predecessors.get(act_id, [])

        for rel in pred_rels:
            pred = scheduled[rel.pred_id]
            if lag_resources is not None:
                pred_cid = network.activities[rel.pred_id].calendar_id
                succ_cid = network.activities[act_id].calendar_id
                # resolve_lag_resources returns (Calendar, workday_table)
                _rel_lag_cal, _rel_lag_wt = lag_resources.get(
                    (pred_cid or "", succ_cid or ""),
                    (_default_lag_cal, _default_lag_wt),
                )
            else:
                _rel_lag_wt, _rel_lag_cal = _default_lag_wt, _default_lag_cal
            c_type, c_date = compute_relationship_constraint(
                rel.rel_type,
                pred.early_start,   # type: ignore[arg-type]
                pred.early_finish,  # type: ignore[arg-type]
                rel.lag,
                _rel_lag_wt,
                _rel_lag_cal,
                convention,
            )
            if c_type == "ES":
                es_constraints.append(c_date)
            else:
                ef_constraints.append(c_date)

        candidate_es = project_start
        if es_constraints:
            candidate_es = max(candidate_es, max(es_constraints))
        if ef_constraints:
            # Derive ES from the most constraining EF: ES = EF - span
            candidate_ef = max(ef_constraints)
            es_from_ef = apply_lag(
                candidate_ef, -span, _act_wt, _act_cal, anchor_is_start=False
            )
            candidate_es = max(candidate_es, es_from_ef)

        # -- V2-A actual-date-anchored CPM ("pinning"; ADR-019, brief §4.2) --
        # A pinned date is a hard fact (the activity actually occurred there),
        # so it OVERRIDES the predecessor-derived candidate entirely — we do
        # NOT take max(candidate_es, pinned). If predecessor logic implies a
        # later date, the logic is wrong (out-of-sequence progress), not the
        # actual date. The pinned es/ef still flow into successors through the
        # unchanged predecessor loop above, which is what propagates the anchor.
        pinned_es = activity.pinned_early_start
        pinned_ef = activity.pinned_early_finish
        if pinned_es is not None and pinned_ef is not None:
            # Completed activity: both dates fixed at actuals.
            es = pinned_es
            ef = pinned_ef
        elif pinned_es is not None:
            # In-progress activity: ES is pinned at the actual start (a historical
            # fact), but the REMAINING work resumes at the data date, NOT at the
            # actual start (P6 semantics; ADR-019). candidate_es already floors at
            # project_start (= data date for anchored runs) and honors any
            # predecessor that drives the remaining work later. EF is therefore
            # computed forward from candidate_es over the remaining span, while ES
            # is recorded at the actual start. remaining_span = max(0, RD - 1).
            es = pinned_es
            rd = activity.remaining_duration
            remaining_span = max(0, int(rd) - 1) if rd is not None else span
            rem_start = max(candidate_es, pinned_es)
            ef = apply_lag(rem_start, remaining_span, _act_wt, _act_cal)
        else:
            # No pins (future activity): unchanged logic-driven behavior.
            es = candidate_es
            ef = apply_lag(es, span, _act_wt, _act_cal)

        sched_act = copy.copy(activity)
        sched_act.early_start = es
        sched_act.early_finish = ef
        scheduled[act_id] = sched_act

    return scheduled, topo_order


def _run_backward_pass(
    network: ActivityNetwork,
    scheduled: dict[str, Activity],
    topo_order: list[str],
    project_finish: date,
    workday_table: dict[date, int],
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
    act_workday_tables: Optional[dict[str, dict[date, int]]] = None,
    act_calendars: Optional[dict[str, Calendar]] = None,
    lag_workday_table: Optional[dict[date, int]] = None,
    lag_calendar: Optional[Calendar] = None,
    lag_resources: Optional[dict] = None,
) -> tuple[dict[str, date], dict[str, date]]:
    """
    Backward pass supporting all four PDM relationship types.

    Returns: (late_start, late_finish) — both dicts mapping activity_id → date.

    LF constraints by relationship type (A→B, lag=k, span_A = max(0, OD_A - 1)):
      FS: A.LF ≤ B.LS - k            → apply_lag(B.LS, -k, ..., start)
      SS: A.LF ≤ B.LS - k + span_A   → apply_lag(B.LS, -k+span_A, ..., start)
      FF: A.LF ≤ B.LF - k            → apply_lag(B.LF, -k, ..., finish)
      SF: A.LF ≤ B.LF - k + span_A   → apply_lag(B.LF, -k+span_A, ..., finish)

    Finish nodes (no successors) receive LF = project_finish.
    LS = apply_lag(LF, -span_A, ..., finish).
    """
    late_finish: dict[str, date] = {}
    late_start: dict[str, date] = {}

    _default_lag_wt = lag_workday_table if lag_workday_table is not None else workday_table
    _default_lag_cal = lag_calendar if lag_calendar is not None else calendar

    for act_id in reversed(topo_order):
        activity = scheduled[act_id]
        od_int = _validate_duration(act_id, activity.original_duration)
        span = max(0, od_int - 1)

        # Per-activity workday resources (fall back to project default)
        _act_wt = (act_workday_tables or {}).get(act_id, workday_table)
        _act_cal = (act_calendars or {}).get(act_id, calendar)

        # V2-A: for a pinned activity the forward pass fixed ES/EF directly, so
        # the effective span is (EF - ES) in workdays — NOT necessarily OD-1.
        # In particular an in-progress pin computes EF from remaining duration.
        # Use the scheduled-date span so LS = apply_lag(LF, -span) stays
        # consistent with the anchored ES/EF (brief §4.2). Unpinned activities
        # keep the original OD-derived span exactly.
        if activity.pinned_early_start is not None:
            es_wd = _act_wt.get(activity.early_start)
            ef_wd = _act_wt.get(activity.early_finish)
            if es_wd is not None and ef_wd is not None:
                span = max(0, ef_wd - es_wd)

        # V2-A: drop outgoing edges into fully-pinned successors, mirroring the
        # topological sort (brief §4.3). Those edges are non-binding (the pinned
        # successor ignores predecessor logic), so they impose no late-date
        # constraint on this activity. This also keeps backward dates available
        # for every successor read below inside a tolerated all-pinned cycle.
        outgoing = [
            rel for rel in network.successors.get(act_id, [])
            if not (
                scheduled[rel.succ_id].pinned_early_start is not None
                and scheduled[rel.succ_id].pinned_early_finish is not None
            )
        ]
        if not outgoing:
            lf = project_finish
        else:
            lf_constraints: list[date] = []
            for rel in outgoing:
                succ_ls = late_start[rel.succ_id]
                succ_lf = late_finish[rel.succ_id]
                k = int(rel.lag)

                if lag_resources is not None:
                    pred_cid = network.activities[act_id].calendar_id
                    succ_cid = network.activities[rel.succ_id].calendar_id
                    # resolve_lag_resources returns (Calendar, workday_table)
                    _rel_lag_cal, _rel_lag_wt = lag_resources.get(
                        (pred_cid or "", succ_cid or ""),
                        (_default_lag_cal, _default_lag_wt),
                    )
                else:
                    _rel_lag_wt, _rel_lag_cal = _default_lag_wt, _default_lag_cal

                if rel.rel_type == "FS":
                    constraint = apply_lag(
                        succ_ls, -k - fs_forward_offset(convention),
                        _rel_lag_wt, _rel_lag_cal, anchor_is_start=True
                    )
                elif rel.rel_type == "SS":
                    constraint = apply_lag(
                        succ_ls, -k + span, _rel_lag_wt, _rel_lag_cal, anchor_is_start=True
                    )
                elif rel.rel_type == "FF":
                    constraint = apply_lag(
                        succ_lf, -k, _rel_lag_wt, _rel_lag_cal, anchor_is_start=False
                    )
                else:  # SF
                    constraint = apply_lag(
                        succ_lf, -k + span, _rel_lag_wt, _rel_lag_cal, anchor_is_start=False
                    )
                lf_constraints.append(constraint)

            lf = min(lf_constraints)

        ls = apply_lag(lf, -span, _act_wt, _act_cal, anchor_is_start=False)
        late_finish[act_id] = lf
        late_start[act_id] = ls

    return late_start, late_finish


def _compute_floats(
    network: ActivityNetwork,
    scheduled: dict[str, Activity],
    late_start: dict[str, date],
    late_finish: dict[str, date],
    workday_table: dict[date, int],
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
    act_workday_tables: Optional[dict[str, dict[date, int]]] = None,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Compute Total Float and Free Float for all activities.

    TF: workday_table[LF] - workday_table[EF]

    FF per outgoing relationship (A→B, lag=k):
      FS: B.ES_workday - A.EF_workday - k
      SS: B.ES_workday - A.ES_workday - k
      FF: B.EF_workday - A.EF_workday - k
      SF: B.EF_workday - A.ES_workday - k
    FF(A) = min over all outgoing relationships.
    Finish nodes (no successors): FF = TF.

    Returns: (total_float, free_float) — both dicts mapping activity_id → int.
    """
    total_float: dict[str, int] = {}
    free_float: dict[str, int] = {}

    for act_id, activity in scheduled.items():
        _act_wt = (act_workday_tables or {}).get(act_id, workday_table)
        ls = late_start[act_id]
        # LS_wd - ES_wd is equivalent to LF_wd - EF_wd for workday arithmetic,
        # and avoids a KeyError when project_finish lands on a non-workday in
        # this activity's calendar (e.g., Saturday for a Mon-Fri activity in
        # a multi-calendar network).
        tf = _wd_index(_act_wt, ls) - _wd_index(_act_wt, activity.early_start)
        total_float[act_id] = tf

        outgoing = network.successors.get(act_id, [])
        if not outgoing:
            free_float[act_id] = tf
        else:
            ff_contribs: list[int] = []
            for rel in outgoing:
                succ = scheduled[rel.succ_id]
                k = int(rel.lag)
                _succ_wt = (act_workday_tables or {}).get(rel.succ_id, workday_table)
                if rel.rel_type == "FS":
                    contrib = (
                        _wd_index(_succ_wt, succ.early_start)
                        - _wd_index(_act_wt, activity.early_finish)
                        - k
                        - fs_forward_offset(convention)
                    )
                elif rel.rel_type == "SS":
                    contrib = (
                        _wd_index(_succ_wt, succ.early_start)
                        - _wd_index(_act_wt, activity.early_start)
                        - k
                    )
                elif rel.rel_type == "FF":
                    contrib = (
                        _wd_index(_succ_wt, succ.early_finish)
                        - _wd_index(_act_wt, activity.early_finish)
                        - k
                    )
                else:  # SF
                    contrib = (
                        _wd_index(_succ_wt, succ.early_finish)
                        - _wd_index(_act_wt, activity.early_start)
                        - k
                    )
                ff_contribs.append(contrib)
            free_float[act_id] = min(ff_contribs)

    return total_float, free_float


# ---------------------------------------------------------------------------
# INFRA-007: CPM engine — public entry point
# ---------------------------------------------------------------------------

def run_analysis(
    activities: list[Activity],
    relationships: list[Relationship],
    project_start: date,
    workday_table: dict[date, int],
    calendar: Calendar,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
    calendar_registry: Optional[CalendarRegistry] = None,
    lag_strategy: Optional[LagCalendarStrategy] = None,
    destatusing_input: Optional[Any] = None,
) -> AnalysisResult:
    """
    INFRA-007 — Phase 3 Core CPM Analytical Engine.

    Runs a complete PDM critical path analysis under Retained Logic scheduling:
    network validation → forward pass → backward pass → float → critical path.

    All four PDM relationship types are supported: FS, SS, FF, SF.

    Source:
        ADR-002 (Retained Logic; integer lags).
        ADR-012 (V1-B.1 multi-calendar: optional CalendarRegistry).
        ADR-005 §7 (determinism; traceability; forensic defensibility).
        CPW-P6 Manual pp. 40-42 (forward/backward pass; lag arithmetic).
        AACE 29R-03/52R-06 (CPM principles; float analysis).

        (W1a port severance: the normalization_policy/data_date and
        simulation_input hooks documented in the mip39 source are not present
        in this port — mip39.normalization and mip39.simulation are not
        ported in this wave. See the module docstring.)

    Assumptions:
        - Integer workday durations only. Fractional durations raise ValueError.
        - FS lag=0: successor ES = predecessor EF (same workday; P6 convention).
        - project_start adjusted to next workday if it falls on a non-workday.
        - Retained Logic throughout; no Progress Override (ADR-002).
        - No date constraints beyond project_start (LIM-028).
        - workday_table must cover the full project date range.

    Args:
        activities:       List of Activity objects.
        relationships:    List of Relationship objects.
        project_start:    Desired project start date.
        workday_table:    Prebuilt workday table covering the full project range.
        calendar:         Project-default calendar.
        convention:       EF convention (default: INCLUSIVE_DAY).
        calendar_registry: Optional CalendarRegistry for multi-calendar scheduling
                          (V1-B.1). When provided, per-activity workday tables are
                          used for duration arithmetic. Must have workday tables
                          already built (call build_workday_tables() first).
                          When None, single-calendar behavior is preserved exactly.
        lag_strategy:     LagCalendarStrategy to use when calendar_registry is
                          provided. Defaults to PREDECESSOR_CALENDAR when not set.
        destatusing_input: Optional DestatusingInput (mip39.destatusing; typed
                          Optional[Any] here since that module is ported
                          separately and is not a hard dependency of this
                          module — W1a port severance) for V1-D destatusing,
                          lag analysis, and auto-drive workflows (ADR-014).
                          When provided, run_destatusing() runs after CPM
                          analysis and attaches a DestatusingResult to the
                          returned AnalysisResult. Default None (no destatusing).

    Returns:
        AnalysisResult with context, validation, warnings, scheduled activities,
        critical path, and is_valid flag.

    Raises:
        ValueError: If any activity has None, fractional, or negative
                    original_duration, or if project_start is outside the table.
    """
    # -- Set up context and warning log -------------------------------------
    ctx = _build_context(activities, relationships, project_start, calendar, convention)
    warning_log = WarningLog()

    # -- Network validation (INFRA-002) -------------------------------------
    validator = NetworkValidator(activities, relationships)
    validation_result = validator.validate_all()
    ctx.record_validation_summary(validation_result.summary())

    if validation_result.has_blocking_issues:
        ctx.warning_count = 0
        return AnalysisResult(
            context=ctx,
            validation=validation_result,
            warnings=warning_log,
            scheduled={},
            critical_path=None,
            project_start=project_start,
            project_finish=None,
            is_valid=False,
        )

    # -- Build network (safe: validation confirmed no blocking issues) ------
    network = ActivityNetwork(activities, relationships)

    # -- Adjust project_start to workday if needed -------------------------
    if not calendar.is_workday(project_start):
        adjusted = _adjust_nonworkday(project_start, calendar, is_start=True)
        warning_log.add(AnalysisWarning(
            code="ENG-001",
            category=WarningCategory.SCHEDULE_INTEGRITY,
            message=(
                f"project_start {project_start} is a non-workday; "
                f"adjusted to next workday {adjusted}."
            ),
            source_reference="CPW-P6 Manual pp. 41-42 (CALC-001 non-workday adjustment)",
        ))
        project_start = adjusted

    if project_start not in workday_table:
        raise ValueError(
            f"run_analysis: project_start {project_start} is not in the workday "
            "table. Extend the table to cover the full project date range."
        )

    # -- Multi-calendar setup (V1-B.1) — build per-activity resources ------
    act_workday_tables: Optional[dict[str, dict[date, int]]] = None
    act_calendars: Optional[dict[str, Calendar]] = None
    lag_wt: Optional[dict[date, int]] = None
    lag_cal: Optional[Calendar] = None
    lag_resources: Optional[dict] = None  # (pred_cid, succ_cid) → (Calendar, table)

    if calendar_registry is not None:
        # No silent single-calendar fallback (ADR-029 r2, Codex guardrail 3): a
        # present registry MUST have per-calendar tables covering the run range.
        # The shared resource helper (build_calendar_resources) ensures this
        # before run_analysis; a direct caller that skips it gets a disclosed
        # error rather than a quiet single-calendar result. ``tables_built()`` is
        # NOT a sufficient gate (it can't prove THIS range is covered — P1b).
        _cov = getattr(calendar_registry, "tables_cover", None)
        _lo, _hi = min(workday_table), max(workday_table)
        if not (callable(_cov) and _cov(_lo, _hi)):
            raise ValueError(
                "run_analysis: calendar_registry is present but its per-calendar "
                f"tables do not cover the run range [{_lo} .. {_hi}]. Call "
                "ensure_workday_tables() (via build_calendar_resources) before "
                "run_analysis — refusing to silently fall back to a single calendar."
            )
        _strategy = lag_strategy or LagCalendarStrategy.PREDECESSOR_CALENDAR
        # Build per-activity tables from registry
        act_workday_tables = {}
        act_calendars = {}
        for act in activities:
            if act.calendar_id is not None:
                tbl = calendar_registry.get_workday_table(act.calendar_id)
                cal = calendar_registry.get(act.calendar_id)
                if tbl is not None and cal is not None:
                    act_workday_tables[act.act_id] = tbl
                    act_calendars[act.act_id] = cal
        # Precompute per-relationship lag resources keyed by (pred_cal_id, succ_cal_id).
        # Each unique calendar pair resolves once; relationships sharing the same
        # pair reuse the cached result.  This replaces the prior single-global
        # resolution that always used the project-default calendar for both sides.
        _act_cal_ids: dict[str, Optional[str]] = {
            act.act_id: act.calendar_id for act in activities
        }
        lag_resources = {}
        for rel in relationships:
            pred_cid = _act_cal_ids.get(rel.pred_id)
            succ_cid = _act_cal_ids.get(rel.succ_id)
            pair = (pred_cid or "", succ_cid or "")
            if pair not in lag_resources:
                lag_resources[pair] = calendar_registry.resolve_lag_resources(
                    strategy=_strategy,
                    pred_clndr_id=pred_cid,
                    succ_clndr_id=succ_cid,
                    fallback_calendar=calendar,
                    fallback_table=workday_table,
                )
        # Scalar fallback — used as lag_workday_table/lag_calendar in both passes
        # for any relationship whose pair was not precomputed (defensive).
        _lag_cal_obj, _lag_tbl = calendar_registry.resolve_lag_resources(
            strategy=_strategy,
            pred_clndr_id=calendar_registry.get_default_clndr_id(),
            succ_clndr_id=calendar_registry.get_default_clndr_id(),
            fallback_calendar=calendar,
            fallback_table=workday_table,
        )
        lag_wt = _lag_tbl
        lag_cal = _lag_cal_obj

    # -- Extended forward pass (all four PDM types) -------------------------
    scheduled, topo_order = _run_forward_pass(
        network, project_start, workday_table, calendar, convention,
        act_workday_tables=act_workday_tables,
        act_calendars=act_calendars,
        lag_workday_table=lag_wt,
        lag_calendar=lag_cal,
        lag_resources=lag_resources,
    )

    project_finish: date = max(
        a.early_finish  # type: ignore[misc]
        for a in scheduled.values()
        if a.early_finish is not None
    )

    # -- Backward pass (all four PDM types) --------------------------------
    late_start, late_finish = _run_backward_pass(
        network, scheduled, topo_order, project_finish, workday_table, calendar, convention,
        act_workday_tables=act_workday_tables,
        act_calendars=act_calendars,
        lag_workday_table=lag_wt,
        lag_calendar=lag_cal,
        lag_resources=lag_resources,
    )

    # -- Float computation -------------------------------------------------
    total_float, free_float = _compute_floats(
        network, scheduled, late_start, late_finish, workday_table, convention,
        act_workday_tables=act_workday_tables,
    )

    # -- Build ScheduledActivity objects -----------------------------------
    result_scheduled: dict[str, ScheduledActivity] = {}
    for act_id in topo_order:
        activity = scheduled[act_id]
        od_int = _validate_duration(act_id, activity.original_duration)
        result_scheduled[act_id] = ScheduledActivity(
            activity_id=act_id,
            original_duration=od_int,
            early_start=activity.early_start,   # type: ignore[arg-type]
            early_finish=activity.early_finish, # type: ignore[arg-type]
            late_start=late_start[act_id],
            late_finish=late_finish[act_id],
            total_float=total_float[act_id],
            free_float=free_float[act_id],
            is_critical=(total_float[act_id] == 0),
        )

    # -- Longest-path tracing (INFRA-008; resolves LIM-029) ---------------
    lp_result = trace_longest_paths(
        scheduled=scheduled,
        predecessors=network.predecessors,
        successors=network.successors,
        topo_order=topo_order,
        total_float=total_float,
        workday_table=workday_table,
        project_finish=project_finish,
        convention=convention,
        act_workday_tables=act_workday_tables,
    )

    # Emit divergence warnings into the run-level warning log
    for warn_msg in lp_result.cp_warnings:
        warning_log.add_plain(
            code=warn_msg.split(":")[0].strip(),
            category=WarningCategory.ANALYST_REVIEW,
            message=warn_msg,
            source_reference="AACE 49R-06 §4.2; ADR-005",
            analyst_action=(
                "Review critical path methodology output and divergence flags "
                "before using results in forensic analysis."
            ),
        )

    # In multi-calendar mode, project_finish may land on a day absent from the
    # default workday_table (e.g., Saturday when the default is Mon-Fri).
    # Fall back to the longest-path duration already computed by trace_longest_paths.
    if project_finish in workday_table and project_start in workday_table:
        project_duration = workday_table[project_finish] - workday_table[project_start] + 1
    else:
        project_duration = lp_result.project_duration
    critical_path = CriticalPathInfo(
        # activity_ids: union of all longest-path activities in topo order
        activity_ids=lp_result.longest_path_activities,
        project_duration=project_duration,
        method_used="longest_path",
        controlling_paths=[p.to_dict() for p in lp_result.controlling_paths],
        path_duration=lp_result.project_duration,
        tied_paths=lp_result.tied_paths,
        controlling_finish_nodes=lp_result.controlling_finish_nodes,
        tf_zero_activities=lp_result.tf_zero_activities,
        divergence_flags=lp_result.divergence_flags,
        divergence_details=lp_result.divergence_details,
        cp_warnings=lp_result.cp_warnings,
        cp_assumptions=lp_result.cp_assumptions,
        ef_convention=convention.value,
    )

    # Update is_critical on each ScheduledActivity to reflect longest path
    lp_set = set(lp_result.longest_path_activities)
    for act_id, sa in result_scheduled.items():
        result_scheduled[act_id] = type(sa)(
            activity_id=sa.activity_id,
            original_duration=sa.original_duration,
            early_start=sa.early_start,
            early_finish=sa.early_finish,
            late_start=sa.late_start,
            late_finish=sa.late_finish,
            total_float=sa.total_float,
            free_float=sa.free_float,
            is_critical=(act_id in lp_set),
        )

    ctx.warning_count = len(warning_log)

    # -- Normalization run: SEVERED in this port (W1a) -----------------------
    # mip39.normalization is not ported in this wave; normalization_policy and
    # data_date are no longer accepted by this function. See module docstring.
    norm_result = None

    # -- Optional destatusing run (V1-D; ADR-014) ----------------------------
    # NOTE (ADR-029 4.7b r6): destatusing_input carries a workday table the CALLER
    # sized. run_destatusing now re-raises a table-COVERAGE error (rather than
    # masking it as DST_011 with unmodified durations) — so if a caller passes an
    # under-sized table here, that ValueError propagates by design. Do NOT "fix" it
    # by re-masking (that reintroduces silent-wrong durations into CPM); the right
    # fix is for the caller to size/grow its table (no in-tree caller passes
    # destatusing_input — the API/CLI run destatusing via build_resources_with_growth).
    #
    # Import is lazy (W1a port severance): mip39.destatusing/scheduleiq.cpm's
    # destatusing package is ported separately, in parallel, and must not be a
    # hard import-time dependency of this module.
    dst_result = None
    if destatusing_input is not None:
        from .destatusing import DestatusingInput, run_destatusing
        dst_result = run_destatusing(destatusing_input)

    # -- Simulation run: SEVERED in this port (W1a) --------------------------
    # mip39.simulation is not ported in this wave; simulation_input is no
    # longer accepted by this function. See module docstring.
    sim_result = None

    return AnalysisResult(
        context=ctx,
        validation=validation_result,
        warnings=warning_log,
        scheduled=result_scheduled,
        critical_path=critical_path,
        project_start=project_start,
        project_finish=project_finish,
        is_valid=True,
        normalization_result=norm_result,
        destatusing_result=dst_result,
        simulation_result=sim_result,
    )
