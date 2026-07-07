"""
Tests for INFRA-008: Phase 4 Longest-Path Tracing.

Covers all 15 required test categories:
  1  Single longest path — simple FS chain; no divergence
  2  Parallel unequal paths — longer path wins; shorter branch has TF > 0
  3  Tied paths (CP-002) — two equal-length parallel paths
  4  Two independent chains to same finish (CP-002 + CP-003)
  5  Diamond network (merge point) — single controlling path through join
  6  FS with positive lag — lagged path tracing
  7  SS relationship path reconstruction
  8  FF relationship path reconstruction
  9  SF relationship path reconstruction
  10 Multiple finish nodes, single controller — no CP-003; no CP-002
  11 CriticalPathInfo Phase 4 field expansion
  12 is_critical reflects longest-path membership (not TF=0)
  13 Serialization stability — all expected keys present in to_dict()
  14 Determinism — same inputs produce identical output
  15 CP-001 and CP-004 detection (unit tests of trace_longest_paths)

  Regression:
  16 Phase 3 blocking validation still short-circuits correctly
  17 Phase 3 non-blocking validation still allows analysis
  18 Phase 3 TF=0 activities recorded in tf_zero_activities
  19 Path relationship sequence correctness
  20 Path identifier assignment (CP-1, CP-2, … in deterministic order)
  21 Three-way tied paths
  22 Milestone (OD=0) on controlling path

All fixtures are synthetic. No proprietary schedule data.

Source: AACE 49R-06 §4.2; ADR-005 §7.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import copy
import pytest
from datetime import date

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.engine import run_analysis  # noqa: E402
from scheduleiq.cpm.longest_path import PathInfo, LongestPathResult, trace_longest_paths  # noqa: E402
from scheduleiq.cpm.results import AnalysisResult, CriticalPathInfo, ScheduledActivity  # noqa: E402


# ---------------------------------------------------------------------------
# Shared calendar and workday table
# Same reference as test_engine.py — Jan 2026, Mon-Fri.
# ---------------------------------------------------------------------------

_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2026, 1, 5), date(2026, 3, 31))
_START = date(2026, 1, 5)   # Monday = wd1

W1  = date(2026, 1, 5)   # wd1
W2  = date(2026, 1, 6)   # wd2
W3  = date(2026, 1, 7)   # wd3
W4  = date(2026, 1, 8)   # wd4
W5  = date(2026, 1, 9)   # wd5
W6  = date(2026, 1, 12)  # wd6
W7  = date(2026, 1, 13)  # wd7
W8  = date(2026, 1, 14)  # wd8
W9  = date(2026, 1, 15)  # wd9
W10 = date(2026, 1, 16)  # wd10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _act(act_id: str, od: int = 3) -> Activity:
    return Activity(act_id=act_id, original_duration=float(od))


def _rel(pred: str, succ: str, rel_type: str = "FS", lag: float = 0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _run(activities, relationships, start=None):
    return run_analysis(activities, relationships, start or _START, _TABLE, _CAL)


def _sa(result: AnalysisResult, act_id: str) -> ScheduledActivity:
    return result.scheduled[act_id]


def _cp(result: AnalysisResult) -> CriticalPathInfo:
    return result.critical_path


def _act_sched(act_id: str, es: date, ef: date, od: int = 3) -> Activity:
    """Create an Activity with early_start/early_finish set for unit testing."""
    a = Activity(act_id=act_id, original_duration=float(od))
    a.early_start = es
    a.early_finish = ef
    return a


# ---------------------------------------------------------------------------
# Category 1 — Single longest path (simple FS chain)
# ---------------------------------------------------------------------------

class TestSingleLongestPath:
    """
    A(3) -> FS(lag=0) -> B(2).
    A: ES=W1, EF=W3. B: ES=W3, EF=W4.
    LP: [A, B]. Duration = wt[W4] - wt[W1] + 1 = 4 wd.
    TF=0: {A, B} = LP set. No divergence flags.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B", "FS")]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_method_used(self):
        assert self.cp.method_used == "longest_path"

    def test_activity_ids_is_longest_path(self):
        assert self.cp.activity_ids == ["A", "B"]

    def test_single_controlling_path(self):
        assert len(self.cp.controlling_paths) == 1

    def test_path_id(self):
        assert self.cp.controlling_paths[0]["path_id"] == "CP-1"

    def test_path_activity_ids(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "B"]

    def test_path_duration(self):
        # wt[W4]=4, wt[W1]=1; 4-1+1=4
        assert self.cp.path_duration == 4

    def test_path_relationship_sequence(self):
        rel_seq = self.cp.controlling_paths[0]["relationship_sequence"]
        assert rel_seq == [["A", "B", "FS"]]

    def test_no_tied_paths(self):
        assert self.cp.tied_paths is False

    def test_controlling_finish_nodes(self):
        assert self.cp.controlling_finish_nodes == ["B"]

    def test_tf_zero_activities(self):
        assert self.cp.tf_zero_activities == ["A", "B"]

    def test_no_divergence_flags(self):
        assert self.cp.divergence_flags == []

    def test_is_critical_a(self):
        assert _sa(self.result, "A").is_critical is True

    def test_is_critical_b(self):
        assert _sa(self.result, "B").is_critical is True

    def test_project_duration(self):
        # Overall project duration (project_start to project_finish inclusive)
        assert self.cp.project_duration == 4


# ---------------------------------------------------------------------------
# Category 2 — Parallel unequal paths (longer wins)
# ---------------------------------------------------------------------------

class TestParallelUnequalPaths:
    """
    A(5) -> FS -> C(2) [FS lag=0]
    B(2) -> FS -> C(2) [FS lag=0]
    A: ES=W1, EF=W5. B: ES=W1, EF=W2.
    C: ES=max(W5,W2)=W5, EF=W6.
    Controlling predecessor of C: only A (wt[A.EF]+0=5=wt[C.ES]).
    LP=[A,C]. B.TF=3. No divergence flags.
    """

    def setup_method(self):
        acts = [_act("A", 5), _act("B", 2), _act("C", 2)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_activity_ids_excludes_short_branch(self):
        assert "B" not in self.cp.activity_ids
        assert "A" in self.cp.activity_ids
        assert "C" in self.cp.activity_ids

    def test_single_path(self):
        assert len(self.cp.controlling_paths) == 1

    def test_no_tied_paths(self):
        assert self.cp.tied_paths is False

    def test_path_is_a_c(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "C"]

    def test_b_not_critical(self):
        assert _sa(self.result, "B").is_critical is False

    def test_a_critical(self):
        assert _sa(self.result, "A").is_critical is True

    def test_c_critical(self):
        assert _sa(self.result, "C").is_critical is True

    def test_b_has_positive_tf(self):
        assert _sa(self.result, "B").total_float == 3

    def test_no_divergence_flags(self):
        assert self.cp.divergence_flags == []

    def test_tf_zero_activities(self):
        # TF=0: A and C (B.TF=3)
        assert self.cp.tf_zero_activities == ["A", "C"]


# ---------------------------------------------------------------------------
# Category 3 — Tied paths (CP-002)
# ---------------------------------------------------------------------------

class TestTiedPathsCP002:
    """
    A(3) -> FS -> C(2) and B(3) -> FS -> C(2).
    A and B both control C (both EF=W3, both impose ES=W3 on C).
    Two paths: [A,C] and [B,C]. CP-002 fires.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3), _act("C", 2)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_tied_paths(self):
        assert self.cp.tied_paths is True

    def test_two_controlling_paths(self):
        assert len(self.cp.controlling_paths) == 2

    def test_path_ids(self):
        ids = [p["path_id"] for p in self.cp.controlling_paths]
        assert ids == ["CP-1", "CP-2"]

    def test_path_a_c_present(self):
        sequences = [p["activity_ids"] for p in self.cp.controlling_paths]
        assert ["A", "C"] in sequences

    def test_path_b_c_present(self):
        sequences = [p["activity_ids"] for p in self.cp.controlling_paths]
        assert ["B", "C"] in sequences

    def test_cp002_in_flags(self):
        assert "CP-002" in self.cp.divergence_flags

    def test_cp002_details(self):
        assert "CP-002" in self.cp.divergence_details
        assert len(self.cp.divergence_details["CP-002"]) == 2

    def test_no_cp001_cp003_cp004(self):
        for flag in ["CP-001", "CP-003", "CP-004"]:
            assert flag not in self.cp.divergence_flags

    def test_activity_ids_is_union(self):
        # Union of both paths in topo order
        assert set(self.cp.activity_ids) == {"A", "B", "C"}

    def test_all_critical(self):
        # A, B, C all on at least one controlling path
        for act_id in ["A", "B", "C"]:
            assert _sa(self.result, act_id).is_critical is True

    def test_cp002_warning_present(self):
        assert any("CP-002" in w for w in self.cp.cp_warnings)


# ---------------------------------------------------------------------------
# Category 4 — Two independent chains to same finish (CP-002 + CP-003)
# ---------------------------------------------------------------------------

class TestTwoChainsCP002CP003:
    """
    Chain 1: A(3) -> B(3) [FS]. B.EF = W5.
    Chain 2: C(3) -> D(3) [FS]. D.EF = W5.
    Two controlling finish nodes. Two tied paths. CP-002 + CP-003.
    All four activities have TF=0.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3), _act("C", 3), _act("D", 3)]
        rels = [_rel("A", "B"), _rel("C", "D")]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_two_controlling_finish_nodes(self):
        assert len(self.cp.controlling_finish_nodes) == 2
        assert "B" in self.cp.controlling_finish_nodes
        assert "D" in self.cp.controlling_finish_nodes

    def test_two_paths(self):
        assert len(self.cp.controlling_paths) == 2

    def test_cp002_fires(self):
        assert "CP-002" in self.cp.divergence_flags

    def test_cp003_fires(self):
        assert "CP-003" in self.cp.divergence_flags

    def test_cp003_details_has_both_finish_nodes(self):
        assert set(self.cp.divergence_details.get("CP-003", [])) == {"B", "D"}

    def test_no_cp001_cp004(self):
        assert "CP-001" not in self.cp.divergence_flags
        assert "CP-004" not in self.cp.divergence_flags

    def test_all_four_critical(self):
        for act_id in ["A", "B", "C", "D"]:
            assert _sa(self.result, act_id).is_critical is True

    def test_tf_zero_all_four(self):
        assert set(self.cp.tf_zero_activities) == {"A", "B", "C", "D"}

    def test_cp003_warning_present(self):
        assert any("CP-003" in w for w in self.cp.cp_warnings)


# ---------------------------------------------------------------------------
# Category 5 — Diamond network (merge point)
# ---------------------------------------------------------------------------

class TestDiamondNetwork:
    """
    A(3) -> B(2) [FS] and A(3) -> C(3) [FS]. B and C -> D(2) [FS].
    A.EF=W3. B.EF=W4. C.EF=W5. D.ES=max(W4,W5)=W5. D.EF=W6.
    Controlling predecessor of D: C (W5=W5 ✓), not B (W4≠W5).
    LP = [A, C, D]. B is on the non-critical branch.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2), _act("C", 3), _act("D", 2)]
        rels = [_rel("A", "B"), _rel("A", "C"), _rel("B", "D"), _rel("C", "D")]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_single_controlling_path(self):
        assert len(self.cp.controlling_paths) == 1

    def test_path_is_a_c_d(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "C", "D"]

    def test_b_not_on_lp(self):
        assert "B" not in self.cp.activity_ids

    def test_b_not_critical(self):
        assert _sa(self.result, "B").is_critical is False

    def test_a_critical(self):
        assert _sa(self.result, "A").is_critical is True

    def test_c_critical(self):
        assert _sa(self.result, "C").is_critical is True

    def test_d_critical(self):
        assert _sa(self.result, "D").is_critical is True

    def test_b_positive_tf(self):
        assert _sa(self.result, "B").total_float == 1

    def test_no_divergence_flags(self):
        assert self.cp.divergence_flags == []

    def test_relationship_sequence_correct(self):
        seq = self.cp.controlling_paths[0]["relationship_sequence"]
        # Expect [(A,C,FS), (C,D,FS)]
        assert ["A", "C", "FS"] in seq
        assert ["C", "D", "FS"] in seq

    def test_tf_zero_matches_lp(self):
        # In diamond with single LP, TF=0 = LP set
        assert set(self.cp.tf_zero_activities) == set(self.cp.activity_ids)


# ---------------------------------------------------------------------------
# Category 6 — FS with positive lag
# ---------------------------------------------------------------------------

class TestFSPositiveLagPath:
    """
    A(3) -> FS(lag=2) -> B(3).
    A.ES=W1, A.EF=W3.
    B.ES = apply_lag(W3, 2) = W5. B.EF = W7.
    Controlling check: wt[A.EF]+2 = 3+2 = 5 = wt[B.ES] ✓.
    LP=[A,B]. No divergence.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3)]
        rels = [_rel("A", "B", "FS", lag=2)]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_path_is_a_b(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "B"]

    def test_relationship_type_in_sequence(self):
        seq = self.cp.controlling_paths[0]["relationship_sequence"]
        assert seq == [["A", "B", "FS"]]

    def test_no_divergence(self):
        assert self.cp.divergence_flags == []

    def test_both_critical(self):
        assert _sa(self.result, "A").is_critical is True
        assert _sa(self.result, "B").is_critical is True


# ---------------------------------------------------------------------------
# Category 7 — SS relationship path reconstruction
# ---------------------------------------------------------------------------

class TestSSRelationshipPath:
    """
    A(3) -> SS(lag=0) -> B(5).
    B.ES = A.ES + 0 = W1. B.EF = W5.
    Controlling check (SS): wt[A.ES]+0 = 1 = wt[B.ES] = 1 ✓.
    LP=[A,B]. Project finish = W5.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 5)]
        rels = [_rel("A", "B", "SS", lag=0)]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_path_is_a_b(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "B"]

    def test_relationship_type_ss(self):
        seq = self.cp.controlling_paths[0]["relationship_sequence"]
        assert seq[0][2] == "SS"

    def test_no_divergence(self):
        assert self.cp.divergence_flags == []

    def test_both_critical(self):
        assert _sa(self.result, "A").is_critical is True
        assert _sa(self.result, "B").is_critical is True


# ---------------------------------------------------------------------------
# Category 8 — FF relationship path reconstruction
# ---------------------------------------------------------------------------

class TestFFRelationshipPath:
    """
    A(5) -> FF(lag=0) -> B(3).
    A.ES=W1, A.EF=W5.
    B.EF constrained = A.EF+0 = W5. B.ES = apply_lag(W5, -(3-1)) = W3.
    Controlling check (FF): wt[A.EF]+0 = 5 = wt[B.EF] = 5 ✓.
    LP=[A,B].
    """

    def setup_method(self):
        acts = [_act("A", 5), _act("B", 3)]
        rels = [_rel("A", "B", "FF", lag=0)]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_path_is_a_b(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "B"]

    def test_relationship_type_ff(self):
        seq = self.cp.controlling_paths[0]["relationship_sequence"]
        assert seq[0][2] == "FF"

    def test_no_divergence(self):
        assert self.cp.divergence_flags == []

    def test_both_critical(self):
        assert _sa(self.result, "A").is_critical is True
        assert _sa(self.result, "B").is_critical is True

    def test_b_early_finish(self):
        # B.EF = A.EF = W5 (FF lag=0)
        assert _sa(self.result, "B").early_finish == W5


# ---------------------------------------------------------------------------
# Category 9 — SF relationship path reconstruction
# ---------------------------------------------------------------------------

class TestSFRelationshipPath:
    """
    A(5) -> SF(lag=5) -> B(3).
    SF: B.EF = A.ES + lag = W1 + 5 = W6. B.ES = W6 - 2 = W4.
    A.EF = W5. Project finish = W6 (B is sole controlling finish node).
    Controlling check (SF): wt[A.ES] + 5 = 1 + 5 = 6 = wt[B.EF] ✓.
    LP=[A,B].
    """

    def setup_method(self):
        acts = [_act("A", 5), _act("B", 3)]
        rels = [_rel("A", "B", "SF", lag=5)]
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_path_is_a_b(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "B"]

    def test_relationship_type_sf(self):
        seq = self.cp.controlling_paths[0]["relationship_sequence"]
        assert seq[0][2] == "SF"

    def test_no_divergence(self):
        assert self.cp.divergence_flags == []

    def test_both_critical(self):
        assert _sa(self.result, "A").is_critical is True
        assert _sa(self.result, "B").is_critical is True


# ---------------------------------------------------------------------------
# Category 10 — Single controlling finish node (no CP-003)
# ---------------------------------------------------------------------------

class TestSingleControllingFinishNode:
    """
    A(5)->B(3)[FS] and C(2) isolated.
    B.EF=W7 (controlling finish, EF=project_finish).
    C.EF=W2 ≠ W7 (non-controlling).
    Only B is a controlling finish node → no CP-003.
    LP=[A,B]. C has positive TF.
    """

    def setup_method(self):
        acts = [_act("A", 5), _act("B", 3), _act("C", 2)]
        rels = [_rel("A", "B")]  # C is isolated
        self.result = _run(acts, rels)
        self.cp = _cp(self.result)

    def test_single_controlling_finish(self):
        assert self.cp.controlling_finish_nodes == ["B"]

    def test_no_cp003(self):
        assert "CP-003" not in self.cp.divergence_flags

    def test_c_not_critical(self):
        assert _sa(self.result, "C").is_critical is False

    def test_c_has_positive_tf(self):
        assert _sa(self.result, "C").total_float > 0


# ---------------------------------------------------------------------------
# Category 11 — CriticalPathInfo Phase 4 field expansion
# ---------------------------------------------------------------------------

class TestCriticalPathInfoExpansion:
    """Verify all Phase 4 fields are present on CriticalPathInfo."""

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        result = _run(acts, rels)
        self.cp = result.critical_path

    def test_method_used_present(self):
        assert hasattr(self.cp, "method_used")

    def test_controlling_paths_present(self):
        assert hasattr(self.cp, "controlling_paths")
        assert isinstance(self.cp.controlling_paths, list)

    def test_path_duration_present(self):
        assert hasattr(self.cp, "path_duration")
        assert isinstance(self.cp.path_duration, int)

    def test_tied_paths_present(self):
        assert hasattr(self.cp, "tied_paths")
        assert isinstance(self.cp.tied_paths, bool)

    def test_controlling_finish_nodes_present(self):
        assert hasattr(self.cp, "controlling_finish_nodes")
        assert isinstance(self.cp.controlling_finish_nodes, list)

    def test_tf_zero_activities_present(self):
        assert hasattr(self.cp, "tf_zero_activities")
        assert isinstance(self.cp.tf_zero_activities, list)

    def test_divergence_flags_present(self):
        assert hasattr(self.cp, "divergence_flags")
        assert isinstance(self.cp.divergence_flags, list)

    def test_divergence_details_present(self):
        assert hasattr(self.cp, "divergence_details")
        assert isinstance(self.cp.divergence_details, dict)

    def test_cp_warnings_present(self):
        assert hasattr(self.cp, "cp_warnings")
        assert isinstance(self.cp.cp_warnings, list)

    def test_cp_assumptions_present(self):
        assert hasattr(self.cp, "cp_assumptions")
        assert isinstance(self.cp.cp_assumptions, list)
        assert len(self.cp.cp_assumptions) > 0

    def test_phase3_activity_ids_still_present(self):
        assert hasattr(self.cp, "activity_ids")

    def test_phase3_project_duration_still_present(self):
        assert hasattr(self.cp, "project_duration")


# ---------------------------------------------------------------------------
# Category 12 — is_critical reflects longest-path membership
# ---------------------------------------------------------------------------

class TestIsCriticalReflectsLongestPath:
    """
    In Phase 4, ScheduledActivity.is_critical reflects LP membership.
    For A(5)->C(2) and B(2)->C(2): only A and C are on LP; B.is_critical=False
    even though in Phase 3 it might have been on a TF-based path.
    """

    def setup_method(self):
        # Parallel: A(5)→C(2) and B(2)→C(2). A is controlling, B is not.
        acts = [_act("A", 5), _act("B", 2), _act("C", 2)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result = _run(acts, rels)

    def test_a_is_critical(self):
        assert _sa(self.result, "A").is_critical is True

    def test_b_is_not_critical(self):
        assert _sa(self.result, "B").is_critical is False

    def test_c_is_critical(self):
        assert _sa(self.result, "C").is_critical is True

    def test_b_tf_is_positive(self):
        assert _sa(self.result, "B").total_float > 0

    def test_critical_activities_match_lp(self):
        lp_ids = set(self.result.critical_path.activity_ids)
        critical_ids = {
            act_id for act_id, sa in self.result.scheduled.items()
            if sa.is_critical
        }
        assert critical_ids == lp_ids


# ---------------------------------------------------------------------------
# Category 13 — Serialization stability
# ---------------------------------------------------------------------------

class TestSerializationStability:
    """All expected keys present in to_dict() output."""

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        result = _run(acts, rels)
        self.d = result.to_dict()
        self.cp_d = self.d["critical_path"]

    def test_top_level_keys(self):
        for key in ["is_valid", "project_start", "project_finish",
                    "context", "validation", "warnings", "scheduled", "critical_path"]:
            assert key in self.d

    def test_critical_path_phase3_keys(self):
        for key in ["activity_ids", "project_duration"]:
            assert key in self.cp_d

    def test_critical_path_phase4_keys(self):
        for key in ["method_used", "controlling_paths", "path_duration",
                    "tied_paths", "controlling_finish_nodes", "tf_zero_activities",
                    "divergence_flags", "divergence_details", "cp_warnings",
                    "cp_assumptions"]:
            assert key in self.cp_d, f"Missing key: {key}"

    def test_controlling_paths_is_list(self):
        assert isinstance(self.cp_d["controlling_paths"], list)

    def test_each_path_has_required_keys(self):
        for path in self.cp_d["controlling_paths"]:
            for key in ["path_id", "activity_ids", "relationship_sequence", "path_duration"]:
                assert key in path, f"Path missing key: {key}"

    def test_date_fields_are_iso_strings(self):
        assert isinstance(self.d["project_start"], str)
        assert isinstance(self.d["project_finish"], str)

    def test_method_used_is_string(self):
        assert isinstance(self.cp_d["method_used"], str)
        assert self.cp_d["method_used"] == "longest_path"


# ---------------------------------------------------------------------------
# Category 14 — Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same inputs always produce the same output."""

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3), _act("C", 2)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result1 = _run(acts, rels)
        self.result2 = _run(acts, rels)

    def test_controlling_paths_identical(self):
        paths1 = [p["activity_ids"] for p in self.result1.critical_path.controlling_paths]
        paths2 = [p["activity_ids"] for p in self.result2.critical_path.controlling_paths]
        assert paths1 == paths2

    def test_divergence_flags_identical(self):
        assert self.result1.critical_path.divergence_flags == \
               self.result2.critical_path.divergence_flags

    def test_activity_ids_identical(self):
        assert self.result1.critical_path.activity_ids == \
               self.result2.critical_path.activity_ids

    def test_path_ids_identical(self):
        ids1 = [p["path_id"] for p in self.result1.critical_path.controlling_paths]
        ids2 = [p["path_id"] for p in self.result2.critical_path.controlling_paths]
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# Category 15 — CP-001 and CP-004 detection (unit tests of trace_longest_paths)
#
# CP-001 and CP-004 cannot arise from unconstrained Retained Logic networks
# (the backward pass preserves TF=0 exactly along the LP). These unit tests
# verify the detection logic by calling trace_longest_paths directly with
# crafted inputs that simulate constraint-driven scenarios (e.g., date
# constraints — LIM-028, not yet implemented).
# ---------------------------------------------------------------------------

class TestCP001Detection:
    """
    Unit test of CP-001 flag: TF=0 activity NOT on any longest path.

    Simulates a scenario that would arise with date constraints:
    A→C[FS] is the controlling chain. B is isolated with EF < project_finish.
    total_float manually set to 0 for B to test the detection logic.

    Expected: CP-001 fires with B in divergence_details.
    """

    def setup_method(self):
        # Build scheduled dict with early_start/early_finish
        self.scheduled = {
            "A": _act_sched("A", W1, W3, od=3),
            "B": _act_sched("B", W1, W2, od=2),   # B.EF=W2 < project_finish=W5
            "C": _act_sched("C", W3, W5, od=3),
        }
        # A→C FS; B is isolated
        rel_ac = _rel("A", "C", "FS")
        self.predecessors = {"A": [], "B": [], "C": [rel_ac]}
        self.successors = {"A": [rel_ac], "B": [], "C": []}
        self.topo_order = ["A", "B", "C"]
        # Artificially set B.TF=0 (simulates constraint-driven scenario)
        self.total_float = {"A": 0, "B": 0, "C": 0}
        self.project_finish = W5

    def test_cp001_fires(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert "CP-001" in lp.divergence_flags

    def test_cp001_details_contains_b(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert "B" in lp.divergence_details["CP-001"]

    def test_cp001_warning_message(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert any("CP-001" in w for w in lp.cp_warnings)

    def test_b_not_on_lp(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert "B" not in lp.longest_path_activities


class TestCP004Detection:
    """
    Unit test of CP-004 flag: LP activity with positive total float.

    Simulates a scenario that would arise with date constraints:
    A→B[FS] and A→C[FS]; both B and C are controlling finish nodes.
    total_float manually set: A=2 (positive), B=0, C=0.

    Expected: CP-004 fires with A in divergence_details.
    """

    def setup_method(self):
        # A.EF=W3; B.ES=W3, B.EF=W5; C.ES=W3, C.EF=W5
        self.scheduled = {
            "A": _act_sched("A", W1, W3, od=3),
            "B": _act_sched("B", W3, W5, od=3),
            "C": _act_sched("C", W3, W5, od=3),
        }
        rel_ab = _rel("A", "B", "FS")
        rel_ac = _rel("A", "C", "FS")
        self.predecessors = {"A": [], "B": [rel_ab], "C": [rel_ac]}
        self.successors = {"A": [rel_ab, rel_ac], "B": [], "C": []}
        self.topo_order = ["A", "B", "C"]
        # A has positive TF artificially (constraint-driven scenario)
        self.total_float = {"A": 2, "B": 0, "C": 0}
        self.project_finish = W5

    def test_cp004_fires(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert "CP-004" in lp.divergence_flags

    def test_cp004_details_contains_a(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert "A" in lp.divergence_details["CP-004"]

    def test_a_still_on_lp(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert "A" in lp.longest_path_activities

    def test_cp004_warning_message(self):
        lp = trace_longest_paths(
            self.scheduled, self.predecessors, self.successors,
            self.topo_order, self.total_float, _TABLE, self.project_finish
        )
        assert any("CP-004" in w for w in lp.cp_warnings)


# ---------------------------------------------------------------------------
# Category 16 — Phase 3 regression: blocking validation
# ---------------------------------------------------------------------------

class TestRegressionBlockingValidation:
    """Blocking validation still short-circuits; critical_path is None."""

    def setup_method(self):
        # Self-referential relationship → NET-009 (CRITICAL)
        acts = [_act("A", 3)]
        rels = [Relationship(pred_id="A", succ_id="A", rel_type="FS")]
        self.result = _run(acts, rels)

    def test_is_valid_false(self):
        assert self.result.is_valid is False

    def test_critical_path_none(self):
        assert self.result.critical_path is None

    def test_scheduled_empty(self):
        assert self.result.scheduled == {}


# ---------------------------------------------------------------------------
# Category 17 — Phase 3 regression: non-blocking validation
# ---------------------------------------------------------------------------

class TestRegressionNonBlocking:
    """Non-blocking issues still allow analysis; LP tracing still runs."""

    def setup_method(self):
        # Multiple start nodes → NET-003 (WARNING, non-blocking)
        acts = [_act("A", 3), _act("B", 3), _act("C", 2)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result = _run(acts, rels)

    def test_is_valid(self):
        assert self.result.is_valid is True

    def test_critical_path_not_none(self):
        assert self.result.critical_path is not None

    def test_method_used_longest_path(self):
        assert self.result.critical_path.method_used == "longest_path"


# ---------------------------------------------------------------------------
# Category 18 — TF=0 activities recorded in tf_zero_activities
# ---------------------------------------------------------------------------

class TestTFZeroActivitiesRecorded:
    """tf_zero_activities field contains all TF=0 activities."""

    def setup_method(self):
        acts = [_act("A", 5), _act("B", 2), _act("C", 2)]
        rels = [_rel("A", "C"), _rel("B", "C")]
        self.result = _run(acts, rels)
        self.cp = self.result.critical_path

    def test_tf_zero_contains_a_and_c(self):
        # A(5) controls C; A.TF=0, C.TF=0
        assert "A" in self.cp.tf_zero_activities
        assert "C" in self.cp.tf_zero_activities

    def test_tf_zero_excludes_b(self):
        # B.TF=3; not in tf_zero_activities
        assert "B" not in self.cp.tf_zero_activities

    def test_tf_zero_matches_scheduled(self):
        expected = {
            act_id for act_id, sa in self.result.scheduled.items()
            if sa.total_float == 0
        }
        assert set(self.cp.tf_zero_activities) == expected


# ---------------------------------------------------------------------------
# Category 19 — Path relationship sequence correctness
# ---------------------------------------------------------------------------

class TestPathRelationshipSequence:
    """Three-activity chain: verify full relationship sequence in output."""

    def setup_method(self):
        # A(3)→B(2)[FS]→C(3)[FS]
        acts = [_act("A", 3), _act("B", 2), _act("C", 3)]
        rels = [_rel("A", "B", "FS"), _rel("B", "C", "FS")]
        self.result = _run(acts, rels)
        self.path = self.result.critical_path.controlling_paths[0]

    def test_path_has_three_activities(self):
        assert self.path["activity_ids"] == ["A", "B", "C"]

    def test_relationship_sequence_length(self):
        # Two relationships for three activities
        assert len(self.path["relationship_sequence"]) == 2

    def test_first_relationship(self):
        assert self.path["relationship_sequence"][0] == ["A", "B", "FS"]

    def test_second_relationship(self):
        assert self.path["relationship_sequence"][1] == ["B", "C", "FS"]


# ---------------------------------------------------------------------------
# Category 20 — Path identifier assignment (deterministic)
# ---------------------------------------------------------------------------

class TestPathIdentifierAssignment:
    """CP-1 is assigned to the lexicographically first path sequence."""

    def setup_method(self):
        # X(3)→Z(2) and Y(3)→Z(2): two tied paths [X,Z] and [Y,Z]
        acts = [_act("X", 3), _act("Y", 3), _act("Z", 2)]
        rels = [_rel("X", "Z"), _rel("Y", "Z")]
        self.result = _run(acts, rels)
        self.cp = self.result.critical_path

    def test_cp1_is_x_z(self):
        # [X,Z] < [Y,Z] lexicographically
        assert self.cp.controlling_paths[0]["path_id"] == "CP-1"
        assert self.cp.controlling_paths[0]["activity_ids"] == ["X", "Z"]

    def test_cp2_is_y_z(self):
        assert self.cp.controlling_paths[1]["path_id"] == "CP-2"
        assert self.cp.controlling_paths[1]["activity_ids"] == ["Y", "Z"]


# ---------------------------------------------------------------------------
# Category 21 — Three-way tied paths
# ---------------------------------------------------------------------------

class TestThreeWayTied:
    """
    A(3), B(3), C(3) all → D(2) [FS]. Three tied controlling paths.
    All three control D (same EF). CP-002 fires with 3 paths.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 3), _act("C", 3), _act("D", 2)]
        rels = [_rel("A", "D"), _rel("B", "D"), _rel("C", "D")]
        self.result = _run(acts, rels)
        self.cp = self.result.critical_path

    def test_three_controlling_paths(self):
        assert len(self.cp.controlling_paths) == 3

    def test_cp002_fires(self):
        assert "CP-002" in self.cp.divergence_flags

    def test_three_path_ids(self):
        ids = [p["path_id"] for p in self.cp.controlling_paths]
        assert ids == ["CP-1", "CP-2", "CP-3"]

    def test_all_start_nodes_critical(self):
        for act_id in ["A", "B", "C", "D"]:
            assert _sa(self.result, act_id).is_critical is True

    def test_paths_in_deterministic_order(self):
        # Paths sorted lexicographically: [A,D], [B,D], [C,D]
        sequences = [p["activity_ids"] for p in self.cp.controlling_paths]
        assert sequences == [["A", "D"], ["B", "D"], ["C", "D"]]


# ---------------------------------------------------------------------------
# Category 22 — Milestone (OD=0) on controlling path
# ---------------------------------------------------------------------------

class TestMilestoneOnPath:
    """
    A(3) -> MILE(0) [FS] -> B(2) [FS].
    Milestone: ES=EF=W3. MILE is on the LP.
    """

    def setup_method(self):
        acts = [_act("A", 3), _act("MILE", 0), _act("B", 2)]
        rels = [_rel("A", "MILE"), _rel("MILE", "B")]
        self.result = _run(acts, rels)
        self.cp = self.result.critical_path

    def test_milestone_on_lp(self):
        assert "MILE" in self.cp.activity_ids

    def test_milestone_is_critical(self):
        assert _sa(self.result, "MILE").is_critical is True

    def test_path_includes_all_three(self):
        assert self.cp.controlling_paths[0]["activity_ids"] == ["A", "MILE", "B"]

    def test_no_divergence(self):
        assert self.cp.divergence_flags == []


# ---------------------------------------------------------------------------
# PathInfo and LongestPathResult unit tests
# ---------------------------------------------------------------------------

class TestPathInfoDataclass:
    """PathInfo construction and serialization."""

    def test_to_dict_keys(self):
        pi = PathInfo(
            path_id="CP-1",
            activity_ids=["A", "B"],
            relationship_sequence=[("A", "B", "FS")],
            path_duration=5,
        )
        d = pi.to_dict()
        assert d["path_id"] == "CP-1"
        assert d["activity_ids"] == ["A", "B"]
        assert d["relationship_sequence"] == [["A", "B", "FS"]]
        assert d["path_duration"] == 5

    def test_to_dict_isolates_lists(self):
        pi = PathInfo("CP-1", ["A", "B"], [("A", "B", "FS")], 5)
        d1 = pi.to_dict()
        d2 = pi.to_dict()
        d1["activity_ids"].append("X")
        assert d2["activity_ids"] == ["A", "B"]


class TestLongestPathResultSerialization:
    """LongestPathResult.to_dict() coverage."""

    def setup_method(self):
        acts = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        result = _run(acts, rels)
        # Access via critical_path (which stores serialized form)
        self.cp = result.critical_path

    def test_cp_assumptions_non_empty(self):
        assert len(self.cp.cp_assumptions) > 0

    def test_controlling_finish_node_is_b(self):
        assert self.cp.controlling_finish_nodes == ["B"]

    def test_path_duration_positive(self):
        assert self.cp.path_duration > 0
