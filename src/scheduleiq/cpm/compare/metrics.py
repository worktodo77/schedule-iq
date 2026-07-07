"""
V1-G: Comparison validation metrics.

ComparisonMetrics summarizes the quantitative outcome of a comparison run.
All metrics are deterministic (same inputs → same values) and reproducible.

Metrics cover:
  - Activity-level match rates
  - Critical-path agreement
  - Finish-date variance
  - Float variance (max and mean)
  - Divergence counts by category
  - Unresolved checkpoint counts

Source: ADR-016.

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.metrics) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ComparisonMetrics:
    """
    Quantitative summary of a comparison run.

    Fields:
        total_activities:           Activities present in both mip39 and reference.
        mip39_only_activities:      Activities in mip39 result but not in reference.
        reference_only_activities:  Activities in reference but not in mip39 result.
        exact_match_activities:     Activities where all comparable fields match exactly.
        within_tolerance_activities: Activities where all fields are within tolerance
                                    (includes exact matches).
        divergent_activities:       Activities with at least one out-of-tolerance field.
        activity_match_pct:         within_tolerance_activities / total_activities × 100.
                                    0.0 when total_activities == 0.
        critical_path_agreement:    True when the set of critical-path activity IDs
                                    matches between mip39 and reference (order-insensitive).
        critical_path_mip39_only:   Activity IDs on mip39 CP but not reference CP.
        critical_path_ref_only:     Activity IDs on reference CP but not mip39 CP.
        finish_date_variance_days:  (mip39_finish - reference_finish).days, or None
                                    if either finish is unavailable.
        total_float_variance_max:   Maximum abs(mip39_TF - ref_TF) across all
                                    activities, or 0 if no float data available.
        total_float_variance_mean:  Mean abs(mip39_TF - ref_TF), or 0.0.
        free_float_variance_max:    Maximum abs(mip39_FF - ref_FF), or 0.
        divergence_count_total:     Total divergence records created.
        divergence_counts:          dict[category_name → count].
        unresolved_divergence_count: Divergences not yet resolved by analyst.
        blocking_divergence_count:  Unresolved divergences whose category is blocking.
        checkpoint_count:           Total analyst checkpoints generated.
        unresolved_checkpoint_count: Checkpoints not yet acknowledged or waived.
    """

    total_activities: int = 0
    mip39_only_activities: int = 0
    reference_only_activities: int = 0
    exact_match_activities: int = 0
    within_tolerance_activities: int = 0
    divergent_activities: int = 0
    activity_match_pct: float = 0.0
    critical_path_agreement: bool = False
    critical_path_mip39_only: list[str] = field(default_factory=list)
    critical_path_ref_only: list[str] = field(default_factory=list)
    finish_date_variance_days: Optional[int] = None
    total_float_variance_max: int = 0
    total_float_variance_mean: float = 0.0
    free_float_variance_max: int = 0
    divergence_count_total: int = 0
    divergence_counts: dict[str, int] = field(default_factory=dict)
    unresolved_divergence_count: int = 0
    blocking_divergence_count: int = 0
    checkpoint_count: int = 0
    unresolved_checkpoint_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_activities": self.total_activities,
            "mip39_only_activities": self.mip39_only_activities,
            "reference_only_activities": self.reference_only_activities,
            "exact_match_activities": self.exact_match_activities,
            "within_tolerance_activities": self.within_tolerance_activities,
            "divergent_activities": self.divergent_activities,
            "activity_match_pct": round(self.activity_match_pct, 2),
            "critical_path_agreement": self.critical_path_agreement,
            "critical_path_mip39_only": list(self.critical_path_mip39_only),
            "critical_path_ref_only": list(self.critical_path_ref_only),
            "finish_date_variance_days": self.finish_date_variance_days,
            "total_float_variance_max": self.total_float_variance_max,
            "total_float_variance_mean": round(self.total_float_variance_mean, 3),
            "free_float_variance_max": self.free_float_variance_max,
            "divergence_count_total": self.divergence_count_total,
            "divergence_counts": dict(self.divergence_counts),
            "unresolved_divergence_count": self.unresolved_divergence_count,
            "blocking_divergence_count": self.blocking_divergence_count,
            "checkpoint_count": self.checkpoint_count,
            "unresolved_checkpoint_count": self.unresolved_checkpoint_count,
        }
