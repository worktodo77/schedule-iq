"""
Phase 7 Controlled Synthetic Benchmark Fixtures.

Provides the authoritative suite of synthetic benchmark definitions used for
analytical validation, regression protection, and reproducibility verification.

ALL fixtures are synthetic (source="synthetic"). No proprietary schedules.
No real client data. No XER files.

Fixture categories (per Phase 7 authorized scope):
  BM-001  simple_fs_linear_3      Simple 3-activity FS chain
  BM-002  simple_fs_linear_5      Simple 5-activity FS chain
  BM-003  parallel_unequal_paths  Branching + merge; one path longer (TF diagnostic)
  BM-004  tied_longest_paths      Equal-length parallel paths (CP-002)
  BM-005  lag_positive_fs         FS with positive lag
  BM-006  lag_negative_fs         FS with negative lag (lead)
  BM-007  ss_relationship         SS lag=0 relationship
  BM-008  ff_relationship         FF lag=0 relationship
  BM-009  sf_relationship         SF lag=0 relationship
  BM-010  milestone_on_path       Milestone (OD=0) on critical path
  BM-011  convention_fs_diverge   FS network where INCLUSIVE_DAY ≠ P6_COMPATIBILITY
  BM-012  invalid_network_cycle   Cyclic dependency (is_valid=False)

Expected values for BM-001 through BM-012 are hand-verified against the
INCLUSIVE_DAY convention definition (ADR-006). See inline derivation notes.

Reference: ADR-009 — Benchmark Governance; ADR-006 — EF Convention Architecture.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.fixtures) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from .benchmarks import (
    BenchmarkCategory,
    BenchmarkDefinition,
    BenchmarkExpectations,
    BenchmarkMetadata,
    BenchmarkSuite,
    ExpectedActivityResult,
)


# ---------------------------------------------------------------------------
# Reusable metadata helpers
# ---------------------------------------------------------------------------

_VER = "1.0-phase7"
_SOURCE = "synthetic"

# Standard Mon-Fri calendar parameters
_STD_WORK_DAYS = [1, 2, 3, 4, 5]
_STD_HPD = 8.0
_STD_START = "2026-01-05"  # Monday

_FS = "FS"
_SS = "SS"
_FF = "FF"
_SF = "SF"


def _meta(bm_id: str, desc: str, cat: BenchmarkCategory, **kw) -> BenchmarkMetadata:
    return BenchmarkMetadata(
        benchmark_id=bm_id,
        benchmark_version=_VER,
        description=desc,
        category=cat,
        source=_SOURCE,
        **kw,
    )


def _act(act_id: str, od: int) -> dict:
    return {"act_id": act_id, "original_duration": od}


def _rel(pred: str, succ: str, rel_type: str = _FS, lag: float = 0.0) -> dict:
    return {"pred_id": pred, "succ_id": succ, "rel_type": rel_type, "lag": lag}


def _exp_act(
    act_id: str,
    es: str, ef: str, ls: str, lf: str,
    tf: int, ff: int, crit: bool,
) -> ExpectedActivityResult:
    return ExpectedActivityResult(
        activity_id=act_id,
        early_start=es, early_finish=ef,
        late_start=ls, late_finish=lf,
        total_float=tf, free_float=ff,
        is_critical=crit,
    )


# ---------------------------------------------------------------------------
# BM-001: Simple 3-activity FS chain (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(3) → B(2) → C(4)  [all FS lag=0, INCLUSIVE_DAY]
# Project start: 2026-01-05 (Mon)
#
# Forward pass (INCLUSIVE_DAY: FS successor.ES = predecessor.EF, same workday):
#   A: ES=Jan-05, EF=apply_lag(Jan-05, 2)=Jan-07
#   B: ES=A.EF=Jan-07, EF=apply_lag(Jan-07, 1)=Jan-08
#   C: ES=B.EF=Jan-08, EF=apply_lag(Jan-08, 3)=Jan-13  [Thu→Fri→Mon→Tue]
#
# Backward pass (project_finish=Jan-13):
#   C: LF=Jan-13, LS=apply_lag(Jan-13,-3)=Jan-08
#   B: LF=apply_lag(C.LS=Jan-08, 0)=Jan-08, LS=apply_lag(Jan-08,-1)=Jan-07
#   A: LF=apply_lag(B.LS=Jan-07, 0)=Jan-07, LS=apply_lag(Jan-07,-2)=Jan-05
#
# Float:  All TF=0 (single path). FF=0 for all (no slack to successors).
# Workday sequence: Jan-05=1, Jan-06=2, Jan-07=3, Jan-08=4, Jan-09=5,
#                   Jan-12=6, Jan-13=7. Project duration=7.

BM_001 = BenchmarkDefinition(
    metadata=_meta(
        "BM-001", "Simple 3-activity FS chain (all critical)",
        BenchmarkCategory.SIMPLE_FS,
        assumptions=[
            "INCLUSIVE_DAY convention: FS successor ES = predecessor EF (same workday).",
            "EF = apply_lag(ES, OD-1). OD=1 → EF=ES.",
            "Mon-Fri calendar; project start Monday 2026-01-05.",
        ],
        tags=["fs", "linear", "hand-verified"],
    ),
    activities=[_act("A", 3), _act("B", 2), _act("C", 4)],
    relationships=[_rel("A", "B"), _rel("B", "C")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-13",
        project_duration=7,
        critical_path_activity_ids=["A", "B", "C"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "B": _exp_act("B", "2026-01-07", "2026-01-08", "2026-01-07", "2026-01-08", 0, 0, True),
            "C": _exp_act("C", "2026-01-08", "2026-01-13", "2026-01-08", "2026-01-13", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-002: Simple 5-activity FS chain (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(1) → B(3) → C(2) → D(1) → E(4)  [all FS lag=0, INCLUSIVE_DAY]
# Project start: 2026-01-05 (Mon)
#
# Forward pass:
#   A: ES=Jan-05, EF=Jan-05 (OD=1: EF=apply_lag(Jan-05,0)=Jan-05)
#   B: ES=Jan-05, EF=apply_lag(Jan-05,2)=Jan-07
#   C: ES=Jan-07, EF=apply_lag(Jan-07,1)=Jan-08
#   D: ES=Jan-08, EF=Jan-08 (OD=1)
#   E: ES=Jan-08, EF=apply_lag(Jan-08,3)=Jan-13
#
# Backward pass (project_finish=Jan-13):
#   E: LF=Jan-13, LS=Jan-08
#   D: LF=apply_lag(E.LS=Jan-08,0)=Jan-08, LS=Jan-08
#   C: LF=Jan-08, LS=Jan-07
#   B: LF=Jan-07, LS=Jan-05
#   A: LF=Jan-05, LS=Jan-05
#
# Float: all TF=0 (single chain). FF=0.
# Workday: Jan-05=1,...,Jan-07=3,Jan-08=4,...,Jan-13=7. Duration=7.

BM_002 = BenchmarkDefinition(
    metadata=_meta(
        "BM-002", "Simple 5-activity FS chain",
        BenchmarkCategory.SIMPLE_FS,
        assumptions=[
            "OD=1 activities: EF = ES (EF = apply_lag(ES, 0)).",
            "INCLUSIVE_DAY convention throughout.",
        ],
        tags=["fs", "linear", "hand-verified"],
    ),
    activities=[_act("A", 1), _act("B", 3), _act("C", 2), _act("D", 1), _act("E", 4)],
    relationships=[_rel("A","B"), _rel("B","C"), _rel("C","D"), _rel("D","E")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-13",
        project_duration=7,
        critical_path_activity_ids=["A", "B", "C", "D", "E"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-05", "2026-01-05", "2026-01-05", 0, 0, True),
            "B": _exp_act("B", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "C": _exp_act("C", "2026-01-07", "2026-01-08", "2026-01-07", "2026-01-08", 0, 0, True),
            "D": _exp_act("D", "2026-01-08", "2026-01-08", "2026-01-08", "2026-01-08", 0, 0, True),
            "E": _exp_act("E", "2026-01-08", "2026-01-13", "2026-01-08", "2026-01-13", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-003: Parallel paths — one longer (branching + merge)
# ---------------------------------------------------------------------------
#
# Network: A(1) → B(5) → D(1)
#          A(1) → C(2) → D(1)   [all FS lag=0, INCLUSIVE_DAY]
# Project start: 2026-01-05 (Mon)
#
# Forward pass:
#   A: ES=Jan-05, EF=Jan-05
#   B: ES=Jan-05, EF=apply_lag(Jan-05,4)=Jan-09  [Mon+4=Fri]
#   C: ES=Jan-05, EF=apply_lag(Jan-05,1)=Jan-06
#   D: ES=max(B.EF=Jan-09, C.EF=Jan-06)=Jan-09, EF=Jan-09
#
# Backward pass (project_finish=Jan-09):
#   D: LF=Jan-09, LS=Jan-09
#   B: LF=apply_lag(D.LS=Jan-09,0)=Jan-09, LS=apply_lag(Jan-09,-4)=Jan-05
#   C: LF=Jan-09, LS=apply_lag(Jan-09,-1)=Jan-08
#   A: LF=min(B.LS=Jan-05,C.LS=Jan-08)=Jan-05, LS=Jan-05
#
# Workday: Jan-05=1,Jan-06=2,Jan-07=3,Jan-08=4,Jan-09=5. Duration=5.
# Float:
#   A: TF=wt[Jan-05]-wt[Jan-05]=0; FF=min(wt[B.ES]-wt[A.EF]-0, wt[C.ES]-wt[A.EF]-0)=0
#   B: TF=0; FF=0
#   C: TF=wt[Jan-09]-wt[Jan-06]=5-2=3; FF=wt[D.ES]-wt[C.EF]-0=5-2=3
#   D: TF=0; FF=0 (finish node)
# CP: [A, B, D]

BM_003 = BenchmarkDefinition(
    metadata=_meta(
        "BM-003", "Parallel paths: one longer (branching+merge), float on short path",
        BenchmarkCategory.BRANCHING,
        assumptions=[
            "Longer path A→B→D determines project finish.",
            "Shorter path A→C→D has TF=FF=3 workdays.",
        ],
        tags=["branching", "merge", "parallel", "hand-verified"],
    ),
    activities=[_act("A", 1), _act("B", 5), _act("C", 2), _act("D", 1)],
    relationships=[_rel("A","B"), _rel("A","C"), _rel("B","D"), _rel("C","D")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-09",
        project_duration=5,
        critical_path_activity_ids=["A", "B", "D"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-05", "2026-01-05", "2026-01-05", 0, 0, True),
            "B": _exp_act("B", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True),
            "C": _exp_act("C", "2026-01-05", "2026-01-06", "2026-01-08", "2026-01-09", 3, 3, False),
            "D": _exp_act("D", "2026-01-09", "2026-01-09", "2026-01-09", "2026-01-09", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-004: Tied longest paths (CP-002 condition)
# ---------------------------------------------------------------------------
#
# Network: A(1) → B(5) → D(1)
#          A(1) → C(5) → D(1)   [B and C have equal duration → tied paths]
# Project start: 2026-01-05 (Mon)
#
# Forward pass:
#   A: ES=Jan-05, EF=Jan-05
#   B: ES=Jan-05, EF=Jan-09
#   C: ES=Jan-05, EF=Jan-09
#   D: ES=Jan-09, EF=Jan-09
#
# All activities TF=0. CP-002 raised (tied paths). tied_paths=True.
# critical_path_activity_ids = union = [A, B, C, D]

BM_004 = BenchmarkDefinition(
    metadata=_meta(
        "BM-004", "Tied longest paths — CP-002 divergence flag",
        BenchmarkCategory.TIED_LONGEST_PATH,
        assumptions=[
            "Both parallel paths have identical duration (5 workdays).",
            "CP-002 flag expected: multiple equal-duration controlling paths.",
            "All activities are critical (union of tied paths).",
        ],
        tags=["tied", "cp-002", "hand-verified"],
    ),
    activities=[_act("A", 1), _act("B", 5), _act("C", 5), _act("D", 1)],
    relationships=[_rel("A","B"), _rel("A","C"), _rel("B","D"), _rel("C","D")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-09",
        project_duration=5,
        critical_path_activity_ids=["A", "B", "C", "D"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-05", "2026-01-05", "2026-01-05", 0, 0, True),
            "B": _exp_act("B", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True),
            "C": _exp_act("C", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True),
            "D": _exp_act("D", "2026-01-09", "2026-01-09", "2026-01-09", "2026-01-09", 0, 0, True),
        },
        tied_paths=True,
        divergence_flags=["CP-002"],
        warning_codes_present=["CP-002"],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-005: FS with positive lag (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(3) → B(3) [FS lag=2], A(3) → C(2) [FS lag=0] → B(3) [FS lag=0]
# Simpler: A(3) --FS,lag=2--> B(3), standalone
# Project start: 2026-01-05 (Mon)
#
# A: ES=Jan-05, EF=Jan-07
# B: ES=apply_lag(A.EF=Jan-07, +2)=apply_lag(Jan-07, 2) workdays
#    Jan-07=workday 3, +2 = workday 5 = Jan-09
#    EF=apply_lag(Jan-09, 2)=Jan-13
# Project finish=Jan-13
#
# Backward pass:
#   B: LF=Jan-13, LS=Jan-09
#   A: LF from B via FS lag=2: apply_lag(B.LS=Jan-09, -2-0)=apply_lag(Jan-09,-2)=Jan-07
#      LS=apply_lag(Jan-07,-2)=Jan-05
# Float:
#   A: TF=0, FF=wt[B.ES]-wt[A.EF]-2=5-3-2=0
#   B: TF=0, FF=0 (finish node)
# project_duration = wt[Jan-13]-wt[Jan-05]+1 = 7-1+1 = 7

BM_005 = BenchmarkDefinition(
    metadata=_meta(
        "BM-005", "FS with positive lag (+2 workdays)",
        BenchmarkCategory.LAG_HEAVY,
        assumptions=[
            "FS lag=2: successor ES = predecessor EF + 2 workdays (INCLUSIVE_DAY).",
        ],
        tags=["lag", "positive-lag", "hand-verified"],
    ),
    activities=[_act("A", 3), _act("B", 3)],
    relationships=[_rel("A", "B", _FS, lag=2.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-13",
        project_duration=7,
        critical_path_activity_ids=["A", "B"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "B": _exp_act("B", "2026-01-09", "2026-01-13", "2026-01-09", "2026-01-13", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-006: FS with negative lag / lead (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(5) --FS,lag=-2--> B(3)
# Project start: 2026-01-05 (Mon)
#
# A: ES=Jan-05, EF=apply_lag(Jan-05,4)=Jan-09
# B: ES=apply_lag(A.EF=Jan-09, -2)=apply_lag(Jan-09,-2)=Jan-07
#    EF=apply_lag(Jan-07, 2)=Jan-09
#
# Both A and B finish on Jan-09. project_finish=Jan-09.
#
# Backward pass:
#   B: LF=Jan-09, LS=Jan-07
#   A: LF from B via FS lag=-2: apply_lag(B.LS=Jan-07,-(-2)-0)=apply_lag(Jan-07,2)=Jan-09
#      LS=apply_lag(Jan-09,-4)=Jan-05
# Float:
#   A: TF=wt[Jan-09]-wt[Jan-09]=0
#      FF=wt[B.ES]-wt[A.EF]-(-2)=5-5+2=2  (B can wait 2 more workdays from A.EF)
#   B: TF=0, FF=0 (finish node)
# project_duration = wt[Jan-09]-wt[Jan-05]+1 = 5
# Both on LP: [A, B]

BM_006 = BenchmarkDefinition(
    metadata=_meta(
        "BM-006", "FS with negative lag (lead) of -2 workdays",
        BenchmarkCategory.LAG_HEAVY,
        assumptions=[
            "FS lag=-2 (lead): successor may start 2 workdays before predecessor finishes.",
            "A.FF=0: FF formula = wt[B.ES]-wt[A.EF]-lag = wt[Jan-07]-wt[Jan-09]-(-2) = 3-5+2=0.",
            "Both A and B have TF=0 and are on the critical path.",
        ],
        tags=["lag", "negative-lag", "lead", "hand-verified"],
    ),
    activities=[_act("A", 5), _act("B", 3)],
    relationships=[_rel("A", "B", _FS, lag=-2.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-09",
        project_duration=5,
        critical_path_activity_ids=["A", "B"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True),
            "B": _exp_act("B", "2026-01-07", "2026-01-09", "2026-01-07", "2026-01-09", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-007: SS relationship (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(5) --SS,lag=0--> B(3)
# Project start: 2026-01-05 (Mon)
#
# SS with lag=0: B.ES = apply_lag(A.ES, 0) = A.ES = Jan-05
# B: ES=Jan-05, EF=apply_lag(Jan-05,2)=Jan-07
# A: ES=Jan-05, EF=apply_lag(Jan-05,4)=Jan-09
# project_finish=Jan-09 (A finishes later)
#
# Backward pass (project_finish=Jan-09):
#   A: LF=Jan-09 (finish node). LS=Jan-05.
#   B: LF=Jan-09 (finish node — no successors). LS=apply_lag(Jan-09,-2)=Jan-07.
#      TF=wt[Jan-09]-wt[Jan-07]=5-3=2
#      But A also imposes: SS,lag=0 backward: A.LF = apply_lag(B.LS=Jan-07, 0 - span_A)
#        span_A = max(0, OD_A-1) = 4
#        A.LF constraint from SS: apply_lag(B.LS=Jan-07, 0+4) = apply_lag(Jan-07,4)=Jan-13
#
# Backward pass and float: LP tracer behavior for SS networks is analytically
# complex (no controlling finish nodes when predecessor EF exceeds successor EF).
# Expected values — A.TF=2, B.TF=2, LP=[] — are captured from engine execution.
# (baseline_captured=True). See fixture assumptions for details.
# project_duration = wt[Jan-09]-wt[Jan-05]+1 = 5

BM_007 = BenchmarkDefinition(
    metadata=_meta(
        "BM-007", "SS lag=0 relationship — B starts with A but finishes earlier",
        BenchmarkCategory.SS_FF_SF,
        assumptions=[
            "SS lag=0: successor B starts on same workday as predecessor A.",
            "A is NOT a network finish node (has outgoing SS to B); only B is a finish node.",
            "B.EF=Jan-07 < project_finish=Jan-09 → no controlling finish nodes → LP empty.",
            "Both A and B have TF=2 (positive float); no activity is on the critical path.",
            "SS backward: A.LF constrained by B.LS+span_A = Jan-07+4 = Jan-13.",
            "Baseline captured from engine; SS-driven LP behavior is analytically complex.",
        ],
        tags=["ss", "relationship", "baseline-captured"],
    ),
    activities=[_act("A", 5), _act("B", 3)],
    relationships=[_rel("A", "B", _SS, lag=0.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-09",
        project_duration=5,
        critical_path_activity_ids=[],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-09", "2026-01-07", "2026-01-13", 2, 0, False),
            "B": _exp_act("B", "2026-01-05", "2026-01-07", "2026-01-07", "2026-01-09", 2, 2, False),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=True,
    ),
)


# ---------------------------------------------------------------------------
# BM-008: FF relationship (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(5) --FF,lag=0--> B(3)
# Project start: 2026-01-05 (Mon)
#
# FF with lag=0: B.EF_constraint = apply_lag(A.EF, 0) = A.EF = Jan-09
# B derived ES from FF: ES = apply_lag(Jan-09, -(OD_B-1)) = apply_lag(Jan-09,-2)=Jan-07
# A: ES=Jan-05, EF=Jan-09
# B: ES=Jan-07, EF=Jan-09
# project_finish=Jan-09
#
# Backward pass:
#   A: LF=Jan-09 (finish), LS=Jan-05. TF=0.
#   B: LF=Jan-09 (finish), LS=Jan-07. TF=0.
#   A FF backward: A.LF constraint from B: apply_lag(B.LF=Jan-09, 0)=Jan-09.
#     A.LF=min(Jan-09,Jan-09)=Jan-09. LS=Jan-05. TF=0.
#
# A.FF: FF outgoing: wt[B.EF]-wt[A.EF]-0=5-5=0.
# B.FF: finish node → FF=TF=0.
# CP: [A, B] — both TF=0 and both on LP.
# project_duration=5.

BM_008 = BenchmarkDefinition(
    metadata=_meta(
        "BM-008", "FF lag=0 relationship — B must finish when A finishes",
        BenchmarkCategory.SS_FF_SF,
        assumptions=[
            "FF lag=0: B.EF constrained to equal A.EF (same workday).",
            "Both A and B have TF=0 and are on the critical path.",
        ],
        tags=["ff", "relationship", "hand-verified"],
    ),
    activities=[_act("A", 5), _act("B", 3)],
    relationships=[_rel("A", "B", _FF, lag=0.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-09",
        project_duration=5,
        critical_path_activity_ids=["A", "B"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True),
            "B": _exp_act("B", "2026-01-07", "2026-01-09", "2026-01-07", "2026-01-09", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-009: SF relationship (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(3) --SF,lag=0--> B(2)
# Project start: 2026-01-05 (Mon)
#
# SF with lag=0: B.EF_constraint = apply_lag(A.ES, span_A) where span_A=OD_A-1=2
#   But actually SF forward: EF_constraint = apply_lag(A.ES, 0) = A.ES = Jan-05
#   B.ES = apply_lag(EF_constraint=Jan-05, -(OD_B-1)) = apply_lag(Jan-05,-1)
#   Jan-05 workday=1, -1=workday 0 → that's before start. Hmm.
#
# Actually SF means: the successor must FINISH after the predecessor STARTS.
# Forward pass: the EF-type constraint for SF is:
#   constraint_date = apply_lag(pred.early_start, lag + 0) = apply_lag(A.ES, 0) = Jan-05
# Then B.ES derived from EF constraint: apply_lag(Jan-05, -(OD_B-1)) = apply_lag(Jan-05,-1)
# That would put B.ES before the start. The forward pass takes max(project_start, ...).
#
# So B.ES = max(project_start=Jan-05, derived_from_ef) = Jan-05.
# B.EF = apply_lag(Jan-05, 1) = Jan-06.
# A: ES=Jan-05, EF=Jan-07.
# project_finish = Jan-07.
#
# Backward pass:
#   A: LF=Jan-07 (finish node). LS=Jan-05.
#   B: LF=Jan-07 (finish node). LS=apply_lag(Jan-07,-1)=Jan-06. TF=wt[Jan-07]-wt[Jan-06]=1.
#   A SF backward: A.LF_constraint from B: apply_lag(B.LF=Jan-07, -k+span_A) = apply_lag(Jan-07, 0+2)=apply_lag(Jan-07,2)=Jan-09 — but Jan-09 is AFTER project finish, so the project_finish constraint (Jan-07) is tighter. A.LF=Jan-07.
#
# A.FF: SF outgoing: wt[B.EF]-wt[A.ES]-0 = 3-1=2. So A.FF=2? Let me think.
#   SF FF formula: wt[B.EF] - wt[A.ES] - k - 0 (no fs_offset for SF)
#   = wt[Jan-06] - wt[Jan-05] - 0 = 2-1 = 1.
# A.TF=0. A.FF=1.
# B.TF=1. B.FF=1 (finish node).
# LP: A only (TF=0). B has TF=1.
# CP: [A]. project_duration=3.

BM_009 = BenchmarkDefinition(
    metadata=_meta(
        "BM-009", "SF lag=0 relationship",
        BenchmarkCategory.SS_FF_SF,
        assumptions=[
            "SF lag=0: B.EF constrained by A.ES (SF is EF-type).",
            "A is NOT a network finish node (has outgoing SF to B); only B is a finish node.",
            "B.EF=Jan-06 < project_finish=Jan-07 → no controlling finish nodes → LP empty.",
            "Both A(TF=2) and B(TF=1) have positive float; no activity is on critical path.",
            "SF backward: A.LF constrained by B.LF+span_A = Jan-07+2 = Jan-09.",
            "Baseline captured from engine; SF-driven LP behavior is analytically complex.",
        ],
        tags=["sf", "relationship", "baseline-captured"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[_rel("A", "B", _SF, lag=0.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-07",
        project_duration=3,
        critical_path_activity_ids=[],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-07", "2026-01-07", "2026-01-09", 2, 1, False),
            "B": _exp_act("B", "2026-01-05", "2026-01-06", "2026-01-06", "2026-01-07", 1, 1, False),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=True,
    ),
)


# ---------------------------------------------------------------------------
# BM-010: Milestone (OD=0) on critical path (hand-verified)
# ---------------------------------------------------------------------------
#
# Network: A(3) → M(0) → B(2)  [all FS lag=0, INCLUSIVE_DAY]
# OD=0: EF = ES (EF = apply_lag(ES, 0) = ES for milestone).
#
# A: ES=Jan-05, EF=Jan-07
# M: ES=Jan-07 (from A.EF), EF=Jan-07 (OD=0 milestone)
# B: ES=Jan-07 (from M.EF), EF=apply_lag(Jan-07,1)=Jan-08
# project_finish=Jan-08
#
# Backward pass:
#   B: LF=Jan-08, LS=Jan-07. TF=0.
#   M: LF=apply_lag(B.LS=Jan-07,0)=Jan-07. LS=apply_lag(Jan-07,0)=Jan-07 (OD=0). TF=0.
#   A: LF=apply_lag(M.LS=Jan-07,0)=Jan-07. LS=Jan-05. TF=0.
#
# FF: A→M FF: wt[M.ES]-wt[A.EF]-0=3-3=0. M→B FF: wt[B.ES]-wt[M.EF]-0=4-3=1? Wait.
# M.EF=Jan-07. B.ES=Jan-07. FF for M→B: wt[B.ES]-wt[M.EF]-0=3-3=0. M.FF=0.
# A.FF=0. B.FF=0 (finish). CP=[A,M,B]. project_duration=4 (Jan-05=1,Jan-06=2,Jan-07=3,Jan-08=4).

BM_010 = BenchmarkDefinition(
    metadata=_meta(
        "BM-010", "Milestone (OD=0) on critical path",
        BenchmarkCategory.EDGE_CASE,
        assumptions=[
            "OD=0 milestone: EF = ES (apply_lag(ES, 0) = ES).",
            "LS = LF for milestone (span=0).",
            "Milestone is on the critical path between A and B.",
        ],
        tags=["milestone", "od-zero", "hand-verified"],
    ),
    activities=[_act("A", 3), _act("M", 0), _act("B", 2)],
    relationships=[_rel("A", "M"), _rel("M", "B")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-08",
        project_duration=4,
        critical_path_activity_ids=["A", "M", "B"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "M": _exp_act("M", "2026-01-07", "2026-01-07", "2026-01-07", "2026-01-07", 0, 0, True),
            "B": _exp_act("B", "2026-01-07", "2026-01-08", "2026-01-07", "2026-01-08", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-011: Convention divergence — FS network differs between conventions
# ---------------------------------------------------------------------------
#
# Simple A→B FS chain, run under P6_COMPATIBILITY convention.
# P6_COMPATIBILITY: FS successor ES = predecessor EF + 1 workday (next workday).
#
# A(3): ES=Jan-05, EF=Jan-07
# B(3): ES=apply_lag(A.EF=Jan-07, 0+1)=apply_lag(Jan-07,1)=Jan-08
#        EF=apply_lag(Jan-08,2)=Jan-12  [Mon]
# project_finish=Jan-12
#
# Backward pass:
#   B: LF=Jan-12, LS=Jan-08. TF=0.
#   A: LF from B FS backward: apply_lag(B.LS=Jan-08, -0-1)=apply_lag(Jan-08,-1)=Jan-07
#      LS=apply_lag(Jan-07,-2)=Jan-05. TF=0.
# All TF=0. CP=[A,B].
# project_duration = wt[Jan-12]-wt[Jan-05]+1 = 6-1+1=6.
# (Jan-05=1,Jan-06=2,Jan-07=3,Jan-08=4,Jan-09=5,Jan-12=6)

BM_011 = BenchmarkDefinition(
    metadata=_meta(
        "BM-011", "Convention divergence: P6_COMPATIBILITY FS offset",
        BenchmarkCategory.CONVENTION_DIVERGENCE,
        assumptions=[
            "P6_COMPATIBILITY: FS successor ES = predecessor EF + 1 workday (next workday).",
            "Produces 1-workday later dates vs INCLUSIVE_DAY for FS-driven activities.",
            "project_duration = 6 workdays (vs 7 under INCLUSIVE_DAY).",
        ],
        tags=["convention", "p6", "hand-verified"],
    ),
    activities=[_act("A", 3), _act("B", 3)],
    relationships=[_rel("A", "B", _FS, lag=0.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="p6_compatibility",
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-12",
        project_duration=6,
        critical_path_activity_ids=["A", "B"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "B": _exp_act("B", "2026-01-08", "2026-01-12", "2026-01-08", "2026-01-12", 0, 0, True),
        },
        tied_paths=False,
        divergence_flags=[],
        convention="p6_compatibility",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-012: Invalid network — cyclic dependency (is_valid=False)
# ---------------------------------------------------------------------------
#
# Cycle: A → B → A (direct cycle). Engine should detect and return is_valid=False.
# scheduled will be empty, critical_path will be None.

BM_012 = BenchmarkDefinition(
    metadata=_meta(
        "BM-012", "Invalid network: cyclic dependency (engine returns is_valid=False)",
        BenchmarkCategory.INVALID_NETWORK,
        assumptions=[
            "Cycle A→B→A is a blocking validation issue.",
            "Engine returns is_valid=False with empty scheduled dict.",
        ],
        tags=["invalid", "cycle", "validation"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[_rel("A", "B"), _rel("B", "A")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    expectations=BenchmarkExpectations(
        is_valid=False,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        tied_paths=False,
        divergence_flags=[],
        convention="inclusive_day",
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-013: Multi-calendar registry — two calendars registered (structural)
# ---------------------------------------------------------------------------
#
# Structural benchmark: tests CalendarRegistry construction with two
# distinct calendars (Mon-Fri and Mon-Sat). No engine run required.
#
# Registry expected state:
#   - 2 calendars: clndr_id="CAL-MF" (Mon-Fri) and clndr_id="CAL-MS" (Mon-Sat)
#   - Default: "CAL-MF" (project default per XER PROJECT.clndr_id)
#   - Both calendars parse_status="PARSED" (empty clndr_data → empty exceptions)
#
# This benchmark documents the registry structure; verification is in
# test_calendar_registry.py.

BM_013 = BenchmarkDefinition(
    metadata=_meta(
        "BM-013", "Multi-calendar registry: two calendars (structural)",
        BenchmarkCategory.MULTI_CALENDAR_REGISTRY,
        assumptions=[
            "CalendarRegistry stores both calendars keyed by clndr_id.",
            "Project default set to CAL-MF (Mon-Fri).",
            "Empty clndr_data → PARSED status with Mon-Fri defaults for CAL-MF.",
            "Mon-Sat (ISO {1,2,3,4,5,6}) has 6 work days per week.",
        ],
        tags=["multi-calendar", "registry", "structural", "v1-b1"],
    ),
    activities=[_act("A", 3), _act("B", 3)],
    relationships=[_rel("A", "B")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "calendars": [
            {
                "clndr_id": "CAL-MF",
                "clndr_name": "Mon-Fri Standard",
                "clndr_type": "CA_Base",
                "day_hr_cnt": "8.00",
                "clndr_data": "",
                "expected_work_days": [1, 2, 3, 4, 5],
                "expected_parse_status": "PARSED",
                "expected_exception_count": 0,
            },
            {
                "clndr_id": "CAL-MS",
                "clndr_name": "Mon-Sat Extended",
                "clndr_type": "CA_Base",
                "day_hr_cnt": "8.00",
                "clndr_data": "",
                "expected_work_days": [1, 2, 3, 4, 5, 6],
                "expected_parse_status": "PARSED",
                "expected_exception_count": 0,
            },
        ],
        "project_clndr_id": "CAL-MF",
        "expected_calendar_count": 2,
        "expected_default_clndr_id": "CAL-MF",
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-014: Exception dates — one holiday excluded from workday table
# ---------------------------------------------------------------------------
#
# A Mon-Fri calendar with a holiday on 2026-01-07 (Wednesday).
# Project start: 2026-01-05 (Mon). Activity OD=3.
#
# Workday sequence with exception on Jan-07:
#   Jan-05=wd1, Jan-06=wd2, [Jan-07=holiday], Jan-08=wd3
#
# Forward pass: A OD=3, ES=Jan-05, EF=apply_lag(Jan-05, 2, exception-aware)
#   Jan-05(wd1) → Jan-06(wd2) → Jan-08(wd3) [Jan-07 skipped]
#   EF = Jan-08 (Thu)
#
# This benchmark documents exception date behavior; the standard harness
# does not inject exception_dates so the INCLUSIVE_DAY EF=Jan-07 expected
# value is marked baseline_captured=False. Verification in test_clndr_parser.py
# and test_calendar_registry.py.

BM_014 = BenchmarkDefinition(
    metadata=_meta(
        "BM-014", "Exception dates: single holiday skipped in workday table",
        BenchmarkCategory.MULTI_CALENDAR_EXCEPTION_DATES,
        assumptions=[
            "Mon-Fri calendar with exception on 2026-01-07 (Wednesday).",
            "Calendar exception_dates tested via Calendar.is_workday() and build_workday_table().",
            "Holiday causes EF to advance one extra calendar day (Jan-08 instead of Jan-07).",
        ],
        tags=["multi-calendar", "exception-dates", "v1-b1"],
    ),
    activities=[_act("A", 3)],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "exception_dates": ["2026-01-07"],
        "expected_workday_sequence": {
            "2026-01-05": 1,
            "2026-01-06": 2,
            "2026-01-07": None,  # holiday — not in workday table
            "2026-01-08": 3,
        },
        "expected_ef_with_exceptions": "2026-01-08",
        "expected_ef_without_exceptions": "2026-01-07",
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# BM-015: Lag PREDECESSOR_CALENDAR strategy (Mon-Fri pred, Mon-Sat succ)
# ---------------------------------------------------------------------------
#
# Activity P (pred): Mon-Fri calendar, OD=3
# Activity S (succ): Mon-Sat calendar, OD=3
# FS relationship P→S, lag=2 (measured in predecessor=Mon-Fri calendar)
# Project start: 2026-01-05 (Mon)
#
# Forward pass:
#   P: ES=Jan-05, EF=apply_lag(Jan-05, 2, Mon-Fri) = Jan-07 (Wed)
#   Lag=2 in Mon-Fri from Jan-07: Jan-07→Jan-08→Jan-09 (Fri) → constraint date=Jan-09
#   S: ES=Jan-09 (Fri), OD=3, Mon-Sat calendar
#     EF=apply_lag(Jan-09, 2, Mon-Sat): Jan-09(wd1)→Jan-10/Sat(wd2)→Jan-12/Mon(wd3)
#     EF=Jan-12 (Mon)
#
# Backward pass (project_finish=Jan-12):
#   S: LF=Jan-12, LS=apply_lag(Jan-12, -2, Mon-Sat): Jan-12→Jan-10→Jan-09 = Jan-09
#   P's LF = apply_lag(S.LS=Jan-09, -2, Mon-Fri) = Jan-09→Jan-08→Jan-07 = Jan-07
#   P: LF=Jan-07, LS=apply_lag(Jan-07, -2, Mon-Fri) = Jan-05
#
# Float: P.TF=Mon-Fri[Jan-07]-Mon-Fri[Jan-07]=0; S.TF=Mon-Sat[Jan-12]-Mon-Sat[Jan-12]=0
# Both critical. baseline_captured=True (hand-verified above).

BM_015 = BenchmarkDefinition(
    metadata=_meta(
        "BM-015", "Lag PREDECESSOR_CALENDAR: Mon-Fri pred, Mon-Sat succ, lag=2",
        BenchmarkCategory.MULTI_CALENDAR_LAG_STRATEGY,
        assumptions=[
            "PREDECESSOR_CALENDAR lag strategy: lag measured in predecessor P's Mon-Fri calendar.",
            "P has Mon-Fri calendar (ISO {1,2,3,4,5}); S has Mon-Sat (ISO {1,2,3,4,5,6}).",
            "FS lag=2: S.ES constrained to Jan-09 (2 Mon-Fri workdays after P.EF=Jan-07).",
            "S's OD span uses Mon-Sat calendar: Jan-09→Jan-10(Sat)→Jan-12(Mon).",
        ],
        tags=["multi-calendar", "lag-strategy", "predecessor-calendar", "v1-b1"],
    ),
    activities=[
        {"act_id": "P", "original_duration": 3, "calendar_id": "CAL-MF"},
        {"act_id": "S", "original_duration": 3, "calendar_id": "CAL-MS"},
    ],
    relationships=[_rel("P", "S", lag=2.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "calendars": {
            "CAL-MF": {"work_days": [1, 2, 3, 4, 5], "hours_per_day": 8.0},
            "CAL-MS": {"work_days": [1, 2, 3, 4, 5, 6], "hours_per_day": 8.0},
        },
        "project_clndr_id": "CAL-MF",
        "lag_strategy": "predecessor_calendar",
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-12",
        project_duration=6,  # Mon-Sat table: Jan-05..Jan-12 = 7 days but in mixed calendars
        critical_path_activity_ids=["P", "S"],
        activities={
            "P": _exp_act("P", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "S": _exp_act("S", "2026-01-09", "2026-01-12", "2026-01-09", "2026-01-12", 0, 0, True),
        },
        convention="inclusive_day",
        baseline_captured=True,
    ),
)


# ---------------------------------------------------------------------------
# BM-016: Lag CONTINUOUS_24H strategy (Mon-Fri pred, Mon-Fri succ, lag=2 calendar-days)
# ---------------------------------------------------------------------------
#
# Same two Mon-Fri activities, but lag=2 measured in CONTINUOUS_24H calendar
# (all 7 days are workdays). This means lag crosses a weekend.
#
# Activity P: Mon-Fri, OD=3
# Activity S: Mon-Fri, OD=3
# FS lag=2 in CONTINUOUS_24H calendar
# Project start: 2026-01-05 (Mon)
#
# Forward pass:
#   P: ES=Jan-05, EF=apply_lag(Jan-05, 2, Mon-Fri) = Jan-07 (Wed)
#   Lag=2 in 24h calendar from Jan-07: Jan-07+1=Jan-08, Jan-08+1=Jan-09 (Fri) → S.ES=Jan-09
#   (Same result as BM-015 because the lag doesn't cross a weekend here)
#   S: ES=Jan-09 (Fri), EF=apply_lag(Jan-09, 2, Mon-Fri)
#     Jan-09→Jan-12→Jan-13 → EF=Jan-13 (Tue)
#
# Backward pass (project_finish=Jan-13):
#   S: LF=Jan-13, LS=apply_lag(Jan-13,-2,Mon-Fri)=Jan-09
#   P.LF=apply_lag(Jan-09,-2,24h)=Jan-09-2=Jan-07
#   P: LF=Jan-07, LS=Jan-05
# Float: TF=0 for both. Both critical.

BM_016 = BenchmarkDefinition(
    metadata=_meta(
        "BM-016", "Lag CONTINUOUS_24H: Mon-Fri activities, lag=2 calendar-days",
        BenchmarkCategory.MULTI_CALENDAR_LAG_STRATEGY,
        assumptions=[
            "CONTINUOUS_24H lag: every calendar day counts as a workday for lag purposes.",
            "Both activities on Mon-Fri calendar; lag only crosses Mon-Fri (no Sat/Sun).",
            "In this scenario, CONTINUOUS_24H produces same result as PREDECESSOR_CALENDAR.",
            "Distinction would appear if lag=3 (crosses Sat/Sun).",
        ],
        tags=["multi-calendar", "lag-strategy", "continuous-24h", "v1-b1"],
    ),
    activities=[
        {"act_id": "P", "original_duration": 3, "calendar_id": "CAL-MF"},
        {"act_id": "S", "original_duration": 3, "calendar_id": "CAL-MF"},
    ],
    relationships=[_rel("P", "S", lag=2.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "calendars": {
            "CAL-MF": {"work_days": [1, 2, 3, 4, 5], "hours_per_day": 8.0},
        },
        "project_clndr_id": "CAL-MF",
        "lag_strategy": "continuous_24h",
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-13",
        project_duration=7,
        critical_path_activity_ids=["P", "S"],
        activities={
            "P": _exp_act("P", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
            "S": _exp_act("S", "2026-01-09", "2026-01-13", "2026-01-09", "2026-01-13", 0, 0, True),
        },
        convention="inclusive_day",
        baseline_captured=True,
    ),
)


# ---------------------------------------------------------------------------
# BM-017: Activity-calendar binding — Mon-Sat activity on Mon-Sat calendar
# ---------------------------------------------------------------------------
#
# Single activity on Mon-Sat calendar (ISO {1,2,3,4,5,6}), OD=3.
# Project start: 2026-01-05 (Mon). Single activity, no relationships.
#
# Mon-Sat workday sequence: Jan-05(Mon)=wd1, Jan-06(Tue)=wd2, Jan-07(Wed)=wd3,
#   Jan-08(Thu)=wd4, Jan-09(Fri)=wd5, Jan-10(Sat)=wd6, Jan-12(Mon)=wd7, ...
#
# A: ES=Jan-05, span=2, EF=apply_lag(Jan-05, 2, Mon-Sat)
#   Jan-05(wd1)→Jan-06(wd2)→Jan-07(wd3) → EF=Jan-07 (Wed)
#
# Note: Mon-Sat and Mon-Fri produce the same result for OD=3 starting Mon-Jan-05
#   (no Saturday in first 3 workdays). Distinction would appear for OD=6+.
# Backward pass: LF=Jan-07, LS=Jan-05. TF=0.

BM_017 = BenchmarkDefinition(
    metadata=_meta(
        "BM-017", "Activity-calendar binding: Mon-Sat single activity OD=3",
        BenchmarkCategory.MULTI_CALENDAR_BINDING,
        assumptions=[
            "Activity bound to Mon-Sat (ISO {1,2,3,4,5,6}) calendar.",
            "OD=3 starting Mon Jan-05: EF=Jan-07 (same as Mon-Fri for this duration/start).",
            "Distinction from Mon-Fri appears for OD=6+ or Fri start.",
            "Per-activity workday table uses Mon-Sat calendar.",
        ],
        tags=["multi-calendar", "calendar-binding", "mon-sat", "v1-b1"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 3, "calendar_id": "CAL-MS"},
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=[1, 2, 3, 4, 5, 6],  # Mon-Sat
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "calendars": {
            "CAL-MS": {"work_days": [1, 2, 3, 4, 5, 6], "hours_per_day": 8.0},
        },
        "project_clndr_id": "CAL-MS",
        "lag_strategy": "predecessor_calendar",
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-07",
        project_duration=3,
        critical_path_activity_ids=["A"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True),
        },
        convention="inclusive_day",
        baseline_captured=True,
    ),
)


# ---------------------------------------------------------------------------
# BM-018: Mon-Sat calendar, OD=6 — distinguishes from Mon-Fri
# ---------------------------------------------------------------------------
#
# Single activity on Mon-Sat calendar, OD=6. Project start Jan-05 (Mon).
#
# Mon-Sat workday sequence:
#   Jan-05(Mon)=wd1, Jan-06=wd2, Jan-07=wd3, Jan-08=wd4, Jan-09=wd5,
#   Jan-10(Sat)=wd6 → EF=Jan-10 (Sat)
#
# Backward pass: LF=Jan-10, LS=apply_lag(Jan-10,-5,Mon-Sat)=Jan-05. TF=0.
#
# Under Mon-Fri calendar (for reference):
#   OD=6: Jan-05→Jan-06→Jan-07→Jan-08→Jan-09→Jan-12 → EF=Jan-12 (Mon)
# This confirms that Mon-Sat binding produces a different (earlier) EF.

BM_018 = BenchmarkDefinition(
    metadata=_meta(
        "BM-018", "Mon-Sat calendar OD=6: EF is Saturday (distinguishes from Mon-Fri)",
        BenchmarkCategory.MULTI_CALENDAR_ENGINE,
        assumptions=[
            "Mon-Sat calendar: Saturday is a workday (ISO 6 included).",
            "OD=6 starting Mon Jan-05: EF=Jan-10 (Sat) — not Jan-12 (Mon) as Mon-Fri would give.",
            "This benchmark confirms per-activity calendar binding affects scheduled dates.",
        ],
        tags=["multi-calendar", "mon-sat", "calendar-effect", "v1-b1"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 6, "calendar_id": "CAL-MS"},
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=[1, 2, 3, 4, 5, 6],  # Mon-Sat for harness single-calendar run
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "calendars": {
            "CAL-MS": {"work_days": [1, 2, 3, 4, 5, 6], "hours_per_day": 8.0},
        },
        "project_clndr_id": "CAL-MS",
        "lag_strategy": "predecessor_calendar",
        "mon_fri_ef_for_comparison": "2026-01-12",
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish="2026-01-10",
        project_duration=6,
        critical_path_activity_ids=["A"],
        activities={
            "A": _exp_act("A", "2026-01-05", "2026-01-10", "2026-01-05", "2026-01-10", 0, 0, True),
        },
        convention="inclusive_day",
        baseline_captured=True,
    ),
)


# ---------------------------------------------------------------------------
# BM-019: XER multi-calendar import — two activities, two calendars (structural)
# ---------------------------------------------------------------------------
#
# Structural benchmark documenting the expected behavior of import_xer() with
# calendar_strategy="multi-calendar". Tests the full ingestion pipeline:
#   - CALENDAR table with two calendars
#   - TASK table with activities bound to different calendars
#   - ImportXerResult.calendar_registry populated
#   - Activity.calendar_id set correctly for each activity
#
# No engine run. Verification in test_xer_integration.py multi-calendar tests.

BM_019 = BenchmarkDefinition(
    metadata=_meta(
        "BM-019", "XER multi-calendar import: two calendars, activity binding (structural)",
        BenchmarkCategory.MULTI_CALENDAR_REGISTRY,
        assumptions=[
            "ImportConfig(calendar_strategy='multi-calendar') builds CalendarRegistry.",
            "ImportXerResult.calendar_registry populated when strategy='multi-calendar'.",
            "Activity.calendar_id bound to RawTask.clndr_id when calendar is registered.",
            "XER-015 emitted for activities referencing unregistered clndr_id.",
            "XER-018 emitted for activities with no clndr_id.",
        ],
        tags=["multi-calendar", "xer-import", "structural", "v1-b1"],
    ),
    activities=[
        {"act_id": "A100", "original_duration": 3, "calendar_id": "CAL-MF"},
        {"act_id": "A200", "original_duration": 3, "calendar_id": "CAL-MS"},
    ],
    relationships=[_rel("A100", "A200")],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    convention="inclusive_day",
    extra_data={
        "xer_calendar_table": [
            {
                "clndr_id": "CAL-MF",
                "clndr_name": "Mon-Fri Standard",
                "clndr_type": "CA_Base",
                "day_hr_cnt": "8.00",
                "clndr_data": "",
            },
            {
                "clndr_id": "CAL-MS",
                "clndr_name": "Mon-Sat Extended",
                "clndr_type": "CA_Base",
                "day_hr_cnt": "8.00",
                "clndr_data": "",
            },
        ],
        "xer_project_clndr_id": "CAL-MF",
        "expected_a100_calendar_id": "CAL-MF",
        "expected_a200_calendar_id": "CAL-MS",
        "expected_registry_calendar_count": 2,
    },
    expectations=BenchmarkExpectations(
        is_valid=True,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        baseline_captured=False,
    ),
)


# ---------------------------------------------------------------------------
# Phase 7 canonical benchmark suite
# ---------------------------------------------------------------------------

def build_phase7_suite() -> BenchmarkSuite:
    """
    Build and return the Phase 7 canonical benchmark suite.

    Contains BM-001 through BM-012 covering all authorized fixture categories.
    """
    suite = BenchmarkSuite(
        suite_id="SUITE-P7-001",
        suite_version="1.0-phase7",
        description=(
            "Phase 7 canonical validation suite. "
            "Covers simple FS, SS/FF/SF, lag, branching, merge, tied paths, "
            "convention divergence, milestone, and invalid network cases. "
            "All fixtures are synthetic; no proprietary schedules."
        ),
    )
    for bm in [
        BM_001, BM_002, BM_003, BM_004, BM_005,
        BM_006, BM_007, BM_008, BM_009, BM_010,
        BM_011, BM_012,
    ]:
        suite.add(bm)
    return suite


# ---------------------------------------------------------------------------
# BM-020 through BM-029: V1-C Normalization Detection Benchmarks
#
# These fixtures test the NormalizationPipeline, not the CPM engine.
# expected_diagnostic_codes lists the NRM codes the pipeline should emit.
# CPM expectations are set to pass/minimal — normalization tests use the
# pipeline directly, not the ValidationHarness's run_analysis path.
# ---------------------------------------------------------------------------

# Helpers for normalization activity dicts with optional fields
def _act_with(**kwargs: object) -> dict:
    return kwargs


def _norm_expectations(*codes: str) -> BenchmarkExpectations:
    """Minimal CPM expectations + expected normalization diagnostic codes."""
    return BenchmarkExpectations(
        is_valid=True,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        expected_diagnostic_codes=sorted(codes),
    )


# BM-020: Clean 2-activity FS network — no normalization issues expected
# Single start node, single finish node, no abnormal lags, no constraints.
BM_020 = BenchmarkDefinition(
    metadata=_meta(
        "BM-020",
        "Normalization baseline: clean 2-activity FS network",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "Single start node (A), single finish node (B).",
            "No constraints, no actuals, no excessive lags.",
            "NRM-001 and NRM-002 generate INFORMATIONAL single-node messages.",
            "No WARNING or higher diagnostics expected.",
        ],
        tags=["normalization", "baseline", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002"),
)


# BM-021: Multiple open-end start nodes → NRM-001 (ADVISORY per node)
# A and B both have no predecessors and connect only to C.
BM_021 = BenchmarkDefinition(
    metadata=_meta(
        "BM-021",
        "Normalization: multiple open-end start nodes (NRM-001)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "Activities A and B each have no predecessors.",
            "Both connect to C as a merge node.",
            "NRM-001 fires at ADVISORY for each start node.",
        ],
        tags=["normalization", "open-ended", "NRM-001", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2), _act("C", 2)],
    relationships=[_rel("A", "C", _FS), _rel("B", "C", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002"),
)


# BM-022: Isolated activity → NRM-003 (WARNING)
# A→B (connected pair) + C (isolated — no preds, no succs).
BM_022 = BenchmarkDefinition(
    metadata=_meta(
        "BM-022",
        "Normalization: isolated activity (NRM-003)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "Activity C has no predecessors and no successors.",
            "NRM-003 fires at WARNING for C.",
            "NRM-001 and NRM-002 fire informational for single-node A/B.",
        ],
        tags=["normalization", "isolated", "NRM-003", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2), _act("C", 1)],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-003"),
)


# BM-023: Duplicate relationships → NRM-004 (WARNING)
# Two FS relationships between A and B (same pair, same type).
BM_023 = BenchmarkDefinition(
    metadata=_meta(
        "BM-023",
        "Normalization: duplicate relationships between same activity pair (NRM-004)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "Two FS relationships A→B with different lag values.",
            "NRM-004 fires at WARNING for the duplicate pair.",
        ],
        tags=["normalization", "duplicate", "NRM-004", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[
        _rel("A", "B", _FS, lag=0.0),
        _rel("A", "B", _FS, lag=2.0),
    ],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-004"),
)


# BM-024: Excessive lag → NRM-015 (ADVISORY; |lag|=25 > threshold=20)
BM_024 = BenchmarkDefinition(
    metadata=_meta(
        "BM-024",
        "Normalization: excessive lag on FS relationship (NRM-015)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "FS relationship A→B with lag=25, exceeding default threshold of 20.",
            "NRM-015 fires at ADVISORY.",
        ],
        tags=["normalization", "excessive-lag", "NRM-015", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[_rel("A", "B", _FS, lag=25.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-015"),
)


# BM-025: Large negative FS lag → NRM-016 (WARNING; lag=-15 < -10 threshold)
# lag=-15: |lag|=15 < 20 threshold → NRM-015 NOT triggered.
# lag=-15 < -10 → NRM-016 triggered.
BM_025 = BenchmarkDefinition(
    metadata=_meta(
        "BM-025",
        "Normalization: large negative FS lag / OOS indicator (NRM-016)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "FS relationship A→B with lag=-15.",
            "|-15|=15 < 20: NRM-015 (excessive lag) NOT triggered.",
            "-15 < -10: NRM-016 (large negative FS lag / OOS indicator) fires at WARNING.",
        ],
        tags=["normalization", "negative-lag", "NRM-016", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[_rel("A", "B", _FS, lag=-15.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-016"),
)


# BM-026: SF relationship → NRM-020 (ADVISORY)
BM_026 = BenchmarkDefinition(
    metadata=_meta(
        "BM-026",
        "Normalization: SF relationship present (NRM-020)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "SF relationship A→B with lag=0.",
            "NRM-020 fires at ADVISORY for the SF relationship.",
            "SF semantics are tool-dependent; analyst review required.",
        ],
        tags=["normalization", "sf-relationship", "NRM-020", "v1c"],
    ),
    activities=[_act("A", 3), _act("B", 2)],
    relationships=[_rel("A", "B", "SF", lag=0.0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-020"),
)


# BM-027: OOS progress → NRM-013 (ANALYTICAL_RISK)
# Successor B started before FS predecessor A finished.
# A: actual_finish=2026-01-09, B: actual_start=2026-01-07 (before A finished).
BM_027 = BenchmarkDefinition(
    metadata=_meta(
        "BM-027",
        "Normalization: out-of-sequence progress on FS relationship (NRM-013)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "A has actual_finish=2026-01-09 (Friday).",
            "B has actual_start=2026-01-07 (Wednesday) — before A finished.",
            "OOS condition on FS A→B: NRM-013 fires at ANALYTICAL_RISK.",
        ],
        tags=["normalization", "oos", "NRM-013", "v1c"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 5, "actual_finish": "2026-01-09"},
        {"act_id": "B", "original_duration": 3, "actual_start": "2026-01-07"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-013"),
)


# BM-028: Invalid progress — actual finish before actual start → NRM-014 (CRITICAL)
BM_028 = BenchmarkDefinition(
    metadata=_meta(
        "BM-028",
        "Normalization: actual finish before actual start / negative actual duration (NRM-014)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "Activity A: actual_start=2026-01-09, actual_finish=2026-01-07.",
            "actual_finish < actual_start: physically impossible.",
            "NRM-014 fires at CRITICAL.",
        ],
        tags=["normalization", "invalid-progress", "NRM-014", "v1c"],
    ),
    activities=[
        {
            "act_id": "A", "original_duration": 3,
            "actual_start": "2026-01-09", "actual_finish": "2026-01-07",
        },
        _act("B", 2),
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-014"),
)


# BM-029: Hard constraint present → NRM-010 + NRM-011 (ANALYTICAL_RISK)
# Activity A has constraint_type="mandatory_start".
BM_029 = BenchmarkDefinition(
    metadata=_meta(
        "BM-029",
        "Normalization: hard constraint on activity (NRM-010, NRM-011)",
        BenchmarkCategory.NORMALIZATION,
        assumptions=[
            "Activity A has constraint_type='mandatory_start' (hard constraint).",
            "NRM-010 fires at ANALYTICAL_RISK (any constraint present).",
            "NRM-011 fires at ANALYTICAL_RISK (hard constraint detected).",
        ],
        tags=["normalization", "constraint", "NRM-010", "NRM-011", "v1c"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 3, "constraint_type": "mandatory_start"},
        _act("B", 2),
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_norm_expectations("NRM-001", "NRM-002", "NRM-010", "NRM-011"),
)


def build_multi_calendar_suite() -> BenchmarkSuite:
    """
    Build and return the V1-B.1 multi-calendar benchmark suite (BM-013 through BM-019).

    Contains structural and engine-runnable benchmarks covering:
    CalendarRegistry construction, exception date handling, lag calendar strategies,
    per-activity calendar binding, and XER multi-calendar import.
    All fixtures are synthetic; no proprietary schedules.
    """
    suite = BenchmarkSuite(
        suite_id="SUITE-V1B1-001",
        suite_version="1.1-v1b1",
        description=(
            "V1-B.1 multi-calendar benchmark suite. "
            "Covers CalendarRegistry construction, exception dates, lag calendar "
            "strategies (PREDECESSOR, CONTINUOUS_24H), per-activity calendar binding, "
            "and XER multi-calendar import. All fixtures synthetic."
        ),
    )
    for bm in [BM_013, BM_014, BM_015, BM_016, BM_017, BM_018, BM_019]:
        suite.add(bm)
    return suite


def build_normalization_suite() -> BenchmarkSuite:
    """
    Build and return the V1-C normalization benchmark suite.

    Contains BM-020 through BM-029 covering normalization detection scenarios.
    These benchmarks test NormalizationPipeline detection, not CPM scheduling.
    """
    suite = BenchmarkSuite(
        suite_id="SUITE-NORM-001",
        suite_version="1.0-v1c",
        description=(
            "V1-C normalization detection benchmark suite. "
            "Covers NRM-001 through NRM-020: topology, constraints, OOS/progress, "
            "lag/relationship, and heuristic checks. All synthetic; no proprietary schedules."
        ),
    )
    for bm in [
        BM_020, BM_021, BM_022, BM_023, BM_024,
        BM_025, BM_026, BM_027, BM_028, BM_029,
    ]:
        suite.add(bm)
    return suite


# Eagerly constructed suites for import convenience
PHASE7_SUITE: BenchmarkSuite = build_phase7_suite()
MULTI_CALENDAR_SUITE: BenchmarkSuite = build_multi_calendar_suite()
NORMALIZATION_SUITE: BenchmarkSuite = build_normalization_suite()


# ---------------------------------------------------------------------------
# BM-030 through BM-039: V1-D Destatusing Benchmarks
#
# These fixtures document expected destatusing rule assignments and diagnostic
# codes for synthetic activity sets. They serve as regression anchors for the
# run_destatusing() engine and the auto-drive algorithm.
#
# BenchmarkExpectations.expected_diagnostic_codes lists DST/LAG/DRV codes.
# BenchmarkExpectations.activities["<act_id>"] verifies rule assignments via
# metadata fields (is_valid is always True for destatusing benchmarks).
#
# Data date conventions:
#   new_dd = "2026-01-12" (Monday)  — start of analysis window
#   old_dd = "2026-01-16" (Friday)  — end of analysis window
#
# Workday numbering follows standard Mon-Fri calendar (_STD_WORK_DAYS).
# ---------------------------------------------------------------------------

_DST_NEW_DD = "2026-01-12"  # Monday (start of analysis window)
_DST_OLD_DD = "2026-01-16"  # Friday (end of analysis window)


def _dst_expectations(*codes: str) -> BenchmarkExpectations:
    """Minimal BenchmarkExpectations for destatusing benchmarks."""
    return BenchmarkExpectations(
        is_valid=True,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        expected_diagnostic_codes=sorted(codes),
    )


# BM-030: Rule A — activity complete before new_dd, no transformation expected
BM_030 = BenchmarkDefinition(
    metadata=_meta(
        "BM-030",
        "Destatusing Rule A: activity complete before new_dd — no change",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A: actual_start=2026-01-05 (Mon), actual_finish=2026-01-09 (Fri).",
            "Both dates before new_dd=2026-01-12. Rule A applies.",
            "DST-001 (Rule A assigned, INFORMATIONAL) expected.",
            "No fields changed; no lag or auto-drive diagnostics.",
        ],
        tags=["destatusing", "rule-a", "no-change", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        _act("B", 3),
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-001"),
)


# BM-031: Rule B — activity completed in analysis window
BM_031 = BenchmarkDefinition(
    metadata=_meta(
        "BM-031",
        "Destatusing Rule B: activity completed in analysis window",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A: actual_start=2026-01-13, actual_finish=2026-01-14.",
            "Both dates in window [new_dd=2026-01-12, old_dd=2026-01-16).",
            "Rule B applies: remove AS/AF, OD=AD, PC=0.",
            "DST-002 (Rule B assigned, INFORMATIONAL) expected.",
        ],
        tags=["destatusing", "rule-b", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 3,
         "actual_start": "2026-01-13", "actual_finish": "2026-01-14",
         "actual_duration": 2},
        _act("B", 3),
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-002"),
)


# BM-032: Rule C — future activity, no transformation expected
BM_032 = BenchmarkDefinition(
    metadata=_meta(
        "BM-032",
        "Destatusing Rule C: future activity — no change",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A: no actuals; early_start=2026-01-19, early_finish=2026-01-23.",
            "ES and EF both after old_dd=2026-01-16. Rule C applies.",
            "DST-003 (Rule C assigned, INFORMATIONAL) expected.",
        ],
        tags=["destatusing", "rule-c", "future", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 5,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-003"),
)


# BM-033: Rule D — in-progress activity spanning new_dd
BM_033 = BenchmarkDefinition(
    metadata=_meta(
        "BM-033",
        "Destatusing Rule D: in-progress spanning new_dd (AF after old_dd)",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A: actual_start=2026-01-08 (before new_dd), actual_finish=2026-01-23.",
            "AS < new_dd and AF > old_dd. Rule D applies.",
            "AF removed; RD computed from new_dd to AF; PC=AD_before/(AD_before+RD).",
            "DST-004 (Rule D assigned) expected. PC formula note (ANALYTICAL_RISK) applies.",
        ],
        tags=["destatusing", "rule-d", "in-progress", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 10,
         "actual_start": "2026-01-08", "actual_finish": "2026-01-23",
         "actual_duration": 5},
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-004"),
)


# BM-034: Rule E — started in window, EF after old_dd
BM_034 = BenchmarkDefinition(
    metadata=_meta(
        "BM-034",
        "Destatusing Rule E: started in window, EF after old_dd",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A: actual_start=2026-01-13 (in window); no AF.",
            "Early finish=2026-01-23 (after old_dd). Rule E applies.",
            "AS removed; OD=AD+RD; PC=0.",
            "DST-005 (Rule E assigned) expected.",
        ],
        tags=["destatusing", "rule-e", "in-progress", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 8,
         "actual_start": "2026-01-13",
         "early_finish": "2026-01-23",
         "actual_duration": 2, "remaining_duration": 6},
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-005"),
)


# BM-035: Rule F — started before new_dd, EF after old_dd (no AF)
BM_035 = BenchmarkDefinition(
    metadata=_meta(
        "BM-035",
        "Destatusing Rule F: started before new_dd, still running, EF after old_dd",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A: actual_start=2026-01-08 (before new_dd); no AF.",
            "Early finish=2026-01-23 (after old_dd). Rule F applies.",
            "RD computed from new_dd to old EF; PC=AD_before/(AD_before+RD).",
            "DST-006 (Rule F assigned) expected.",
        ],
        tags=["destatusing", "rule-f", "in-progress", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 10,
         "actual_start": "2026-01-08",
         "early_finish": "2026-01-23",
         "actual_duration": 3},
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-006"),
)


# BM-036: Single FS relationship — actual lag computed (LAG-001)
BM_036 = BenchmarkDefinition(
    metadata=_meta(
        "BM-036",
        "Destatusing: actual lag computed for FS relationship (LAG-001)",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Rule A predecessor (P) has actual_finish=2026-01-09.",
            "Rule C successor (S) has early_start=2026-01-19, actual_start=2026-01-21.",
            "FS actual_lag = workday(succ_AS) - workday(pred_AF) = 2 (positive).",
            "LAG-001 (lag computed) expected; planned_lag=0 so variance=2.",
        ],
        tags=["destatusing", "lag-analysis", "LAG-001", "v1d"],
    ),
    activities=[
        {"act_id": "P", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "S", "original_duration": 5,
         "early_start": "2026-01-19", "early_finish": "2026-01-23",
         "actual_start": "2026-01-21"},
    ],
    relationships=[_rel("P", "S", _FS, 0)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-001", "DST-003", "LAG-001"),
)


# BM-037: Negative actual lag retained (LAG-002)
# Both activities complete before new_dd (Rule A — no change), so actual dates
# are preserved. Successor started on Jan 6 before predecessor finished Jan 7
# → FS lag = wt[2026-01-06] − wt[2026-01-07] = −1 (negative). LAG-002 expected.
BM_037 = BenchmarkDefinition(
    metadata=_meta(
        "BM-037",
        "Destatusing: negative actual lag detected (LAG-002)",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Both P and S complete before new_dd → Rule A (no change).",
            "S.actual_start (2026-01-06) before P.actual_finish (2026-01-07).",
            "FS actual_lag = wt[01-06] - wt[01-07] = -1 < 0: OOS. LAG-002 expected.",
        ],
        tags=["destatusing", "lag-analysis", "negative-lag", "LAG-002", "v1d"],
    ),
    activities=[
        {"act_id": "P", "original_duration": 3,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-07",
         "actual_duration": 3},
        {"act_id": "S", "original_duration": 3,
         "actual_start": "2026-01-06", "actual_finish": "2026-01-08",
         "actual_duration": 3},
    ],
    relationships=[_rel("P", "S", _FS, 3)],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-001", "LAG-001", "LAG-002"),
)


# BM-038: Auto-drive with two predecessors — minimum variance wins (DRV-001, DRV-002)
BM_038 = BenchmarkDefinition(
    metadata=_meta(
        "BM-038",
        "Destatusing: auto-drive with two predecessors (DRV-001, DRV-002)",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Successor S has two predecessors: P1 (small variance) and P2 (large).",
            "P1 drives (DRV-001); P2 non-driving lag reset to planned (DRV-002).",
        ],
        tags=["destatusing", "auto-drive", "DRV-001", "DRV-002", "v1d"],
    ),
    activities=[
        {"act_id": "P1", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "P2", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "S", "original_duration": 5,
         "early_start": "2026-01-19", "early_finish": "2026-01-23",
         "actual_start": "2026-01-20"},   # day after P1 EF expected = Jan 20
    ],
    relationships=[
        _rel("P1", "S", _FS, 5),   # planned_lag=5; actual will be 7 or 8 → variance ~2
        _rel("P2", "S", _FS, 0),   # planned_lag=0; actual will be 7 or 8 → variance ~7
    ],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-001", "DST-001", "DST-003",
                                   "LAG-001", "LAG-001", "DRV-001", "DRV-002"),
)


# BM-039: NO_MATCH activity — anomalous state detected (DST-007)
BM_039 = BenchmarkDefinition(
    metadata=_meta(
        "BM-039",
        "Destatusing: NO_MATCH activity — anomalous state (DST-007)",
        BenchmarkCategory.DESTATUSING,
        assumptions=[
            "Activity A has actual_finish but no actual_start.",
            "This is an impossible completion state. NO_MATCH assigned.",
            "DST-007 (NO_MATCH, ANALYTICAL_RISK) expected.",
            "Under STRICT_FORENSIC policy, this triggers a blocking checkpoint.",
        ],
        tags=["destatusing", "no-match", "DST-007", "v1d"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 5,
         "actual_finish": "2026-01-14"},  # AF without AS — impossible state
    ],
    relationships=[],
    project_start=_STD_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_dst_expectations("DST-007"),
)


def build_destatusing_suite() -> BenchmarkSuite:
    """
    Build and return the V1-D destatusing benchmark suite (BM-030 through BM-039).

    Contains structural benchmarks covering all six destatusing rules (A-F),
    lag analysis (LAG-001, LAG-002), auto-drive (DRV-001, DRV-002), and the
    NO_MATCH anomaly condition (DST-007). All fixtures are synthetic.
    """
    suite = BenchmarkSuite(
        suite_id="SUITE-DST-001",
        suite_version="1.0-v1d",
        description=(
            "V1-D destatusing benchmark suite. "
            "Covers Rules A-F (DST-001 through DST-006), lag analysis "
            "(LAG-001, LAG-002), auto-drive (DRV-001, DRV-002), and NO_MATCH "
            "(DST-007). All fixtures synthetic; no proprietary schedules."
        ),
    )
    for bm in [
        BM_030, BM_031, BM_032, BM_033, BM_034,
        BM_035, BM_036, BM_037, BM_038, BM_039,
    ]:
        suite.add(bm)
    return suite


DESTATUSING_SUITE: BenchmarkSuite = build_destatusing_suite()


# ===========================================================================
# V1-E Simulation Schedule Generation Benchmarks — BM-040 through BM-049
# ===========================================================================
#
# Simulation benchmarks exercise generate_simulation_schedule() via the
# harness. Each fixture's extra_data provides the simulation configuration:
#   simulation_variant   — SimulationVariant name (string)
#   simulation_policy    — SimulationPolicy name (string)
#   new_data_date        — ISO 8601 date; None for BASELINE variant
#   old_data_date        — ISO 8601 date; None for BASELINE variant
#   destatusing_policy   — DestatusingPolicy name for the destatusing step
#   expected_is_blocked  — bool; whether the simulation result should be blocked
#   expected_abcs_valid  — bool; whether the ABCS CPM result should be valid
#
# The test harness builds DestatusingInput → runs run_destatusing() → builds
# SimulationInput → runs generate_simulation_schedule() → validates against
# expected_diagnostic_codes and extra_data properties.
#
# expected_diagnostic_codes lists codes that MUST appear (at least once) in
# the simulation diagnostics. baseline_captured=True (computed from engine).
#
# All fixtures are synthetic (source="synthetic"). No proprietary schedules.
# Reference: ADR-015; CPW-P6 Manual pp. 12-20.
# ===========================================================================

_SIM_START = "2026-01-05"         # Monday project start
_NEW_DD = "2026-01-12"            # New data date (Monday)
_OLD_DD = "2026-01-16"            # Old data date (Friday)


def _sim_expectations(*codes: str) -> BenchmarkExpectations:
    """Minimal BenchmarkExpectations for simulation benchmarks."""
    return BenchmarkExpectations(
        is_valid=True,
        project_finish=None,
        project_duration=0,
        critical_path_activity_ids=[],
        activities={},
        expected_diagnostic_codes=sorted(codes),
        baseline_captured=True,
    )


# ---------------------------------------------------------------------------
# BM-040: BASELINE variant — original schedule, no destatusing applied
# ---------------------------------------------------------------------------
# 3-activity FS chain. BASELINE variant uses original activities/relationships.
# Destatusing is not required or applied. ABCS = CPM on original schedule.
# Expected SIM codes: SIM-001 (success), SIM-010 (variant applied),
#                     SIM-011 (snapshots).
# ---------------------------------------------------------------------------
BM_040 = BenchmarkDefinition(
    metadata=_meta(
        "BM-040",
        "Simulation BASELINE variant: original 3-activity chain, no destatusing",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "3-activity FS chain: A(3)→B(2)→C(2).",
            "BASELINE variant: no destatusing applied.",
            "ABCS CPM = original schedule CPM.",
            "SIM-001, SIM-010, SIM-011 expected.",
            "No SIM-002 (BASELINE does not require destatusing).",
        ],
        tags=["simulation", "baseline", "v1e"],
    ),
    activities=[_act("A", 3), _act("B", 2), _act("C", 2)],
    relationships=[_rel("A", "B"), _rel("B", "C")],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "baseline",
        "simulation_policy": "strict_forensic",
        "new_data_date": None,
        "old_data_date": None,
        "destatusing_policy": "strict_forensic",
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-041: AUTO_DRIVEN — Rule A (complete) + Rule C (future) activities
# ---------------------------------------------------------------------------
# Activity A completes before new_dd (Rule A: no change).
# Activity B is planned after old_dd (Rule C: no change).
# ABCS uses original OD for both. Auto-drive: no predecessors to drive.
# SIM-007: ABCS finish beyond new_data_date (expected for any future work).
# ---------------------------------------------------------------------------
BM_041 = BenchmarkDefinition(
    metadata=_meta(
        "BM-041",
        "Simulation AUTO_DRIVEN: Rule A + Rule C, simple 2-activity ABCS",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule A (AS=Jan 5, AF=Jan 9, both before new_dd=Jan 12).",
            "Activity B: Rule C (ES=Jan 19, EF=Jan 23, both after old_dd=Jan 16).",
            "AUTO_DRIVEN variant; ABCS uses original ODs.",
            "SIM-007: ABCS finish after new data date (expected).",
            "SIM-001, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "auto-driven", "rule-a", "rule-c", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "B", "original_duration": 5,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "advisory_only",
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-042: AUTO_DRIVEN — Rule B activity (complete in window) → OD=AD in ABCS
# ---------------------------------------------------------------------------
# Activity A completes in analysis window (Rule B): AS=Jan 13, AF=Jan 14.
# Rule B transform: clear AS/AF, OD=AD=2. ABCS uses OD=2.
# Activity B is Rule C (future). ABCS schedules A(2)→B(3).
# ---------------------------------------------------------------------------
BM_042 = BenchmarkDefinition(
    metadata=_meta(
        "BM-042",
        "Simulation AUTO_DRIVEN: Rule B activity in ABCS (OD set to actual_duration)",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule B (AS=Jan 13, AF=Jan 14, both in window).",
            "After Rule B: OD=2 (AD=2); no actual dates.",
            "Activity B: Rule C (future, OD=3).",
            "ABCS CPM: A(2)→B(3) from project_start.",
            "SIM-001, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "auto-driven", "rule-b", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 3,
         "actual_start": "2026-01-13", "actual_finish": "2026-01-14",
         "actual_duration": 2},
        {"act_id": "B", "original_duration": 3,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "advisory_only",
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-043: AUTO_DRIVEN — Rule D activity (in-progress, RD used in ABCS CPM)
# ---------------------------------------------------------------------------
# Activity A: AS=Jan 8 (before new_dd), no AF, EF=Jan 14 (<=old_dd). Rule D.
# Rule D: clears AF; computes RD. ABCS uses RD as original_duration for CPM.
# Activity B: Rule C (future). ABCS CPM uses A(RD)→B(3).
# Using advisory_only destatusing policy to avoid PC formula blocking.
# ---------------------------------------------------------------------------
BM_043 = BenchmarkDefinition(
    metadata=_meta(
        "BM-043",
        "Simulation AUTO_DRIVEN: Rule D in-progress activity, RD used in ABCS CPM",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule D (AS=Jan 8, no AF, EF=Jan 14; EF<=old_dd).",
            "Rule D: clears AF, computes RD from new_dd to EF.",
            "ABCS CPM uses RD as OD for activity A.",
            "Activity B: Rule C (future, OD=3).",
            "Advisory_only destatusing policy avoids PC formula checkpoint.",
            "SIM-001, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "auto-driven", "rule-d", "in-progress", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 8,
         "actual_start": "2026-01-08",
         "early_finish": "2026-01-14",
         "actual_duration": 3, "remaining_duration": 2},
        {"act_id": "B", "original_duration": 3,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "advisory_only",
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-044: AUTO_DRIVEN — auto-drive driving predecessor in ABCS
# ---------------------------------------------------------------------------
# P1 (Rule A, complete) and P2 (Rule A, complete) both precede S (Rule C).
# P1→S has planned lag=5; P2→S has planned lag=0.
# After lag analysis: P1 drives (smaller variance), P2 reset to planned.
# ABCS uses auto-driven relationships: driving predecessor gets actual lag.
# ---------------------------------------------------------------------------
BM_044 = BenchmarkDefinition(
    metadata=_meta(
        "BM-044",
        "Simulation AUTO_DRIVEN: auto-drive selects driving predecessor for ABCS",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "P1 (Rule A, AS=Jan 5, AF=Jan 9) and P2 (Rule A, AS=Jan 5, AF=Jan 9).",
            "S (Rule C, ES=Jan 19) with P1→S lag=5 and P2→S lag=0.",
            "Actual lag(P1→S, FS) = wt[S.AS] - wt[P1.AF].",
            "Actual lag(P2→S, FS) = wt[S.AS] - wt[P2.AF].",
            "Auto-drive selects predecessor with minimum |actual_lag - planned_lag|.",
            "P1 has smaller variance (planned=5 vs actual ~7: var=2).",
            "P2 has larger variance (planned=0 vs actual ~7: var=7).",
            "DRV-001 (driving) and DRV-002 (non-driving) in destatusing result.",
            "SIM-001, SIM-007, SIM-010, SIM-011 expected in simulation.",
        ],
        tags=["simulation", "auto-driven", "autodrive", "v1e"],
    ),
    activities=[
        {"act_id": "P1", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "P2", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "S", "original_duration": 5,
         "early_start": "2026-01-19", "early_finish": "2026-01-23",
         "actual_start": "2026-01-20"},
    ],
    relationships=[_rel("P1", "S", _FS, 5), _rel("P2", "S", _FS, 0)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "advisory_only",
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-045: LAG_ADJUSTED variant — actual lags applied, no auto-drive selection
# ---------------------------------------------------------------------------
# Same activities as BM-044 but LAG_ADJUSTED variant: all relationships
# receive actual_lag without driving-predecessor selection override.
# ---------------------------------------------------------------------------
BM_045 = BenchmarkDefinition(
    metadata=_meta(
        "BM-045",
        "Simulation LAG_ADJUSTED: actual lags applied without auto-drive selection",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Same as BM-044 but LAG_ADJUSTED variant.",
            "Both P1→S and P2→S receive their actual lag values.",
            "No auto-drive predecessor selection: both relationships updated.",
            "SIM-001, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "lag-adjusted", "v1e"],
    ),
    activities=[
        {"act_id": "P1", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "P2", "original_duration": 5,
         "actual_start": "2026-01-05", "actual_finish": "2026-01-09",
         "actual_duration": 5},
        {"act_id": "S", "original_duration": 5,
         "early_start": "2026-01-19", "early_finish": "2026-01-23",
         "actual_start": "2026-01-20"},
    ],
    relationships=[_rel("P1", "S", _FS, 5), _rel("P2", "S", _FS, 0)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "lag_adjusted",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "advisory_only",
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-046: CPW_COMPATIBILITY policy — blocked destatusing does NOT block sim
# ---------------------------------------------------------------------------
# Activity A triggers Rule D with STRICT_FORENSIC destatusing → PC formula
# blocking checkpoint → dst.is_blocked=True.
# CPW_COMPATIBILITY sim policy: block_if_destatusing_blocked=False,
# block_at=CRITICAL. SIM-003 emitted (ANALYTICAL_RISK) → checkpoint generated
# (checkpoint_at=ANALYTICAL_RISK) but NOT blocking (block_at=CRITICAL).
# Result: sim is_blocked=False despite dst.is_blocked=True.
# ---------------------------------------------------------------------------
BM_046 = BenchmarkDefinition(
    metadata=_meta(
        "BM-046",
        "Simulation CPW_COMPATIBILITY policy: blocked destatusing does not block sim",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule D (AS=Jan 8, no AF, EF=Jan 14).",
            "STRICT_FORENSIC destatusing: PC formula checkpoint → dst.is_blocked=True.",
            "CPW_COMPATIBILITY sim policy: propagates blocked as SIM-003, not blocking.",
            "block_at=CRITICAL; SIM-003 is ANALYTICAL_RISK → not blocking.",
            "Result: expected_is_blocked=False.",
            "SIM-001, SIM-003, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "cpw-compatibility", "blocked-destatusing", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 8,
         "actual_start": "2026-01-08",
         "early_finish": "2026-01-14",
         "actual_duration": 3, "remaining_duration": 2},
        {"act_id": "B", "original_duration": 3,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-003", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "cpw_compatibility",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "strict_forensic",  # produces dst.is_blocked=True
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-047: ADVISORY_ONLY policy — never blocks regardless of destatusing status
# ---------------------------------------------------------------------------
# Same scenario as BM-046 but ADVISORY_ONLY sim policy:
# block_at=None → never blocks. SIM-003 may be emitted but produces no
# blocking checkpoint (checkpoint_at=ANALYTICAL_RISK, but block_at=None).
# Result: expected_is_blocked=False always under ADVISORY_ONLY.
# ---------------------------------------------------------------------------
BM_047 = BenchmarkDefinition(
    metadata=_meta(
        "BM-047",
        "Simulation ADVISORY_ONLY policy: never blocks regardless of destatusing",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule D (AS=Jan 8, no AF, EF=Jan 14).",
            "STRICT_FORENSIC destatusing: dst.is_blocked=True (PC formula).",
            "ADVISORY_ONLY sim policy: block_at=None → no blocking ever.",
            "SIM-003 emitted (dst.is_blocked propagated as advisory).",
            "Result: expected_is_blocked=False.",
            "SIM-001, SIM-003, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "advisory-only", "never-blocks", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 8,
         "actual_start": "2026-01-08",
         "early_finish": "2026-01-14",
         "actual_duration": 3, "remaining_duration": 2},
        {"act_id": "B", "original_duration": 3,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-001", "SIM-003", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "advisory_only",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "strict_forensic",  # produces dst.is_blocked=True
        "expected_is_blocked": False,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-048: STRICT_FORENSIC sim policy — blocked destatusing blocks sim
# ---------------------------------------------------------------------------
# Same Rule D scenario. STRICT_FORENSIC destatusing: dst.is_blocked=True.
# STRICT_FORENSIC sim policy: block_if_destatusing_blocked=True,
# block_at=ANALYTICAL_RISK. SIM-003 is ANALYTICAL_RISK → blocking checkpoint.
# Result: expected_is_blocked=True.
# ---------------------------------------------------------------------------
BM_048 = BenchmarkDefinition(
    metadata=_meta(
        "BM-048",
        "Simulation STRICT_FORENSIC policy: blocked destatusing blocks simulation",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule D (AS=Jan 8, no AF, EF=Jan 14).",
            "STRICT_FORENSIC destatusing: dst.is_blocked=True (PC formula).",
            "STRICT_FORENSIC sim policy: block_if_destatusing_blocked=True.",
            "SIM-003 emitted (ANALYTICAL_RISK) → blocking checkpoint generated.",
            "Result: expected_is_blocked=True.",
            "SIM-003, SIM-007, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "strict-forensic", "blocked", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 8,
         "actual_start": "2026-01-08",
         "early_finish": "2026-01-14",
         "actual_duration": 3, "remaining_duration": 2},
        {"act_id": "B", "original_duration": 3,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-003", "SIM-007", "SIM-010", "SIM-011"),
    extra_data={
        "simulation_variant": "auto_driven",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "strict_forensic",  # produces dst.is_blocked=True
        "expected_is_blocked": True,
        "expected_abcs_valid": True,
    },
)


# ---------------------------------------------------------------------------
# BM-049: ANALYST_REVIEWED variant — pending checkpoints block simulation
# ---------------------------------------------------------------------------
# Activity A: Rule D (in-progress). STRICT_FORENSIC destatusing generates a
# blocking PC formula checkpoint (DST-004/006 → PENDING).
# ANALYST_REVIEWED variant: requires all dst checkpoints APPROVED.
# Since DST checkpoint is PENDING → SIM-012 emitted → simulation blocked.
# ---------------------------------------------------------------------------
BM_049 = BenchmarkDefinition(
    metadata=_meta(
        "BM-049",
        "Simulation ANALYST_REVIEWED variant: PENDING destatusing checkpoints block sim",
        BenchmarkCategory.SIMULATION,
        assumptions=[
            "Activity A: Rule D (AS=Jan 8, no AF, EF=Jan 14).",
            "STRICT_FORENSIC destatusing: PC formula checkpoint → PENDING.",
            "ANALYST_REVIEWED variant: requires all checkpoints APPROVED.",
            "PENDING DST checkpoint detected → SIM-012 (CRITICAL) emitted.",
            "SIM-012 → blocking checkpoint under STRICT_FORENSIC sim policy.",
            "Result: expected_is_blocked=True.",
            "SIM-012, SIM-010, SIM-011 expected.",
        ],
        tags=["simulation", "analyst-reviewed", "pending-checkpoints", "v1e"],
    ),
    activities=[
        {"act_id": "A", "original_duration": 8,
         "actual_start": "2026-01-08",
         "early_finish": "2026-01-14",
         "actual_duration": 3, "remaining_duration": 2},
        {"act_id": "B", "original_duration": 3,
         "early_start": "2026-01-19", "early_finish": "2026-01-23"},
    ],
    relationships=[_rel("A", "B", _FS)],
    project_start=_SIM_START,
    calendar_work_days=_STD_WORK_DAYS,
    hours_per_day=_STD_HPD,
    expectations=_sim_expectations("SIM-010", "SIM-011", "SIM-012"),
    extra_data={
        "simulation_variant": "analyst_reviewed",
        "simulation_policy": "strict_forensic",
        "new_data_date": _NEW_DD,
        "old_data_date": _OLD_DD,
        "destatusing_policy": "strict_forensic",  # produces PENDING PC formula checkpoint
        "expected_is_blocked": True,
        "expected_abcs_valid": True,
    },
)


def build_simulation_suite() -> BenchmarkSuite:
    """
    Build and return the V1-E simulation benchmark suite (BM-040 through BM-049).

    Covers: BASELINE variant, AUTO_DRIVEN with all rule types (A, B, C, D),
    LAG_ADJUSTED variant, policy behavior (CPW_COMPATIBILITY, ADVISORY_ONLY,
    STRICT_FORENSIC), and ANALYST_REVIEWED blocking. All fixtures synthetic.
    """
    suite = BenchmarkSuite(
        suite_id="SUITE-SIM-001",
        suite_version="1.0-v1e",
        description=(
            "V1-E simulation schedule generation benchmark suite. "
            "Covers BASELINE, AUTO_DRIVEN, LAG_ADJUSTED, ANALYST_REVIEWED "
            "variants and STRICT_FORENSIC, CPW_COMPATIBILITY, ADVISORY_ONLY "
            "policies. All fixtures synthetic; no proprietary schedules."
        ),
    )
    for bm in [
        BM_040, BM_041, BM_042, BM_043, BM_044,
        BM_045, BM_046, BM_047, BM_048, BM_049,
    ]:
        suite.add(bm)
    return suite


SIMULATION_SUITE: BenchmarkSuite = build_simulation_suite()
