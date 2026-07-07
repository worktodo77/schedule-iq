"""
V1-D: Transformation provenance infrastructure.

Every destatusing action generates an explicit TransformationRecord. No silent
transformations are permitted (ADR-014 extends ADR-007's no-silent-normalization
principle to schedule-level destatusing).

TransformationRecord fields capture:
  - What changed (field, source value, target value)
  - Why it changed (governing rule and calculation reference)
  - Whether analyst review is required
  - Whether the transformation is reversible
  - Analytical implications for the expert analyst

Source: ADR-014; CPW-P6 Manual p. 40; ADR-007 (no-silent-normalization precedent).

Ported from the LI MIP 3.9 tool (mip39.destatusing.provenance) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# TransformationRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransformationRecord:
    """
    Immutable record of a single field transformation applied during destatusing.

    One TransformationRecord is generated per field changed per activity.
    Records accumulate in a TransformationLog for the full destatusing run.

    Fields:
        transformation_id       — Unique identifier (e.g., "TX-001").
        act_id                  — Affected activity identifier.
        rule                    — Destatusing rule that triggered this change
                                  (e.g., "RULE_B", "RULE_D").
        governing_calc          — Calculation reference (e.g., "CALC-006").
        field_name              — Name of the field that was changed.
        source_value            — Field value before transformation (None = was None).
        target_value            — Field value after transformation (None = removed).
        transformation_type     — "REMOVE", "SET", or "COMPUTE".
        reversible              — True when the transformation can be undone using
                                  the provenance record alone.
        analyst_review_required — True when the transformation result requires
                                  analyst confirmation before reliance.
        analytical_implication  — Human-readable statement of how this transformation
                                  affects CPM analysis.
        context                 — Optional run-level context string (e.g., run ID
                                  or session reference) for audit linkage.
    """
    transformation_id: str
    act_id: str
    rule: str
    governing_calc: str
    field_name: str
    source_value: Any
    target_value: Any
    transformation_type: str       # "REMOVE" | "SET" | "COMPUTE"
    reversible: bool
    analyst_review_required: bool
    analytical_implication: str
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for audit output."""
        def _fmt(v: Any) -> Any:
            if isinstance(v, date):
                return v.isoformat()
            return v

        return {
            "transformation_id": self.transformation_id,
            "act_id": self.act_id,
            "rule": self.rule,
            "governing_calc": self.governing_calc,
            "field_name": self.field_name,
            "source_value": _fmt(self.source_value),
            "target_value": _fmt(self.target_value),
            "transformation_type": self.transformation_type,
            "reversible": self.reversible,
            "analyst_review_required": self.analyst_review_required,
            "analytical_implication": self.analytical_implication,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# TransformationLog
# ---------------------------------------------------------------------------

class TransformationLog:
    """
    Ordered log of all TransformationRecord objects from a destatusing run.

    Records are appended in check-execution order (deterministic given the same
    activity list ordering). Exposes query helpers for review workflows.
    """

    def __init__(self, context: str = "") -> None:
        self._records: list[TransformationRecord] = []
        self._next_seq: int = 1
        self._context = context

    def next_id(self) -> str:
        """Return next sequential transformation ID ("TX-001", ...)."""
        tid = f"TX-{self._next_seq:03d}"
        self._next_seq += 1
        return tid

    def add(self, record: TransformationRecord) -> None:
        """Append a record to the log."""
        self._records.append(record)

    @property
    def all(self) -> list[TransformationRecord]:
        """All records in insertion order."""
        return list(self._records)

    def for_activity(self, act_id: str) -> list[TransformationRecord]:
        """All records for a specific activity, in insertion order."""
        return [r for r in self._records if r.act_id == act_id]

    def requiring_review(self) -> list[TransformationRecord]:
        """Records with analyst_review_required=True."""
        return [r for r in self._records if r.analyst_review_required]

    def irreversible(self) -> list[TransformationRecord]:
        """Records with reversible=False."""
        return [r for r in self._records if not r.reversible]

    def __len__(self) -> int:
        return len(self._records)

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Serialize all records."""
        return [r.to_dict() for r in self._records]


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_removal_record(
    log: TransformationLog,
    act_id: str,
    rule: str,
    governing_calc: str,
    field_name: str,
    source_value: Any,
    analyst_review_required: bool,
    analytical_implication: str,
    context: str = "",
) -> TransformationRecord:
    """Create and add a REMOVE-type record to the log."""
    record = TransformationRecord(
        transformation_id=log.next_id(),
        act_id=act_id,
        rule=rule,
        governing_calc=governing_calc,
        field_name=field_name,
        source_value=source_value,
        target_value=None,
        transformation_type="REMOVE",
        reversible=True,
        analyst_review_required=analyst_review_required,
        analytical_implication=analytical_implication,
        context=context,
    )
    log.add(record)
    return record


def make_set_record(
    log: TransformationLog,
    act_id: str,
    rule: str,
    governing_calc: str,
    field_name: str,
    source_value: Any,
    target_value: Any,
    reversible: bool,
    analyst_review_required: bool,
    analytical_implication: str,
    context: str = "",
) -> TransformationRecord:
    """Create and add a SET-type record to the log."""
    record = TransformationRecord(
        transformation_id=log.next_id(),
        act_id=act_id,
        rule=rule,
        governing_calc=governing_calc,
        field_name=field_name,
        source_value=source_value,
        target_value=target_value,
        transformation_type="SET",
        reversible=reversible,
        analyst_review_required=analyst_review_required,
        analytical_implication=analytical_implication,
        context=context,
    )
    log.add(record)
    return record


def make_compute_record(
    log: TransformationLog,
    act_id: str,
    rule: str,
    governing_calc: str,
    field_name: str,
    source_value: Any,
    target_value: Any,
    analyst_review_required: bool,
    analytical_implication: str,
    context: str = "",
) -> TransformationRecord:
    """Create and add a COMPUTE-type record (derived value) to the log."""
    record = TransformationRecord(
        transformation_id=log.next_id(),
        act_id=act_id,
        rule=rule,
        governing_calc=governing_calc,
        field_name=field_name,
        source_value=source_value,
        target_value=target_value,
        transformation_type="COMPUTE",
        reversible=False,
        analyst_review_required=analyst_review_required,
        analytical_implication=analytical_implication,
        context=context,
    )
    log.add(record)
    return record
