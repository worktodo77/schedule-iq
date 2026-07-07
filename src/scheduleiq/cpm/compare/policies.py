"""
V1-G: Comparison validation policy architecture.

Four named policies govern comparison run behavior:
  blocking conditions, checkpoint generation, and analyst-review requirements.

Policies:
  STRICT:       Block on any unresolved MATERIAL_ANALYTICAL_DIFFERENCE or
                UNKNOWN_DIFFERENCE. Requires all blocking divergences to be
                resolved before reliance. Appropriate for final forensic
                deliverable validation.
  GOVERNED:     Block on unresolved MATERIAL_ANALYTICAL_DIFFERENCE. Generates
                checkpoints for UNKNOWN_DIFFERENCE but does not block.
                Appropriate for governed gap analysis with analyst waiver
                workflow.
  ADVISORY:     Never blocks. All divergences generate checkpoints for analyst
                visibility but do not prevent reliance. Appropriate for
                preliminary gap analysis or internal review.
  EXPERIMENTAL: No blocking; no checkpoints. Proceeds regardless of divergence
                count or severity. NOT recommended for forensic or
                litigation-support contexts.

Default: STRICT.

Source: ADR-016.

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.policies) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .divergences import DivergenceCategory


class ComparisonPolicy(str, Enum):
    """Named comparison validation policy modes."""
    STRICT = "STRICT"
    GOVERNED = "GOVERNED"
    ADVISORY = "ADVISORY"
    EXPERIMENTAL = "EXPERIMENTAL"


@dataclass(frozen=True)
class ComparisonPolicyConfig:
    """
    Configuration record for a comparison policy.

    Fields:
        policy:                   The policy this config describes.
        block_categories:         Set of DivergenceCategories that block reliance
                                  when any unresolved divergence of this category
                                  exists. Empty = never blocks.
        checkpoint_categories:    Set of DivergenceCategories that generate an
                                  analyst checkpoint regardless of resolution.
        require_resolution_for:   Categories where all divergences must be
                                  resolved before generating a non-blocked result.
        description:              Human-readable policy description.
    """

    policy: ComparisonPolicy
    block_categories: frozenset[DivergenceCategory]
    checkpoint_categories: frozenset[DivergenceCategory]
    require_resolution_for: frozenset[DivergenceCategory]
    description: str

    def is_blocking_category(self, category: DivergenceCategory) -> bool:
        """True when unresolved divergences of this category block reliance."""
        return category in self.block_categories

    def requires_checkpoint(self, category: DivergenceCategory) -> bool:
        """True when divergences of this category generate an analyst checkpoint."""
        return category in self.checkpoint_categories

    def requires_resolution(self, category: DivergenceCategory) -> bool:
        """True when all divergences of this category must be resolved before reliance."""
        return category in self.require_resolution_for


POLICY_CONFIGS: dict[ComparisonPolicy, ComparisonPolicyConfig] = {
    ComparisonPolicy.STRICT: ComparisonPolicyConfig(
        policy=ComparisonPolicy.STRICT,
        block_categories=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
        }),
        checkpoint_categories=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
            DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE,
            DivergenceCategory.LAG_BEHAVIOR_DIFFERENCE,
            DivergenceCategory.FLOAT_METHOD_DIFFERENCE,
            DivergenceCategory.P6_EMULATION_DIFFERENCE,
            DivergenceCategory.GOVERNED_DIFFERENCE,
        }),
        require_resolution_for=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
        }),
        description=(
            "Most conservative. Blocks when any unresolved MATERIAL_ANALYTICAL_DIFFERENCE "
            "or UNKNOWN_DIFFERENCE exists. Generates checkpoints for all non-expected "
            "divergence categories. Requires resolution for all blocking categories. "
            "Appropriate for final forensic deliverable validation before reliance."
        ),
    ),
    ComparisonPolicy.GOVERNED: ComparisonPolicyConfig(
        policy=ComparisonPolicy.GOVERNED,
        block_categories=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
        }),
        checkpoint_categories=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
            DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE,
            DivergenceCategory.LAG_BEHAVIOR_DIFFERENCE,
            DivergenceCategory.FLOAT_METHOD_DIFFERENCE,
        }),
        require_resolution_for=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
        }),
        description=(
            "Blocks on unresolved MATERIAL_ANALYTICAL_DIFFERENCE. Checkpoints for "
            "UNKNOWN_DIFFERENCE and behavioral divergences but does not block on them. "
            "Appropriate for governed gap analysis where UNKNOWN divergences are expected "
            "and documented but do not prevent interim reliance."
        ),
    ),
    ComparisonPolicy.ADVISORY: ComparisonPolicyConfig(
        policy=ComparisonPolicy.ADVISORY,
        block_categories=frozenset(),
        checkpoint_categories=frozenset({
            DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            DivergenceCategory.UNKNOWN_DIFFERENCE,
            DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE,
            DivergenceCategory.LAG_BEHAVIOR_DIFFERENCE,
        }),
        require_resolution_for=frozenset(),
        description=(
            "Never blocks. Generates checkpoints for material, unknown, and behavioral "
            "divergences for analyst visibility. Appropriate for preliminary gap analysis "
            "or internal review where blocking would impede investigation. "
            "NOT appropriate for final forensic reliance."
        ),
    ),
    ComparisonPolicy.EXPERIMENTAL: ComparisonPolicyConfig(
        policy=ComparisonPolicy.EXPERIMENTAL,
        block_categories=frozenset(),
        checkpoint_categories=frozenset(),
        require_resolution_for=frozenset(),
        description=(
            "No blocking; no checkpoints. Proceeds regardless of divergence count "
            "or category. NOT recommended for forensic or litigation-support contexts. "
            "Appropriate only for exploratory analysis and framework development."
        ),
    ),
}


def get_comparison_policy_config(policy: ComparisonPolicy) -> ComparisonPolicyConfig:
    """Return the ComparisonPolicyConfig for the given policy."""
    return POLICY_CONFIGS[policy]
