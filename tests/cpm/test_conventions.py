"""
Tests for INFRA-009 and INFRA-010: Phase 5 EF Convention Architecture.

Covers 16 required test categories:
  1  EFConvention enum — values, names, membership
  2  fs_forward_offset() — returns 0 (INCLUSIVE_DAY) and 1 (P6_COMPATIBILITY)
  3  Inclusive-day forward pass — FS: successor ES = predecessor EF (same workday)
  4  P6-compatibility forward pass — FS: successor ES = predecessor EF + 1 workday
  5  SS unchanged by convention — identical scheduling under both
  6  FF unchanged by convention — identical scheduling under both
  7  SF unchanged by convention — identical scheduling under both
  8  Backward pass FS — LF constraint differs by convention
  9  Free float FS — FF formula differs by convention
  10 Longest-path FS tightness — controlling predecessor identified correctly
  11 Milestone FS — zero-duration predecessor with FS successor
  12 Backward compatibility — no-arg call uses INCLUSIVE_DAY (833-test baseline)
  13 Convention in AnalysisContext — ef_convention, convention_assumptions recorded
  14 Convention in CriticalPathInfo — ef_convention field set correctly
  15 compare_conventions() — returns ConventionComparisonResult, both results valid
  16 Divergence flags — CV-001 through CV-004 detected in appropriate networks

All fixtures are synthetic. No proprietary schedule data.

Workday grid (Standard Mon–Fri, Jan 2026):
  W1 =2026-01-05 (Mon, wd1)  W2 =2026-01-06 (Tue, wd2)
  W3 =2026-01-07 (Wed, wd3)  W4 =2026-01-08 (Thu, wd4)
  W5 =2026-01-09 (Fri, wd5)  W6 =2026-01-12 (Mon, wd6)
  W7 =2026-01-13 (Tue, wd7)  W8 =2026-01-14 (Wed, wd8)
  W9 =2026-01-15 (Thu, wd9)  W10=2026-01-16 (Fri, wd10)
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.conventions import EFConvention, fs_forward_offset  # noqa: E402
from scheduleiq.cpm.engine import run_analysis  # noqa: E402
# NOT PORTED IN W1a: mip39.comparison (compare_conventions,
# ConventionComparisonResult) is not ported in this wave — see the dropped
# TestCompareConventions / TestDivergenceFlags classes near the end of file.


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2026, 1, 5), date(2026, 3, 31))
_START = date(2026, 1, 5)  # Monday = wd1

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


def _act(act_id: str, od: int = 3) -> Activity:
    return Activity(act_id=act_id, original_duration=float(od))


def _fs(pred: str, succ: str, lag: int = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="FS", lag=float(lag))


def _ss(pred: str, succ: str, lag: int = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="SS", lag=float(lag))


def _ff(pred: str, succ: str, lag: int = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="FF", lag=float(lag))


def _sf(pred: str, succ: str, lag: int = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type="SF", lag=float(lag))


# ---------------------------------------------------------------------------
# 1. EFConvention enum — values, names, membership
# ---------------------------------------------------------------------------

class TestEFConventionEnum:
    def test_inclusive_day_value(self):
        assert EFConvention.INCLUSIVE_DAY.value == "inclusive_day"

    def test_p6_compatibility_value(self):
        assert EFConvention.P6_COMPATIBILITY.value == "p6_compatibility"

    def test_both_members_exist(self):
        members = {e.value for e in EFConvention}
        assert "inclusive_day" in members
        assert "p6_compatibility" in members

    def test_exactly_two_members(self):
        assert len(list(EFConvention)) == 2

    def test_enum_from_value_inclusive(self):
        assert EFConvention("inclusive_day") is EFConvention.INCLUSIVE_DAY

    def test_enum_from_value_p6(self):
        assert EFConvention("p6_compatibility") is EFConvention.P6_COMPATIBILITY

    def test_conventions_are_distinct(self):
        assert EFConvention.INCLUSIVE_DAY != EFConvention.P6_COMPATIBILITY


# ---------------------------------------------------------------------------
# 2. fs_forward_offset() — returns 0 (INCLUSIVE_DAY) and 1 (P6_COMPATIBILITY)
# ---------------------------------------------------------------------------

class TestFsForwardOffset:
    def test_inclusive_day_offset_is_zero(self):
        assert fs_forward_offset(EFConvention.INCLUSIVE_DAY) == 0

    def test_p6_compatibility_offset_is_one(self):
        assert fs_forward_offset(EFConvention.P6_COMPATIBILITY) == 1

    def test_return_type_is_int(self):
        assert isinstance(fs_forward_offset(EFConvention.INCLUSIVE_DAY), int)
        assert isinstance(fs_forward_offset(EFConvention.P6_COMPATIBILITY), int)


# ---------------------------------------------------------------------------
# 3. Inclusive-day forward pass — FS: successor ES = predecessor EF (same workday)
# ---------------------------------------------------------------------------

class TestInclusiveDayForwardPass:
    def setup_method(self):
        """A(OD=3) --FS,lag=0--> B(OD=3)"""
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        self.result = run_analysis(
            acts, rels, _START, _TABLE, _CAL,
            convention=EFConvention.INCLUSIVE_DAY,
        )

    def test_a_early_start(self):
        assert self.result.scheduled["A"].early_start == W1

    def test_a_early_finish(self):
        # OD=3: EF = ES + 2 workdays = W3
        assert self.result.scheduled["A"].early_finish == W3

    def test_b_early_start_same_as_a_ef(self):
        # INCLUSIVE_DAY FS lag=0: B.ES = A.EF (same workday W3)
        assert self.result.scheduled["B"].early_start == W3

    def test_b_early_finish(self):
        # B.EF = W3 + 2 = W5
        assert self.result.scheduled["B"].early_finish == W5

    def test_project_finish_is_w5(self):
        assert self.result.project_finish == W5

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_fs_lag_one_shifts_b_by_one(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 1)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        # B.ES = A.EF + 1 = W3 + 1 = W4
        assert r.scheduled["B"].early_start == W4


# ---------------------------------------------------------------------------
# 4. P6-compatibility forward pass — FS: successor ES = predecessor EF + 1 workday
# ---------------------------------------------------------------------------

class TestP6CompatibilityForwardPass:
    def setup_method(self):
        """A(OD=3) --FS,lag=0--> B(OD=3)"""
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        self.result = run_analysis(
            acts, rels, _START, _TABLE, _CAL,
            convention=EFConvention.P6_COMPATIBILITY,
        )

    def test_a_early_start(self):
        assert self.result.scheduled["A"].early_start == W1

    def test_a_early_finish(self):
        # EF formula unchanged: EF = ES + (OD-1) = W3
        assert self.result.scheduled["A"].early_finish == W3

    def test_b_early_start_is_next_workday(self):
        # P6_COMPATIBILITY FS lag=0: B.ES = A.EF + 0 + 1 = W4 (next workday)
        assert self.result.scheduled["B"].early_start == W4

    def test_b_early_finish(self):
        # B.EF = W4 + 2 = W6
        assert self.result.scheduled["B"].early_finish == W6

    def test_project_finish_is_w6(self):
        assert self.result.project_finish == W6

    def test_b_es_differs_from_inclusive(self):
        inc = run_analysis(
            [_act("A", 3), _act("B", 3)], [_fs("A", "B", 0)],
            _START, _TABLE, _CAL, convention=EFConvention.INCLUSIVE_DAY,
        )
        assert inc.scheduled["B"].early_start == W3
        assert self.result.scheduled["B"].early_start == W4

    def test_fs_lag_one_shifts_b_by_offset_plus_lag(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 1)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        # B.ES = A.EF + 1 + 1 = W3 + 2 = W5
        assert r.scheduled["B"].early_start == W5


# ---------------------------------------------------------------------------
# 5. SS unchanged by convention — identical scheduling under both
# ---------------------------------------------------------------------------

class TestSSUnchangedByConvention:
    """SS relationship type produces identical ES/EF/LS/LF/TF under both conventions."""

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_ss("A", "B", 0)]
        self.inc = run_analysis(acts, rels, _START, _TABLE, _CAL,
                                convention=EFConvention.INCLUSIVE_DAY)
        self.p6  = run_analysis(acts, rels, _START, _TABLE, _CAL,
                                convention=EFConvention.P6_COMPATIBILITY)

    def test_b_early_start_identical(self):
        assert self.inc.scheduled["B"].early_start == self.p6.scheduled["B"].early_start

    def test_b_early_finish_identical(self):
        assert self.inc.scheduled["B"].early_finish == self.p6.scheduled["B"].early_finish

    def test_b_late_start_identical(self):
        assert self.inc.scheduled["B"].late_start == self.p6.scheduled["B"].late_start

    def test_b_late_finish_identical(self):
        assert self.inc.scheduled["B"].late_finish == self.p6.scheduled["B"].late_finish

    def test_a_total_float_identical(self):
        assert self.inc.scheduled["A"].total_float == self.p6.scheduled["A"].total_float

    def test_project_finish_identical(self):
        assert self.inc.project_finish == self.p6.project_finish

    def test_ss_with_lag_identical(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_ss("A", "B", 2)]
        inc = run_analysis(acts, rels, _START, _TABLE, _CAL,
                           convention=EFConvention.INCLUSIVE_DAY)
        p6  = run_analysis(acts, rels, _START, _TABLE, _CAL,
                           convention=EFConvention.P6_COMPATIBILITY)
        assert inc.scheduled["B"].early_start == p6.scheduled["B"].early_start
        assert inc.project_finish == p6.project_finish


# ---------------------------------------------------------------------------
# 6. FF unchanged by convention — identical scheduling under both
# ---------------------------------------------------------------------------

class TestFFUnchangedByConvention:
    """FF relationship type produces identical results under both conventions."""

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_ff("A", "B", 0)]
        self.inc = run_analysis(acts, rels, _START, _TABLE, _CAL,
                                convention=EFConvention.INCLUSIVE_DAY)
        self.p6  = run_analysis(acts, rels, _START, _TABLE, _CAL,
                                convention=EFConvention.P6_COMPATIBILITY)

    def test_b_early_finish_identical(self):
        assert self.inc.scheduled["B"].early_finish == self.p6.scheduled["B"].early_finish

    def test_b_early_start_identical(self):
        assert self.inc.scheduled["B"].early_start == self.p6.scheduled["B"].early_start

    def test_project_finish_identical(self):
        assert self.inc.project_finish == self.p6.project_finish

    def test_a_total_float_identical(self):
        assert self.inc.scheduled["A"].total_float == self.p6.scheduled["A"].total_float


# ---------------------------------------------------------------------------
# 7. SF unchanged by convention — identical scheduling under both
# ---------------------------------------------------------------------------

class TestSFUnchangedByConvention:
    """SF relationship type produces identical results under both conventions."""

    def setup_method(self):
        # SF: B.EF = A.ES + lag. A(OD=3): A.ES=W1. B(OD=3): B.EF=W1+5=W6 (lag=5)
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_sf("A", "B", 5)]
        self.inc = run_analysis(acts, rels, _START, _TABLE, _CAL,
                                convention=EFConvention.INCLUSIVE_DAY)
        self.p6  = run_analysis(acts, rels, _START, _TABLE, _CAL,
                                convention=EFConvention.P6_COMPATIBILITY)

    def test_b_early_finish_identical(self):
        assert self.inc.scheduled["B"].early_finish == self.p6.scheduled["B"].early_finish

    def test_b_early_start_identical(self):
        assert self.inc.scheduled["B"].early_start == self.p6.scheduled["B"].early_start

    def test_project_finish_identical(self):
        assert self.inc.project_finish == self.p6.project_finish

    def test_a_total_float_identical(self):
        assert self.inc.scheduled["A"].total_float == self.p6.scheduled["A"].total_float


# ---------------------------------------------------------------------------
# 8. Backward pass FS — LF constraint differs by convention
# ---------------------------------------------------------------------------

class TestBackwardPassFSConvention:
    """
    A(OD=3) --FS,lag=0--> B(OD=3).
    Backward pass must be consistent with forward pass under each convention.
    """

    def test_a_total_float_zero_inclusive(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        # Single FS chain: all TF=0
        assert r.scheduled["A"].total_float == 0
        assert r.scheduled["B"].total_float == 0

    def test_b_total_float_zero_p6(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["A"].total_float == 0
        assert r.scheduled["B"].total_float == 0

    def test_a_lf_inclusive(self):
        # INCLUSIVE_DAY: B.LS = B.EF - 2 = W5 - 2 = W3. A.LF = B.LS - 0 = W3
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.scheduled["A"].late_finish == W3

    def test_a_lf_p6(self):
        # P6: B.LF=W6, B.LS=W4. A.LF = B.LS - 0 - 1 = W4 - 1 = W3
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["A"].late_finish == W3

    def test_project_duration_differs_between_conventions(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        inc = run_analysis(acts, rels, _START, _TABLE, _CAL,
                           convention=EFConvention.INCLUSIVE_DAY)
        p6  = run_analysis(acts, rels, _START, _TABLE, _CAL,
                           convention=EFConvention.P6_COMPATIBILITY)
        # INC: project_finish=W5. P6: project_finish=W6
        assert inc.project_finish != p6.project_finish

    def test_backward_pass_consistent_with_forward_tf_zero_p6(self):
        # Single chain must always produce TF=0 regardless of convention
        acts = [_act("A", 3), _act("B", 3), _act("C", 3)]
        rels = [_fs("A", "B", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        for sa in r.scheduled.values():
            assert sa.total_float == 0


# ---------------------------------------------------------------------------
# 9. Free float FS — FF formula differs by convention
# ---------------------------------------------------------------------------

class TestFreeFloatFSConvention:
    """
    FF for FS predecessor under each convention.
    A(OD=3) --FS,lag=0--> B(OD=3). A is the only predecessor of B.
    """

    def test_a_free_float_zero_inclusive(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        # FF(A) = wt[B.ES] - wt[A.EF] - 0 - 0 = wt[W3] - wt[W3] = 0
        assert r.scheduled["A"].free_float == 0

    def test_a_free_float_zero_p6(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        # FF(A) = wt[B.ES] - wt[A.EF] - 0 - 1 = wt[W4] - wt[W3] - 1 = 4-3-1 = 0
        assert r.scheduled["A"].free_float == 0

    def test_a_free_float_with_slack_inclusive(self):
        # A(OD=1) --FS,lag=0--> B(OD=3). A has 2 days slack.
        acts = [_act("A", 1), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        # A: ES=W1, EF=W1. B: ES=W1, EF=W3.
        # FF(A) = wt[W1] - wt[W1] - 0 - 0 = 0
        assert r.scheduled["A"].free_float == 0

    def test_parallel_predecessor_free_float_inclusive(self):
        # Two preds A(OD=2) and B(OD=3) both FS lag=0 to C.
        # C.ES = max(A.EF, B.EF) = max(W2, W3) = W3
        # A.FF = wt[C.ES] - wt[A.EF] - 0 - 0 = wt[W3] - wt[W2] = 3-2 = 1
        acts = [_act("A", 2), _act("B", 3), _act("C", 3)]
        rels = [_fs("A", "C", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.scheduled["A"].free_float == 1
        assert r.scheduled["B"].free_float == 0

    def test_parallel_predecessor_free_float_p6(self):
        # Under P6: C.ES = max(A.EF+1, B.EF+1) = max(W3, W4) = W4
        # A.FF = wt[C.ES] - wt[A.EF] - 0 - 1 = wt[W4] - wt[W2] - 1 = 4-2-1 = 1
        # B.FF = wt[W4] - wt[W3] - 0 - 1 = 4-3-1 = 0
        acts = [_act("A", 2), _act("B", 3), _act("C", 3)]
        rels = [_fs("A", "C", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["A"].free_float == 1
        assert r.scheduled["B"].free_float == 0


# ---------------------------------------------------------------------------
# 10. Longest-path FS tightness — controlling predecessor identified correctly
# ---------------------------------------------------------------------------

class TestLongestPathFSConvention:
    """
    Verify controlling-predecessor identification uses fs_forward_offset.
    """

    def test_single_chain_critical_inclusive(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.scheduled["A"].is_critical is True
        assert r.scheduled["B"].is_critical is True

    def test_single_chain_critical_p6(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["A"].is_critical is True
        assert r.scheduled["B"].is_critical is True

    def test_non_controlling_pred_not_critical_inclusive(self):
        # A(OD=3) and B(OD=2) both FS to C. Only A drives C under INC.
        acts = [_act("A", 3), _act("B", 2), _act("C", 1)]
        rels = [_fs("A", "C", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        # A.EF=W3, B.EF=W2. C.ES=W3. Only A controls C.
        assert r.scheduled["A"].is_critical is True
        assert r.scheduled["B"].is_critical is False

    def test_non_controlling_pred_not_critical_p6(self):
        acts = [_act("A", 3), _act("B", 2), _act("C", 1)]
        rels = [_fs("A", "C", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        # A.EF=W3, B.EF=W2. C.ES=max(W3+1,W2+1)=W4. Only A controls C.
        assert r.scheduled["A"].is_critical is True
        assert r.scheduled["B"].is_critical is False

    def test_tied_controlling_preds_inclusive(self):
        # A(OD=3) and B(OD=3) both FS lag=0 to C. Tied under INC.
        acts = [_act("A", 3), _act("B", 3), _act("C", 1)]
        rels = [_fs("A", "C", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.scheduled["A"].is_critical is True
        assert r.scheduled["B"].is_critical is True

    def test_tied_controlling_preds_p6(self):
        # Both A and B (OD=3) FS lag=0 to C. Still tied under P6 (both offset by same amount).
        acts = [_act("A", 3), _act("B", 3), _act("C", 1)]
        rels = [_fs("A", "C", 0), _fs("B", "C", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["A"].is_critical is True
        assert r.scheduled["B"].is_critical is True


# ---------------------------------------------------------------------------
# 11. Milestone FS — zero-duration predecessor with FS successor
# ---------------------------------------------------------------------------

class TestMilestoneFSConvention:
    """
    Milestone (OD=0): EF = ES in both conventions. FS successor differs.
    """

    def test_milestone_ef_equals_es_inclusive(self):
        acts = [_act("M", 0), _act("B", 3)]
        rels = [_fs("M", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.scheduled["M"].early_finish == r.scheduled["M"].early_start

    def test_milestone_ef_equals_es_p6(self):
        acts = [_act("M", 0), _act("B", 3)]
        rels = [_fs("M", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["M"].early_finish == r.scheduled["M"].early_start

    def test_b_es_after_milestone_inclusive(self):
        # INCLUSIVE_DAY: B.ES = M.EF + 0 = W1 (same workday)
        acts = [_act("M", 0), _act("B", 3)]
        rels = [_fs("M", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.scheduled["B"].early_start == W1

    def test_b_es_after_milestone_p6(self):
        # P6_COMPATIBILITY: B.ES = M.EF + 0 + 1 = W1 + 1 = W2 (next workday)
        acts = [_act("M", 0), _act("B", 3)]
        rels = [_fs("M", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.scheduled["B"].early_start == W2

    def test_milestone_successor_es_differs_by_one(self):
        acts = [_act("M", 0), _act("B", 3)]
        rels = [_fs("M", "B", 0)]
        inc = run_analysis(acts, rels, _START, _TABLE, _CAL,
                           convention=EFConvention.INCLUSIVE_DAY)
        p6  = run_analysis(acts, rels, _START, _TABLE, _CAL,
                           convention=EFConvention.P6_COMPATIBILITY)
        # B.ES under P6 is exactly 1 workday later than under INC
        assert (_TABLE[p6.scheduled["B"].early_start]
                - _TABLE[inc.scheduled["B"].early_start]) == 1


# ---------------------------------------------------------------------------
# 12. Backward compatibility — no convention arg uses INCLUSIVE_DAY
# ---------------------------------------------------------------------------

class TestBackwardCompatibilityDefault:
    """
    run_analysis() called without convention= must behave identically to
    run_analysis(..., convention=EFConvention.INCLUSIVE_DAY).
    """

    def test_default_matches_inclusive_es(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        default_r = run_analysis(acts, rels, _START, _TABLE, _CAL)
        inc_r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                             convention=EFConvention.INCLUSIVE_DAY)
        assert default_r.scheduled["B"].early_start == inc_r.scheduled["B"].early_start

    def test_default_matches_inclusive_ef(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        default_r = run_analysis(acts, rels, _START, _TABLE, _CAL)
        inc_r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                             convention=EFConvention.INCLUSIVE_DAY)
        assert default_r.scheduled["B"].early_finish == inc_r.scheduled["B"].early_finish

    def test_default_project_finish_matches_inclusive(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        default_r = run_analysis(acts, rels, _START, _TABLE, _CAL)
        inc_r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                             convention=EFConvention.INCLUSIVE_DAY)
        assert default_r.project_finish == inc_r.project_finish

    def test_default_differs_from_p6(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        default_r = run_analysis(acts, rels, _START, _TABLE, _CAL)
        p6_r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                            convention=EFConvention.P6_COMPATIBILITY)
        assert default_r.project_finish != p6_r.project_finish

    def test_relationship_logic_default_is_inclusive(self):
        from scheduleiq.cpm.relationship_logic import compute_relationship_constraint  # noqa: E402
        from scheduleiq.cpm.lag_analysis import apply_lag  # noqa: E402
        # FS lag=0 with default convention: constrained_es = pred_ef (same workday)
        constrained_type, constrained_date = compute_relationship_constraint(
            "FS", W1, W3, 0, _TABLE, _CAL
        )
        assert constrained_type == "ES"
        assert constrained_date == W3  # same workday as pred_ef under INCLUSIVE_DAY


# ---------------------------------------------------------------------------
# 13. Convention in AnalysisContext
# ---------------------------------------------------------------------------

class TestConventionInContext:
    def test_ef_convention_inclusive_recorded(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.context.ef_convention == "inclusive_day"

    def test_ef_convention_p6_recorded(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.context.ef_convention == "p6_compatibility"

    def test_convention_assumptions_populated(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert len(r.context.convention_assumptions) >= 1

    def test_convention_assumptions_mention_offset(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        text = " ".join(r.context.convention_assumptions)
        assert "offset" in text.lower() or "convention" in text.lower()

    def test_p6_convention_warnings_populated(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert len(r.context.convention_warnings) >= 1
        warn_text = " ".join(r.context.convention_warnings)
        # Must mention approximation, not exact equivalence
        assert "approximation" in warn_text.lower() or "not exact" in warn_text.lower()

    def test_inclusive_convention_warnings_empty(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.context.convention_warnings == []

    def test_context_to_dict_includes_ef_convention(self):
        acts = [_act("A", 3)]
        r = run_analysis(acts, [], _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        d = r.context.to_dict()
        assert "ef_convention" in d
        assert d["ef_convention"] == "p6_compatibility"
        assert "convention_assumptions" in d
        assert "convention_warnings" in d


# ---------------------------------------------------------------------------
# 14. Convention in CriticalPathInfo
# ---------------------------------------------------------------------------

class TestConventionInCriticalPath:
    def test_ef_convention_inclusive_in_critical_path(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        assert r.critical_path is not None
        assert r.critical_path.ef_convention == "inclusive_day"

    def test_ef_convention_p6_in_critical_path(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.P6_COMPATIBILITY)
        assert r.critical_path is not None
        assert r.critical_path.ef_convention == "p6_compatibility"

    def test_critical_path_to_dict_includes_ef_convention(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_fs("A", "B", 0)]
        r = run_analysis(acts, rels, _START, _TABLE, _CAL,
                         convention=EFConvention.INCLUSIVE_DAY)
        d = r.critical_path.to_dict()
        assert "ef_convention" in d
        assert d["ef_convention"] == "inclusive_day"

    def test_default_ef_convention_is_inclusive(self):
        from scheduleiq.cpm.results import CriticalPathInfo  # noqa: E402
        cp = CriticalPathInfo(activity_ids=["A"], project_duration=5)
        assert cp.ef_convention == "inclusive_day"


# ---------------------------------------------------------------------------
# NOT PORTED IN W1a: TestCompareConventions and TestDivergenceFlags (source
# sections 15-16) depend on mip39.comparison (compare_conventions,
# ConventionComparisonResult), which is not ported in this wave
# (superseded/deferred to later waves per the port instructions).
# ---------------------------------------------------------------------------
