"""
Ported from the LI MIP 3.9 tool (mip39.longest_path) per ADR-0007 — port-and-validate.
INFRA-008: Phase 4 Longest-Path Tracing.

Implements actual longest-path (controlling-path) identification for PDM
networks under Retained Logic scheduling. Resolves LIM-029.

Algorithm:
  1. After the forward pass (ES/EF known for all activities), identify
     the "controlling predecessor" relationship(s) for each activity —
     the predecessor whose forward-pass constraint equals the activity's
     scheduled ES (FS/SS relationships) or EF (FF/SF relationships).
  2. Trace backward from controlling finish node(s) through controlling
     predecessors to reconstruct all longest/controlling paths.
  3. Identify ties (equal-duration controlling paths).
  4. Compute divergence between TF=0 set and longest-path set.

Divergence diagnostics:
  CP-001  TF=0 activities NOT on any longest path.
  CP-002  Multiple equal-duration controlling paths (tied).
  CP-003  Multiple finish nodes controlling the project duration.
  CP-004  Longest-path activity with positive total float.

Source:
  AACE 49R-06 §4.2 — Identifying the Critical Path (primary methodology).
  AACE 92R-17 — Near-critical context (path bounding; not implemented here).
  ADR-005     — Forensic defensibility; determinism; traceability.

Limitations:
  - Date constraints not yet implemented (LIM-028); results assume
    unconstrained network.
  - Single calendar only.
  - Integer workday precision only.
  - Near-critical path analysis deferred (future phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .conventions import EFConvention, fs_forward_offset
from .calendar_ops import nearest_workday_index as _wd_index


# ---------------------------------------------------------------------------
# INFRA-008: Data structures
# ---------------------------------------------------------------------------

@dataclass
class PathInfo:
    """
    One reconstructed controlling (longest) path through the network.

    Fields:
        path_id:               Unique identifier — "CP-1", "CP-2", etc.
                               Stable ordering: paths are sorted lexicographically
                               by activity_ids list before IDs are assigned.
        activity_ids:          Activity IDs in source-to-sink (start → finish) order.
        relationship_sequence: [(pred_id, succ_id, rel_type), ...] in path order.
        path_duration:         Workday span: wt[last.EF] − wt[first.ES] + 1.
    """
    path_id: str
    activity_ids: list[str]
    relationship_sequence: list[tuple[str, str, str]]
    path_duration: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for audit output."""
        return {
            "path_id": self.path_id,
            "activity_ids": list(self.activity_ids),
            "relationship_sequence": [list(r) for r in self.relationship_sequence],
            "path_duration": self.path_duration,
        }


@dataclass
class LongestPathResult:
    """
    Complete longest-path analysis result produced by trace_longest_paths().

    Fields:
        controlling_paths:        All equal-duration controlling paths (PathInfo list).
        project_duration:         Workday span (inclusive) of the controlling path(s).
        tied_paths:               True when more than one controlling path exists.
        controlling_finish_nodes: Finish-node activity IDs with EF == project_finish.
        tf_zero_activities:       Activities with TF=0 in topological order.
        longest_path_activities:  Union of all activities on any controlling path,
                                  in topological order.
        divergence_flags:         CP-001 through CP-004, sorted, when detected.
        divergence_details:       Per-flag detail — flag_code → list of activity IDs.
        cp_warnings:              Advisory messages for analyst review.
        cp_assumptions:           Methodology assumptions applied during tracing.
    """
    controlling_paths: list[PathInfo]
    project_duration: int
    tied_paths: bool
    controlling_finish_nodes: list[str]
    tf_zero_activities: list[str]
    longest_path_activities: list[str]
    divergence_flags: list[str]
    divergence_details: dict[str, list[str]]
    cp_warnings: list[str]
    cp_assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for audit output."""
        return {
            "controlling_paths": [p.to_dict() for p in self.controlling_paths],
            "project_duration": self.project_duration,
            "tied_paths": self.tied_paths,
            "controlling_finish_nodes": list(self.controlling_finish_nodes),
            "tf_zero_activities": list(self.tf_zero_activities),
            "longest_path_activities": list(self.longest_path_activities),
            "divergence_flags": list(self.divergence_flags),
            "divergence_details": {k: list(v) for k, v in self.divergence_details.items()},
            "cp_warnings": list(self.cp_warnings),
            "cp_assumptions": list(self.cp_assumptions),
        }


# ---------------------------------------------------------------------------
# Internal: controlling predecessor identification
# ---------------------------------------------------------------------------

def _find_controlling_predecessors(
    act_id: str,
    scheduled: dict[str, Any],
    predecessors: dict[str, list],  # act_id -> list[Relationship]
    workday_table: dict[Any, int],
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
    act_workday_tables: Optional[dict[str, dict[Any, int]]] = None,
) -> list:
    """
    Return all relationships that are controlling predecessors for act_id.

    A relationship A→B is controlling if the forward-pass constraint it
    imposes on B equals B's actual scheduled date:
      FS (lag k):  wt[A.EF] + k == wt[B.ES]
      SS (lag k):  wt[A.ES] + k == wt[B.ES]
      FF (lag k):  wt[A.EF] + k == wt[B.EF]
      SF (lag k):  wt[A.ES] + k == wt[B.EF]

    Ties (multiple simultaneously-tight constraints) are preserved.
    Result is sorted by pred_id for determinism.

    act_workday_tables: Optional per-activity workday tables (V1-B.1 multi-calendar).
    When provided, each activity's dates are looked up in its own table.
    """
    rels = predecessors.get(act_id, [])
    if not rels:
        return []

    _awt = act_workday_tables or {}
    _succ_wt = _awt.get(act_id, workday_table)
    act = scheduled[act_id]
    wt_es = _wd_index(_succ_wt, act.early_start)
    wt_ef = _wd_index(_succ_wt, act.early_finish)

    controlling = []
    for rel in rels:
        pred = scheduled[rel.pred_id]
        k = int(rel.lag)
        _pred_wt = _awt.get(rel.pred_id, workday_table)

        if rel.rel_type == "FS":
            tight = (_wd_index(_pred_wt, pred.early_finish) + k + fs_forward_offset(convention) == wt_es)
        elif rel.rel_type == "SS":
            tight = (_wd_index(_pred_wt, pred.early_start) + k == wt_es)
        elif rel.rel_type == "FF":
            tight = (_wd_index(_pred_wt, pred.early_finish) + k == wt_ef)
        elif rel.rel_type == "SF":
            tight = (_wd_index(_pred_wt, pred.early_start) + k == wt_ef)
        else:
            tight = False

        if tight:
            controlling.append(rel)

    return sorted(controlling, key=lambda r: r.pred_id)


# ---------------------------------------------------------------------------
# Internal: path reconstruction (memoised backward DFS)
# ---------------------------------------------------------------------------

def _trace_from(
    act_id: str,
    ctrl_preds: dict[str, list],
    memo: dict[str, list[list[str]]],
) -> list[list[str]]:
    """
    Return all paths from a network start node to act_id, where each path is
    a list of activity IDs in source-to-sink order ending with act_id.

    Memoised: each activity's paths are computed once.
    """
    if act_id in memo:
        return memo[act_id]

    controlling = ctrl_preds[act_id]
    if not controlling:
        result = [[act_id]]
    else:
        result = []
        for rel in controlling:
            pred_paths = _trace_from(rel.pred_id, ctrl_preds, memo)
            for path in pred_paths:
                result.append(path + [act_id])

    memo[act_id] = result
    return result


# ---------------------------------------------------------------------------
# INFRA-008: Public entry point
# ---------------------------------------------------------------------------

def trace_longest_paths(
    scheduled: dict[str, Any],
    predecessors: dict[str, list],
    successors: dict[str, list],
    topo_order: list[str],
    total_float: dict[str, int],
    workday_table: dict[Any, int],
    project_finish: Any,
    convention: EFConvention = EFConvention.INCLUSIVE_DAY,
    act_workday_tables: Optional[dict[str, dict[Any, int]]] = None,
) -> LongestPathResult:
    """
    INFRA-008 — Trace all controlling (longest) paths through the network.

    Inputs are the outputs of run_analysis()'s forward pass and float
    computation:
      scheduled     — activity_id → Activity with early_start, early_finish set.
      predecessors  — activity_id → list[Relationship] (incoming).
      successors    — activity_id → list[Relationship] (outgoing).
      topo_order    — activity IDs in topological order.
      total_float   — activity_id → TF (int workdays).
      workday_table — date → workday number (must cover full project range).
      project_finish — date: max EF across all activities.

    Returns:
        LongestPathResult with all controlling paths, divergence flags,
        and supporting metadata for analyst review.

    Source: AACE 49R-06 §4.2; ADR-005 §7.
    """
    # -- 1. Build controlling-predecessor map for every activity -----------
    ctrl_preds: dict[str, list] = {
        act_id: _find_controlling_predecessors(
            act_id, scheduled, predecessors, workday_table, convention,
            act_workday_tables=act_workday_tables,
        )
        for act_id in topo_order
    }

    # -- 2. Identify finish nodes (no successors) -------------------------
    finish_nodes = [act_id for act_id in topo_order if not successors.get(act_id)]

    # -- 3. Identify controlling finish nodes (EF == project_finish) ------
    # Use direct date comparison to support multi-calendar mode where the
    # project_finish date may not be in the default workday_table (V1-B.1).
    controlling_finish_nodes = sorted(
        act_id for act_id in finish_nodes
        if scheduled[act_id].early_finish == project_finish
    )

    # -- 4. Trace paths backward from every controlling finish node -------
    memo: dict[str, list[list[str]]] = {}
    raw_paths: list[list[str]] = []
    for fn in controlling_finish_nodes:
        raw_paths.extend(_trace_from(fn, ctrl_preds, memo))

    # -- 5. Deduplicate and build PathInfo objects (deterministic order) --
    seen: set[tuple[str, ...]] = set()
    unique_paths: list[list[str]] = []
    for path in raw_paths:
        key = tuple(path)
        if key not in seen:
            seen.add(key)
            unique_paths.append(path)

    # Deterministic sort: lexicographic by activity ID sequence
    unique_paths.sort()

    path_infos: list[PathInfo] = []
    for idx, path in enumerate(unique_paths, 1):
        # Build relationship sequence
        rel_seq: list[tuple[str, str, str]] = []
        for i in range(len(path) - 1):
            pred_id, succ_id = path[i], path[i + 1]
            # Find the controlling relationship between these two
            rel_type = "FS"  # fallback (should always find a match)
            for rel in ctrl_preds[succ_id]:
                if rel.pred_id == pred_id:
                    rel_type = rel.rel_type
                    break
            rel_seq.append((pred_id, succ_id, rel_type))

        first_act = scheduled[path[0]]
        last_act = scheduled[path[-1]]
        _awt = act_workday_tables or {}
        _first_wt = _awt.get(path[0], workday_table)
        _last_wt = _awt.get(path[-1], workday_table)
        duration = (
            _wd_index(_last_wt, last_act.early_finish)
            - _wd_index(_first_wt, first_act.early_start)
            + 1
        )

        path_infos.append(PathInfo(
            path_id=f"CP-{idx}",
            activity_ids=list(path),
            relationship_sequence=rel_seq,
            path_duration=duration,
        ))

    # Project duration (all controlling paths have the same duration)
    project_duration = path_infos[0].path_duration if path_infos else 0

    # -- 6. Compute supporting sets ---------------------------------------
    lp_set: set[str] = set()
    for pi in path_infos:
        lp_set.update(pi.activity_ids)
    longest_path_activities = [a for a in topo_order if a in lp_set]

    tf_zero_activities = [a for a in topo_order if total_float[a] == 0]
    tf_zero_set = set(tf_zero_activities)

    # -- 7. Divergence flags ----------------------------------------------
    divergence_flags: list[str] = []
    divergence_details: dict[str, list[str]] = {}
    cp_warnings: list[str] = []

    # CP-001: TF=0 activities NOT on the longest path
    tf_not_lp = sorted(tf_zero_set - lp_set)
    if tf_not_lp:
        divergence_flags.append("CP-001")
        divergence_details["CP-001"] = tf_not_lp
        cp_warnings.append(
            f"CP-001: {len(tf_not_lp)} TF=0 activity(ies) are not on any "
            f"longest path: {tf_not_lp}. Common cause: multiple finish nodes "
            "with different project completion dates. Analyst review required — "
            "TF=0 is not a reliable sole indicator of critical path membership."
        )

    # CP-002: Multiple tied controlling paths
    if len(path_infos) > 1:
        divergence_flags.append("CP-002")
        divergence_details["CP-002"] = [pi.path_id for pi in path_infos]
        cp_warnings.append(
            f"CP-002: {len(path_infos)} tied controlling paths detected "
            f"(each {project_duration} workdays). All paths are reported. "
            "Analyst must identify which path(s) are relevant for the forensic "
            "analysis and whether concurrent delay conditions exist."
        )

    # CP-003: Multiple finish nodes controlling the project duration
    if len(controlling_finish_nodes) > 1:
        divergence_flags.append("CP-003")
        divergence_details["CP-003"] = list(controlling_finish_nodes)
        cp_warnings.append(
            f"CP-003: {len(controlling_finish_nodes)} finish nodes share the "
            f"controlling project finish date: {controlling_finish_nodes}. "
            "Open-end network detected. Analyst must confirm which activity "
            "represents the intended project completion milestone."
        )

    # CP-004: Longest-path activities with positive total float
    lp_positive_tf = sorted(a for a in lp_set if total_float.get(a, 0) > 0)
    if lp_positive_tf:
        divergence_flags.append("CP-004")
        divergence_details["CP-004"] = lp_positive_tf
        cp_warnings.append(
            f"CP-004: {len(lp_positive_tf)} activity(ies) on the longest path "
            f"have positive total float: {lp_positive_tf}. This arises in networks "
            "with multiple finish nodes where the backward-pass LF anchor for some "
            "activities differs from the overall project finish. Analyst review "
            "required — reported TF values may understate schedule risk."
        )

    cp_assumptions: list[str] = [
        "Longest-path tracing uses forward-pass ES/EF results under Retained Logic "
        "(ADR-002). No date constraints applied (LIM-028).",
        "Controlling predecessor: the predecessor whose forward-pass constraint "
        "exactly equals the activity's scheduled ES (FS/SS) or EF (FF/SF).",
        "Ties — multiple simultaneously tight constraints — produce multiple "
        "paths; all are reported (AACE 49R-06 §4.2).",
        "Project finish is defined as the maximum EF across all activities.",
        "All activities with EF == project_finish are controlling finish nodes.",
        "Integer workday arithmetic throughout; no fractional lags (ADR-002).",
    ]

    return LongestPathResult(
        controlling_paths=path_infos,
        project_duration=project_duration,
        tied_paths=len(path_infos) > 1,
        controlling_finish_nodes=controlling_finish_nodes,
        tf_zero_activities=tf_zero_activities,
        longest_path_activities=longest_path_activities,
        divergence_flags=sorted(divergence_flags),
        divergence_details=divergence_details,
        cp_warnings=cp_warnings,
        cp_assumptions=cp_assumptions,
    )
