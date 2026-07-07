"""
V1-D: Auto-drive algorithm (CALC-004).

The auto-drive algorithm determines which predecessor "drives" each successor
by selecting the one with the smallest lag variance (actual_lag - planned_lag).

CPW-P6 Manual pp. 4-6 specification:
  - For each successor with multiple predecessors:
    * Compute variance = actual_lag - planned_lag for each predecessor.
    * The predecessor with the SMALLEST variance is designated driving; ANY
      predecessor whose variance is negative also drives (CPW p. 42) — resetting
      a negative-variance lag would bind the successor after its actual date.
    * Non-driving predecessors have their lags RESET to planned (user-defined)
      values, EXCEPT that a negative ACTUAL lag is retained (CPW p. 4).
    * If two or more predecessors have EQUAL smallest variance: lags are distributed
      so they equally drive (each gets actual_lag set to its planned_lag + shared_variance).
    * All actual NEGATIVE lags are RETAINED regardless of driving status.
    * Single-predecessor activities always use the actual lag (trivially driving).

Determinism: when multiple predecessors have equal minimum variance, they are
sorted by pred_id before variance distribution, ensuring reproducible output.

Source: CPW-P6 Manual pp. 4-6; ADR-014 §5.

Ported from the LI MIP 3.9 tool (mip39.destatusing.autodrive) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..models import Relationship
from .lag import ActualLagResult


# ---------------------------------------------------------------------------
# Auto-drive decision per successor
# ---------------------------------------------------------------------------

@dataclass
class AutoDriveDecision:
    """
    Auto-drive resolution for a single successor activity.

    Fields:
        succ_id             — Successor activity ID.
        predecessor_count   — Total number of predecessors evaluated.
        driving_pred_ids    — IDs of driving predecessor(s).
        non_driving_pred_ids — IDs of non-driving predecessors.
        min_variance        — The minimum (driving) variance value. None if no
                              actual lags were computable.
        equal_variance_tie  — True when two or more predecessors share min_variance.
        all_negative        — True when all actual lags are negative (all retained).
        lag_decisions       — Per-predecessor lag decision dict.
    """
    succ_id: str
    predecessor_count: int
    driving_pred_ids: list[str]
    non_driving_pred_ids: list[str]
    min_variance: Optional[float]
    equal_variance_tie: bool
    all_negative: bool
    lag_decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "succ_id": self.succ_id,
            "predecessor_count": self.predecessor_count,
            "driving_pred_ids": list(self.driving_pred_ids),
            "non_driving_pred_ids": list(self.non_driving_pred_ids),
            "min_variance": self.min_variance,
            "equal_variance_tie": self.equal_variance_tie,
            "all_negative": self.all_negative,
            "lag_decisions": list(self.lag_decisions),
        }


@dataclass
class AutoDriveResult:
    """
    Summary of auto-drive analysis for the entire schedule.

    Fields:
        decisions           — Per-successor AutoDriveDecision list, sorted by
                              succ_id for determinism.
        applied_relationships — Relationship list with auto-drive lags applied.
                              Non-driving lags are reset to planned values.
                              Driving lags use actual values.
        single_pred_count   — Successors with exactly one predecessor.
        multi_pred_count    — Successors with two or more predecessors.
        tie_count           — Successors with equal-variance ties.
        all_negative_count  — Successors where all predecessors had negative lags.
    """
    decisions: list[AutoDriveDecision]
    applied_relationships: list[Relationship]
    single_pred_count: int
    multi_pred_count: int
    tie_count: int
    all_negative_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [d.to_dict() for d in self.decisions],
            "applied_relationships": [
                {"pred_id": r.pred_id, "succ_id": r.succ_id,
                 "rel_type": r.rel_type, "lag": r.lag}
                for r in self.applied_relationships
            ],
            "single_pred_count": self.single_pred_count,
            "multi_pred_count": self.multi_pred_count,
            "tie_count": self.tie_count,
            "all_negative_count": self.all_negative_count,
        }


# ---------------------------------------------------------------------------
# CALC-004: Auto-drive algorithm
# ---------------------------------------------------------------------------

def run_autodrive(
    relationships: list[Relationship],
    lag_results: list[ActualLagResult],
) -> AutoDriveResult:
    """
    CALC-004 — Apply the auto-drive algorithm.

    For each successor with multiple predecessors:
    - Find the predecessor(s) with the minimum lag variance; a predecessor whose
      variance is negative also drives (CPW p. 42).
    - Mark them as driving; retain their actual lags.
    - For non-driving predecessors: reset lag to planned value, except a negative
      actual lag is retained (CPW p. 4).
    - If all actual lags are negative: retain all (CPW spec).

    Single-predecessor relationships always use the actual lag (if computed).
    If actual lag was not computable (missing dates), planned lag is used.

    Args:
        relationships: Original relationship list (source values).
        lag_results:   ActualLagResult list from run_lag_analysis().

    Returns:
        AutoDriveResult with decisions and a new applied_relationships list
        with auto-drive lags applied.
    """
    # Index lag results by (pred_id, succ_id, rel_type)
    lag_by_key: dict[str, ActualLagResult] = {
        (r.pred_id, r.succ_id, r.rel_type): r  # type: ignore[misc]
        for r in lag_results
    }

    # Group relationships by successor
    by_succ: dict[str, list[Relationship]] = {}
    for rel in relationships:
        by_succ.setdefault(rel.succ_id, []).append(rel)

    decisions: list[AutoDriveDecision] = []
    applied: list[Relationship] = []
    single_count = multi_count = tie_count = all_neg_count = 0

    for succ_id in sorted(by_succ):
        preds = sorted(by_succ[succ_id], key=lambda r: r.pred_id)

        if len(preds) == 1:
            # Single predecessor — always driving; use actual lag if available
            rel = preds[0]
            lr = lag_by_key.get((rel.pred_id, rel.succ_id, rel.rel_type))  # type: ignore[arg-type]
            actual_lag = lr.actual_lag if lr is not None else None
            final_lag = actual_lag if actual_lag is not None else rel.lag
            new_rel = copy.copy(rel)
            new_rel.lag = final_lag
            applied.append(new_rel)
            decisions.append(AutoDriveDecision(
                succ_id=succ_id,
                predecessor_count=1,
                driving_pred_ids=[rel.pred_id],
                non_driving_pred_ids=[],
                min_variance=lr.lag_variance if lr else None,
                equal_variance_tie=False,
                all_negative=actual_lag is not None and actual_lag < 0,
                lag_decisions=[{
                    "pred_id": rel.pred_id,
                    "planned_lag": rel.lag,
                    "actual_lag": actual_lag,
                    "applied_lag": final_lag,
                    "is_driving": True,
                    "reason": "single_predecessor",
                }],
            ))
            single_count += 1
            continue

        # Multiple predecessors
        multi_count += 1
        lr_list = [lag_by_key.get((r.pred_id, r.succ_id, r.rel_type)) for r in preds]  # type: ignore[arg-type]

        # Check if all actual lags are negative — if so, retain all
        computed_lrs = [lr for lr in lr_list if lr is not None and lr.actual_lag is not None]
        all_negative = bool(computed_lrs) and all(lr.actual_lag < 0 for lr in computed_lrs)  # type: ignore[operator]

        if all_negative:
            all_neg_count += 1
            lag_decisions = []
            for rel, lr in zip(preds, lr_list):
                actual = lr.actual_lag if lr is not None else None
                final_lag = actual if actual is not None else rel.lag
                new_rel = copy.copy(rel)
                new_rel.lag = final_lag
                applied.append(new_rel)
                lag_decisions.append({
                    "pred_id": rel.pred_id,
                    "planned_lag": rel.lag,
                    "actual_lag": actual,
                    "applied_lag": final_lag,
                    "is_driving": True,
                    "reason": "all_negative_lags_retained",
                })
            decisions.append(AutoDriveDecision(
                succ_id=succ_id,
                predecessor_count=len(preds),
                driving_pred_ids=[r.pred_id for r in preds],
                non_driving_pred_ids=[],
                min_variance=None,
                equal_variance_tie=False,
                all_negative=True,
                lag_decisions=lag_decisions,
            ))
            continue

        # Find minimum variance among predecessors with computable actual lag
        variances: list[tuple[float, str, Relationship, ActualLagResult | None]] = []
        for rel, lr in zip(preds, lr_list):
            if lr is not None and lr.lag_variance is not None:
                variances.append((lr.lag_variance, rel.pred_id, rel, lr))

        if not variances:
            # No actual lags computable — use planned lags for all
            lag_decisions = []
            for rel in preds:
                new_rel = copy.copy(rel)
                applied.append(new_rel)
                lag_decisions.append({
                    "pred_id": rel.pred_id,
                    "planned_lag": rel.lag,
                    "actual_lag": None,
                    "applied_lag": rel.lag,
                    "is_driving": False,
                    "reason": "no_actual_lag_available",
                })
            decisions.append(AutoDriveDecision(
                succ_id=succ_id,
                predecessor_count=len(preds),
                driving_pred_ids=[],
                non_driving_pred_ids=[r.pred_id for r in preds],
                min_variance=None,
                equal_variance_tie=False,
                all_negative=False,
                lag_decisions=lag_decisions,
            ))
            continue

        variances.sort(key=lambda t: (t[0], t[1]))  # sort by (variance, pred_id) for determinism
        min_var = variances[0][0]

        # Tie detection is a property of the MINIMUM-variance group only — two or
        # more predecessors sharing the smallest variance. Compute it BEFORE the
        # driving set is widened below so negative-variance auto-drivers (WF-02)
        # are never miscounted as ties.
        min_var_entries = [(v, pid, rel, lr) for v, pid, rel, lr in variances if v == min_var]
        is_tie = len(min_var_entries) > 1

        # WF-02 (CPW p. 42): "if the variance ... is negative, then the
        # relationship also automatically must become a driving relationship in
        # order to maintain the correct as-built dates." A reset negative-variance
        # lag would bind the successor AFTER its actual date and overconstrain the
        # network. Driving set = the minimum-variance group PLUS every
        # negative-variance relationship.
        driving_entries = [
            (v, pid, rel, lr) for v, pid, rel, lr in variances
            if v == min_var or v < 0
        ]
        non_driving_entries = [
            (v, pid, rel, lr) for v, pid, rel, lr in variances
            if not (v == min_var or v < 0)
        ]

        if is_tie:
            tie_count += 1

        # Non-driving: predecessors with no computable actual lag (planned lag applied)
        computed_pred_ids = {pid for _, pid, _, _ in variances}
        no_actual_preds = [r for r in preds if r.pred_id not in computed_pred_ids]

        lag_decisions = []
        driving_ids = []
        non_driving_ids = []

        # Driving predecessors: use actual lag. Minimum-variance member(s) are
        # labelled minimum_variance[_tie]; additional negative-variance members
        # are labelled negative_variance_auto_driving (WF-02).
        for v, pid, rel, lr in driving_entries:
            new_rel = copy.copy(rel)
            new_rel.lag = float(lr.actual_lag)  # type: ignore[arg-type]
            applied.append(new_rel)
            driving_ids.append(pid)
            if v == min_var:
                reason = "minimum_variance" + ("_tie" if is_tie else "")
            else:
                reason = "negative_variance_auto_driving"
            lag_decisions.append({
                "pred_id": pid,
                "planned_lag": rel.lag,
                "actual_lag": lr.actual_lag,
                "applied_lag": float(lr.actual_lag),  # type: ignore[arg-type]
                "is_driving": True,
                "reason": reason,
            })

        # Non-driving predecessors: reset lag to planned value — EXCEPT that a
        # negative ACTUAL lag is always retained (WF-03; CPW p. 4: "All actual
        # negative lags will remain negative in order to retain the original
        # dates"). Such a relationship keeps its actual lag but stays non-driving.
        for _, pid, rel, lr in non_driving_entries:
            new_rel = copy.copy(rel)
            if lr is not None and lr.actual_lag is not None and lr.actual_lag < 0:
                applied_lag = float(lr.actual_lag)
                reason = "negative_actual_lag_retained"
            else:
                applied_lag = rel.lag  # reset to planned
                reason = "higher_variance_reset_to_planned"
            new_rel.lag = applied_lag
            applied.append(new_rel)
            non_driving_ids.append(pid)
            lag_decisions.append({
                "pred_id": pid,
                "planned_lag": rel.lag,
                "actual_lag": lr.actual_lag,
                "applied_lag": applied_lag,
                "is_driving": False,
                "reason": reason,
            })

        # Predecessors with no actual lag: use planned (conservative)
        for rel in no_actual_preds:
            new_rel = copy.copy(rel)
            applied.append(new_rel)
            non_driving_ids.append(rel.pred_id)
            lag_decisions.append({
                "pred_id": rel.pred_id,
                "planned_lag": rel.lag,
                "actual_lag": None,
                "applied_lag": rel.lag,
                "is_driving": False,
                "reason": "no_actual_lag_available",
            })

        decisions.append(AutoDriveDecision(
            succ_id=succ_id,
            predecessor_count=len(preds),
            driving_pred_ids=sorted(driving_ids),
            non_driving_pred_ids=sorted(non_driving_ids),
            min_variance=min_var,
            equal_variance_tie=is_tie,
            all_negative=False,
            lag_decisions=sorted(lag_decisions, key=lambda d: d["pred_id"]),
        ))

    # Sort applied relationships deterministically
    applied_sorted = sorted(applied, key=lambda r: (r.pred_id, r.succ_id, r.rel_type))

    return AutoDriveResult(
        decisions=sorted(decisions, key=lambda d: d.succ_id),
        applied_relationships=applied_sorted,
        single_pred_count=single_count,
        multi_pred_count=multi_count,
        tie_count=tie_count,
        all_negative_count=all_neg_count,
    )
