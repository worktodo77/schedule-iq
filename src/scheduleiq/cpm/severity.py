"""
V1-C: Normalization diagnostic severity levels.

Severity governs whether a diagnostic blocks analysis, requires analyst
acknowledgment, or is purely informational. Severity is deterministic:
the same condition always produces the same severity level for a given
NormalizationPolicy.

Levels (ascending risk):
    INFORMATIONAL   — No analytical impact. Awareness only.
    ADVISORY        — Minor concern. Results likely still reliable.
    WARNING         — May distort results. Analyst review recommended.
    ANALYTICAL_RISK — Will likely distort results. Resolution required before
                      analysis can be considered reliable.
    CRITICAL        — Blocks analysis. Must be resolved or explicitly
                      acknowledged before any results are trusted.

Sources:
    ADR-005 — Forensic defensibility requirements
    ADR-013 — Normalization workflow governance

Ported from the LI MIP 3.9 tool (mip39.normalization.severity) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from enum import Enum


class DiagnosticSeverity(Enum):
    """
    Severity level for a normalization diagnostic finding.

    Values are ordered from lowest (INFORMATIONAL) to highest (CRITICAL).
    Use is_at_least() for policy threshold comparisons.
    """

    INFORMATIONAL = "INFORMATIONAL"
    ADVISORY = "ADVISORY"
    WARNING = "WARNING"
    ANALYTICAL_RISK = "ANALYTICAL_RISK"
    CRITICAL = "CRITICAL"

    _LEVELS: dict  # type annotation placeholder; overridden below

    @staticmethod
    def _level_order() -> dict[str, int]:
        return {
            "INFORMATIONAL": 0,
            "ADVISORY": 1,
            "WARNING": 2,
            "ANALYTICAL_RISK": 3,
            "CRITICAL": 4,
        }

    def _order(self) -> int:
        return self._level_order()[self.value]

    def is_at_least(self, threshold: "DiagnosticSeverity") -> bool:
        """True if this severity is at or above threshold (inclusive)."""
        return self._order() >= threshold._order()

    def __lt__(self, other: "DiagnosticSeverity") -> bool:
        return self._order() < other._order()

    def __le__(self, other: "DiagnosticSeverity") -> bool:
        return self._order() <= other._order()

    def __gt__(self, other: "DiagnosticSeverity") -> bool:
        return self._order() > other._order()

    def __ge__(self, other: "DiagnosticSeverity") -> bool:
        return self._order() >= other._order()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DiagnosticSeverity):
            return self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)
