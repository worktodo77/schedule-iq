"""
V1-G: CPW comparison divergence classification framework.

Divergences represent differences between mip39 analytical outputs and
historical CPW reference outputs. Every divergence is:
  - explicitly categorized (no silent suppression);
  - analyst-visible (to_dict() output for audit trail);
  - resolvable (analysts can acknowledge and waive with notes).

Eight divergence categories cover all expected difference types. Auto-
classification provides a best-effort category based on the field and
context; analysts can override via resolve().

Source: ADR-016; ADR-005 (no silent modification); ADR-009 (governance).

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.divergences) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Divergence category enumeration
# ---------------------------------------------------------------------------

class DivergenceCategory(str, Enum):
    """
    Controlled classification of comparison divergences.

    Members:
        EXPECTED_DIFFERENCE:           Known, pre-approved difference with documented
                                       analytical justification (e.g., integer workday
                                       granularity vs P6 minute-level precision).
        GOVERNED_DIFFERENCE:           Difference reviewed and explicitly waived by an
                                       analyst with a written rationale. Requires a
                                       non-empty resolution note.
        MATERIAL_ANALYTICAL_DIFFERENCE: Difference that affects primary analytical
                                       outputs (critical path, total float, project
                                       finish). Requires analyst investigation. Blocking
                                       under STRICT and GOVERNED policies.
        P6_EMULATION_DIFFERENCE:       Difference arising from a P6-specific behavior
                                       that this tool does not emulate by design
                                       (e.g., Progress Override, resource leveling).
                                       Documented in ADR-005.
        CALENDAR_BEHAVIOR_DIFFERENCE:  Difference attributable to calendar arithmetic
                                       (calendar assignment, exception dates, hours/day).
                                       Often a 1-workday shift at week boundaries.
        LAG_BEHAVIOR_DIFFERENCE:       Difference attributable to lag calendar strategy
                                       (predecessor vs successor vs project-default
                                       calendar for lag workday arithmetic).
        FLOAT_METHOD_DIFFERENCE:       Difference in float calculation method (TF=0
                                       vs longest-path criticality; retained logic vs
                                       progress override float impact).
        UNKNOWN_DIFFERENCE:            Unexplained difference. Requires analyst
                                       investigation before reliance. Blocking under
                                       STRICT policy.
    """
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    GOVERNED_DIFFERENCE = "GOVERNED_DIFFERENCE"
    MATERIAL_ANALYTICAL_DIFFERENCE = "MATERIAL_ANALYTICAL_DIFFERENCE"
    P6_EMULATION_DIFFERENCE = "P6_EMULATION_DIFFERENCE"
    CALENDAR_BEHAVIOR_DIFFERENCE = "CALENDAR_BEHAVIOR_DIFFERENCE"
    LAG_BEHAVIOR_DIFFERENCE = "LAG_BEHAVIOR_DIFFERENCE"
    FLOAT_METHOD_DIFFERENCE = "FLOAT_METHOD_DIFFERENCE"
    UNKNOWN_DIFFERENCE = "UNKNOWN_DIFFERENCE"

    def is_blocking(self) -> bool:
        """True when this category is blocking by default (before policy override)."""
        return self in (
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
        )

    def requires_analyst_note(self) -> bool:
        """True when a resolution note is mandatory before the divergence can be waived."""
        return self in (
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
            DivergenceCategory.GOVERNED_DIFFERENCE,
        )


# ---------------------------------------------------------------------------
# Divergence record
# ---------------------------------------------------------------------------

@dataclass
class DivergenceRecord:
    """
    A single field-level divergence between mip39 and a reference schedule.

    Fields:
        div_id:         Sequential identifier (e.g. "DIV-001").
        act_id:         Activity ID, or None for project-level divergences.
        field:          Field name where the divergence was detected.
        mip39_value:    Value produced by the mip39 engine.
        reference_value: Value from the CPW/reference schedule.
        delta:          Numeric difference (mip39 - reference), or None for
                        non-numeric fields.
        category:       DivergenceCategory classification.
        explanation:    Auto-generated explanation string.
        analyst_note:   Analyst-supplied resolution note (required for GOVERNED).
        is_resolved:    True once the analyst has acknowledged or waived.
        resolution:     "acknowledged", "waived", or "" (pending).
    """

    div_id: str
    act_id: Optional[str]
    field: str
    mip39_value: Any
    reference_value: Any
    delta: Optional[float]
    category: DivergenceCategory
    explanation: str
    analyst_note: str = ""
    is_resolved: bool = False
    resolution: str = ""

    def acknowledge(self, note: str = "") -> None:
        """Mark as acknowledged — analyst has reviewed and agrees with category."""
        self.is_resolved = True
        self.resolution = "acknowledged"
        self.analyst_note = note

    def waive(self, note: str) -> None:
        """
        Waive the divergence — analyst accepts it with a written rationale.

        A non-empty note is required for categories that require_analyst_note().
        This method does not enforce the note requirement; the caller or the
        policy layer is responsible for enforcement.
        """
        self.is_resolved = True
        self.resolution = "waived"
        self.analyst_note = note

    def reclassify(self, new_category: DivergenceCategory, note: str = "") -> None:
        """Reclassify the divergence to a different category with an optional note."""
        self.category = new_category
        if note:
            self.analyst_note = note

    def to_dict(self) -> dict[str, Any]:
        return {
            "div_id": self.div_id,
            "act_id": self.act_id,
            "field": self.field,
            "mip39_value": (
                self.mip39_value.isoformat()
                if hasattr(self.mip39_value, "isoformat")
                else self.mip39_value
            ),
            "reference_value": (
                self.reference_value.isoformat()
                if hasattr(self.reference_value, "isoformat")
                else self.reference_value
            ),
            "delta": self.delta,
            "category": self.category.value,
            "explanation": self.explanation,
            "analyst_note": self.analyst_note,
            "is_resolved": self.is_resolved,
            "resolution": self.resolution,
        }


# ---------------------------------------------------------------------------
# Divergence accumulator
# ---------------------------------------------------------------------------

@dataclass
class DivergenceAccumulator:
    """
    Ordered collection of DivergenceRecords with category-bucketed sublists.

    Insertion order is preserved for deterministic output. Category buckets
    provide O(1) access to subsets without refiltering the full list.
    """

    _all: list[DivergenceRecord] = field(default_factory=list)
    _by_category: dict[DivergenceCategory, list[DivergenceRecord]] = field(
        default_factory=dict
    )
    _counter: int = field(default=0)

    def __post_init__(self) -> None:
        for cat in DivergenceCategory:
            self._by_category[cat] = []

    def _next_id(self) -> str:
        self._counter += 1
        return f"DIV-{self._counter:03d}"

    def add(
        self,
        act_id: Optional[str],
        field: str,
        mip39_value: Any,
        reference_value: Any,
        category: DivergenceCategory,
        explanation: str,
        delta: Optional[float] = None,
    ) -> DivergenceRecord:
        """Create and register a DivergenceRecord. Returns the created record."""
        record = DivergenceRecord(
            div_id=self._next_id(),
            act_id=act_id,
            field=field,
            mip39_value=mip39_value,
            reference_value=reference_value,
            delta=delta,
            category=category,
            explanation=explanation,
        )
        self._all.append(record)
        self._by_category[category].append(record)
        return record

    @property
    def all(self) -> list[DivergenceRecord]:
        return list(self._all)

    def by_category(self, category: DivergenceCategory) -> list[DivergenceRecord]:
        return list(self._by_category.get(category, []))

    def unresolved(self) -> list[DivergenceRecord]:
        return [d for d in self._all if not d.is_resolved]

    def material(self) -> list[DivergenceRecord]:
        return list(self._by_category[DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE])

    def unknown(self) -> list[DivergenceRecord]:
        return list(self._by_category[DivergenceCategory.UNKNOWN_DIFFERENCE])

    def unresolved_blocking(self) -> list[DivergenceRecord]:
        """Unresolved divergences whose category is blocking by default."""
        return [d for d in self._all if not d.is_resolved and d.category.is_blocking()]

    def counts_by_category(self) -> dict[str, int]:
        return {cat.value: len(lst) for cat, lst in self._by_category.items()}

    def __len__(self) -> int:
        return len(self._all)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._all]
