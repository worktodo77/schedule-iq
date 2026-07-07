"""
Tests for the Progress Override statusing mode (net-new; the ported source
implements Retained Logic only, per ADR-002).

Under RETAINED_LOGIC (default) the pinning mechanism makes an unstarted
successor of an incomplete predecessor WAIT for the predecessor's remaining
work. Under PROGRESS_OVERRIDE, the retained-logic tie from a STARTED-but-
INCOMPLETE (in-progress) predecessor is DROPPED — the successor may proceed at
the data date as if the incomplete predecessor did not restrain it.

Expected dates are hand-derived from the day-granularity P6 scheduling reference
behavior (a documented approximation — a P6-compatible analytical convention,
NOT exact P6 emulation; ADR-006).

Workday reference (Mon-Fri):
  W1 = 2026-01-05 (Mon) ... W5 = 2026-01-09 (Fri)
  W6 = 2026-01-12 (Mon) ... W10 = 2026-01-16 (Fri)  W11 = 2026-01-19 (Mon)

All fixtures are synthetic. No proprietary schedule data.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.engine import run_analysis  # noqa: E402
from scheduleiq.cpm.constraints import StatusingMode  # noqa: E402


_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2025, 12, 1), date(2026, 6, 30))
_START = date(2026, 1, 5)   # Monday = data date

W1  = date(2026, 1, 5)
W2  = date(2026, 1, 6)
W6  = date(2026, 1, 12)
W8  = date(2026, 1, 14)
W9  = date(2026, 1, 15)
W10 = date(2026, 1, 16)
W11 = date(2026, 1, 19)


def _act(act_id, od):
    return Activity(act_id=act_id, original_duration=float(od))


def _rel(pred, succ, rel_type="FS", lag=0):
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _run(acts, rels, mode=StatusingMode.RETAINED_LOGIC):
    return run_analysis(acts, rels, _START, _TABLE, _CAL, statusing_mode=mode)


def _in_progress_pred_network():
    # P: in-progress (actual start pinned W6, remaining_duration 5 -> EF = W6 + 4
    # workdays = W10). S: unstarted FS successor (OD 2).
    p = Activity(act_id="P", original_duration=10.0, remaining_duration=5.0,
                 pinned_early_start=W6)
    s = _act("S", 2)
    return [p, s], [_rel("P", "S")]


# ===========================================================================
# Out-of-sequence: in-progress predecessor, unstarted FS successor.
# ===========================================================================

class TestInProgressPredecessor:

    def test_retained_logic_successor_waits_for_remaining(self):
        # Default: S waits for P's remaining finish (W10). S.ES=W10, EF=W11.
        acts, rels = _in_progress_pred_network()
        r = _run(acts, rels)   # default RETAINED_LOGIC
        assert r.scheduled["P"].early_finish == W10
        assert r.scheduled["S"].early_start == W10
        assert r.scheduled["S"].early_finish == W11

    def test_progress_override_successor_starts_at_data_date(self):
        # PROGRESS_OVERRIDE: the retained-logic tie from in-progress P is dropped;
        # S floors at the data date (project_start W1). S.ES=W1, EF=W2.
        acts, rels = _in_progress_pred_network()
        r = _run(acts, rels, mode=StatusingMode.PROGRESS_OVERRIDE)
        assert r.scheduled["P"].early_finish == W10   # P itself is unchanged
        assert r.scheduled["S"].early_start == W1
        assert r.scheduled["S"].early_finish == W2

    def test_progress_override_flag_recorded_with_count(self):
        acts, rels = _in_progress_pred_network()
        r = _run(acts, rels, mode=StatusingMode.PROGRESS_OVERRIDE)
        flags = [f for f in r.context.interpretation_flags if "Progress Override" in f]
        assert len(flags) == 1
        assert "1 relationship(s)" in flags[0]

    def test_retained_logic_records_no_override_flag(self):
        acts, rels = _in_progress_pred_network()
        r = _run(acts, rels)
        assert not any("Progress Override" in f for f in r.context.interpretation_flags)


# ===========================================================================
# Backward-pass symmetry + free-float consistency.
# ===========================================================================

class TestBackwardSymmetryAndFloat:

    def test_backward_pass_symmetry_pred_unconstrained_by_overridden_succ(self):
        # Under PROGRESS_OVERRIDE the in-progress predecessor's overridden
        # successor relationship imposes no late-date constraint on it: P behaves
        # like a finish node -> P.LF == project_finish.
        acts, rels = _in_progress_pred_network()
        po = _run(acts, rels, mode=StatusingMode.PROGRESS_OVERRIDE)
        assert po.scheduled["P"].late_finish == po.project_finish
        # Contrast: under RETAINED_LOGIC the successor DOES constrain P, so P.LF
        # is pulled earlier than the (later) project finish.
        rl = _run(*_in_progress_pred_network())
        assert rl.scheduled["P"].late_finish < rl.project_finish

    def test_free_float_consistency_override_drops_contribution(self):
        # The dropped relationship is skipped for free float too: an in-progress
        # predecessor whose only successor tie is overridden has FF == TF.
        acts, rels = _in_progress_pred_network()
        po = _run(acts, rels, mode=StatusingMode.PROGRESS_OVERRIDE)
        sp = po.scheduled["P"]
        assert sp.free_float == sp.total_float


# ===========================================================================
# Completed and unstarted predecessors behave identically in both modes.
# ===========================================================================

class TestUnaffectedPredecessors:

    def test_completed_predecessor_unchanged_in_both_modes(self):
        # C completed (fully pinned W6..W8). Successor S waits for C.EF=W8 in both
        # modes (Progress Override only drops IN-PROGRESS ties, not completed).
        def net():
            c = Activity(act_id="C", original_duration=3.0,
                         pinned_early_start=W6, pinned_early_finish=W8)
            return [c, _act("S", 2)], [_rel("C", "S")]
        rl = _run(*net())
        po = _run(*net(), mode=StatusingMode.PROGRESS_OVERRIDE)
        assert rl.scheduled["S"].early_start == W8
        assert po.scheduled["S"].early_start == W8

    def test_unstarted_predecessor_unchanged_in_both_modes(self):
        # No pins at all: pure logic network A(3)->B(2). Identical in both modes.
        def net():
            return [_act("A", 3), _act("B", 2)], [_rel("A", "B")]
        rl = _run(*net())
        po = _run(*net(), mode=StatusingMode.PROGRESS_OVERRIDE)
        assert rl.scheduled["B"].early_start == po.scheduled["B"].early_start
        assert rl.to_dict()["scheduled"] == po.to_dict()["scheduled"]


# ===========================================================================
# RETAINED_LOGIC regression guard: default vs explicit RL are bit-identical,
# and match an existing anchored-CPM scenario.
# ===========================================================================

class TestRetainedLogicRegression:

    def _anchored_scenario(self):
        # Mirrors tests/cpm/test_anchored_cpm_edges.py mixed chain: a completed
        # predecessor, an in-progress activity, and an unstarted activity feeding
        # a finish milestone.
        comp = Activity(act_id="COMP", original_duration=3.0,
                        pinned_early_start=W6, pinned_early_finish=W8)
        inpr = Activity(act_id="INPR", original_duration=10.0,
                        remaining_duration=5.0, pinned_early_start=W6)
        ns = _act("NS", 2)
        fin = _act("FIN", 0)
        rels = [
            _rel("COMP", "NS"), _rel("COMP", "FIN"),
            _rel("INPR", "FIN"), _rel("NS", "FIN"),
        ]
        return [comp, inpr, ns, fin], rels

    def test_default_equals_explicit_retained_logic(self):
        acts1, rels = self._anchored_scenario()
        acts2, _ = self._anchored_scenario()
        default = run_analysis(acts1, rels, _START, _TABLE, _CAL)  # no statusing arg
        explicit = run_analysis(
            acts2, rels, _START, _TABLE, _CAL,
            statusing_mode=StatusingMode.RETAINED_LOGIC,
        )
        assert default.to_dict()["scheduled"] == explicit.to_dict()["scheduled"]
        assert default.to_dict()["critical_path"] == explicit.to_dict()["critical_path"]

    def test_retained_logic_matches_known_anchored_dates(self):
        # Same expected dates as test_anchored_cpm_edges: COMP.EF=W8,
        # INPR.EF=W10, NS.EF=W9, FIN = max = W10.
        acts, rels = self._anchored_scenario()
        r = run_analysis(acts, rels, _START, _TABLE, _CAL)
        assert r.scheduled["COMP"].early_finish == W8
        assert r.scheduled["INPR"].early_finish == W10
        assert r.scheduled["NS"].early_finish == W9
        assert r.scheduled["FIN"].early_finish == W10
