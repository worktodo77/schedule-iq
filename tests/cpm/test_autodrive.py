"""
Tests for V1-D: Auto-drive algorithm (CALC-004, run_autodrive).

Covers:
  - Single predecessor: always driving, uses actual lag
  - Multiple predecessors: minimum variance wins
  - Equal variance tie: all tied predecessors marked driving
  - All-negative lags: all retained (CPW spec)
  - Non-driving predecessors reset to planned lag
  - No actual lags computable: planned lags used
  - Deterministic output (sorted by pred_id/succ_id)
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.destatusing import (  # noqa: E402
    AutoDriveDecision,
    AutoDriveResult,
    run_autodrive,
    ActualLagResult,
)
from scheduleiq.cpm.models import Relationship  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel(pred, succ, lag=0.0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="FS", lag=float(lag))


def _lag_result(pred, succ, planned, actual) -> ActualLagResult:
    if actual is None:
        return ActualLagResult(
            pred_id=pred, succ_id=succ, rel_type="FS",
            planned_lag=planned, actual_lag=None,
            lag_variance=None, is_negative=False,
            formula_used="FS_workday_unavailable",
            dates_missing=["pred_actual_finish"],
        )
    variance = float(actual) - float(planned)
    return ActualLagResult(
        pred_id=pred, succ_id=succ, rel_type="FS",
        planned_lag=planned, actual_lag=float(actual),
        lag_variance=variance, is_negative=actual < 0,
        formula_used="FS_workday",
    )


# ---------------------------------------------------------------------------
# Single predecessor
# ---------------------------------------------------------------------------

class TestSinglePredecessor:
    def test_single_pred_uses_actual_lag(self):
        rels = [_rel("P1", "S1", lag=2)]
        lags = [_lag_result("P1", "S1", planned=2, actual=3)]
        result = run_autodrive(rels, lags)
        applied = {(r.pred_id, r.succ_id): r.lag for r in result.applied_relationships}
        assert applied[("P1", "S1")] == 3.0

    def test_single_pred_driving_id(self):
        rels = [_rel("P1", "S1", lag=2)]
        lags = [_lag_result("P1", "S1", planned=2, actual=3)]
        result = run_autodrive(rels, lags)
        dec = result.decisions[0]
        assert "P1" in dec.driving_pred_ids
        assert dec.non_driving_pred_ids == []

    def test_single_pred_no_actual_uses_planned(self):
        rels = [_rel("P1", "S1", lag=5)]
        lags = [_lag_result("P1", "S1", planned=5, actual=None)]
        result = run_autodrive(rels, lags)
        applied = {(r.pred_id, r.succ_id): r.lag for r in result.applied_relationships}
        assert applied[("P1", "S1")] == 5.0

    def test_single_pred_count(self):
        rels = [_rel("P1", "S1")]
        lags = [_lag_result("P1", "S1", planned=0, actual=0)]
        result = run_autodrive(rels, lags)
        assert result.single_pred_count == 1
        assert result.multi_pred_count == 0

    def test_single_pred_negative_lag(self):
        rels = [_rel("P1", "S1", lag=0)]
        lags = [_lag_result("P1", "S1", planned=0, actual=-2)]
        result = run_autodrive(rels, lags)
        applied = result.applied_relationships[0]
        assert applied.lag == -2.0
        dec = result.decisions[0]
        assert dec.all_negative is True


# ---------------------------------------------------------------------------
# Multiple predecessors — minimum variance wins
# ---------------------------------------------------------------------------

class TestMultiplePredecessors:
    def test_min_variance_wins(self):
        # P1: variance = 5-0 = 5 (big)
        # P2: variance = 1-0 = 1 (small → driving)
        rels = [_rel("P1", "S1", lag=0), _rel("P2", "S1", lag=0)]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=5),
            _lag_result("P2", "S1", planned=0, actual=1),
        ]
        result = run_autodrive(rels, lags)
        dec = result.decisions[0]
        assert "P2" in dec.driving_pred_ids
        assert "P1" in dec.non_driving_pred_ids

    def test_non_driving_reset_to_planned(self):
        rels = [_rel("P1", "S1", lag=3), _rel("P2", "S1", lag=2)]
        lags = [
            _lag_result("P1", "S1", planned=3, actual=8),  # variance=5
            _lag_result("P2", "S1", planned=2, actual=3),  # variance=1 → driving
        ]
        result = run_autodrive(rels, lags)
        applied = {r.pred_id: r.lag for r in result.applied_relationships if r.succ_id == "S1"}
        # P1 non-driving → reset to planned=3
        assert applied["P1"] == 3.0
        # P2 driving → actual=3
        assert applied["P2"] == 3.0

    def test_multi_pred_count(self):
        rels = [_rel("P1", "S1"), _rel("P2", "S1")]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=5),
            _lag_result("P2", "S1", planned=0, actual=1),
        ]
        result = run_autodrive(rels, lags)
        assert result.multi_pred_count == 1
        assert result.single_pred_count == 0


# ---------------------------------------------------------------------------
# Equal variance tie
# ---------------------------------------------------------------------------

class TestEqualVarianceTie:
    def test_tie_both_marked_driving(self):
        # P1 variance = 2-0 = 2; P2 variance = 3-1 = 2 — equal tie
        rels = [_rel("P1", "S1", lag=0), _rel("P2", "S1", lag=1)]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=2),
            _lag_result("P2", "S1", planned=1, actual=3),
        ]
        result = run_autodrive(rels, lags)
        dec = result.decisions[0]
        assert dec.equal_variance_tie is True
        assert "P1" in dec.driving_pred_ids
        assert "P2" in dec.driving_pred_ids
        assert dec.non_driving_pred_ids == []

    def test_tie_count_incremented(self):
        rels = [_rel("P1", "S1", lag=0), _rel("P2", "S1", lag=1)]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=2),
            _lag_result("P2", "S1", planned=1, actual=3),
        ]
        result = run_autodrive(rels, lags)
        assert result.tie_count == 1

    def test_tie_deterministic_ordering(self):
        # Ensure pred_ids sorted alphabetically for reproducibility
        rels = [_rel("Z_PRED", "S1", lag=0), _rel("A_PRED", "S1", lag=0)]
        lags = [
            _lag_result("Z_PRED", "S1", planned=0, actual=2),
            _lag_result("A_PRED", "S1", planned=0, actual=2),
        ]
        result = run_autodrive(rels, lags)
        dec = result.decisions[0]
        assert dec.driving_pred_ids == sorted(dec.driving_pred_ids)


# ---------------------------------------------------------------------------
# All-negative lags
# ---------------------------------------------------------------------------

class TestAllNegativeLags:
    def test_all_negative_retained(self):
        rels = [_rel("P1", "S1", lag=0), _rel("P2", "S1", lag=0)]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=-1),
            _lag_result("P2", "S1", planned=0, actual=-3),
        ]
        result = run_autodrive(rels, lags)
        applied = {r.pred_id: r.lag for r in result.applied_relationships if r.succ_id == "S1"}
        assert applied["P1"] == -1.0
        assert applied["P2"] == -3.0

    def test_all_negative_count(self):
        rels = [_rel("P1", "S1"), _rel("P2", "S1")]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=-1),
            _lag_result("P2", "S1", planned=0, actual=-3),
        ]
        result = run_autodrive(rels, lags)
        assert result.all_negative_count == 1

    def test_all_negative_decision_all_driving(self):
        rels = [_rel("P1", "S1"), _rel("P2", "S1")]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=-1),
            _lag_result("P2", "S1", planned=0, actual=-2),
        ]
        result = run_autodrive(rels, lags)
        dec = result.decisions[0]
        assert dec.all_negative is True
        assert set(dec.driving_pred_ids) == {"P1", "P2"}
        assert dec.non_driving_pred_ids == []


# ---------------------------------------------------------------------------
# No actual lags computable
# ---------------------------------------------------------------------------

class TestNoActualLags:
    def test_no_actual_lags_use_planned(self):
        rels = [_rel("P1", "S1", lag=5), _rel("P2", "S1", lag=3)]
        lags = [
            _lag_result("P1", "S1", planned=5, actual=None),
            _lag_result("P2", "S1", planned=3, actual=None),
        ]
        result = run_autodrive(rels, lags)
        applied = {r.pred_id: r.lag for r in result.applied_relationships if r.succ_id == "S1"}
        assert applied["P1"] == 5.0
        assert applied["P2"] == 3.0

    def test_no_actual_lags_no_driving(self):
        rels = [_rel("P1", "S1"), _rel("P2", "S1")]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=None),
            _lag_result("P2", "S1", planned=0, actual=None),
        ]
        result = run_autodrive(rels, lags)
        dec = result.decisions[0]
        assert dec.driving_pred_ids == []
        assert "P1" in dec.non_driving_pred_ids
        assert "P2" in dec.non_driving_pred_ids


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_applied_relationships_sorted(self):
        rels = [_rel("P2", "S2"), _rel("P1", "S1"), _rel("P1", "S2")]
        lags = [
            _lag_result("P2", "S2", planned=0, actual=1),
            _lag_result("P1", "S1", planned=0, actual=2),
            _lag_result("P1", "S2", planned=0, actual=0),
        ]
        result = run_autodrive(rels, lags)
        keys = [(r.pred_id, r.succ_id) for r in result.applied_relationships]
        assert keys == sorted(keys)

    def test_decisions_sorted_by_succ_id(self):
        rels = [_rel("P1", "SB"), _rel("P1", "SA")]
        lags = [
            _lag_result("P1", "SB", planned=0, actual=2),
            _lag_result("P1", "SA", planned=0, actual=1),
        ]
        result = run_autodrive(rels, lags)
        succ_ids = [d.succ_id for d in result.decisions]
        assert succ_ids == sorted(succ_ids)

    def test_same_input_same_output(self):
        rels = [_rel("P1", "S1", lag=2), _rel("P2", "S1", lag=1)]
        lags = [
            _lag_result("P1", "S1", planned=2, actual=5),
            _lag_result("P2", "S1", planned=1, actual=3),
        ]
        r1 = run_autodrive(rels, lags)
        r2 = run_autodrive(rels, lags)
        assert r1.decisions[0].driving_pred_ids == r2.decisions[0].driving_pred_ids


# ---------------------------------------------------------------------------
# AutoDriveResult structure
# ---------------------------------------------------------------------------

class TestAutodriveResultStructure:
    def test_to_dict_keys(self):
        rels = [_rel("P1", "S1")]
        lags = [_lag_result("P1", "S1", planned=0, actual=1)]
        result = run_autodrive(rels, lags)
        d = result.to_dict()
        assert "decisions" in d
        assert "applied_relationships" in d
        assert "single_pred_count" in d
        assert "multi_pred_count" in d

    def test_decision_to_dict_keys(self):
        rels = [_rel("P1", "S1"), _rel("P2", "S1")]
        lags = [
            _lag_result("P1", "S1", planned=0, actual=1),
            _lag_result("P2", "S1", planned=0, actual=3),
        ]
        result = run_autodrive(rels, lags)
        d = result.decisions[0].to_dict()
        for key in ("succ_id", "predecessor_count", "driving_pred_ids",
                    "non_driving_pred_ids", "min_variance", "equal_variance_tie",
                    "all_negative", "lag_decisions"):
            assert key in d
