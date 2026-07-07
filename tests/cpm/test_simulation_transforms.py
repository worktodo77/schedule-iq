"""
Tests for src/mip39/simulation/transforms.py.

Covers prepare_activities_for_cpm() and prepare_relationships_for_variant().
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date
from unittest.mock import MagicMock

from scheduleiq.cpm.transforms import (  # noqa: E402
    prepare_activities_for_cpm,
    prepare_relationships_for_variant,
)
from scheduleiq.cpm.models import Activity, Relationship  # noqa: E402
from scheduleiq.cpm.destatusing.rules import DestatusingRule, RuleAssignment  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assignment(act_id: str, rule: DestatusingRule) -> RuleAssignment:
    return RuleAssignment(act_id=act_id, rule=rule, reason="test")


def _act(act_id: str, od: float, rd: float = None) -> Activity:
    a = Activity(act_id=act_id, original_duration=od)
    if rd is not None:
        a.remaining_duration = rd
    return a


def _rel(pred: str, succ: str, lag: float = 0.0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="FS", lag=lag)


# ---------------------------------------------------------------------------
# prepare_activities_for_cpm — passthrough rules
# ---------------------------------------------------------------------------

class TestPrepareActivitiesPassthrough:

    def test_rule_a_preserves_original_duration(self):
        act = _act("A", od=10)
        assignments = {"A": _assignment("A", DestatusingRule.A)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 10

    def test_rule_b_preserves_original_duration(self):
        act = _act("B", od=5)
        assignments = {"B": _assignment("B", DestatusingRule.B)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 5

    def test_rule_c_preserves_original_duration(self):
        act = _act("C", od=7)
        assignments = {"C": _assignment("C", DestatusingRule.C)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 7

    def test_rule_e_preserves_original_duration(self):
        act = _act("E", od=8)
        assignments = {"E": _assignment("E", DestatusingRule.E)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 8

    def test_no_match_passthrough(self):
        act = _act("X", od=3)
        assignments = {"X": _assignment("X", DestatusingRule.NO_MATCH)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 3

    def test_not_in_scope_passthrough(self):
        act = _act("Y", od=4)
        assignments = {"Y": _assignment("Y", DestatusingRule.NOT_IN_SCOPE)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 4

    def test_no_assignment_passthrough(self):
        act = _act("Z", od=6)
        result = prepare_activities_for_cpm([act], {})
        assert result[0].original_duration == 6


# ---------------------------------------------------------------------------
# prepare_activities_for_cpm — Rule D duration substitution
# ---------------------------------------------------------------------------

class TestPrepareActivitiesRuleD:

    def test_rule_d_substitutes_remaining_duration(self):
        act = _act("D1", od=10, rd=4)
        assignments = {"D1": _assignment("D1", DestatusingRule.D)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 4

    def test_rule_d_converts_float_rd_to_int(self):
        act = _act("D2", od=10, rd=3.7)
        assignments = {"D2": _assignment("D2", DestatusingRule.D)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 3
        assert isinstance(result[0].original_duration, int)

    def test_rule_d_none_rd_becomes_zero(self):
        act = _act("D3", od=10)  # remaining_duration is None
        assignments = {"D3": _assignment("D3", DestatusingRule.D)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 0

    def test_rule_d_preserves_other_fields(self):
        act = _act("D4", od=10, rd=5)
        act.actual_start = date(2026, 1, 5)
        assignments = {"D4": _assignment("D4", DestatusingRule.D)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].act_id == "D4"
        assert result[0].actual_start == date(2026, 1, 5)


# ---------------------------------------------------------------------------
# prepare_activities_for_cpm — Rule F duration substitution
# ---------------------------------------------------------------------------

class TestPrepareActivitiesRuleF:

    def test_rule_f_substitutes_remaining_duration(self):
        act = _act("F1", od=15, rd=6)
        assignments = {"F1": _assignment("F1", DestatusingRule.F)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 6

    def test_rule_f_converts_float_rd_to_int(self):
        act = _act("F2", od=15, rd=5.9)
        assignments = {"F2": _assignment("F2", DestatusingRule.F)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 5

    def test_rule_f_none_rd_becomes_zero(self):
        act = _act("F3", od=15)  # remaining_duration is None
        assignments = {"F3": _assignment("F3", DestatusingRule.F)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0].original_duration == 0


# ---------------------------------------------------------------------------
# prepare_activities_for_cpm — mutation and ordering
# ---------------------------------------------------------------------------

class TestPrepareActivitiesMutation:

    def test_returns_copies_not_same_objects(self):
        act = _act("A", od=5, rd=2)
        assignments = {"A": _assignment("A", DestatusingRule.D)}
        result = prepare_activities_for_cpm([act], assignments)
        assert result[0] is not act

    def test_does_not_mutate_original(self):
        act = _act("A", od=5, rd=2)
        assignments = {"A": _assignment("A", DestatusingRule.D)}
        prepare_activities_for_cpm([act], assignments)
        assert act.original_duration == 5  # unchanged

    def test_preserves_order(self):
        acts = [_act("A", od=1), _act("B", od=2), _act("C", od=3)]
        result = prepare_activities_for_cpm(acts, {})
        assert [r.act_id for r in result] == ["A", "B", "C"]

    def test_empty_input_returns_empty(self):
        result = prepare_activities_for_cpm([], {})
        assert result == []

    def test_mixed_rules(self):
        acts = [
            _act("A", od=10),        # Rule A — passthrough
            _act("D", od=10, rd=4),  # Rule D — substitute
            _act("C", od=7),         # Rule C — passthrough
        ]
        assignments = {
            "A": _assignment("A", DestatusingRule.A),
            "D": _assignment("D", DestatusingRule.D),
            "C": _assignment("C", DestatusingRule.C),
        }
        result = prepare_activities_for_cpm(acts, assignments)
        assert result[0].original_duration == 10
        assert result[1].original_duration == 4
        assert result[2].original_duration == 7


# ---------------------------------------------------------------------------
# prepare_relationships_for_variant — BASELINE (copy-through)
# ---------------------------------------------------------------------------

class TestPrepareRelationshipsBaseline:

    def test_returns_copies_of_original(self):
        rels = [_rel("A", "B", lag=2.0)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=None,
            use_actual_lags=False,
            use_autodrive=False,
        )
        assert len(result) == 1
        assert result[0] is not rels[0]
        assert result[0].lag == 2.0

    def test_empty_relationships_returns_empty(self):
        result = prepare_relationships_for_variant(
            relationships=[],
            lag_results=None,
            use_actual_lags=False,
            use_autodrive=False,
        )
        assert result == []

    def test_preserves_rel_type_and_ids(self):
        rels = [Relationship(pred_id="X", succ_id="Y", rel_type="SS", lag=1.0)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=None,
            use_actual_lags=False,
            use_autodrive=False,
        )
        assert result[0].pred_id == "X"
        assert result[0].succ_id == "Y"
        assert result[0].rel_type == "SS"


# ---------------------------------------------------------------------------
# prepare_relationships_for_variant — AUTO_DRIVEN
# ---------------------------------------------------------------------------

class TestPrepareRelationshipsAutodrive:

    def test_returns_autodrive_relationships(self):
        original = [_rel("A", "B", lag=0.0)]
        autodrive = [_rel("A", "B", lag=3.0)]
        result = prepare_relationships_for_variant(
            relationships=original,
            lag_results=None,
            use_actual_lags=False,
            use_autodrive=True,
            autodrive_relationships=autodrive,
        )
        assert len(result) == 1
        assert result[0].lag == 3.0

    def test_autodrive_result_is_copy_not_same_list(self):
        autodrive = [_rel("A", "B", lag=3.0)]
        result = prepare_relationships_for_variant(
            relationships=[],
            lag_results=None,
            use_actual_lags=False,
            use_autodrive=True,
            autodrive_relationships=autodrive,
        )
        assert result is not autodrive

    def test_autodrive_none_falls_through_to_baseline(self):
        rels = [_rel("A", "B", lag=2.0)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=None,
            use_actual_lags=False,
            use_autodrive=True,
            autodrive_relationships=None,
        )
        # No autodrive rels available → falls through to baseline copy
        assert len(result) == 1
        assert result[0].lag == 2.0


# ---------------------------------------------------------------------------
# prepare_relationships_for_variant — LAG_ADJUSTED
# ---------------------------------------------------------------------------

class TestPrepareRelationshipsLagAdjusted:

    def _mock_lag_result(self, pred_id, succ_id, rel_type, actual_lag):
        lr = MagicMock()
        lr.pred_id = pred_id
        lr.succ_id = succ_id
        lr.rel_type = rel_type
        lr.actual_lag = actual_lag
        return lr

    def test_applies_actual_lag_when_available(self):
        rels = [_rel("A", "B", lag=0.0)]
        lag_results = [self._mock_lag_result("A", "B", "FS", 5.0)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=lag_results,
            use_actual_lags=True,
            use_autodrive=False,
        )
        assert result[0].lag == 5.0

    def test_preserves_planned_lag_when_no_actual(self):
        rels = [_rel("A", "B", lag=2.0)]
        lag_results = [self._mock_lag_result("A", "B", "FS", None)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=lag_results,
            use_actual_lags=True,
            use_autodrive=False,
        )
        assert result[0].lag == 2.0

    def test_mixed_lag_and_no_lag(self):
        rels = [_rel("A", "B", lag=1.0), _rel("B", "C", lag=1.0)]
        lag_results = [
            self._mock_lag_result("A", "B", "FS", 4.0),
            self._mock_lag_result("B", "C", "FS", None),
        ]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=lag_results,
            use_actual_lags=True,
            use_autodrive=False,
        )
        assert result[0].lag == 4.0
        assert result[1].lag == 1.0

    def test_lag_results_none_falls_through_to_copy(self):
        rels = [_rel("A", "B", lag=3.0)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=None,
            use_actual_lags=True,
            use_autodrive=False,
        )
        assert result[0].lag == 3.0

    def test_returns_copies_not_originals(self):
        rels = [_rel("A", "B", lag=1.0)]
        lag_results = [self._mock_lag_result("A", "B", "FS", 5.0)]
        result = prepare_relationships_for_variant(
            relationships=rels,
            lag_results=lag_results,
            use_actual_lags=True,
            use_autodrive=False,
        )
        assert result[0] is not rels[0]
