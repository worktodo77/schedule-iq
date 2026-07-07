"""
V1-D: Analyst review checkpoints for destatusing workflows.

Checkpoints are generated when a diagnostic meets the policy's checkpoint
threshold, or when conditions require analyst confirmation (e.g., NO_MATCH
activities, PC formula interpretation).

Lifecycle mirrors the normalization checkpoint model (ADR-013 precedent):
  PENDING → ACKNOWLEDGED or OVERRIDDEN.

Override requires non-empty justification notes. V1-D generates PENDING
checkpoints only. Transitioning to ACKNOWLEDGED or OVERRIDDEN is an analyst
workflow action.

Source: ADR-014; ADR-013 (checkpoint lifecycle precedent).

Ported from the LI MIP 3.9 tool (mip39.destatusing.checkpoints) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DSTCheckpointStatus(Enum):
    """Lifecycle status of a destatusing analyst checkpoint."""
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OVERRIDDEN = "OVERRIDDEN"


@dataclass
class DSTCheckpoint:
    """
    One analyst review checkpoint from the destatusing workflow.

    Fields:
        checkpoint_id       — Sequential identifier ("DC-001", "DC-002", ...).
        reason              — Why this checkpoint was generated.
        triggering_codes    — DST/LAG/DRV diagnostic codes that triggered this.
        act_ids             — Activity IDs involved.
        status              — Current lifecycle status (default PENDING).
        resolution_notes    — Analyst notes (required for OVERRIDDEN).
        is_blocking         — True when analysis should not proceed without resolution.
    """
    checkpoint_id: str
    reason: str
    triggering_codes: list[str]
    act_ids: list[str]
    status: DSTCheckpointStatus = DSTCheckpointStatus.PENDING
    resolution_notes: str = ""
    is_blocking: bool = False

    def acknowledge(self, notes: str = "") -> "DSTCheckpoint":
        return DSTCheckpoint(
            checkpoint_id=self.checkpoint_id,
            reason=self.reason,
            triggering_codes=list(self.triggering_codes),
            act_ids=list(self.act_ids),
            status=DSTCheckpointStatus.ACKNOWLEDGED,
            resolution_notes=notes,
            is_blocking=self.is_blocking,
        )

    def override(self, notes: str) -> "DSTCheckpoint":
        if not notes.strip():
            raise ValueError(
                f"Override of checkpoint {self.checkpoint_id!r} requires "
                "non-empty justification notes."
            )
        return DSTCheckpoint(
            checkpoint_id=self.checkpoint_id,
            reason=self.reason,
            triggering_codes=list(self.triggering_codes),
            act_ids=list(self.act_ids),
            status=DSTCheckpointStatus.OVERRIDDEN,
            resolution_notes=notes,
            is_blocking=self.is_blocking,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "reason": self.reason,
            "triggering_codes": list(self.triggering_codes),
            "act_ids": list(self.act_ids),
            "status": self.status.value,
            "resolution_notes": self.resolution_notes,
            "is_blocking": self.is_blocking,
        }


class DSTCheckpointRegistry:
    """Ordered collection of DSTCheckpoint objects from a destatusing run."""

    def __init__(self) -> None:
        self._items: list[DSTCheckpoint] = []
        self._next_id: int = 1

    def next_id(self) -> str:
        """Return next sequential checkpoint ID ("DC-001", ...)."""
        cid = f"DC-{self._next_id:03d}"
        self._next_id += 1
        return cid

    def add(self, checkpoint: DSTCheckpoint) -> None:
        self._items.append(checkpoint)

    @property
    def all(self) -> list[DSTCheckpoint]:
        return list(self._items)

    def pending(self) -> list[DSTCheckpoint]:
        return [c for c in self._items if c.status == DSTCheckpointStatus.PENDING]

    def blocking(self) -> list[DSTCheckpoint]:
        return [c for c in self._items if c.is_blocking]

    def unresolved_blocking(self) -> list[DSTCheckpoint]:
        return [
            c for c in self._items
            if c.is_blocking and c.status == DSTCheckpointStatus.PENDING
        ]

    def is_analysis_blocked(self) -> bool:
        return bool(self.unresolved_blocking())

    def __len__(self) -> int:
        return len(self._items)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._items]
