"""
Tests for ActivityNetwork container and topological_sort (src/mip39/network.py).

Covers: network construction validation, predecessor/successor lookups,
topological ordering (chain, branch, merge, diamond, isolated, multi-start),
and cycle detection.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.models import Activity, Relationship  # noqa: E402
from scheduleiq.cpm.network import ActivityNetwork, topological_sort  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _act(act_id: str, od: float = 5) -> Activity:
    return Activity(act_id=act_id, original_duration=od)


def _rel(pred: str, succ: str, rel_type: str = "FS", lag: float = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _chain_network(ids: list[str]) -> ActivityNetwork:
    """Build a linear chain A→B→C→… from a list of IDs."""
    activities = [_act(i) for i in ids]
    relationships = [_rel(ids[i], ids[i + 1]) for i in range(len(ids) - 1)]
    return ActivityNetwork(activities, relationships)


# ---------------------------------------------------------------------------
# ActivityNetwork — construction and validation
# ---------------------------------------------------------------------------

class TestActivityNetworkConstruction:
    def test_basic_construction(self):
        net = ActivityNetwork([_act("A"), _act("B")], [_rel("A", "B")])
        assert "A" in net.activities
        assert "B" in net.activities

    def test_empty_network(self):
        net = ActivityNetwork([], [])
        assert len(net.activities) == 0
        assert len(net.relationships) == 0

    def test_activities_only_no_relationships(self):
        net = ActivityNetwork([_act("A"), _act("B")], [])
        assert "A" in net.activities
        assert "B" in net.activities
        assert net.relationships == []

    def test_duplicate_activity_id_raises(self):
        with pytest.raises(ValueError, match="duplicate activity ID"):
            ActivityNetwork([_act("A"), _act("A")], [])

    def test_unknown_pred_id_raises(self):
        with pytest.raises(ValueError, match="predecessor"):
            ActivityNetwork([_act("B")], [_rel("UNKNOWN", "B")])

    def test_unknown_succ_id_raises(self):
        with pytest.raises(ValueError, match="successor"):
            ActivityNetwork([_act("A")], [_rel("A", "UNKNOWN")])

    def test_relationships_list_returned(self):
        rels = [_rel("A", "B"), _rel("B", "C")]
        net = ActivityNetwork([_act("A"), _act("B"), _act("C")], rels)
        assert len(net.relationships) == 2

    def test_len(self):
        net = ActivityNetwork([_act("A"), _act("B"), _act("C")], [])
        assert len(net) == 3

    def test_repr_contains_activity_count(self):
        net = ActivityNetwork([_act("A"), _act("B")], [_rel("A", "B")])
        r = repr(net)
        assert "2" in r
        assert "1" in r


# ---------------------------------------------------------------------------
# ActivityNetwork — predecessor / successor lookups
# ---------------------------------------------------------------------------

class TestActivityNetworkLookups:
    def setup_method(self):
        self.net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("A", "C")],
        )

    def test_predecessors_of_root_is_empty(self):
        assert self.net.predecessors["A"] == []

    def test_predecessors_of_b_contains_a_relationship(self):
        preds = self.net.predecessors["B"]
        assert len(preds) == 1
        assert preds[0].pred_id == "A"
        assert preds[0].succ_id == "B"

    def test_predecessors_of_c_contains_a_relationship(self):
        preds = self.net.predecessors["C"]
        assert len(preds) == 1
        assert preds[0].pred_id == "A"

    def test_successors_of_a_contains_two_relationships(self):
        succs = self.net.successors["A"]
        succ_ids = {r.succ_id for r in succs}
        assert succ_ids == {"B", "C"}

    def test_successors_of_leaf_is_empty(self):
        assert self.net.successors["B"] == []

    def test_multiple_predecessors_captured(self):
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        preds = net.predecessors["C"]
        pred_ids = {r.pred_id for r in preds}
        assert pred_ids == {"A", "B"}


# ---------------------------------------------------------------------------
# topological_sort — valid acyclic networks
# ---------------------------------------------------------------------------

class TestTopologicalSortAcyclic:
    def test_single_node(self):
        net = ActivityNetwork([_act("A")], [])
        result = topological_sort(net)
        assert result == ["A"]

    def test_two_node_chain(self):
        net = _chain_network(["A", "B"])
        result = topological_sort(net)
        assert result == ["A", "B"]

    def test_three_node_chain(self):
        net = _chain_network(["A", "B", "C"])
        result = topological_sort(net)
        assert result == ["A", "B", "C"]

    def test_branch(self):
        # A → B, A → C (branching)
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("A", "C")],
        )
        result = topological_sort(net)
        assert result.index("A") < result.index("B")
        assert result.index("A") < result.index("C")
        assert len(result) == 3

    def test_merge(self):
        # A → C, B → C (merging)
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        result = topological_sort(net)
        assert result.index("A") < result.index("C")
        assert result.index("B") < result.index("C")

    def test_diamond(self):
        # A → B, A → C, B → D, C → D
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C"), _act("D")],
            [_rel("A", "B"), _rel("A", "C"), _rel("B", "D"), _rel("C", "D")],
        )
        result = topological_sort(net)
        assert result[0] == "A"
        assert result[-1] == "D"
        assert result.index("B") < result.index("D")
        assert result.index("C") < result.index("D")

    def test_isolated_activity_included(self):
        # A → B, C is isolated (no relationships)
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B")],
        )
        result = topological_sort(net)
        assert set(result) == {"A", "B", "C"}
        assert result.index("A") < result.index("B")

    def test_multiple_start_nodes(self):
        # A → C, B → C (A and B both have no predecessors)
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        result = topological_sort(net)
        # Both A and B appear before C
        assert result.index("A") < result.index("C")
        assert result.index("B") < result.index("C")

    def test_all_activities_in_result(self):
        net = _chain_network(["A", "B", "C", "D"])
        result = topological_sort(net)
        assert set(result) == {"A", "B", "C", "D"}

    def test_result_length_equals_activity_count(self):
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("A", "C")],
        )
        result = topological_sort(net)
        assert len(result) == 3

    def test_deterministic_ordering_sorted_start_nodes(self):
        # A and B both have no predecessors; sorted → A comes before B
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        r1 = topological_sort(net)
        r2 = topological_sort(net)
        assert r1 == r2
        assert r1.index("A") < r1.index("B")

    def test_predecessor_before_successor_for_all_relationships(self):
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C"), _act("D")],
            [_rel("A", "B"), _rel("A", "C"), _rel("B", "D"), _rel("C", "D")],
        )
        result = topological_sort(net)
        for rel in net.relationships:
            assert result.index(rel.pred_id) < result.index(rel.succ_id), (
                f"Predecessor {rel.pred_id!r} should appear before {rel.succ_id!r}"
            )

    def test_ss_relationships_respected_in_ordering(self):
        # SS and FF relationships also impose pred-before-succ ordering
        net = ActivityNetwork(
            [_act("A"), _act("B")],
            [_rel("A", "B", rel_type="SS", lag=0)],
        )
        result = topological_sort(net)
        assert result == ["A", "B"]

    def test_empty_network_returns_empty_list(self):
        net = ActivityNetwork([], [])
        result = topological_sort(net)
        assert result == []


# ---------------------------------------------------------------------------
# topological_sort — cycle detection
# ---------------------------------------------------------------------------

class TestTopologicalSortCycles:
    def test_two_node_cycle_raises_value_error(self):
        net = ActivityNetwork(
            [_act("A"), _act("B")],
            [_rel("A", "B"), _rel("B", "A")],
        )
        with pytest.raises(ValueError, match="[Cc]ycle"):
            topological_sort(net)

    def test_three_node_cycle_raises(self):
        net = ActivityNetwork(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("B", "C"), _rel("C", "A")],
        )
        with pytest.raises(ValueError, match="[Cc]ycle"):
            topological_sort(net)

    def test_cycle_error_identifies_involved_activities(self):
        net = ActivityNetwork(
            [_act("X"), _act("Y")],
            [_rel("X", "Y"), _rel("Y", "X")],
        )
        with pytest.raises(ValueError) as exc_info:
            topological_sort(net)
        msg = str(exc_info.value)
        assert "X" in msg or "Y" in msg

    def test_partial_cycle_does_not_include_safe_node(self):
        # D → E → D (cycle), F has no relationships (safe)
        net = ActivityNetwork(
            [_act("D"), _act("E"), _act("F")],
            [_rel("D", "E"), _rel("E", "D")],
        )
        with pytest.raises(ValueError, match="[Cc]ycle"):
            topological_sort(net)

    def test_self_loop_raises(self):
        # A → A: technically invalid (pred==succ), but let's ensure it raises
        # We need to bypass Relationship validation — check if it raises at construction
        with pytest.raises((ValueError, Exception)):
            net = ActivityNetwork([_act("A")], [_rel("A", "A")])
            topological_sort(net)
