"""
V1-D: Destatusing, lag analysis, and auto-drive diagnostic codes.

Three code namespaces:
  DST-XXX — Destatusing anomalies and rule-application findings.
  LAG-XXX — Lag analysis findings (actual lag vs. planned, lag chains, etc.).
  DRV-XXX — Auto-drive decisions (driving predecessor selection).

Severity levels reuse DiagnosticSeverity from the normalization package.
All diagnostics are deterministic: given the same inputs and rule order,
the same diagnostic list is produced.

Source: ADR-014; CPW-P6 Manual pp. 40-44 (destatusing, lag, auto-drive).

Ported from the LI MIP 3.9 tool (mip39.destatusing.diagnostics) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..severity import DiagnosticSeverity


# ---------------------------------------------------------------------------
# Diagnostic code definitions
# ---------------------------------------------------------------------------

class DSTCode(str, Enum):
    """
    DST diagnostic codes — destatusing anomalies and findings.

    DST-001 through DST-015.
    """
    DST_001 = "DST-001"  # Rule A assigned — complete before window (informational)
    DST_002 = "DST-002"  # Rule B assigned — actuals removed in window
    DST_003 = "DST-003"  # Rule C assigned — future activity (informational)
    DST_004 = "DST-004"  # Rule D assigned — AF removed, RD/PC computed
    DST_005 = "DST-005"  # Rule E assigned — AS removed, OD reset
    DST_006 = "DST-006"  # Rule F assigned — RD/PC computed from new_dd
    DST_007 = "DST-007"  # NO_MATCH — anomalous state, analyst review required
    DST_008 = "DST-008"  # Future actual — actual date after new_dd unexpectedly
    DST_009 = "DST-009"  # Negative remaining duration computed
    DST_010 = "DST-010"  # Inconsistent progress — AF before AS
    DST_011 = "DST-011"  # Missing required field for rule application
    DST_012 = "DST-012"  # Percent complete out of valid range [0.0, 1.0]
    DST_013 = "DST-013"  # Destatusing would produce zero or negative original duration
    DST_014 = "DST-014"  # Actual duration inconsistent with OD (AD > OD)
    DST_015 = "DST-015"  # NOT_IN_SCOPE — no actuals, dates ambiguous


class LAGCode(str, Enum):
    """
    LAG diagnostic codes — lag analysis findings.
    """
    LAG_001 = "LAG-001"  # Actual lag computed for relationship (informational)
    LAG_002 = "LAG-002"  # Actual lag is negative — retained per auto-drive spec
    LAG_003 = "LAG-003"  # Large positive lag variance (actual >> planned)
    LAG_004 = "LAG-004"  # Large negative lag variance (actual << planned)
    LAG_005 = "LAG-005"  # Cross-calendar lag — predecessor and successor on different calendars
    LAG_006 = "LAG-006"  # Lag chain detected — transitive lag affecting critical path
    LAG_007 = "LAG-007"  # Missing actual dates for lag computation (cannot compute)
    LAG_008 = "LAG-008"  # Lag contributes to driving criticality


class DRVCode(str, Enum):
    """
    DRV diagnostic codes — auto-drive decisions.
    """
    DRV_001 = "DRV-001"  # Driving predecessor identified
    DRV_002 = "DRV-002"  # Non-driving predecessor lag reset to planned value
    DRV_003 = "DRV-003"  # Equal variance tie — lags distributed equally
    DRV_004 = "DRV-004"  # Single predecessor — always driving, actual lag used
    DRV_005 = "DRV-005"  # All lags negative — all retained (CPW spec)
    DRV_006 = "DRV-006"  # Multiple equally-driving paths detected
    DRV_007 = "DRV-007"  # Non-driving predecessor — negative actual lag retained (not reset)


# ---------------------------------------------------------------------------
# Default severities
# ---------------------------------------------------------------------------

_DST_SEVERITY: dict[DSTCode, DiagnosticSeverity] = {
    DSTCode.DST_001: DiagnosticSeverity.INFORMATIONAL,
    DSTCode.DST_002: DiagnosticSeverity.INFORMATIONAL,
    DSTCode.DST_003: DiagnosticSeverity.INFORMATIONAL,
    DSTCode.DST_004: DiagnosticSeverity.INFORMATIONAL,
    DSTCode.DST_005: DiagnosticSeverity.INFORMATIONAL,
    DSTCode.DST_006: DiagnosticSeverity.INFORMATIONAL,
    DSTCode.DST_007: DiagnosticSeverity.ANALYTICAL_RISK,
    DSTCode.DST_008: DiagnosticSeverity.WARNING,
    DSTCode.DST_009: DiagnosticSeverity.ANALYTICAL_RISK,
    DSTCode.DST_010: DiagnosticSeverity.ANALYTICAL_RISK,
    DSTCode.DST_011: DiagnosticSeverity.WARNING,
    DSTCode.DST_012: DiagnosticSeverity.WARNING,
    DSTCode.DST_013: DiagnosticSeverity.ANALYTICAL_RISK,
    DSTCode.DST_014: DiagnosticSeverity.WARNING,
    DSTCode.DST_015: DiagnosticSeverity.ADVISORY,
}

_LAG_SEVERITY: dict[LAGCode, DiagnosticSeverity] = {
    LAGCode.LAG_001: DiagnosticSeverity.INFORMATIONAL,
    LAGCode.LAG_002: DiagnosticSeverity.ADVISORY,
    LAGCode.LAG_003: DiagnosticSeverity.WARNING,
    LAGCode.LAG_004: DiagnosticSeverity.WARNING,
    LAGCode.LAG_005: DiagnosticSeverity.ADVISORY,
    LAGCode.LAG_006: DiagnosticSeverity.WARNING,
    LAGCode.LAG_007: DiagnosticSeverity.WARNING,
    LAGCode.LAG_008: DiagnosticSeverity.ADVISORY,
}

_DRV_SEVERITY: dict[DRVCode, DiagnosticSeverity] = {
    DRVCode.DRV_001: DiagnosticSeverity.INFORMATIONAL,
    DRVCode.DRV_002: DiagnosticSeverity.INFORMATIONAL,
    DRVCode.DRV_003: DiagnosticSeverity.ADVISORY,
    DRVCode.DRV_004: DiagnosticSeverity.INFORMATIONAL,
    DRVCode.DRV_005: DiagnosticSeverity.ADVISORY,
    DRVCode.DRV_006: DiagnosticSeverity.ADVISORY,
    DRVCode.DRV_007: DiagnosticSeverity.ADVISORY,
}


# ---------------------------------------------------------------------------
# Diagnostic dataclass
# ---------------------------------------------------------------------------

@dataclass
class V1dDiagnostic:
    """
    A single diagnostic finding from destatusing, lag analysis, or auto-drive.

    Fields:
        code        — DST/LAG/DRV code string (e.g., "DST-007").
        severity    — DiagnosticSeverity level.
        act_id      — Activity ID (None for relationship-level diagnostics).
        rel_key     — Relationship key "(pred_id,succ_id,type)" for LAG/DRV codes.
        message     — Human-readable description.
        details     — Supplementary key-value data for analyst review.
    """
    code: str
    severity: DiagnosticSeverity
    message: str
    act_id: str | None = None
    rel_key: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "act_id": self.act_id,
            "rel_key": self.rel_key,
            "message": self.message,
            "details": dict(self.details),
        }


# ---------------------------------------------------------------------------
# Diagnostic accumulator
# ---------------------------------------------------------------------------

class V1dDiagnosticAccumulator:
    """
    Accumulates V1dDiagnostic objects from a destatusing run.

    Sorting: activity diagnostics are sorted by (act_id, code);
    relationship diagnostics are sorted by (rel_key, code).
    """

    def __init__(self) -> None:
        self._items: list[V1dDiagnostic] = []

    def add(self, diag: V1dDiagnostic) -> None:
        self._items.append(diag)

    def add_dst(
        self,
        code: DSTCode,
        message: str,
        act_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.add(V1dDiagnostic(
            code=code.value,
            severity=_DST_SEVERITY[code],
            message=message,
            act_id=act_id,
            details=details or {},
        ))

    def add_lag(
        self,
        code: LAGCode,
        message: str,
        act_id: str | None = None,
        rel_key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.add(V1dDiagnostic(
            code=code.value,
            severity=_LAG_SEVERITY[code],
            message=message,
            act_id=act_id,
            rel_key=rel_key,
            details=details or {},
        ))

    def add_drv(
        self,
        code: DRVCode,
        message: str,
        act_id: str | None = None,
        rel_key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.add(V1dDiagnostic(
            code=code.value,
            severity=_DRV_SEVERITY[code],
            message=message,
            act_id=act_id,
            rel_key=rel_key,
            details=details or {},
        ))

    @property
    def all(self) -> list[V1dDiagnostic]:
        """All diagnostics, sorted deterministically."""
        return sorted(
            self._items,
            key=lambda d: (d.act_id or "", d.rel_key or "", d.code),
        )

    def by_severity(self, severity: DiagnosticSeverity) -> list[V1dDiagnostic]:
        return [d for d in self.all if d.severity == severity]

    def at_least(self, severity: DiagnosticSeverity) -> list[V1dDiagnostic]:
        return [d for d in self.all if d.severity.is_at_least(severity)]

    def by_code_prefix(self, prefix: str) -> list[V1dDiagnostic]:
        """Return diagnostics whose code starts with prefix (e.g., 'DST', 'LAG')."""
        return [d for d in self.all if d.code.startswith(prefix)]

    def codes(self) -> list[str]:
        return sorted({d.code for d in self._items})

    def __len__(self) -> int:
        return len(self._items)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self.all]
