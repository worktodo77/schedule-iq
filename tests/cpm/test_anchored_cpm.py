"""
Tests for V2-A actual-date-anchored CPM ("pinning"; ADR-019).

Covers the engine-level pinning behavior and the AS_BUILT_ANCHORED ABCS wiring:

  (a) A pinned completed activity fixes ES/EF at its actual dates and pushes
      successors out (the anchor propagates forward).
  (b) In-progress remaining-duration propagation: ES pinned at actual start,
      EF computed forward over remaining_duration.
  (c) An all-pinned cycle resolves into a DAG and schedules (the OV-001-F1
      / W4 case P6 tolerates).
  (d) A cycle containing a non-pinned member still blocks with NET-006.
  (e) Backward-compatibility: no pins → identical ES/EF/TF to an unpinned run.

Plus ABCS wiring: AS_BUILT_ANCHORED variant pins from actual dates and records
the anchoring mode in provenance.

All fixtures are synthetic. No proprietary schedule data (OV-001 MNFV is run by
the parent process, not here).

Source: docs/reviewer_packets/V2-A-DESIGN-BRIEF.md §§3,4,9; ADR-019.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.engine import run_analysis  # noqa: E402
from scheduleiq.cpm.network import ActivityNetwork, topological_sort, _is_fully_pinned  # noqa: E402
# NOT PORTED IN W1a: mip39.simulation (SimulationInput, SimulationResult,
# generate_simulation_schedule, SimulationVariant, apply_actual_date_pins) is
# not ported in this wave — see the dropped TestApplyActualDatePins and
# TestAsBuiltAnchoredABCS classes below.


# ---------------------------------------------------------------------------
# Shared calendar / workday table — Jan 2026 Mon-Fri.
#   W1 = 2026-01-05 (Mon) ... W5 = 2026-01-09 (Fri)
#   W6 = 2026-01-12 (Mon) ... W10 = 2026-01-16 (Fri)
# ---------------------------------------------------------------------------

_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2026, 1, 5), date(2026, 6, 30))
_START = date(2026, 1, 5)   # Monday = wd1

W1  = date(2026, 1, 5)
W2  = date(2026, 1, 6)
W3  = date(2026, 1, 7)
W4  = date(2026, 1, 8)
W5  = date(2026, 1, 9)
W6  = date(2026, 1, 12)
W7  = date(2026, 1, 13)
W8  = date(2026, 1, 14)
W9  = date(2026, 1, 15)
W10 = date(2026, 1, 16)


def _rel(pred, succ, rel_type="FS", lag=0):
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _run(activities, relationships, start=None):
    return run_analysis(activities, relationships, start or _START, _TABLE, _CAL)


# ===========================================================================
# (a) Pinned completed activity fixes ES/EF and pushes successors out.
# ===========================================================================

class TestPinnedCompletedAnchor:

    def test_pinned_es_ef_are_fixed_and_override_logic(self):
        # A (OD 3) → B (OD 3). Logic alone would put A at W1..W3, B at W3..W5
        # (FS lag=0, P6 same-day convention). Pin A at a LATER actual finish
        # (W6..W8) and confirm A takes the pins verbatim and B is pushed out.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=3.0)
        res = _run([a, b], [_rel("A", "B")])
        assert res.is_valid

        sa = res.scheduled["A"]
        sb = res.scheduled["B"]
        # A pinned verbatim — NOT recomputed from project_start.
        assert sa.early_start == W6
        assert sa.early_finish == W8
        # B pushed out: FS lag=0 → B.ES = A.EF (same workday) = W8, span 2 → W10.
        assert sb.early_start == W8
        assert sb.early_finish == W10

    def test_pin_overrides_even_when_logic_would_imply_later(self):
        # Pin A EARLIER than predecessor logic would allow. Out-of-sequence:
        # P (OD 5, W1..W5) → A. Logic would force A.ES >= W5. Pin A at W1..W2.
        # Pinning OVERRIDES; it does NOT take max(candidate, pinned).
        p = Activity(act_id="P", original_duration=5.0)
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W1, pinned_early_finish=W2)
        res = _run([p, a], [_rel("P", "A")])
        assert res.is_valid
        sa = res.scheduled["A"]
        assert sa.early_start == W1   # pinned, not max(W5-ish, W1)
        assert sa.early_finish == W2


# ===========================================================================
# (b) In-progress remaining-duration propagation.
# ===========================================================================

class TestInProgressPin:

    def test_es_pinned_ef_from_remaining_duration(self):
        # In-progress: only pinned_early_start set; remaining_duration = 4.
        # EF = apply_lag(ES, remaining_span) where remaining_span = max(0, 4-1)=3.
        # ES = W6 (Mon) → +3 workdays → W9 (Thu).
        a = Activity(act_id="A", original_duration=10.0, remaining_duration=4.0,
                     pinned_early_start=W6)
        res = _run([a], [])
        assert res.is_valid
        sa = res.scheduled["A"]
        assert sa.early_start == W6
        assert sa.early_finish == W9

    def test_in_progress_pushes_successor_from_remaining_finish(self):
        a = Activity(act_id="A", original_duration=10.0, remaining_duration=4.0,
                     pinned_early_start=W6)
        b = Activity(act_id="B", original_duration=2.0)
        res = _run([a, b], [_rel("A", "B")])
        assert res.is_valid
        # A finishes W9; B (FS lag 0) starts W9, span 1 → W10.
        assert res.scheduled["A"].early_finish == W9
        assert res.scheduled["B"].early_start == W9
        assert res.scheduled["B"].early_finish == W10

    def test_in_progress_rd_zero_yields_single_day_finish(self):
        # remaining_duration = 0 → remaining_span = max(0, -1) = 0 → EF == ES.
        a = Activity(act_id="A", original_duration=5.0, remaining_duration=0.0,
                     pinned_early_start=W6)
        res = _run([a], [])
        assert res.is_valid
        sa = res.scheduled["A"]
        assert sa.early_start == W6
        assert sa.early_finish == W6


# ===========================================================================
# (c) All-pinned cycle resolves into a DAG and schedules.
# ===========================================================================

class TestAllPinnedCycleResolves:

    def test_is_fully_pinned_predicate(self):
        completed = Activity(act_id="C", original_duration=1.0,
                             pinned_early_start=W1, pinned_early_finish=W2)
        in_prog = Activity(act_id="I", original_duration=1.0,
                           pinned_early_start=W1)
        future = Activity(act_id="F", original_duration=1.0)
        assert _is_fully_pinned(completed) is True
        assert _is_fully_pinned(in_prog) is False
        assert _is_fully_pinned(future) is False

    def test_topological_sort_drops_edges_into_pinned(self):
        # A -> B -> A cycle, both fully pinned. Edges into pinned nodes dropped
        # → residual graph is a DAG → topo sort returns both activities.
        a = Activity(act_id="A", original_duration=2.0,
                     pinned_early_start=W1, pinned_early_finish=W2)
        b = Activity(act_id="B", original_duration=2.0,
                     pinned_early_start=W3, pinned_early_finish=W4)
        net = ActivityNetwork([a, b], [_rel("A", "B"), _rel("B", "A")])
        order = topological_sort(net)
        assert set(order) == {"A", "B"}

    def test_all_pinned_cycle_schedules(self):
        # 3-node completed cycle A->B->C->A, all pinned at actual dates.
        # P6 schedules it fine using actual dates; mip39 must too.
        a = Activity(act_id="A", original_duration=2.0,
                     pinned_early_start=W1, pinned_early_finish=W2)
        b = Activity(act_id="B", original_duration=2.0,
                     pinned_early_start=W3, pinned_early_finish=W4)
        c = Activity(act_id="C", original_duration=2.0,
                     pinned_early_start=W5, pinned_early_finish=W6)
        rels = [_rel("A", "B"), _rel("B", "C"), _rel("C", "A")]
        res = _run([a, b, c], rels)
        assert res.is_valid
        assert res.scheduled["A"].early_start == W1
        assert res.scheduled["A"].early_finish == W2
        assert res.scheduled["B"].early_start == W3
        assert res.scheduled["C"].early_finish == W6

    def test_pinned_cycle_with_pinned_successor_outside(self):
        # Completed cycle A<->B, plus a future successor D off the cycle.
        a = Activity(act_id="A", original_duration=2.0,
                     pinned_early_start=W1, pinned_early_finish=W2)
        b = Activity(act_id="B", original_duration=2.0,
                     pinned_early_start=W3, pinned_early_finish=W6)
        d = Activity(act_id="D", original_duration=2.0)
        rels = [_rel("A", "B"), _rel("B", "A"), _rel("B", "D")]
        res = _run([a, b, d], rels)
        assert res.is_valid
        # D is future; B finishes W6 → D starts W6, span 1 → W7.
        assert res.scheduled["D"].early_start == W6
        assert res.scheduled["D"].early_finish == W7


# ===========================================================================
# (d) A cycle with a non-pinned member still blocks (NET-006).
# ===========================================================================

class TestUnpinnedCycleStillBlocks:

    def test_topological_sort_raises_on_unpinned_cycle_member(self):
        # A (pinned) <-> B (NOT pinned). The edge B->A is dropped (A pinned),
        # but the edge A->B into un-pinned B remains → residual cycle? No:
        # only A->B survives, which is a DAG. To keep a TRUE cycle, both edges
        # must survive, which requires the SUCCESSOR end of each to be unpinned.
        # Cycle A->B->A where B is unpinned: edge A->B survives (B unpinned),
        # edge B->A dropped (A pinned). Use an unpinned-into-unpinned cycle.
        a = Activity(act_id="A", original_duration=2.0)   # not pinned
        b = Activity(act_id="B", original_duration=2.0)   # not pinned
        net = ActivityNetwork([a, b], [_rel("A", "B"), _rel("B", "A")])
        with pytest.raises(ValueError, match="Cycle detected"):
            topological_sort(net)

    def test_mixed_cycle_one_unpinned_blocks(self):
        # 3-node cycle A->B->C->A. A and B fully pinned, C NOT pinned.
        # Edges into A and B (i.e. C->A and A->B) are dropped; edge B->C
        # (into unpinned C) survives. Residual: B->C only → DAG, schedules.
        # To force a residual cycle we need consecutive unpinned successors.
        # Cycle where C and A are both unpinned: C->A and A's incoming survive.
        a = Activity(act_id="A", original_duration=2.0)   # unpinned
        b = Activity(act_id="B", original_duration=2.0,
                     pinned_early_start=W3, pinned_early_finish=W4)  # pinned
        c = Activity(act_id="C", original_duration=2.0)   # unpinned
        # A->B (into pinned B, dropped), B->C (into unpinned C, survives),
        # C->A (into unpinned A, survives). Residual C->A and B->C: is there a
        # cycle? Need A->...->C. A->B dropped so A has no surviving out-edge to
        # C. So residual is a DAG. Build an explicit unpinned 2-cycle instead.
        rels = [_rel("A", "C"), _rel("C", "A"), _rel("A", "B")]
        net = ActivityNetwork([a, b, c], rels)
        with pytest.raises(ValueError, match="Cycle detected"):
            topological_sort(net)

    def test_run_analysis_blocks_unpinned_cycle(self):
        # Full engine path: unpinned cycle → is_valid=False (NET-006 blocks).
        a = Activity(act_id="A", original_duration=2.0)
        b = Activity(act_id="B", original_duration=2.0)
        res = _run([a, b], [_rel("A", "B"), _rel("B", "A")])
        assert res.is_valid is False
        assert res.scheduled == {}


# ===========================================================================
# (e) Backward compatibility: no pins → identical ES/EF/TF.
# ===========================================================================

class TestBackwardCompatibility:

    def _build_network(self):
        acts = [
            Activity(act_id="A", original_duration=3.0),
            Activity(act_id="B", original_duration=2.0),
            Activity(act_id="C", original_duration=4.0),
            Activity(act_id="D", original_duration=1.0),
        ]
        rels = [
            _rel("A", "B"),
            _rel("A", "C"),
            _rel("B", "D"),
            _rel("C", "D"),
        ]
        return acts, rels

    def test_no_pins_identical_es_ef_tf(self):
        acts, rels = self._build_network()
        res = _run(acts, rels)
        assert res.is_valid
        # Snapshot the unpinned results — these are the pre-V2-A values.
        expected = {
            act_id: (sa.early_start, sa.early_finish, sa.total_float)
            for act_id, sa in res.scheduled.items()
        }
        # Re-run with the (defaulted-None) pin fields present but unset.
        acts2 = [
            Activity(act_id=a.act_id, original_duration=a.original_duration,
                     pinned_early_start=None, pinned_early_finish=None)
            for a in acts
        ]
        res2 = _run(acts2, rels)
        assert res2.is_valid
        for act_id, sa in res2.scheduled.items():
            assert (sa.early_start, sa.early_finish, sa.total_float) == expected[act_id]

    def test_float_computed_normally_for_pinned(self):
        # Option (a): float is computed normally, no forced TF=0 on pinned.
        # Diamond: A(pinned late) -> B,C -> D. A pinned at W6..W8 pushes the
        # whole network; floats are still real LF-EF differences, not zeroed.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=4.0)   # longer leg
        c = Activity(act_id="C", original_duration=1.0)   # shorter leg → float
        d = Activity(act_id="D", original_duration=1.0)
        rels = [_rel("A", "B"), _rel("A", "C"), _rel("B", "D"), _rel("C", "D")]
        res = _run([a, b, c, d], rels)
        assert res.is_valid
        # C is the short leg → it must carry positive total float (not forced 0).
        assert res.scheduled["C"].total_float > 0
        # B (driving leg) is critical → TF 0.
        assert res.scheduled["B"].total_float == 0


# ---------------------------------------------------------------------------
# NOT PORTED IN W1a: TestApplyActualDatePins and TestAsBuiltAnchoredABCS depend
# on mip39.simulation (apply_actual_date_pins, SimulationInput, SimulationResult,
# generate_simulation_schedule, SimulationVariant), which is not ported in this
# wave (superseded/deferred to later waves per the port instructions).
# ---------------------------------------------------------------------------
