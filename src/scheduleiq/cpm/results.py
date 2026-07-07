"""
Ported from the LI MIP 3.9 tool (mip39.results) per ADR-0007 — port-and-validate.
INFRA-006: Phase 3/4 Analysis Result Structures.

Defines the structured output types for the CPM analytical engine (INFRA-007)
and the longest-path tracer (INFRA-008):
  ScheduledActivity  — per-activity CPM result (ES, EF, LS, LF, TF, FF, criticality)
  CriticalPathInfo   — critical path summary; Phase 4 expanded with longest-path
                       tracing fields, divergence diagnostics, and path metadata.
  AnalysisResult     — top-level result envelope tying together all outputs

All structures are serializable via to_dict() for audit logging and reporting.
Deterministic: given the same inputs, to_dict() produces the same output.

Source: ADR-005 §7 (determinism, reproducibility, auditability requirements).
        AACE 49R-06 (critical path identification methodology).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from .context import AnalysisContext
from .validation import ValidationResult
from .warnings import WarningLog

# NormalizationResult imported lazily to avoid circular imports.
# Type annotation uses string forward reference.



# ---------------------------------------------------------------------------
# INFRA-006: Per-activity CPM result
# ---------------------------------------------------------------------------

@dataclass
class ScheduledActivity:
    """
    CPM result for a single activity after a full forward/backward pass.

    Fields:
        activity_id:       Activity identifier.
        original_duration: Original duration in integer workdays.
        early_start:       Early Start (ES) — earliest possible start date.
        early_finish:      Early Finish (EF) — earliest possible finish date.
        late_start:        Late Start (LS) — latest allowable start without
                           delaying the project finish.
        late_finish:       Late Finish (LF) — latest allowable finish without
                           delaying the project finish.
        total_float:       Total Float (TF) in workdays:
                           workday_table[LF] − workday_table[EF].
                           Equivalent to workday_table[LS] − workday_table[ES]
                           under Retained Logic.
        free_float:        Free Float (FF) in workdays: how much this activity's
                           EF (or ES, for SS/SF predecessors) can slip before
                           delaying any immediate successor.
        is_critical:       True when this activity is on at least one INFRA-008
                           longest/controlling path (Phase 4). This field no
                           longer represents TF=0 criticality. TF=0 status is
                           available separately in
                           CriticalPathInfo.tf_zero_activities.
    """

    activity_id: str
    original_duration: int
    early_start: date
    early_finish: date
    late_start: date
    late_finish: date
    total_float: int
    free_float: int
    is_critical: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for audit logging and reporting."""
        return {
            "activity_id": self.activity_id,
            "original_duration": self.original_duration,
            "early_start": self.early_start.isoformat(),
            "early_finish": self.early_finish.isoformat(),
            "late_start": self.late_start.isoformat(),
            "late_finish": self.late_finish.isoformat(),
            "total_float": self.total_float,
            "free_float": self.free_float,
            "is_critical": self.is_critical,
        }


# ---------------------------------------------------------------------------
# INFRA-006/008: Critical path summary (expanded in Phase 4)
# ---------------------------------------------------------------------------

@dataclass
class CriticalPathInfo:
    """
    Critical path summary produced by the CPM engine (Phase 4 expanded).

    Phase 4 adds actual longest-path tracing (INFRA-008, resolving LIM-029).
    activity_ids now contains the union of all longest-path activities in
    topological order. tf_zero_activities retains the TF=0 diagnostic list.

    Fields (Phase 3 — unchanged):
        activity_ids:      Union of all longest-path activity IDs, in topological
                           order. When multiple tied paths exist, this is the union
                           across all controlling paths.
                           (Phase 3 meaning: TF=0 activities — superseded by Phase 4.)
        project_duration:  Total workday span of the project, inclusive:
                           workday_table[project_finish] − workday_table[project_start] + 1.

    Fields (Phase 4 additions — all have defaults for backward compatibility):
        method_used:             "longest_path" (Phase 4) or "tf_zero_diagnostic" (Phase 3).
        controlling_paths:       All equal-duration controlling paths as dicts
                                 (serialized PathInfo — see longest_path.py).
        path_duration:           Workday duration of the controlling path(s).
        tied_paths:              True when multiple equal-duration controlling paths exist.
        controlling_finish_nodes: Finish-node activity IDs with EF == project_finish.
        tf_zero_activities:      TF=0 activity IDs in topological order (secondary diagnostic).
        divergence_flags:        Detected divergence conditions: CP-001, CP-002, CP-003, CP-004.
        divergence_details:      Per-flag detail — flag_code → list of affected activity IDs.
        cp_warnings:             Advisory messages describing each divergence condition.
        cp_assumptions:          Methodology assumptions applied during longest-path tracing.

    Divergence flag meanings:
        CP-001  TF=0 activities NOT on any longest path.
        CP-002  Multiple tied controlling paths (equal duration).
        CP-003  Multiple finish nodes controlling the project duration.
        CP-004  Longest-path activity with positive total float.

    Source: AACE 49R-06 §4.2; ADR-005 §7.
    """

    # Phase 3 fields (required, no defaults)
    activity_ids: list[str]
    project_duration: int

    # Phase 4 fields (all with defaults for backward compatibility)
    method_used: str = "longest_path"
    controlling_paths: list[dict[str, Any]] = field(default_factory=list)
    path_duration: int = 0
    tied_paths: bool = False
    controlling_finish_nodes: list[str] = field(default_factory=list)
    tf_zero_activities: list[str] = field(default_factory=list)
    divergence_flags: list[str] = field(default_factory=list)
    divergence_details: dict[str, list[str]] = field(default_factory=dict)
    cp_warnings: list[str] = field(default_factory=list)
    cp_assumptions: list[str] = field(default_factory=list)

    # Phase 5 field (default for backward compatibility)
    ef_convention: str = "inclusive_day"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for audit logging and reporting."""
        return {
            "activity_ids": list(self.activity_ids),
            "project_duration": self.project_duration,
            "method_used": self.method_used,
            "controlling_paths": list(self.controlling_paths),
            "path_duration": self.path_duration,
            "tied_paths": self.tied_paths,
            "controlling_finish_nodes": list(self.controlling_finish_nodes),
            "tf_zero_activities": list(self.tf_zero_activities),
            "divergence_flags": list(self.divergence_flags),
            "divergence_details": {k: list(v) for k, v in self.divergence_details.items()},
            "cp_warnings": list(self.cp_warnings),
            "cp_assumptions": list(self.cp_assumptions),
            "ef_convention": self.ef_convention,
        }


# ---------------------------------------------------------------------------
# INFRA-006: Top-level result envelope
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """
    Top-level result envelope from run_analysis() (INFRA-007).

    When is_valid=False (blocking validation failures prevented scheduling),
    scheduled is empty, critical_path is None, and project_finish is None.
    context and validation are always populated.

    Fields:
        context:         Per-run metadata and traceability container (INFRA-005).
        validation:      Network validation findings (INFRA-002).
        warnings:        Runtime warning log (INFRA-003).
        scheduled:       Activity ID → ScheduledActivity for all activities.
                         Empty dict when is_valid=False.
        critical_path:   Critical path summary. None when is_valid=False.
        project_start:   Project start date (workday-adjusted from input if needed).
        project_finish:  Latest EF across all activities. None when is_valid=False.
        is_valid:        False when blocking validation issues prevented scheduling.
    """

    context: AnalysisContext
    validation: ValidationResult
    warnings: WarningLog
    scheduled: dict[str, ScheduledActivity]
    critical_path: Optional[CriticalPathInfo]
    project_start: date
    project_finish: Optional[date]
    is_valid: bool
    normalization_result: "Optional[Any]" = field(default=None)
    destatusing_result: "Optional[Any]" = field(default=None)
    simulation_result: "Optional[Any]" = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for audit logging and reporting."""
        norm = None
        if self.normalization_result is not None:
            norm = self.normalization_result.to_dict()
        dst = None
        if self.destatusing_result is not None:
            dst = self.destatusing_result.to_dict()
        sim = None
        if self.simulation_result is not None:
            sim = self.simulation_result.to_dict()
        return {
            "is_valid": self.is_valid,
            "project_start": self.project_start.isoformat(),
            "project_finish": (
                self.project_finish.isoformat() if self.project_finish else None
            ),
            "context": self.context.to_dict(),
            "validation": self.validation.to_list(),
            "warnings": self.warnings.to_list(),
            "scheduled": {k: v.to_dict() for k, v in self.scheduled.items()},
            "critical_path": (
                self.critical_path.to_dict() if self.critical_path else None
            ),
            "normalization_result": norm,
            "destatusing_result": dst,
            "simulation_result": sim,
        }
