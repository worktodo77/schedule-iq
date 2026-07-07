"""
Edge-case tests for V2-A actual-date-anchored CPM ("pinning"; ADR-019).

Complements tests/test_anchored_cpm.py with cases that exercise the pinned-date
PROPAGATION paths under each PDM relationship type, multi-activity in-progress
fan-in, mixed completed/in-progress/not-started chains feeding a finish
milestone, and the not-started-after-completed data-date floor.

Two layers are covered:

  (1) Engine-level pinning via run_analysis() with pins assigned directly on the
      Activity objects (INCLUSIVE_DAY convention — the existing test_anchored_cpm
      _run helper convention). These verify the forward-pass propagation math for
      FS / SS / FF / SF when the predecessor is fully pinned (completed).

  (2) AS_BUILT_ANCHORED ABCS wiring via generate_simulation_schedule(), which
      auto-promotes INCLUSIVE_DAY → P6_COMPATIBILITY (FS successor starts the
      NEXT workday). These verify the as-built (CPW/P6-equivalent) propagation
      that analysts actually run.

All fixtures are synthetic. No proprietary schedule data.

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
# NOT PORTED IN W1a: mip39.simulation (SimulationInput, SimulationResult,
# generate_simulation_schedule, SimulationVariant) is not ported in this wave —
# see the dropped _anchored_sim() helper and the tests/classes that used it
# below (TestAnchoredABCSRelationshipPropagation and every test whose name
# involves "anchored"/"abcs").


# ---------------------------------------------------------------------------
# Shared calendar / workday table — Jan 2026 Mon-Fri (same as test_anchored_cpm).
#   W1 = 2026-01-05 (Mon) ... W5 = 2026-01-09 (Fri)
#   W6 = 2026-01-12 (Mon) ... W10 = 2026-01-16 (Fri)
#   W11 = 2026-01-19 (Mon) ... W15 = 2026-01-23 (Fri)
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
W11 = date(2026, 1, 19)
W12 = date(2026, 1, 20)
W13 = date(2026, 1, 21)
W14 = date(2026, 1, 22)
W15 = date(2026, 1, 23)


def _rel(pred, succ, rel_type="FS", lag=0):
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _run(activities, relationships, start=None):
    """Engine-level run (INCLUSIVE_DAY; same convention as test_anchored_cpm)."""
    return run_analysis(activities, relationships, start or _START, _TABLE, _CAL)


# NOT PORTED IN W1a: _anchored_sim() (AS_BUILT_ANCHORED ABCS run) depended on
# mip39.simulation, which is not ported in this wave. Every test that called
# it is dropped below (see individual "NOT PORTED IN W1a" comments).


# ===========================================================================
# (1) Engine-level: a completed (fully-pinned) predecessor drives a successor
#     under each PDM relationship type. Pins propagate through the unchanged
#     predecessor loop (INCLUSIVE_DAY convention; FS offset 0).
# ===========================================================================

class TestPinnedCompletedPredecessorPropagation:

    def test_completed_pred_drives_fs_successor(self):
        # A completed W6..W8 (3 wd). B is FS successor (OD 2).
        # FS lag=0, INCLUSIVE_DAY: B.ES = A.EF = W8; span 1 → B.EF = W9.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=2.0)
        res = _run([a, b], [_rel("A", "B", "FS")])
        assert res.is_valid
        assert res.scheduled["A"].early_start == W6
        assert res.scheduled["A"].early_finish == W8
        assert res.scheduled["B"].early_start == W8
        assert res.scheduled["B"].early_finish == W9

    def test_completed_pred_drives_ff_successor(self):
        # FF lag=0: B.EF = A.EF = W8. B OD 3 → span 2 → B.ES = W8 - 2 wd = W6.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=3.0)
        res = _run([a, b], [_rel("A", "B", "FF")])
        assert res.is_valid
        assert res.scheduled["B"].early_finish == W8
        assert res.scheduled["B"].early_start == W6

    def test_completed_pred_drives_ss_successor(self):
        # SS lag=0: B.ES = A.ES = W6. B OD 2 → span 1 → B.EF = W7.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=2.0)
        res = _run([a, b], [_rel("A", "B", "SS")])
        assert res.is_valid
        assert res.scheduled["B"].early_start == W6
        assert res.scheduled["B"].early_finish == W7

    def test_completed_pred_drives_sf_successor(self):
        # SF lag=0: B.EF = A.ES = W6. B OD 2 → span 1 → B.ES = W6 - 1 wd = W5.
        # SF constrains EF only; ES floors at project_start (W1), so the
        # EF-derived ES (W5) wins as the later candidate.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=2.0)
        res = _run([a, b], [_rel("A", "B", "SF")])
        assert res.is_valid
        assert res.scheduled["B"].early_finish == W6
        assert res.scheduled["B"].early_start == W5

    def test_completed_pred_drives_fs_successor_with_lag(self):
        # FS lag=2 (INCLUSIVE_DAY): B.ES = A.EF + 2 wd = W8 + 2 = W10.
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        b = Activity(act_id="B", original_duration=1.0)
        res = _run([a, b], [_rel("A", "B", "FS", lag=2)])
        assert res.is_valid
        assert res.scheduled["B"].early_start == W10
        assert res.scheduled["B"].early_finish == W10  # OD 1 milestone-span


# ---------------------------------------------------------------------------
# NOT PORTED IN W1a: TestAnchoredABCSRelationshipPropagation (source section
# 1b — test_anchored_fs_successor_starts_next_workday,
# test_anchored_ff_successor_convention_invariant,
# test_anchored_ss_successor_convention_invariant,
# test_anchored_sf_successor_convention_invariant) depends on _anchored_sim()
# / mip39.simulation, which is not ported in this wave.
# ---------------------------------------------------------------------------


# ===========================================================================
# (2) Multiple in-progress activities feeding a common successor.
#     Each in-progress activity is pinned at actual_start; EF is computed
#     forward from remaining_duration (data-date floor). The successor picks up
#     the LATEST driving finish.
# ===========================================================================

class TestMultipleInProgressFanIn:

    def test_two_in_progress_feed_common_fs_successor_later_wins(self):
        # I1 actual_start W6, RD 2 → remaining_span 1 → EF = W6 +1 = W7.
        # I2 actual_start W6, RD 4 → remaining_span 3 → EF = W6 +3 = W9.
        # Both FS → C. C.ES = max(W7, W9) = W9; OD 2 → C.EF = W10.
        i1 = Activity(act_id="I1", original_duration=10.0, remaining_duration=2.0,
                      pinned_early_start=W6)
        i2 = Activity(act_id="I2", original_duration=10.0, remaining_duration=4.0,
                      pinned_early_start=W6)
        c = Activity(act_id="C", original_duration=2.0)
        res = _run([i1, i2, c], [_rel("I1", "C"), _rel("I2", "C")])
        assert res.is_valid
        assert res.scheduled["I1"].early_finish == W7
        assert res.scheduled["I2"].early_finish == W9
        assert res.scheduled["C"].early_start == W9
        assert res.scheduled["C"].early_finish == W10

    def test_three_in_progress_distinct_remaining_durations(self):
        # Three in-progress pinned at the same actual_start W6, different RD.
        # I1 RD1 → EF W6 ; I2 RD3 → EF W8 ; I3 RD5 → EF W10. C.ES = W10.
        i1 = Activity(act_id="I1", original_duration=9.0, remaining_duration=1.0,
                      pinned_early_start=W6)
        i2 = Activity(act_id="I2", original_duration=9.0, remaining_duration=3.0,
                      pinned_early_start=W6)
        i3 = Activity(act_id="I3", original_duration=9.0, remaining_duration=5.0,
                      pinned_early_start=W6)
        c = Activity(act_id="C", original_duration=1.0)
        res = _run([i1, i2, i3, c],
                   [_rel("I1", "C"), _rel("I2", "C"), _rel("I3", "C")])
        assert res.is_valid
        assert res.scheduled["I1"].early_finish == W6
        assert res.scheduled["I2"].early_finish == W8
        assert res.scheduled["I3"].early_finish == W10
        assert res.scheduled["C"].early_start == W10
        assert res.scheduled["C"].early_finish == W10

    def test_in_progress_remaining_floors_at_data_date(self):
        # In-progress pinned BEFORE the data date: actual_start = W1, but
        # project_start (data date) = W6. Remaining work resumes at the data
        # date floor, NOT at the historical actual_start. RD 3 → span 2 →
        # EF = W6 + 2 wd = W8. ES recorded at the actual_start W1.
        i = Activity(act_id="I", original_duration=10.0, remaining_duration=3.0,
                     pinned_early_start=W1)
        res = _run([i], [], start=W6)
        assert res.is_valid
        assert res.scheduled["I"].early_start == W1   # historical fact
        assert res.scheduled["I"].early_finish == W8   # floored at data date W6


# ===========================================================================
# (3) Mixed completed + in-progress + not-started feeding a finish milestone.
#     The milestone EF must equal the max over the driving chain.
# ===========================================================================

class TestMixedChainToFinishMilestone:

    def test_finish_milestone_is_max_over_driving_chain(self):
        # COMP completed W6..W8 (EF W8).
        # INPR in-progress actual_start W6, RD 5 → EF = W6 + 4 wd = W10.
        # NS  not-started OD 2, FS-after COMP → ES = COMP.EF = W8; EF = W9.
        # All three feed FIN (OD 0 milestone, FS). FIN.ES = max(W8, W10, W9) = W10.
        # Milestone EF == ES == W10.
        comp = Activity(act_id="COMP", original_duration=3.0,
                        pinned_early_start=W6, pinned_early_finish=W8)
        inpr = Activity(act_id="INPR", original_duration=10.0,
                        remaining_duration=5.0, pinned_early_start=W6)
        ns = Activity(act_id="NS", original_duration=2.0)
        fin = Activity(act_id="FIN", original_duration=0.0)
        rels = [
            _rel("COMP", "NS"),
            _rel("COMP", "FIN"),
            _rel("INPR", "FIN"),
            _rel("NS", "FIN"),
        ]
        res = _run([comp, inpr, ns, fin], rels)
        assert res.is_valid
        assert res.scheduled["COMP"].early_finish == W8
        assert res.scheduled["INPR"].early_finish == W10
        assert res.scheduled["NS"].early_finish == W9
        # Finish milestone = max over driving chain.
        assert res.scheduled["FIN"].early_start == W10
        assert res.scheduled["FIN"].early_finish == W10
        finishes = [
            res.scheduled["COMP"].early_finish,
            res.scheduled["INPR"].early_finish,
            res.scheduled["NS"].early_finish,
        ]
        assert res.scheduled["FIN"].early_finish == max(finishes)

    def test_finish_milestone_driven_by_completed_when_latest(self):
        # Make the COMPLETED activity the latest driver. COMP completed W11..W13.
        # INPR actual_start W6 RD 2 → EF W7. NS OD 1 after INPR → ES W7, EF W7.
        # FIN = max(W13, W7, W7) = W13 (the completed activity drives the finish).
        comp = Activity(act_id="COMP", original_duration=3.0,
                        pinned_early_start=W11, pinned_early_finish=W13)
        inpr = Activity(act_id="INPR", original_duration=10.0,
                        remaining_duration=2.0, pinned_early_start=W6)
        ns = Activity(act_id="NS", original_duration=1.0)
        fin = Activity(act_id="FIN", original_duration=0.0)
        rels = [
            _rel("INPR", "NS"),
            _rel("COMP", "FIN"),
            _rel("INPR", "FIN"),
            _rel("NS", "FIN"),
        ]
        res = _run([comp, inpr, ns, fin], rels)
        assert res.is_valid
        assert res.scheduled["FIN"].early_finish == W13

    # NOT PORTED IN W1a: test_mixed_chain_through_anchored_abcs depends on
    # _anchored_sim() / mip39.simulation, which is not ported in this wave.


# ===========================================================================
# (4) A not-started activity whose only predecessor is completed: it floors at
#     the data date (project_start) and, under P6 FS, starts the NEXT workday.
# ===========================================================================

class TestNotStartedAfterCompleted:

    def test_engine_inclusive_day_not_started_starts_same_workday(self):
        # Engine INCLUSIVE_DAY: completed COMP W6..W8 → NS.ES = COMP.EF = W8.
        comp = Activity(act_id="COMP", original_duration=3.0,
                        pinned_early_start=W6, pinned_early_finish=W8)
        ns = Activity(act_id="NS", original_duration=2.0)
        res = _run([comp, ns], [_rel("COMP", "NS")])
        assert res.is_valid
        assert res.scheduled["NS"].early_start == W8
        assert res.scheduled["NS"].early_finish == W9

    # NOT PORTED IN W1a: test_anchored_not_started_starts_next_workday_after_completed
    # and test_not_started_floors_at_data_date_when_pred_completed_early depend
    # on _anchored_sim() / mip39.simulation, which is not ported in this wave.

    def test_engine_not_started_floors_at_data_date(self):
        # Engine-level equivalent of the data-date floor: pinned-completed COMP
        # at W1..W2, project_start W6 (INCLUSIVE_DAY). NS floors at W6 (data
        # date), NOT at COMP.EF (W2). OD 2 → EF W7.
        comp = Activity(act_id="COMP", original_duration=2.0,
                        pinned_early_start=W1, pinned_early_finish=W2)
        ns = Activity(act_id="NS", original_duration=2.0)
        res = _run([comp, ns], [_rel("COMP", "NS")], start=W6)
        assert res.is_valid
        assert res.scheduled["NS"].early_start == W6
        assert res.scheduled["NS"].early_finish == W7
