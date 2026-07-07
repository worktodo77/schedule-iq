"""
V1-G: Comparison run provenance.

Every comparison run receives a UUID run_id and UTC timestamp. The provenance
record captures the comparison assumptions, policy and tolerance policy applied,
and a stage-by-stage record of the comparison pipeline.

This follows the same provenance governance model as SimProvenance (V1-E) and
the destatusing TransformationLog (V1-D): every comparison decision is traceable
to a specific run, policy, and set of documented assumptions.

Source: ADR-016; ADR-005 (forensic defensibility — determinism and traceability).

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.provenance) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ComparisonStageRecord:
    """
    Provenance record for one stage of the comparison pipeline.

    Fields:
        stage_name:           Name of the comparison stage.
        items_compared:       Number of items compared in this stage.
        divergences_found:    Number of divergences found in this stage.
        notes:                Free-form notes about this stage.
    """

    stage_name: str
    items_compared: int
    divergences_found: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "items_compared": self.items_compared,
            "divergences_found": self.divergences_found,
            "notes": list(self.notes),
        }


@dataclass
class ComparisonProvenance:
    """
    Complete provenance chain for a single comparison run.

    Fields:
        run_id:             UUID identifying this specific comparison run.
        timestamp_utc:      ISO 8601 UTC timestamp of run start.
        policy:             ComparisonPolicy name applied.
        tolerance_policy:   TolerancePolicy name applied.
        reference_source:   Source identifier for the reference schedule.
        reference_id:       Reference schedule ID or fixture ID.
        original_activity_count: Activity count in the mip39 analysis result.
        reference_activity_count: Activity count in the reference schedule.
        context:            Optional caller context string.
        assumptions:        List of analytical assumptions for this run.
        disclosures:        List of governance disclosures.
        stages:             Pipeline stage records in execution order.
    """

    run_id: str
    timestamp_utc: str
    policy: str
    tolerance_policy: str
    reference_source: str
    reference_id: str
    original_activity_count: int
    reference_activity_count: int
    context: str = ""
    assumptions: list[str] = field(default_factory=list)
    disclosures: list[str] = field(default_factory=list)
    stages: list[ComparisonStageRecord] = field(default_factory=list)

    def add_assumption(self, assumption: str) -> None:
        self.assumptions.append(assumption)

    def add_disclosure(self, disclosure: str) -> None:
        self.disclosures.append(disclosure)

    def add_stage(self, stage: ComparisonStageRecord) -> None:
        self.stages.append(stage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "policy": self.policy,
            "tolerance_policy": self.tolerance_policy,
            "reference_source": self.reference_source,
            "reference_id": self.reference_id,
            "original_activity_count": self.original_activity_count,
            "reference_activity_count": self.reference_activity_count,
            "context": self.context,
            "assumptions": list(self.assumptions),
            "disclosures": list(self.disclosures),
            "stages": [s.to_dict() for s in self.stages],
        }


def build_comparison_provenance(
    policy: str,
    tolerance_policy: str,
    reference_source: str,
    reference_id: str,
    original_activity_count: int,
    reference_activity_count: int,
    context: str = "",
) -> ComparisonProvenance:
    """
    Construct a ComparisonProvenance with a fresh UUID run_id and UTC timestamp.

    Standard assumptions and disclosures are added automatically. Callers
    add pipeline-stage records via prov.add_stage() during the comparison run.
    """
    prov = ComparisonProvenance(
        run_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        policy=policy,
        tolerance_policy=tolerance_policy,
        reference_source=reference_source,
        reference_id=reference_id,
        original_activity_count=original_activity_count,
        reference_activity_count=reference_activity_count,
        context=context,
    )
    prov.add_assumption(
        "Activity comparison is performed in sorted act_id order for determinism."
    )
    prov.add_assumption(
        "Date field tolerance is measured in calendar days, not workdays. "
        "See LIM-043 for implications at week boundaries."
    )
    prov.add_assumption(
        "CPW is an operational comparison reference, not the mathematical authority. "
        "AACE RPs and Long International methodology remain authoritative (ADR-016)."
    )
    prov.add_disclosure(
        "This comparison framework does not emulate P6 internal behavior. "
        "Divergences classified as P6_EMULATION_DIFFERENCE are by-design (ADR-005)."
    )
    return prov
