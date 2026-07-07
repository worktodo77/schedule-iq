"""
Ported from the LI MIP 3.9 tool (mip39.context) per ADR-0007 — port-and-validate.
Analysis context and traceability metadata for the MIP 3.9 Schedule Analysis Tool.

Provides a centralized AnalysisContext object that records all parameters,
assumptions, interpretation flags, and traceability information for a single
analytical run.

The context object is the root metadata container for future reporting, audit
logging, and reproducibility verification. It is designed to be serializable
(to_dict) and deterministically reproducible given the same inputs.

Source: ADR-005 §7 (determinism, reproducibility, auditability requirements)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# Replaces the original `from .version import __version__` (mip39.version is not
# ported in this wave). ScheduleIQ carries its own engine version marker here.
ENGINE_VERSION = "scheduleiq-cpm 0.3.0 (port of mip39 1.x)"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION: str = "1.0-phase2"
HIERARCHY_VERSION: str = "2026-05-14-canonical"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CalculationMode(Enum):
    """
    CPM calculation mode for an analysis run.

    Only RETAINED_LOGIC is supported in Phase 2 (ADR-002, D-005).
    Other modes are documented for future implementation.
    """
    RETAINED_LOGIC = "retained_logic"
    # PROGRESS_OVERRIDE = "progress_override"   # Future — not yet implemented
    # ACTUAL_DATES = "actual_dates"             # Future — not yet implemented


# ---------------------------------------------------------------------------
# Schedule metadata
# ---------------------------------------------------------------------------

@dataclass
class ScheduleMetadata:
    """
    Metadata describing the source schedule for an analysis run.

    All fields default to empty/zero for Phase 2 synthetic fixtures.
    Populated from schedule headers when XER import is implemented (Phase 3+).
    """
    schedule_name: str = ""
    data_date: str = ""           # ISO 8601 date string
    project_start: str = ""       # ISO 8601 date string
    activity_count: int = 0
    relationship_count: int = 0
    calendar_count: int = 1
    source_format: str = "synthetic"   # "synthetic" | "xer" | "csv"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_name": self.schedule_name,
            "data_date": self.data_date,
            "project_start": self.project_start,
            "activity_count": self.activity_count,
            "relationship_count": self.relationship_count,
            "calendar_count": self.calendar_count,
            "source_format": self.source_format,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Analysis context
# ---------------------------------------------------------------------------

@dataclass
class AnalysisContext:
    """
    Centralized analysis metadata and traceability container.

    One AnalysisContext is created per analytical run. It records all
    parameters required to reproduce the analysis: engine version,
    methodology version, calendar assumptions, calculation mode,
    interpretation flags, and a summary of validation and warning results.

    All fields are serializable via to_dict(). The context is the root
    metadata object for future report generation and audit output.

    Source: ADR-005 §7
    """

    # --- Identity ---
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    analysis_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # --- Versioning ---
    engine_version: str = field(default_factory=lambda: ENGINE_VERSION)
    methodology_version: str = field(default_factory=lambda: METHODOLOGY_VERSION)
    hierarchy_version: str = field(default_factory=lambda: HIERARCHY_VERSION)

    # --- Schedule source ---
    schedule_metadata: ScheduleMetadata = field(default_factory=ScheduleMetadata)

    # --- Calculation parameters ---
    calculation_mode: CalculationMode = CalculationMode.RETAINED_LOGIC
    calendar_name: str = "default"
    hours_per_day: float = 8.0

    # --- Traceability ---
    interpretation_flags: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    excluded_capabilities: list[str] = field(default_factory=list)

    # --- EF Convention (Phase 5) ---
    ef_convention: str = "inclusive_day"
    convention_assumptions: list[str] = field(default_factory=list)
    convention_warnings: list[str] = field(default_factory=list)

    # --- Import provenance (Phase 6) ---
    # Populated when the input was produced by import_xer(). None for synthetic inputs.
    import_provenance: Optional[dict[str, Any]] = None
    import_warnings: list[str] = field(default_factory=list)
    normalization_summary: dict[str, int] = field(default_factory=dict)

    # --- Benchmark / validation metadata (Phase 7) ---
    # Populated when the run was initiated by the ValidationHarness.
    benchmark_id: Optional[str] = None
    benchmark_version: Optional[str] = None
    validation_provenance: Optional[dict[str, Any]] = None

    # --- Results summary (populated after analysis) ---
    validation_summary: dict[str, int] = field(default_factory=dict)
    warning_count: int = 0

    # --- Methods ---

    def add_interpretation_flag(self, flag: str) -> None:
        """Record an interpretation flag requiring analyst review. De-duplicated."""
        if flag not in self.interpretation_flags:
            self.interpretation_flags.append(flag)

    def add_assumption(self, assumption: str) -> None:
        """Record a documented assumption. De-duplicated."""
        if assumption not in self.assumptions:
            self.assumptions.append(assumption)

    def add_excluded_capability(self, capability: str) -> None:
        """Record an explicitly excluded capability. De-duplicated."""
        if capability not in self.excluded_capabilities:
            self.excluded_capabilities.append(capability)

    def record_validation_summary(self, summary: dict[str, int]) -> None:
        """Record the validation result counts by severity."""
        self.validation_summary = dict(summary)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for audit logging and reporting."""
        return {
            "analysis_id": self.analysis_id,
            "analysis_timestamp": self.analysis_timestamp,
            "engine_version": self.engine_version,
            "methodology_version": self.methodology_version,
            "hierarchy_version": self.hierarchy_version,
            "schedule_metadata": self.schedule_metadata.to_dict(),
            "calculation_mode": self.calculation_mode.value,
            "calendar_name": self.calendar_name,
            "hours_per_day": self.hours_per_day,
            "interpretation_flags": list(self.interpretation_flags),
            "assumptions": list(self.assumptions),
            "excluded_capabilities": list(self.excluded_capabilities),
            "ef_convention": self.ef_convention,
            "convention_assumptions": list(self.convention_assumptions),
            "convention_warnings": list(self.convention_warnings),
            "import_provenance": self.import_provenance,
            "import_warnings": list(self.import_warnings),
            "normalization_summary": dict(self.normalization_summary),
            "benchmark_id": self.benchmark_id,
            "benchmark_version": self.benchmark_version,
            "validation_provenance": self.validation_provenance,
            "validation_summary": dict(self.validation_summary),
            "warning_count": self.warning_count,
        }
