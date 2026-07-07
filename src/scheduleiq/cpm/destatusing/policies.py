"""
V1-D: Destatusing policy architecture.

Four named policies govern which transformations are permitted, which conditions
require analyst checkpoints, and which block analysis. No hidden defaults.

Policies:
  STRICT_FORENSIC         — Most conservative. All anomalies checkpoint;
                            ANALYTICAL_RISK conditions block.
  ADVISORY_ONLY           — All transformations proceed; advisory diagnostics only;
                            no blocking.
  CPW_COMPATIBILITY       — Mirrors CPW-P6 behavior: applies Rules A-F as documented;
                            checkpoints WARNING+ conditions.
  AGGRESSIVE_NORMALIZATION — Most permissive. Attempts all rule applications;
                             suppresses advisory checkpoints.

Default: STRICT_FORENSIC (safest for forensic work).

Source: ADR-014; CPW-P6 Manual pp. 40-44.

Ported from the LI MIP 3.9 tool (mip39.destatusing.policies) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from ..severity import DiagnosticSeverity


class DestatusingPolicy(str, Enum):
    """Named policy modes for destatusing behavior."""
    STRICT_FORENSIC = "strict_forensic"
    ADVISORY_ONLY = "advisory_only"
    CPW_COMPATIBILITY = "cpw_compatibility"
    AGGRESSIVE_NORMALIZATION = "aggressive_normalization"


@dataclass(frozen=True)
class DSTpolicyConfig:
    """
    Configuration for a destatusing policy.

    Fields:
        policy                  — The policy this config describes.
        block_at                — Minimum severity that blocks analysis.
                                  None = never block.
        checkpoint_at           — Minimum severity that generates a checkpoint.
                                  None = no checkpoints.
        require_analyst_review_on_no_match
                                — If True, NO_MATCH activities generate a
                                  blocking checkpoint.
        allow_pc_formula_interpretation
                                — If True, the PC formula (implementation
                                  interpretation for Rules D and F) is accepted
                                  without forced checkpoint.
        description             — Human-readable policy description.
    """
    policy: DestatusingPolicy
    block_at: DiagnosticSeverity | None
    checkpoint_at: DiagnosticSeverity | None
    require_analyst_review_on_no_match: bool
    allow_pc_formula_interpretation: bool
    description: str

    def is_blocking(self, severity: DiagnosticSeverity) -> bool:
        """True when a diagnostic of this severity blocks analysis under this policy."""
        if self.block_at is None:
            return False
        return severity.is_at_least(self.block_at)

    def requires_checkpoint(self, severity: DiagnosticSeverity) -> bool:
        """True when a diagnostic of this severity requires a checkpoint."""
        if self.checkpoint_at is None:
            return False
        return severity.is_at_least(self.checkpoint_at)


POLICY_CONFIGS: dict[DestatusingPolicy, DSTpolicyConfig] = {
    DestatusingPolicy.STRICT_FORENSIC: DSTpolicyConfig(
        policy=DestatusingPolicy.STRICT_FORENSIC,
        block_at=DiagnosticSeverity.ANALYTICAL_RISK,
        checkpoint_at=DiagnosticSeverity.WARNING,
        require_analyst_review_on_no_match=True,
        allow_pc_formula_interpretation=False,
        description=(
            "Most conservative. Blocks at ANALYTICAL_RISK; checkpoints at WARNING+. "
            "PC formula for Rules D/F requires explicit analyst confirmation. "
            "Appropriate for high-stakes forensic analysis and litigation support."
        ),
    ),
    DestatusingPolicy.ADVISORY_ONLY: DSTpolicyConfig(
        policy=DestatusingPolicy.ADVISORY_ONLY,
        block_at=None,
        checkpoint_at=DiagnosticSeverity.ANALYTICAL_RISK,
        require_analyst_review_on_no_match=False,
        allow_pc_formula_interpretation=True,
        description=(
            "Never blocks. Checkpoints at ANALYTICAL_RISK+. "
            "Appropriate for preliminary advisory review where blocking is impractical."
        ),
    ),
    DestatusingPolicy.CPW_COMPATIBILITY: DSTpolicyConfig(
        policy=DestatusingPolicy.CPW_COMPATIBILITY,
        block_at=DiagnosticSeverity.ANALYTICAL_RISK,
        checkpoint_at=DiagnosticSeverity.WARNING,
        require_analyst_review_on_no_match=True,
        allow_pc_formula_interpretation=True,
        description=(
            "Mirrors CPW-P6 behavior. Applies Rules A-F as documented in the CPW "
            "manual (SRC-001 p. 40). Blocks at ANALYTICAL_RISK; checkpoints at "
            "WARNING+. PC formula accepted without forced checkpoint. "
            "Appropriate for CPW-equivalent workflows."
        ),
    ),
    DestatusingPolicy.AGGRESSIVE_NORMALIZATION: DSTpolicyConfig(
        policy=DestatusingPolicy.AGGRESSIVE_NORMALIZATION,
        block_at=None,
        checkpoint_at=DiagnosticSeverity.ANALYTICAL_RISK,
        require_analyst_review_on_no_match=False,
        allow_pc_formula_interpretation=True,
        description=(
            "Most permissive. Attempts all applicable rule transformations. "
            "No blocking; checkpoints only at ANALYTICAL_RISK+. "
            "NOT recommended for litigation-support contexts."
        ),
    ),
}


def get_policy_config(policy: DestatusingPolicy) -> DSTpolicyConfig:
    """Return the policy configuration for the given policy."""
    return POLICY_CONFIGS[policy]
