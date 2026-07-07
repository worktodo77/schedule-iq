"""
Ported from the LI MIP 3.9 tool (mip39.warnings) per ADR-0007 — port-and-validate.
Warning aggregation framework for the MIP 3.9 Schedule Analysis Tool.

Provides a structured AnalysisWarning dataclass and WarningLog aggregator
for collecting, categorizing, and serializing non-fatal conditions during
analytical CPM calculations.

This module extends the informal list[str] warnings from the forward-pass
module into a structured, serializable, and traceable system.

Design: Warnings preserve insertion order for traceability. They are
serializable (to_dict / to_list) for audit logging. All operations are
deterministic for a given sequence of add() calls.

Source: ADR-005 §7 (determinism and reproducibility requirements)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WarningCategory(Enum):
    """Classification of the analytical condition producing a warning."""
    SCHEDULE_INTEGRITY = "SCHEDULE_INTEGRITY"   # Network structure issues
    CALENDAR = "CALENDAR"                       # Date / non-workday adjustments
    DURATION = "DURATION"                       # Duration anomalies
    LAG = "LAG"                                 # Lag anomalies
    METHODOLOGY = "METHODOLOGY"                 # Interpretation flags
    P6_DIVERGENCE = "P6_DIVERGENCE"             # Known P6 behavioral divergences
    CONSTRAINT = "CONSTRAINT"                   # Constraint-related conditions
    ANALYST_REVIEW = "ANALYST_REVIEW"           # Conditions requiring analyst judgment


@dataclass
class AnalysisWarning:
    """
    A structured, serializable analytical warning.

    Attributes:
        code:             Short identifier (e.g., "CAL-001", "METH-001").
        category:         WarningCategory classification.
        message:          Human-readable description.
        source_reference: Methodology source supporting this warning.
        analyst_action:   Recommended response (may be empty for informational items).
        context:          Optional key-value pairs providing additional context.
    """
    code: str
    category: WarningCategory
    message: str
    source_reference: str = ""
    analyst_action: str = ""
    context: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "category": self.category.value,
            "message": self.message,
            "source_reference": self.source_reference,
            "analyst_action": self.analyst_action,
            "context": dict(self.context),
        }


class WarningLog:
    """
    Ordered, serializable collection of AnalysisWarning objects.

    Warnings are stored in insertion order for traceability. Filtering by
    category is supported. The log can be serialized for audit output.
    """

    def __init__(self) -> None:
        self._warnings: list[AnalysisWarning] = []

    def add(self, warning: AnalysisWarning) -> None:
        """Append a warning."""
        self._warnings.append(warning)

    def add_plain(
        self,
        code: str,
        category: WarningCategory,
        message: str,
        source_reference: str = "",
        analyst_action: str = "",
        context: dict[str, str] | None = None,
    ) -> None:
        """Convenience method — construct and append a warning."""
        self.add(AnalysisWarning(
            code=code,
            category=category,
            message=message,
            source_reference=source_reference,
            analyst_action=analyst_action,
            context=context or {},
        ))

    @property
    def warnings(self) -> list[AnalysisWarning]:
        """All warnings in insertion order (read-only copy)."""
        return list(self._warnings)

    def by_category(self, category: WarningCategory) -> list[AnalysisWarning]:
        """Return warnings of the specified category, in insertion order."""
        return [w for w in self._warnings if w.category == category]

    def codes(self) -> list[str]:
        """Return all warning codes in insertion order."""
        return [w.code for w in self._warnings]

    def to_list(self) -> list[dict]:
        """Serialize all warnings to a list of dicts for audit output."""
        return [w.to_dict() for w in self._warnings]

    def __len__(self) -> int:
        return len(self._warnings)

    def __bool__(self) -> bool:
        return bool(self._warnings)

    def __repr__(self) -> str:
        return f"WarningLog({len(self._warnings)} warnings)"
