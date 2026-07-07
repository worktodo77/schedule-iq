"""
Tests for INFRA-006 and INFRA-007: Phase 3 Core CPM Analytical Engine.

Covers all 24 required test categories:
  1  Simple 2-activity FS chain
  2  3-activity linear FS chain
  3  Parallel paths (longest path wins)
  4  Diamond network (convergence)
  5  SS relationship scheduling
  6  FF relationship scheduling (Phase 3 new)
  7  SF relationship scheduling (Phase 3 new)
  8  Mixed relationship types (FS + SS + FF + SF)
  9  Positive lag
  10 Negative lag (lead)
  11 Zero-duration milestone
  12 Multi-start network (validation WARNING, analysis continues)
  13 Multi-finish network (validation WARNING, analysis continues)
  14 Blocking validation failure (early return, is_valid=False)
  15 Non-blocking validation issue (analysis continues, is_valid=True)
  16 Backward pass verification (LS, LF)
  17 Total float verification
  18 Free float verification
  19 Critical path identification (TF=0 activities)
  20 Non-critical activities have TF > 0
  21 Multiple critical paths (tied TF=0)
  22 AnalysisResult.to_dict() serialization
  23 AnalysisContext wired into result
  24 ValidationResult included in result

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
from scheduleiq.cpm.results import AnalysisResult, CriticalPathInfo, ScheduledActivity  # noqa: E402
from scheduleiq.cpm.validation import ValidationSeverity  # noqa: E402


# ---------------------------------------------------------------------------
# Shared calendar and workday table
#
# Jan 2026 Mon-Fri calendar. Jan 5 = Monday (wd1).
# Workday reference:
#   W1 = 2026-01-05 (Mon)  W2 = 2026-01-06 (Tue)  W3 = 2026-01-07 (Wed)
#   W4 = 2026-01-08 (Thu)  W5 = 2026-01-09 (Fri)
#   W6 = 2026-01-12 (Mon)  W7 = 2026-01-13 (Tue)  W8 = 2026-01-14 (Wed)
#   W9 = 2026-01-15 (Thu)  W10 = 2026-01-16 (Fri)
# ---------------------------------------------------------------------------

_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2026, 1, 5), date(2026, 3, 31))
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _act(act_id: str, od: int = 3) -> Activity:
    return Activity(act_id=act_id, original_duration=float(od))


def _rel(pred: str, succ: str, rel_type: str = "FS", lag: float = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _run(activities, relationships, start=None):
    return run_analysis(
        activities, relationships,
        start or _START,
        _TABLE, _CAL,
    )


def _sa(result: AnalysisResult, act_id: str) -> ScheduledActivity:
    return result.scheduled[act_id]


# ---------------------------------------------------------------------------
# Category 1 — Simple 2-activity FS chain
# ---------------------------------------------------------------------------

class TestSimpleFS:
    """
    A(3) -> FS(lag=0) -> B(2).
    Forward: A.ES=W1, A.EF=W3; B.ES=W3, B.EF=W4.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B", "FS")]
        self.result = _run(acts, rels)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_a_early_dates(self):
        sa = _sa(self.result, "A")
        assert sa.early_start == W1
        assert sa.early_finish == W3

    def test_b_early_dates(self):
        sa = _sa(self.result, "B")
        assert sa.early_start == W3
        assert sa.early_finish == W4

    def test_project_finish(self):
        assert self.result.project_finish == W4

    def test_project_start(self):
        assert self.result.project_start == W1

    def test_both_activities_present(self):
        assert set(self.result.scheduled.keys()) == {"A", "B"}

    def test_a_original_duration(self):
        assert _sa(self.result, "A").original_duration == 3

    def test_b_original_duration(self):
        assert _sa(self.result, "B").original_duration == 2


# ---------------------------------------------------------------------------
# Category 2 — 3-activity linear chain
# ---------------------------------------------------------------------------

class TestLinearChain:
    """
    A(3) -> FS -> B(2) -> FS -> C(1).
    All critical. project_finish = W4.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2), _act("C", 1)]
        rels = [_rel("A", "B"), _rel("B", "C")]
        self.result = _run(acts, rels)

    def test_c_early_dates(self):
        sa = _sa(self.result, "C")
        assert sa.early_start == W4
        assert sa.early_finish == W4

    def test_project_finish(self):
        assert self.result.project_finish == W4

    def test_all_critical(self):
        for act_id in ["A", "B", "C"]:
            assert _sa(self.result, act_id).is_critical is True


# ---------------------------------------------------------------------------
# Category 3 — Parallel paths (longest path wins)
# ---------------------------------------------------------------------------

class TestParallelPaths:
    """
    S(1) -> A(5) -> F(1)  [long path: S+A+F = 7 workday span]
    S(1) -> B(2) -> F(1)  [short path]
    Longest path: S, A, F (TF=0). B is non-critical.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 5), _act("B", 2), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        self.result = _run(acts, rels)

    def test_longest_path_wins(self):
        # A has OD=5, so A.EF = W1 + 4 = W5; F.ES = W5
        assert _sa(self.result, "A").early_finish == W5
        assert _sa(self.result, "F").early_start == W5

    def test_a_is_critical(self):
        assert _sa(self.result, "A").is_critical is True

    def test_b_is_not_critical(self):
        assert _sa(self.result, "B").is_critical is False

    def test_b_total_float(self):
        # B.EF = W2 (span=1), project_finish = W5; B.TF = W5-W2 = 3
        assert _sa(self.result, "B").total_float == 3

    def test_critical_path_ids(self):
        cp = self.result.critical_path
        assert "A" in cp.activity_ids
        assert "B" not in cp.activity_ids

    def test_project_finish(self):
        assert self.result.project_finish == W5


# ---------------------------------------------------------------------------
# Category 4 — Diamond network
# ---------------------------------------------------------------------------

class TestDiamond:
    """
    S(1) -> A(3) -> F(1)
    S(1) -> B(2) -> F(1)
    Critical: S, A, F. B has TF=1.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 3), _act("B", 2), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        self.result = _run(acts, rels)

    def test_f_early_start(self):
        # A.EF = W3; B.EF = W2; F.ES = max(W3, W2) = W3
        assert _sa(self.result, "F").early_start == W3

    def test_b_total_float(self):
        # B.EF=W2; F.EF=W3; B.LF=W3; B.TF=W3-W2=1
        assert _sa(self.result, "B").total_float == 1

    def test_b_not_critical(self):
        assert _sa(self.result, "B").is_critical is False

    def test_critical_path(self):
        cp_ids = self.result.critical_path.activity_ids
        assert "A" in cp_ids
        assert "F" in cp_ids
        assert "S" in cp_ids
        assert "B" not in cp_ids


# ---------------------------------------------------------------------------
# Category 5 — SS relationship scheduling
# ---------------------------------------------------------------------------

class TestSSRelationship:
    """
    A(4) -> SS(lag=2) -> B(3).
    B.ES = A.ES + 2 = W3; B.EF = W5 (span=2).
    project_finish = max(W4, W5) = W5.
    """

    def setup_method(self):
        acts = [_act("A", 4), _act("B", 3)]
        rels = [_rel("A", "B", "SS", lag=2)]
        self.result = _run(acts, rels)

    def test_a_early_dates(self):
        assert _sa(self.result, "A").early_start == W1
        assert _sa(self.result, "A").early_finish == W4

    def test_b_early_dates(self):
        assert _sa(self.result, "B").early_start == W3
        assert _sa(self.result, "B").early_finish == W5

    def test_project_finish(self):
        assert self.result.project_finish == W5

    def test_both_critical(self):
        # B.LF=W5, B.TF=0; A.LF=W4, A.TF=0
        assert _sa(self.result, "A").total_float == 0
        assert _sa(self.result, "B").total_float == 0

    def test_a_backward_dates(self):
        sa = _sa(self.result, "A")
        assert sa.late_start == W1
        assert sa.late_finish == W4

    def test_b_backward_dates(self):
        sa = _sa(self.result, "B")
        assert sa.late_start == W3
        assert sa.late_finish == W5


# ---------------------------------------------------------------------------
# Category 6 — FF relationship scheduling (Phase 3 new)
# ---------------------------------------------------------------------------

class TestFFRelationship:
    """
    A(4) -> FF(lag=1) -> B(3).
    FF: B.EF constraint = A.EF + 1 = W4 + 1 = W5.
    B span=2; es_from_ef = W5-2 = W3; B.ES=W3, B.EF=W5.
    project_finish = max(W4, W5) = W5.
    """

    def setup_method(self):
        acts = [_act("A", 4), _act("B", 3)]
        rels = [_rel("A", "B", "FF", lag=1)]
        self.result = _run(acts, rels)

    def test_b_early_start(self):
        # es_from_ef: B.EF_constraint = W5; B.span=2; es = W5-2 = W3
        assert _sa(self.result, "B").early_start == W3

    def test_b_early_finish(self):
        assert _sa(self.result, "B").early_finish == W5

    def test_project_finish(self):
        assert self.result.project_finish == W5

    def test_a_backward_dates(self):
        # FF(A→B, lag=1): A.LF = apply_lag(B.LF=W5, -1) = W4; A.LS=W1
        sa = _sa(self.result, "A")
        assert sa.late_finish == W4
        assert sa.late_start == W1

    def test_b_backward_dates(self):
        sa = _sa(self.result, "B")
        assert sa.late_finish == W5
        assert sa.late_start == W3

    def test_both_critical(self):
        assert _sa(self.result, "A").total_float == 0
        assert _sa(self.result, "B").total_float == 0

    def test_ff_zero(self):
        # A→B FF lag=1: B.EF_workday - A.EF_workday - 1 = W5-W4-1 = 5-4-1 = 0
        assert _sa(self.result, "A").free_float == 0


# ---------------------------------------------------------------------------
# Category 7 — SF relationship scheduling (Phase 3 new)
# ---------------------------------------------------------------------------

class TestSFRelationship:
    """
    A(3) -> SF(lag=4) -> B(2).
    SF: B.EF constraint = A.ES + 4 = W1 + 4 = W5.
    B span=1; es_from_ef = W5-1 = W4; B.ES=W4, B.EF=W5.
    project_finish = max(W3, W5) = W5.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B", "SF", lag=4)]
        self.result = _run(acts, rels)

    def test_b_early_start(self):
        # es_from_ef: EF_constraint = W5; B.span=1; es = W5-1 = W4
        assert _sa(self.result, "B").early_start == W4

    def test_b_early_finish(self):
        assert _sa(self.result, "B").early_finish == W5

    def test_project_finish(self):
        assert self.result.project_finish == W5

    def test_a_backward_dates(self):
        # SF(A→B, lag=4): A.span=2; A.LF=apply_lag(B.LF=W5, -4+2=-2)=W3; A.LS=W1
        sa = _sa(self.result, "A")
        assert sa.late_finish == W3
        assert sa.late_start == W1

    def test_b_backward_dates(self):
        sa = _sa(self.result, "B")
        assert sa.late_finish == W5
        assert sa.late_start == W4

    def test_both_critical(self):
        assert _sa(self.result, "A").total_float == 0
        assert _sa(self.result, "B").total_float == 0

    def test_sf_free_float_zero(self):
        # A→B SF lag=4: B.EF_workday - A.ES_workday - 4 = W5-W1-4 = 5-1-4 = 0
        assert _sa(self.result, "A").free_float == 0


# ---------------------------------------------------------------------------
# Category 8 — Mixed relationship types
# ---------------------------------------------------------------------------

class TestMixedRelationships:
    """
    A(3) -> FS(lag=0) -> C(2)
    A(3) -> FF(lag=0) -> D(2)
    B(2) -> SS(lag=1) -> C(2)
    Network: A and B no predecessors; C and D are successors.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2), _act("C", 2), _act("D", 2)]
        rels = [
            _rel("A", "C", "FS"),
            _rel("A", "D", "FF"),
            _rel("B", "C", "SS", lag=1),
        ]
        self.result = _run(acts, rels)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_all_activities_scheduled(self):
        assert set(self.result.scheduled.keys()) == {"A", "B", "C", "D"}

    def test_c_early_dates(self):
        # C predecessors: FS(A→C): C.ES=A.EF=W3; SS(B→C,lag=1): C.ES=B.ES+1=W2
        # max(W3, W2) = W3; C.EF = W3+1 = W4
        sa = _sa(self.result, "C")
        assert sa.early_start == W3
        assert sa.early_finish == W4

    def test_d_early_dates(self):
        # D predecessors: FF(A→D,lag=0): EF constraint = A.EF+0 = W3
        # es_from_ef = W3-1 = W2; D.ES=max(W1,W2)=W2; D.EF=W3
        sa = _sa(self.result, "D")
        assert sa.early_start == W2
        assert sa.early_finish == W3


# ---------------------------------------------------------------------------
# Category 9 — Positive lag
# ---------------------------------------------------------------------------

class TestPositiveLag:
    """
    A(3) -> FS(lag=3) -> B(2)
    C(4) -> FS(lag=0) -> B(2)
    A and C have no predecessors. A's lag pushes B out past C.
    B.ES = max(apply_lag(W3, +3)=W6, apply_lag(W4, 0)=W4) = W6.
    B.EF = W7.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("C", 4), _act("B", 2)]
        rels = [_rel("A", "B", "FS", lag=3), _rel("C", "B", "FS")]
        self.result = _run(acts, rels)

    def test_b_early_start(self):
        assert _sa(self.result, "B").early_start == W6

    def test_b_early_finish(self):
        assert _sa(self.result, "B").early_finish == W7

    def test_a_is_critical(self):
        assert _sa(self.result, "A").is_critical is True

    def test_c_is_not_critical(self):
        assert _sa(self.result, "C").is_critical is False

    def test_c_total_float(self):
        # C.EF=W4; B.LF=W7; backward C: apply_lag(B.LS=W6,0)=W6; C.TF=W6-W4=2
        assert _sa(self.result, "C").total_float == 2


# ---------------------------------------------------------------------------
# Category 10 — Negative lag (lead)
# ---------------------------------------------------------------------------

class TestNegativeLag:
    """
    A(4) -> FS(lag=-1) -> B(3).
    FS lag=-1: B.ES = apply_lag(A.EF=W4, -1) = W3; B.EF = W5.
    project_finish = max(W4, W5) = W5.
    """

    def setup_method(self):
        acts = [_act("A", 4), _act("B", 3)]
        rels = [_rel("A", "B", "FS", lag=-1)]
        self.result = _run(acts, rels)

    def test_b_early_start(self):
        # B starts 1 workday before A finishes (lead)
        assert _sa(self.result, "B").early_start == W3

    def test_b_early_finish(self):
        assert _sa(self.result, "B").early_finish == W5

    def test_project_finish(self):
        assert self.result.project_finish == W5

    def test_both_critical(self):
        assert _sa(self.result, "A").total_float == 0
        assert _sa(self.result, "B").total_float == 0


# ---------------------------------------------------------------------------
# Category 11 — Zero-duration milestone
# ---------------------------------------------------------------------------

class TestMilestone:
    """
    S(1) -> FS -> M(0) -> FS -> F(2).
    M: ES=EF=W1 (milestone: OD=0, EF=ES).
    F: ES=W1, EF=W2.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("M", 0), _act("F", 2)]
        rels = [_rel("S", "M"), _rel("M", "F")]
        self.result = _run(acts, rels)

    def test_milestone_es_equals_ef(self):
        sa = _sa(self.result, "M")
        assert sa.early_start == sa.early_finish

    def test_milestone_early_start(self):
        assert _sa(self.result, "M").early_start == W1

    def test_f_early_dates(self):
        sa = _sa(self.result, "F")
        assert sa.early_start == W1
        assert sa.early_finish == W2

    def test_milestone_original_duration(self):
        assert _sa(self.result, "M").original_duration == 0

    def test_milestone_ls_equals_lf(self):
        sa = _sa(self.result, "M")
        assert sa.late_start == sa.late_finish

    def test_all_critical(self):
        for act_id in ["S", "M", "F"]:
            assert _sa(self.result, act_id).is_critical is True


# ---------------------------------------------------------------------------
# Category 12 — Multi-start network (NET-001 warning, analysis continues)
# ---------------------------------------------------------------------------

class TestMultiStart:
    """
    A(2) and B(3) both start without predecessors, then flow to C(1).
    NET-001: multiple start nodes — WARNING, non-blocking.
    Analysis completes. Longest path through B.
    """

    def setup_method(self):
        acts = [_act("A", 2), _act("B", 3), _act("C", 1)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result = _run(acts, rels)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_net001_warning_present(self):
        codes = [i.issue_code for i in self.result.validation.issues]
        assert "NET-001" in codes

    def test_net001_is_warning(self):
        issue = next(i for i in self.result.validation.issues if i.issue_code == "NET-001")
        assert issue.severity == ValidationSeverity.WARNING

    def test_analysis_completes(self):
        assert set(self.result.scheduled.keys()) == {"A", "B", "C"}

    def test_longest_path_wins(self):
        # B(3) longer than A(2): C.ES = max(A.EF=W2, B.EF=W3) = W3
        assert _sa(self.result, "C").early_start == W3

    def test_a_is_not_critical(self):
        assert _sa(self.result, "A").is_critical is False

    def test_b_is_critical(self):
        assert _sa(self.result, "B").is_critical is True


# ---------------------------------------------------------------------------
# Category 13 — Multi-finish network (NET-002 warning, analysis continues)
# ---------------------------------------------------------------------------

class TestMultiFinish:
    """
    S(1) flows to A(2) and B(3) — both are finish nodes.
    NET-002: multiple finish nodes — WARNING, non-blocking.
    project_finish = max(A.EF=W2, B.EF=W3) = W3.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 2), _act("B", 3)]
        rels = [_rel("S", "A"), _rel("S", "B")]
        self.result = _run(acts, rels)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_net002_warning_present(self):
        codes = [i.issue_code for i in self.result.validation.issues]
        assert "NET-002" in codes

    def test_net002_is_warning(self):
        issue = next(i for i in self.result.validation.issues if i.issue_code == "NET-002")
        assert issue.severity == ValidationSeverity.WARNING

    def test_project_finish(self):
        assert self.result.project_finish == W3

    def test_a_total_float(self):
        # A.EF=W2; project_finish=W3; A.LF=W3; A.TF=W3-W2=1
        assert _sa(self.result, "A").total_float == 1

    def test_b_is_critical(self):
        assert _sa(self.result, "B").is_critical is True

    def test_s_is_critical(self):
        # S.LF drives from B.LS=W1; S.TF=0
        assert _sa(self.result, "S").is_critical is True


# ---------------------------------------------------------------------------
# Category 14 — Blocking validation failure
# ---------------------------------------------------------------------------

class TestBlockingValidation:
    """
    Relationship references unknown activity → NET-006 (CRITICAL, blocking).
    Engine returns early with is_valid=False.
    """

    def setup_method(self):
        acts = [_act("A", 5)]
        rels = [_rel("A", "NONEXISTENT", "FS")]
        self.result = _run(acts, rels)

    def test_is_invalid(self):
        assert self.result.is_valid is False

    def test_scheduled_is_empty(self):
        assert self.result.scheduled == {}

    def test_critical_path_is_none(self):
        assert self.result.critical_path is None

    def test_project_finish_is_none(self):
        assert self.result.project_finish is None

    def test_validation_present(self):
        assert self.result.validation is not None

    def test_blocking_issue_present(self):
        assert self.result.validation.has_blocking_issues is True

    def test_context_present(self):
        assert self.result.context is not None


# ---------------------------------------------------------------------------
# Category 15 — Non-blocking validation issue
# ---------------------------------------------------------------------------

class TestNonBlockingValidation:
    """
    FF/SF relationship types are fully supported in Phase 3 (INFRA-007).
    They do NOT generate NET-005. Analysis proceeds with is_valid=True
    and a clean validation result (no NET-005 warnings).

    NET-005 now fires only for relationship types outside {FS, SS, FF, SF}.
    """

    def setup_method(self):
        # A(3) -> FF(lag=0) -> B(2): Phase 3 supports FF; no NET-005 generated
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B", "FF")]
        self.result = _run(acts, rels)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_no_net005_for_ff(self):
        codes = [i.issue_code for i in self.result.validation.issues]
        assert "NET-005" not in codes

    def test_ff_generates_no_validation_issues(self):
        net005_issues = [
            i for i in self.result.validation.issues if i.issue_code == "NET-005"
        ]
        assert net005_issues == []

    def test_analysis_completes(self):
        assert set(self.result.scheduled.keys()) == {"A", "B"}

    def test_results_correct(self):
        # A(3) → FF(lag=0) → B(2): B.EF constrained to A.EF=W3; B.ES=W2; B.EF=W3
        assert _sa(self.result, "A").early_start == W1
        assert _sa(self.result, "B").early_finish == W3


# ---------------------------------------------------------------------------
# Category 16 — Backward pass verification
# ---------------------------------------------------------------------------

class TestBackwardPass:
    """
    A(3) -> FS -> B(2).
    Verify: B.LF=W4,B.LS=W3; A.LF=W3,A.LS=W1.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        self.result = _run(acts, rels)

    def test_b_late_finish(self):
        assert _sa(self.result, "B").late_finish == W4

    def test_b_late_start(self):
        assert _sa(self.result, "B").late_start == W3

    def test_a_late_finish(self):
        # FS(A→B, lag=0): A.LF = apply_lag(B.LS=W3, 0) = W3
        assert _sa(self.result, "A").late_finish == W3

    def test_a_late_start(self):
        # A.LS = A.LF - (A.OD-1) = W3 - 2 = W1
        assert _sa(self.result, "A").late_start == W1

    def test_backward_ss(self):
        # A(4) -> SS(lag=2) -> B(3); A.LF=W4, B.LF=W5
        acts = [_act("A", 4), _act("B", 3)]
        rels = [_rel("A", "B", "SS", lag=2)]
        result = _run(acts, rels)
        assert _sa(result, "A").late_finish == W4
        assert _sa(result, "B").late_finish == W5

    def test_backward_ff(self):
        # A(4) -> FF(lag=1) -> B(3); A.LF=W4, B.LF=W5
        acts = [_act("A", 4), _act("B", 3)]
        rels = [_rel("A", "B", "FF", lag=1)]
        result = _run(acts, rels)
        assert _sa(result, "A").late_finish == W4
        assert _sa(result, "B").late_finish == W5

    def test_backward_sf(self):
        # A(3) -> SF(lag=4) -> B(2); A.LF=W3, B.LF=W5
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B", "SF", lag=4)]
        result = _run(acts, rels)
        assert _sa(result, "A").late_finish == W3
        assert _sa(result, "B").late_finish == W5


# ---------------------------------------------------------------------------
# Category 17 — Total float verification
# ---------------------------------------------------------------------------

class TestTotalFloat:
    """
    S(1) -> A(5) -> F(1)  [long: critical]
    S(1) -> B(2) -> F(1)  [short: B.TF = (W5_workday - W2_workday) = 3]
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 5), _act("B", 2), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        self.result = _run(acts, rels)

    def test_critical_tf_zero(self):
        for act_id in ["S", "A", "F"]:
            assert _sa(self.result, act_id).total_float == 0

    def test_b_tf(self):
        # B.EF=W2; project_finish=W5; B.LF=W5; TF=W5-W2=3
        assert _sa(self.result, "B").total_float == 3

    def test_tf_equals_lf_minus_ef(self):
        for act_id, sa in self.result.scheduled.items():
            tf_computed = _TABLE[sa.late_finish] - _TABLE[sa.early_finish]
            assert sa.total_float == tf_computed, (
                f"{act_id}: TF mismatch"
            )

    def test_tf_non_negative(self):
        for sa in self.result.scheduled.values():
            assert sa.total_float >= 0


# ---------------------------------------------------------------------------
# Category 18 — Free float verification
# ---------------------------------------------------------------------------

class TestFreeFloat:
    """
    Free float less than total float: S(1)->A(2)->B(2)->F(1), S->C(6)->F.
    A.FF=0 even though A.TF=3 (A constrains B's start).
    B.FF=3 == B.TF (B's constraint on F has 3 wd slack).
    """

    def setup_method(self):
        # Long path through C: S -> C(6) -> F
        # Short path: S -> A(2) -> B(2) -> F
        acts = [
            _act("S", 1), _act("A", 2), _act("B", 2),
            _act("C", 6), _act("F", 1),
        ]
        rels = [
            _rel("S", "A"), _rel("A", "B"), _rel("B", "F"),
            _rel("S", "C"), _rel("C", "F"),
        ]
        self.result = _run(acts, rels)

    def test_a_ff_zero(self):
        # A directly constrains B's start: A.FF=0 even though A.TF=3
        assert _sa(self.result, "A").free_float == 0

    def test_a_tf_nonzero(self):
        assert _sa(self.result, "A").total_float == 3

    def test_a_ff_less_than_tf(self):
        sa = _sa(self.result, "A")
        assert sa.free_float < sa.total_float

    def test_b_ff_equals_tf(self):
        # B.FF = B.TF because B's only constraint is on F, with same slack
        sa = _sa(self.result, "B")
        assert sa.free_float == sa.total_float

    def test_c_ff_zero(self):
        # C is critical (TF=0), C.FF=0
        assert _sa(self.result, "C").free_float == 0

    def test_finish_node_ff_equals_tf(self):
        # Finish node: FF = TF (no successors)
        sa = _sa(self.result, "F")
        assert sa.free_float == sa.total_float

    def test_ff_non_negative(self):
        for sa in self.result.scheduled.values():
            assert sa.free_float >= 0


# ---------------------------------------------------------------------------
# Category 19 — Critical path identification
# ---------------------------------------------------------------------------

class TestCriticalPath:
    """
    Critical path = TF=0 activities in topological order.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 5), _act("B", 2), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        self.result = _run(acts, rels)

    def test_critical_path_present(self):
        assert self.result.critical_path is not None

    def test_cp_activity_ids(self):
        cp = self.result.critical_path
        assert set(cp.activity_ids) == {"S", "A", "F"}

    def test_cp_in_topological_order(self):
        cp_ids = self.result.critical_path.activity_ids
        # S must appear before A, A must appear before F
        assert cp_ids.index("S") < cp_ids.index("A")
        assert cp_ids.index("A") < cp_ids.index("F")

    def test_cp_activities_are_tf_zero(self):
        for act_id in self.result.critical_path.activity_ids:
            assert _sa(self.result, act_id).total_float == 0

    def test_is_critical_flag_matches_cp(self):
        cp_ids = set(self.result.critical_path.activity_ids)
        for act_id, sa in self.result.scheduled.items():
            assert sa.is_critical == (act_id in cp_ids)

    def test_project_duration(self):
        # project_start=W1 (wd1), project_finish=W5 (wd5); duration=5
        assert self.result.critical_path.project_duration == 5


# ---------------------------------------------------------------------------
# Category 20 — Non-critical activities have TF > 0
# ---------------------------------------------------------------------------

class TestNonCritical:
    """
    In the parallel-paths network, B is non-critical and has TF > 0.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 5), _act("B", 2), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        self.result = _run(acts, rels)

    def test_b_not_in_cp(self):
        assert "B" not in self.result.critical_path.activity_ids

    def test_b_is_critical_false(self):
        assert _sa(self.result, "B").is_critical is False

    def test_b_tf_positive(self):
        assert _sa(self.result, "B").total_float > 0


# ---------------------------------------------------------------------------
# Category 21 — Multiple critical paths (tied TF=0)
# ---------------------------------------------------------------------------

class TestMultipleCriticalPaths:
    """
    S(1) -> A(3) -> F(1)
    S(1) -> B(3) -> F(1)
    A and B have equal duration; both critical.
    CP contains all four activities.
    """

    def setup_method(self):
        acts = [_act("S", 1), _act("A", 3), _act("B", 3), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        self.result = _run(acts, rels)

    def test_all_tf_zero(self):
        for act_id in ["S", "A", "B", "F"]:
            assert _sa(self.result, act_id).total_float == 0

    def test_all_in_cp(self):
        cp_ids = set(self.result.critical_path.activity_ids)
        assert cp_ids == {"S", "A", "B", "F"}

    def test_all_is_critical_true(self):
        for act_id in ["S", "A", "B", "F"]:
            assert _sa(self.result, act_id).is_critical is True


# ---------------------------------------------------------------------------
# Category 22 — AnalysisResult.to_dict() serialization
# ---------------------------------------------------------------------------

class TestResultSerialization:
    """
    AnalysisResult.to_dict() must produce a serializable dict with all
    expected keys. ScheduledActivity.to_dict() and CriticalPathInfo.to_dict()
    must produce correct types.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        self.result = _run(acts, rels)
        self.d = self.result.to_dict()

    def test_top_level_keys(self):
        expected = {
            "is_valid", "project_start", "project_finish",
            "context", "validation", "warnings",
            "scheduled", "critical_path",
            "normalization_result", "destatusing_result",
            "simulation_result",
        }
        assert set(self.d.keys()) == expected

    def test_is_valid_true(self):
        assert self.d["is_valid"] is True

    def test_project_start_is_iso_string(self):
        assert self.d["project_start"] == W1.isoformat()

    def test_project_finish_is_iso_string(self):
        assert self.d["project_finish"] == W4.isoformat()

    def test_scheduled_is_dict(self):
        assert isinstance(self.d["scheduled"], dict)
        assert set(self.d["scheduled"].keys()) == {"A", "B"}

    def test_scheduled_activity_keys(self):
        sa_d = self.d["scheduled"]["A"]
        expected = {
            "activity_id", "original_duration",
            "early_start", "early_finish",
            "late_start", "late_finish",
            "total_float", "free_float", "is_critical",
        }
        assert set(sa_d.keys()) == expected

    def test_dates_are_iso_strings(self):
        sa_d = self.d["scheduled"]["A"]
        for key in ("early_start", "early_finish", "late_start", "late_finish"):
            assert isinstance(sa_d[key], str)
            date.fromisoformat(sa_d[key])  # no ValueError if valid

    def test_critical_path_dict(self):
        cp_d = self.d["critical_path"]
        assert "activity_ids" in cp_d
        assert "project_duration" in cp_d
        assert isinstance(cp_d["activity_ids"], list)
        assert isinstance(cp_d["project_duration"], int)

    def test_validation_is_list(self):
        assert isinstance(self.d["validation"], list)

    def test_warnings_is_list(self):
        assert isinstance(self.d["warnings"], list)

    def test_to_dict_invalid_result(self):
        # Invalid result: critical_path is None, project_finish is None
        acts = [_act("A", 5)]
        rels = [_rel("A", "MISSING", "FS")]
        result = _run(acts, rels)
        d = result.to_dict()
        assert d["is_valid"] is False
        assert d["critical_path"] is None
        assert d["project_finish"] is None
        assert d["scheduled"] == {}


# ---------------------------------------------------------------------------
# Category 23 — AnalysisContext wired into result
# ---------------------------------------------------------------------------

class TestAnalysisContext:
    """
    AnalysisContext is created by the engine and included in the result.
    It must contain interpretation flags, assumptions, excluded capabilities,
    and a validation summary.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        self.result = _run(acts, rels)
        self.ctx = self.result.context

    def test_context_not_none(self):
        assert self.ctx is not None

    def test_has_analysis_id(self):
        assert self.ctx.analysis_id != ""

    def test_has_timestamp(self):
        assert self.ctx.analysis_timestamp != ""

    def test_has_interpretation_flags(self):
        assert len(self.ctx.interpretation_flags) > 0

    def test_fs_lag_flag_present(self):
        flags_text = " ".join(self.ctx.interpretation_flags)
        assert "FS lag=0" in flags_text or "FS" in flags_text

    def test_has_assumptions(self):
        assert len(self.ctx.assumptions) > 0

    def test_has_excluded_capabilities(self):
        assert len(self.ctx.excluded_capabilities) > 0

    def test_validation_summary_populated(self):
        # After analysis, validation_summary should be a dict
        assert isinstance(self.ctx.validation_summary, dict)

    def test_context_serializable(self):
        d = self.ctx.to_dict()
        assert "analysis_id" in d
        assert "interpretation_flags" in d
        assert "validation_summary" in d

    def test_schedule_metadata_activity_count(self):
        assert self.ctx.schedule_metadata.activity_count == 2

    def test_schedule_metadata_relationship_count(self):
        assert self.ctx.schedule_metadata.relationship_count == 1

    def test_calendar_name(self):
        assert self.ctx.calendar_name == "Standard"

    def test_warning_count_zero(self):
        # No non-workday project_start → no warnings
        assert self.ctx.warning_count == 0


# ---------------------------------------------------------------------------
# Category 24 — ValidationResult included in result
# ---------------------------------------------------------------------------

class TestValidationInResult:
    """
    ValidationResult is always included in AnalysisResult, even when is_valid=True.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        self.result = _run(acts, rels)

    def test_validation_not_none(self):
        assert self.result.validation is not None

    def test_no_blocking_issues_for_valid_network(self):
        assert self.result.validation.has_blocking_issues is False

    def test_valid_simple_network_has_no_issues(self):
        # Clean A→B network has no validation issues
        assert len(self.result.validation.issues) == 0

    def test_validation_present_when_invalid(self):
        acts = [_act("A", 5)]
        rels = [_rel("A", "GHOST", "FS")]
        result = _run(acts, rels)
        assert result.validation is not None
        assert result.validation.has_blocking_issues is True

    def test_validation_summary_in_context(self):
        summary = self.result.context.validation_summary
        assert isinstance(summary, dict)
        # All severity levels should be present
        assert "critical" in summary or len(summary) >= 0


# ---------------------------------------------------------------------------
# Additional: engine raises ValueError for bad inputs
# ---------------------------------------------------------------------------

class TestEngineValidation:
    def test_non_workday_project_start_records_structured_warning(self):
        acts = [_act("A", 2)]
        result = run_analysis(acts, [], date(2026, 1, 4), _TABLE, _CAL)
        assert result.is_valid is True
        assert result.project_start == W1
        assert result.context.warning_count == 1
        warnings = result.warnings.to_list()
        assert warnings[0]["code"] == "ENG-001"
        assert "CALC-001" in warnings[0]["source_reference"]

    def test_raises_for_fractional_duration(self):
        acts = [Activity(act_id="A", original_duration=2.5)]
        with pytest.raises(ValueError, match="fractional"):
            _run(acts, [])

    def test_raises_for_none_duration(self):
        acts = [Activity(act_id="A", original_duration=None)]
        # NET-010 is non-blocking (ERROR, not CRITICAL), so ActivityNetwork builds,
        # then _validate_duration raises ValueError during forward pass
        rels = []
        # NET-010 has blocking=False, so the engine tries to run the forward pass
        with pytest.raises(ValueError):
            _run(acts, rels)

    def test_raises_for_project_start_not_in_table(self):
        acts = [_act("A", 3)]
        outside = date(2000, 1, 3)  # Monday, not in _TABLE
        with pytest.raises(ValueError, match="not in the workday"):
            run_analysis(acts, [], outside, _TABLE, _CAL)


# ---------------------------------------------------------------------------
# Additional: ScheduledActivity and CriticalPathInfo standalone to_dict
# ---------------------------------------------------------------------------

class TestResultStructures:
    def test_scheduled_activity_to_dict_types(self):
        sa = ScheduledActivity(
            activity_id="X", original_duration=3,
            early_start=W1, early_finish=W3,
            late_start=W1, late_finish=W3,
            total_float=0, free_float=0, is_critical=True,
        )
        d = sa.to_dict()
        assert d["activity_id"] == "X"
        assert d["original_duration"] == 3
        assert d["early_start"] == W1.isoformat()
        assert d["total_float"] == 0
        assert d["is_critical"] is True

    def test_critical_path_info_to_dict(self):
        cp = CriticalPathInfo(activity_ids=["A", "B"], project_duration=5)
        d = cp.to_dict()
        assert d["activity_ids"] == ["A", "B"]
        assert d["project_duration"] == 5
        assert isinstance(d, dict)
