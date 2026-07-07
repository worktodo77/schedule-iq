"""
V1-D: Destatusing, Lag Analysis, and Auto-Drive package.

Public API — import any of these symbols directly from `mip39.destatusing`.

Backward-compatible re-exports: destatus_rule_a through destatus_rule_f are
preserved here so that existing code (tests/test_destatusing.py) continues to
work without modification after the V1-D package conversion.

New V1-D symbols:
  Rules & classification: DestatusingRule, RuleAssignment, determine_rule
  Transformation rules:   destatus_rule_a … destatus_rule_f
  Provenance:             TransformationRecord, TransformationLog,
                          make_removal_record, make_set_record, make_compute_record
  Diagnostics:            DSTCode, LAGCode, DRVCode, V1dDiagnostic,
                          V1dDiagnosticAccumulator
  Policies:               DestatusingPolicy, DSTpolicyConfig, POLICY_CONFIGS,
                          get_policy_config
  Checkpoints:            DSTCheckpointStatus, DSTCheckpoint,
                          DSTCheckpointRegistry
  Transformations:        apply_rule_with_provenance
  Lag analysis:           ActualLagResult, LagAnalysisResult,
                          compute_actual_fs_lag, compute_actual_ss_lag,
                          compute_actual_ff_lag, compute_actual_sf_lag,
                          compute_actual_lag, run_lag_analysis
  Auto-drive:             AutoDriveDecision, AutoDriveResult, run_autodrive
  Engine:                 DestatusingInput, DestatusingResult,
                          SimulationMetadata, run_destatusing

Source: ADR-014; CPW-P6 Manual pp. 4-6, 40-44.

Ported from the LI MIP 3.9 tool (mip39.destatusing) per ADR-0007 — port-and-validate.
"""

# Rules & classification
from .rules import (
    DestatusingRule,
    RuleAssignment,
    determine_rule,
    destatus_rule_a,
    destatus_rule_b,
    destatus_rule_c,
    destatus_rule_d,
    destatus_rule_e,
    destatus_rule_f,
)

# Transformation provenance
from .provenance import (
    TransformationRecord,
    TransformationLog,
    make_removal_record,
    make_set_record,
    make_compute_record,
)

# Diagnostics
from .diagnostics import (
    DSTCode,
    LAGCode,
    DRVCode,
    V1dDiagnostic,
    V1dDiagnosticAccumulator,
)

# Policies
from .policies import (
    DestatusingPolicy,
    DSTpolicyConfig,
    POLICY_CONFIGS,
    get_policy_config,
)

# Analyst checkpoints
from .checkpoints import (
    DSTCheckpointStatus,
    DSTCheckpoint,
    DSTCheckpointRegistry,
)

# Governed transformation layer
from .transformations import apply_rule_with_provenance

# Lag analysis
from .lag import (
    ActualLagResult,
    LagAnalysisResult,
    compute_actual_fs_lag,
    compute_actual_ss_lag,
    compute_actual_ff_lag,
    compute_actual_sf_lag,
    compute_actual_lag,
    run_lag_analysis,
)

# Auto-drive
from .autodrive import (
    AutoDriveDecision,
    AutoDriveResult,
    run_autodrive,
)

# Engine
from .engine import (
    DestatusingInput,
    DestatusingResult,
    SimulationMetadata,
    run_destatusing,
)

__all__ = [
    # Rules & classification
    "DestatusingRule",
    "RuleAssignment",
    "determine_rule",
    "destatus_rule_a",
    "destatus_rule_b",
    "destatus_rule_c",
    "destatus_rule_d",
    "destatus_rule_e",
    "destatus_rule_f",
    # Provenance
    "TransformationRecord",
    "TransformationLog",
    "make_removal_record",
    "make_set_record",
    "make_compute_record",
    # Diagnostics
    "DSTCode",
    "LAGCode",
    "DRVCode",
    "V1dDiagnostic",
    "V1dDiagnosticAccumulator",
    # Policies
    "DestatusingPolicy",
    "DSTpolicyConfig",
    "POLICY_CONFIGS",
    "get_policy_config",
    # Checkpoints
    "DSTCheckpointStatus",
    "DSTCheckpoint",
    "DSTCheckpointRegistry",
    # Transformations
    "apply_rule_with_provenance",
    # Lag analysis
    "ActualLagResult",
    "LagAnalysisResult",
    "compute_actual_fs_lag",
    "compute_actual_ss_lag",
    "compute_actual_ff_lag",
    "compute_actual_sf_lag",
    "compute_actual_lag",
    "run_lag_analysis",
    # Auto-drive
    "AutoDriveDecision",
    "AutoDriveResult",
    "run_autodrive",
    # Engine
    "DestatusingInput",
    "DestatusingResult",
    "SimulationMetadata",
    "run_destatusing",
]
