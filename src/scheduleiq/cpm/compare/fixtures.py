"""
V1-G: Reference schedule model and synthetic comparison fixtures.

ReferenceSchedule represents the structured output of a CPW or P6-equivalent
analysis — what the reference tool would produce for the same input schedule.
All reference fields are Optional to support partial reference data (e.g.,
historical CPW outputs that only report ES/EF/TF but not LS/LF/FF).

ComparisonFixture pairs a reference schedule with metadata about the comparison
scenario (expected divergence categories, notes).

Synthetic fixtures CV-001 through CV-010 provide governed benchmark scenarios:
  CV-001: Simple FS chain — exact match expected
  CV-002: Multi-calendar lag shift — CALENDAR_BEHAVIOR_DIFFERENCE expected
  CV-003: Float method divergence — FLOAT_METHOD_DIFFERENCE expected
  CV-004: Negative float — MATERIAL_ANALYTICAL_DIFFERENCE expected
  CV-005: Critical path agreement — exact CP match expected
  CV-006: ABCS comparison — project finish match expected
  CV-007: Retained Logic vs Progress Override — P6_EMULATION_DIFFERENCE expected
  CV-008: Auto-drive lag comparison — LAG_BEHAVIOR_DIFFERENCE possible
  CV-009: Lag calendar strategy sensitivity — LAG_BEHAVIOR_DIFFERENCE expected
  CV-010: Normalization comparison — EXPECTED_DIFFERENCE expected

All fixtures are synthetic. No proprietary schedule data is included.
Fixture source is always "synthetic" or "analyst_reviewed".

Source: ADR-016; ADR-009 (benchmark governance — no proprietary data).

Ported from the LI MIP 3.9 tool (mip39.comparison_validation.fixtures) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Reference activity model
# ---------------------------------------------------------------------------

@dataclass
class ReferenceScheduledActivity:
    """
    Structured representation of one activity's output from a CPW/reference tool.

    All fields are Optional to accommodate partial reference data. Fields set
    to None are skipped during comparison (not treated as divergences).

    Fields:
        act_id:            Activity identifier (must match mip39 activity ID).
        early_start:       Expected Early Start date, or None.
        early_finish:      Expected Early Finish date, or None.
        late_start:        Expected Late Start date, or None.
        late_finish:       Expected Late Finish date, or None.
        total_float:       Expected Total Float in workdays, or None.
        free_float:        Expected Free Float in workdays, or None.
        is_critical:       Expected criticality flag, or None.
        original_duration: Expected original duration in workdays, or None.
        notes:             Analyst notes about this reference activity.
    """

    act_id: str
    early_start: Optional[date] = None
    early_finish: Optional[date] = None
    late_start: Optional[date] = None
    late_finish: Optional[date] = None
    total_float: Optional[int] = None
    free_float: Optional[int] = None
    is_critical: Optional[bool] = None
    original_duration: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "act_id": self.act_id,
            "early_start": self.early_start.isoformat() if self.early_start else None,
            "early_finish": self.early_finish.isoformat() if self.early_finish else None,
            "late_start": self.late_start.isoformat() if self.late_start else None,
            "late_finish": self.late_finish.isoformat() if self.late_finish else None,
            "total_float": self.total_float,
            "free_float": self.free_float,
            "is_critical": self.is_critical,
            "original_duration": self.original_duration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReferenceScheduledActivity":
        return cls(
            act_id=d["act_id"],
            early_start=date.fromisoformat(d["early_start"]) if d.get("early_start") else None,
            early_finish=date.fromisoformat(d["early_finish"]) if d.get("early_finish") else None,
            late_start=date.fromisoformat(d["late_start"]) if d.get("late_start") else None,
            late_finish=date.fromisoformat(d["late_finish"]) if d.get("late_finish") else None,
            total_float=d.get("total_float"),
            free_float=d.get("free_float"),
            is_critical=d.get("is_critical"),
            original_duration=d.get("original_duration"),
            notes=d.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Reference schedule model
# ---------------------------------------------------------------------------

@dataclass
class ReferenceSchedule:
    """
    Structured output of a CPW/reference tool for one analysis run.

    Fields:
        schedule_id:              Unique identifier (e.g. "REF-001").
        description:              Human-readable description.
        activities:               dict[act_id → ReferenceScheduledActivity].
        project_finish:           Expected project finish date, or None.
        project_start:            Project start date used, or None.
        critical_path_activity_ids: Activity IDs on the CPW critical path (order
                                  preserved but comparison is order-insensitive).
        source:                   "synthetic", "analyst_reviewed", or "historical_cpw".
        tool:                     Reference tool name (e.g. "CPW-P6", "Primavera P6").
        tool_version:             Tool version string, or "" if unknown.
        notes:                    Analyst notes about this reference schedule.
        lag_strategy_assumed:     Lag calendar strategy assumed by the reference tool.
                                  "unknown" when not documented.
        calendar_convention:      Calendar convention used (e.g. "inclusive_day").
    """

    schedule_id: str
    description: str
    activities: dict[str, ReferenceScheduledActivity] = field(default_factory=dict)
    project_finish: Optional[date] = None
    project_start: Optional[date] = None
    critical_path_activity_ids: list[str] = field(default_factory=list)
    source: str = "synthetic"
    tool: str = "CPW-P6"
    tool_version: str = ""
    notes: str = ""
    lag_strategy_assumed: str = "predecessor_calendar"
    calendar_convention: str = "inclusive_day"

    def add_activity(self, act: ReferenceScheduledActivity) -> None:
        self.activities[act.act_id] = act

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "description": self.description,
            "activities": {k: v.to_dict() for k, v in self.activities.items()},
            "project_finish": self.project_finish.isoformat() if self.project_finish else None,
            "project_start": self.project_start.isoformat() if self.project_start else None,
            "critical_path_activity_ids": list(self.critical_path_activity_ids),
            "source": self.source,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "notes": self.notes,
            "lag_strategy_assumed": self.lag_strategy_assumed,
            "calendar_convention": self.calendar_convention,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReferenceSchedule":
        ref = cls(
            schedule_id=d["schedule_id"],
            description=d.get("description", ""),
            project_finish=date.fromisoformat(d["project_finish"]) if d.get("project_finish") else None,
            project_start=date.fromisoformat(d["project_start"]) if d.get("project_start") else None,
            critical_path_activity_ids=list(d.get("critical_path_activity_ids", [])),
            source=d.get("source", "synthetic"),
            tool=d.get("tool", "CPW-P6"),
            tool_version=d.get("tool_version", ""),
            notes=d.get("notes", ""),
            lag_strategy_assumed=d.get("lag_strategy_assumed", "predecessor_calendar"),
            calendar_convention=d.get("calendar_convention", "inclusive_day"),
        )
        for act_dict in d.get("activities", {}).values():
            ref.add_activity(ReferenceScheduledActivity.from_dict(act_dict))
        return ref


# ---------------------------------------------------------------------------
# Comparison fixture
# ---------------------------------------------------------------------------

@dataclass
class ComparisonFixture:
    """
    Pairing of a reference schedule with metadata for governed comparison testing.

    Fields:
        fixture_id:                  Unique fixture ID (e.g. "CV-001").
        description:                 Human-readable description of the scenario.
        reference:                   ReferenceSchedule for this fixture.
        expected_divergence_cats:    DivergenceCategory names expected to appear.
        expected_match_pct_min:      Minimum acceptable activity match percentage.
        expected_cp_agreement:       Whether CP agreement is expected.
        notes:                       Analyst notes.
        source:                      "synthetic" or "analyst_reviewed".
    """

    fixture_id: str
    description: str
    reference: ReferenceSchedule
    expected_divergence_cats: list[str] = field(default_factory=list)
    expected_match_pct_min: float = 100.0
    expected_cp_agreement: bool = True
    notes: str = ""
    source: str = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "description": self.description,
            "reference": self.reference.to_dict(),
            "expected_divergence_cats": list(self.expected_divergence_cats),
            "expected_match_pct_min": self.expected_match_pct_min,
            "expected_cp_agreement": self.expected_cp_agreement,
            "notes": self.notes,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Synthetic comparison fixtures CV-001 through CV-010
# ---------------------------------------------------------------------------

def _ra(
    act_id: str,
    es: str,
    ef: str,
    ls: str,
    lf: str,
    tf: int,
    ff: int,
    critical: bool,
    dur: int,
) -> ReferenceScheduledActivity:
    """Helper: build a fully-specified ReferenceScheduledActivity."""
    return ReferenceScheduledActivity(
        act_id=act_id,
        early_start=date.fromisoformat(es),
        early_finish=date.fromisoformat(ef),
        late_start=date.fromisoformat(ls),
        late_finish=date.fromisoformat(lf),
        total_float=tf,
        free_float=ff,
        is_critical=critical,
        original_duration=dur,
    )


def _ra_partial(
    act_id: str,
    es: Optional[str] = None,
    ef: Optional[str] = None,
    tf: Optional[int] = None,
    critical: Optional[bool] = None,
) -> ReferenceScheduledActivity:
    """Helper: build a partial ReferenceScheduledActivity (CPW output often partial)."""
    return ReferenceScheduledActivity(
        act_id=act_id,
        early_start=date.fromisoformat(es) if es else None,
        early_finish=date.fromisoformat(ef) if ef else None,
        total_float=tf,
        is_critical=critical,
    )


# CV-001: Simple FS chain — exact match expected
# Schedule: A→B→C, all Mon–Fri, no lags. Reference matches mip39 exactly.
CV_001 = ComparisonFixture(
    fixture_id="CV-001",
    description=(
        "Simple 3-activity FS chain on a standard Mon–Fri calendar. "
        "No lags. Reference matches mip39 analytical output exactly. "
        "Validates baseline exact-match detection."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-001",
        description="Simple FS chain — exact CPW match expected",
        project_finish=date(2026, 1, 14),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B", "C"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "Reference built to match mip39 output for a 3-activity FS chain "
            "starting 2026-01-05. A: dur=2, B: dur=3, C: dur=2. "
            "Inclusive day convention: A ES=Jan5 EF=Jan6, B ES=Jan7 EF=Jan9, "
            "C ES=Jan12 EF=Jan14 (weekends skipped)."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06", 0, 0, True, 2),
            "B": _ra("B", "2026-01-07", "2026-01-09", "2026-01-07", "2026-01-09", 0, 0, True, 3),
            "C": _ra("C", "2026-01-12", "2026-01-14", "2026-01-12", "2026-01-14", 0, 0, True, 2),
        },
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes="Baseline exact-match scenario. Any divergence indicates an engine regression.",
    source="synthetic",
)

# CV-002: Parallel paths — float divergence scenario
# Schedule: A→C and B→C where A and B start at project start.
# mip39: A=critical, B has float. Reference agrees on CP but reports slightly
# different TF due to a documented CPW display rounding behavior.
# Expected: FLOAT_METHOD_DIFFERENCE on B.total_float if reference differs.
# For this synthetic fixture, reference matches exactly (float rounding not exposed).
CV_002 = ComparisonFixture(
    fixture_id="CV-002",
    description=(
        "Parallel paths with float. A and B both lead to C. A is critical "
        "(longer). B has total float equal to the path difference. Reference "
        "provided with exact float values. Validates float comparison and "
        "CP agreement on parallel-path schedule."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-002",
        description="Parallel paths — float and CP comparison",
        project_finish=date(2026, 1, 14),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "C"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "A: dur=5 (Jan5–Jan9), B: dur=2 (Jan5–Jan6), C: dur=3 (Jan12–Jan14). "
            "B has TF=3 (Jan7–Jan9 unused). "
            "C ES=Jan12 because A EF=Jan9 (Mon), next workday Jan12."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True, 5),
            "B": _ra("B", "2026-01-05", "2026-01-06", "2026-01-08", "2026-01-09", 3, 3, False, 2),
            "C": _ra("C", "2026-01-12", "2026-01-14", "2026-01-12", "2026-01-14", 0, 0, True, 3),
        },
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes=(
        "Reference matches expected mip39 output exactly. "
        "Tests parallel-path float computation and CP agreement."
    ),
    source="synthetic",
)

# CV-003: Float method divergence
# CPW uses TF=0 as the criticality criterion; mip39 uses longest-path.
# For a schedule with a tied longest path, CPW may mark additional activities
# critical via TF=0 that mip39 does not (or vice versa for non-tie cases).
# This fixture has an activity with TF=0 that is NOT on the longest path.
# Expected: FLOAT_METHOD_DIFFERENCE on is_critical.
CV_003 = ComparisonFixture(
    fixture_id="CV-003",
    description=(
        "Schedule with an activity that has TF=0 but is not on the "
        "longest/controlling path (e.g., a short parallel path that finishes "
        "at project finish but is not the primary driver). CPW marks it critical "
        "via TF=0; mip39 uses longest-path (INFRA-008). Expected divergence: "
        "FLOAT_METHOD_DIFFERENCE on is_critical."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-003",
        description="TF=0 vs longest-path criticality divergence",
        project_finish=date(2026, 1, 9),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B", "C"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "CPW marks B critical (TF=0 via project finish constraint) even though "
            "A→C is the driving path. mip39 longest-path: A and C are critical, "
            "B is not (B is an alternate finish node with TF=0 but not the "
            "controlling path). Reference deliberately uses TF=0 criterion."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True, 3),
            "B": _ra("B", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True, 5),
            "C": _ra("C", "2026-01-08", "2026-01-09", "2026-01-08", "2026-01-09", 0, 0, True, 2),
        },
    ),
    expected_divergence_cats=["FLOAT_METHOD_DIFFERENCE"],
    expected_match_pct_min=50.0,
    expected_cp_agreement=False,
    notes=(
        "is_critical divergence on A and C (or B, depending on which path mip39 "
        "selects as the controlling path) is FLOAT_METHOD_DIFFERENCE by design. "
        "Documents the longest-path vs TF=0 governance decision (ADR-005, INFRA-008)."
    ),
    source="synthetic",
)

# CV-004: Lag behavior — FS lag with predecessor calendar
# Schedule with a FS+5 lag. CPW uses predecessor calendar for lag.
# mip39 uses configurable LagCalendarStrategy. Under PREDECESSOR_CALENDAR,
# results should match. Under other strategies, LAG_BEHAVIOR_DIFFERENCE appears.
CV_004 = ComparisonFixture(
    fixture_id="CV-004",
    description=(
        "FS relationship with a 5-workday lag. CPW assumes predecessor calendar "
        "for lag arithmetic. mip39 with PREDECESSOR_CALENDAR strategy should "
        "produce matching results. This fixture validates lag behavior under the "
        "CPW-default lag calendar strategy. No divergence expected under "
        "PREDECESSOR_CALENDAR."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-004",
        description="FS+5 lag, predecessor calendar — no divergence expected",
        project_finish=date(2026, 1, 23),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B"],
        source="synthetic",
        tool="CPW-P6",
        lag_strategy_assumed="predecessor_calendar",
        notes=(
            "A: dur=3 (Jan5–Jan7). FS+5 lag on A→B: B ES = Jan7+5wd = Jan14. "
            "B: dur=7 (Jan14–Jan22, skipping Jan17-18 weekend, Jan21-22 not workdays, "
            "actually Jan14–Jan22 = 7 workdays: Jan14,15,16,19,20,21,22). "
            "Project finish: Jan22. Inclusive day."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True, 3),
            "B": _ra("B", "2026-01-14", "2026-01-22", "2026-01-14", "2026-01-22", 0, 0, True, 7),
        },
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes=(
        "Run comparison with PREDECESSOR_CALENDAR lag strategy. "
        "Divergence expected under other strategies → LAG_BEHAVIOR_DIFFERENCE."
    ),
    source="synthetic",
)

# CV-005: Negative total float detection
# Activity on a path that finishes after project finish due to a constraint.
# mip39 and CPW should both report negative TF. Validates negative-float
# comparison and MATERIAL_ANALYTICAL_DIFFERENCE when values differ.
CV_005 = ComparisonFixture(
    fixture_id="CV-005",
    description=(
        "Schedule with one activity chain producing negative total float. "
        "Both mip39 and CPW reference report the same negative TF. "
        "Validates correct handling of negative float in comparison metrics."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-005",
        description="Negative float — agreed result",
        project_finish=date(2026, 1, 9),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "A: dur=5 (Jan5–Jan9 critical, TF=0). B: dur=5, but predecessor "
            "is C which starts after project finish → B has TF<0. "
            "Simplified: two separate paths, one overrunning."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-09", "2026-01-05", "2026-01-09", 0, 0, True, 5),
            "B": _ra("B", "2026-01-07", "2026-01-13", "2026-01-05", "2026-01-09", -2, 0, False, 5),
        },
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes=(
        "Negative float scenario. Agreement expected when both tools implement "
        "the same float formula. Divergence indicates a float calculation difference."
    ),
    source="synthetic",
)

# CV-006: Calendar behavior — short chain, exact match
# Single-calendar schedule; no calendar divergence expected.
# Tests that the comparison framework correctly identifies an exact match
# on a schedule with more complex dating (mid-week start, multiple durations).
CV_006 = ComparisonFixture(
    fixture_id="CV-006",
    description=(
        "Mid-week start, multi-duration chain. Single calendar. "
        "Validates exact match detection on a non-Monday start schedule "
        "where week-boundary arithmetic is exercised."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-006",
        description="Mid-week start, exact match expected",
        project_finish=date(2026, 1, 21),
        project_start=date(2026, 1, 7),
        critical_path_activity_ids=["X", "Y", "Z"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "X: dur=3 Wed Jan7–Fri Jan9, Y: dur=5 Mon Jan12–Fri Jan16, "
            "Z: dur=3 Mon Jan19–Wed Jan21. All on CP, TF=0."
        ),
        activities={
            "X": _ra("X", "2026-01-07", "2026-01-09", "2026-01-07", "2026-01-09", 0, 0, True, 3),
            "Y": _ra("Y", "2026-01-12", "2026-01-16", "2026-01-12", "2026-01-16", 0, 0, True, 5),
            "Z": _ra("Z", "2026-01-19", "2026-01-21", "2026-01-19", "2026-01-21", 0, 0, True, 3),
        },
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes="Mid-week start scenario validates workday boundary arithmetic.",
    source="synthetic",
)

# CV-007: P6 Emulation divergence
# CPW applies a Progress Override scheduling mode for one partially-complete
# activity. mip39 uses Retained Logic only (ADR-002). This produces different
# ES/EF for successor activities. Expected: P6_EMULATION_DIFFERENCE.
CV_007 = ComparisonFixture(
    fixture_id="CV-007",
    description=(
        "Schedule where CPW/P6 used Progress Override for one in-progress "
        "activity. mip39 uses Retained Logic only (ADR-002). Successor dates "
        "will differ. Expected divergence: P6_EMULATION_DIFFERENCE. "
        "Documents the Retained Logic design decision."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-007",
        description="Progress Override vs Retained Logic — P6 emulation divergence",
        project_finish=date(2026, 1, 21),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B", "C"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "CPW ran B (in-progress) under Progress Override: B EF computed "
            "from actual remaining duration ignoring predecessors (OOS). "
            "mip39 Retained Logic: B's successor is constrained by B's planned "
            "finish. CPW reference shows earlier C ES than mip39 would compute."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True, 3),
            "B": _ra("B", "2026-01-06", "2026-01-14", "2026-01-06", "2026-01-14", 0, 0, True, 7),
            "C": _ra("C", "2026-01-15", "2026-01-21", "2026-01-15", "2026-01-21", 0, 0, True, 5),
        },
    ),
    expected_divergence_cats=["P6_EMULATION_DIFFERENCE"],
    expected_match_pct_min=33.0,
    expected_cp_agreement=False,
    notes=(
        "P6_EMULATION_DIFFERENCE is expected and governed. mip39 uses Retained "
        "Logic (ADR-002); CPW may use Progress Override. This difference does "
        "not indicate an mip39 defect."
    ),
    source="synthetic",
)

# CV-008: ABCS comparison — project finish agreement
# After destatusing and ABCS generation, compare ABCS project finish against
# a reference ABCS finish. Only project_finish and critical_path checked
# (no per-activity reference data available in this fixture).
CV_008 = ComparisonFixture(
    fixture_id="CV-008",
    description=(
        "ABCS project finish comparison. Reference provides only project_finish "
        "and critical_path_activity_ids (no per-activity data). Tests that "
        "the comparison framework correctly handles partial reference data "
        "and project-level comparisons."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-008",
        description="ABCS project finish — partial reference",
        project_finish=date(2026, 2, 13),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B", "C", "D"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "CPW ABCS produced project finish 2026-02-13 for a 4-activity destatused "
            "schedule. Per-activity CPW output not available. Only project finish "
            "and CP activity list provided. Partial comparison only."
        ),
        activities={},
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes=(
        "Partial reference fixture. Tests project-level comparison when per-activity "
        "reference data is unavailable. Common scenario with historical CPW outputs."
    ),
    source="synthetic",
)

# CV-009: Lag calendar strategy sensitivity experiment fixture
# A schedule with lags where different LagCalendarStrategy values produce
# different results. Reference uses predecessor calendar (CPW default).
# This fixture defines what the reference reports; the experiment framework
# tests all strategies and compares to this reference.
CV_009 = ComparisonFixture(
    fixture_id="CV-009",
    description=(
        "Lag calendar strategy sensitivity. Reference uses predecessor calendar "
        "(CPW default). The experiment framework tests PREDECESSOR, SUCCESSOR, "
        "PROJECT_DEFAULT, and CONTINUOUS_24H strategies. Divergences from the "
        "predecessor-calendar baseline are classified LAG_BEHAVIOR_DIFFERENCE. "
        "Documents whether per-relationship lag calendar assignment is necessary."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-009",
        description="Lag strategy sensitivity — predecessor calendar baseline",
        project_finish=date(2026, 1, 23),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B"],
        source="synthetic",
        tool="CPW-P6",
        lag_strategy_assumed="predecessor_calendar",
        notes=(
            "A: dur=3 (Jan5–Jan7). FS+5 lag → B ES=Jan14 (5 workdays after A EF). "
            "B: dur=8 (Jan14–Jan23). Project finish Jan23. "
            "Predecessor calendar = standard Mon-Fri calendar."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True, 3),
            "B": _ra("B", "2026-01-14", "2026-01-23", "2026-01-14", "2026-01-23", 0, 0, True, 8),
        },
    ),
    expected_divergence_cats=["LAG_BEHAVIOR_DIFFERENCE"],
    expected_match_pct_min=50.0,
    expected_cp_agreement=True,
    notes=(
        "Run the lag strategy experiment against this reference. "
        "If all strategies agree on B ES, run-level strategy is sufficient. "
        "If strategies disagree, per-relationship lag calendar may be necessary."
    ),
    source="synthetic",
)

# CV-010: Normalization comparison
# A schedule with a known normalization condition (out-of-sequence progress).
# CPW reference does not apply OOS correction (not in CPW scope);
# mip39 detects and reports via NRM-013. No difference in CPM outputs expected
# (V1-C is detection-only). Expected: EXPECTED_DIFFERENCE on normalization flags.
CV_010 = ComparisonFixture(
    fixture_id="CV-010",
    description=(
        "Normalization scenario: out-of-sequence progress detected by mip39 "
        "(NRM-013) but not reported by CPW. V1-C is detection-only (ADR-013), "
        "so CPM outputs (ES/EF/TF) should match. The divergence is in "
        "normalization diagnostics only, not in schedule dates or float. "
        "Expected: exact CPM match; EXPECTED_DIFFERENCE on normalization reporting."
    ),
    reference=ReferenceSchedule(
        schedule_id="REF-CV-010",
        description="Normalization — CPM match, diagnostic divergence only",
        project_finish=date(2026, 1, 14),
        project_start=date(2026, 1, 5),
        critical_path_activity_ids=["A", "B", "C"],
        source="synthetic",
        tool="CPW-P6",
        notes=(
            "CPW does not flag NRM-013 OOS condition. mip39 detects it "
            "and records in NormalizationResult. CPM dates are identical — "
            "V1-C normalization is detection-only, no schedule modification."
        ),
        activities={
            "A": _ra("A", "2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06", 0, 0, True, 2),
            "B": _ra("B", "2026-01-07", "2026-01-09", "2026-01-07", "2026-01-09", 0, 0, True, 3),
            "C": _ra("C", "2026-01-12", "2026-01-14", "2026-01-12", "2026-01-14", 0, 0, True, 2),
        },
    ),
    expected_divergence_cats=[],
    expected_match_pct_min=100.0,
    expected_cp_agreement=True,
    notes=(
        "CPM outputs match exactly. The mip39 normalization detection layer "
        "adds diagnostic information not present in CPW. This is an "
        "EXPECTED_DIFFERENCE in analytical capabilities, not a CPM divergence."
    ),
    source="synthetic",
)


# ---------------------------------------------------------------------------
# Comparison fixture registry
# ---------------------------------------------------------------------------

COMPARISON_FIXTURES: dict[str, ComparisonFixture] = {
    "CV-001": CV_001,
    "CV-002": CV_002,
    "CV-003": CV_003,
    "CV-004": CV_004,
    "CV-005": CV_005,
    "CV-006": CV_006,
    "CV-007": CV_007,
    "CV-008": CV_008,
    "CV-009": CV_009,
    "CV-010": CV_010,
}


def get_comparison_fixture(fixture_id: str) -> ComparisonFixture:
    """Return the named comparison fixture. Raises KeyError for unknown IDs."""
    return COMPARISON_FIXTURES[fixture_id]
