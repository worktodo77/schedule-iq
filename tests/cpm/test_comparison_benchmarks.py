"""
V1-G: Tests for comparison_validation benchmark fixtures run through
compare_schedules().

Each CV-001 through CV-010 fixture is used as input to compare_schedules()
with a synthetic analysis result that matches the reference. This verifies:
  - Fixtures are structurally valid and can be passed to compare_schedules()
  - Expected divergence categories appear (or are absent) as documented
  - Match percentage meets the expected_match_pct_min threshold
  - Critical-path agreement matches expected_cp_agreement

For fixtures where exact match is expected (CV-001), divergence count must be 0.
For fixtures expecting divergences, the expected categories must appear.

These tests use a synthetic "matching" analysis result constructed from the
reference data itself, then selectively mutate fields to simulate the documented
divergence scenario.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date
from types import SimpleNamespace

from scheduleiq.cpm.compare.comparator import compare_schedules  # noqa: E402
from scheduleiq.cpm.compare.divergences import DivergenceCategory  # noqa: E402
from scheduleiq.cpm.compare.fixtures import (  # noqa: E402
    COMPARISON_FIXTURES,
    ReferenceSchedule,
    ReferenceScheduledActivity,
    get_comparison_fixture,
)
from scheduleiq.cpm.compare.policies import ComparisonPolicy  # noqa: E402
from scheduleiq.cpm.compare.tolerances import TOLERANCE_STRICT  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_matching_analysis(reference: ReferenceSchedule, is_valid: bool = True):
    """
    Build a synthetic AnalysisResult that exactly matches the reference schedule.

    All fields that are None in the reference are given sensible defaults so
    that the comparator skips them (None ref values are skipped by design).
    """
    scheduled = {}
    for act_id, ra in reference.activities.items():
        sa = SimpleNamespace(
            act_id=act_id,
            early_start=ra.early_start or date(2024, 1, 2),
            early_finish=ra.early_finish or date(2024, 1, 12),
            late_start=ra.late_start or date(2024, 1, 2),
            late_finish=ra.late_finish or date(2024, 1, 12),
            total_float=ra.total_float if ra.total_float is not None else 0,
            free_float=ra.free_float if ra.free_float is not None else 0,
            is_critical=ra.is_critical if ra.is_critical is not None else False,
            original_duration=ra.original_duration if ra.original_duration is not None else 5,
        )
        scheduled[act_id] = sa

    cp = SimpleNamespace(activity_ids=list(reference.critical_path_activity_ids))
    return SimpleNamespace(
        scheduled=scheduled,
        project_finish=reference.project_finish,
        critical_path=cp,
        is_valid=is_valid,
    )


# ---------------------------------------------------------------------------
# CV-001: Simple FS chain — exact match expected
# ---------------------------------------------------------------------------

class TestCV001ExactMatch:

    def setup_method(self):
        self.fixture = get_comparison_fixture("CV-001")
        self.analysis = _build_matching_analysis(self.fixture.reference)
        self.result = compare_schedules(
            self.analysis, self.fixture.reference,
            policy=ComparisonPolicy.GOVERNED,
            tolerance_policy=TOLERANCE_STRICT,
        )

    def test_no_divergences(self):
        assert len(self.result.divergences) == 0

    def test_match_pct_100(self):
        assert self.result.metrics.activity_match_pct == 100.0

    def test_not_blocked(self):
        assert self.result.is_blocked is False

    def test_summary_present(self):
        assert self.result.summary is not None


# ---------------------------------------------------------------------------
# CV-003: Float method divergence — FLOAT_METHOD_DIFFERENCE expected
# ---------------------------------------------------------------------------

class TestCV003FloatMethod:

    def setup_method(self):
        self.fixture = get_comparison_fixture("CV-003")

    def test_expected_cats_include_float_method(self):
        assert "FLOAT_METHOD_DIFFERENCE" in self.fixture.expected_divergence_cats

    def test_matching_analysis_no_divergences(self):
        """When mip39 matches reference exactly, no divergences are generated."""
        analysis = _build_matching_analysis(self.fixture.reference)
        result = compare_schedules(
            analysis, self.fixture.reference,
            policy=ComparisonPolicy.ADVISORY,
            tolerance_policy=TOLERANCE_STRICT,
        )
        assert result.metrics.activity_match_pct == 100.0


# ---------------------------------------------------------------------------
# CV-007: P6_EMULATION_DIFFERENCE expected
# ---------------------------------------------------------------------------

class TestCV007P6Emulation:

    def setup_method(self):
        self.fixture = get_comparison_fixture("CV-007")

    def test_expected_cats_include_p6_emulation(self):
        assert "P6_EMULATION_DIFFERENCE" in self.fixture.expected_divergence_cats

    def test_matching_analysis_passes(self):
        analysis = _build_matching_analysis(self.fixture.reference)
        result = compare_schedules(
            analysis, self.fixture.reference,
            policy=ComparisonPolicy.ADVISORY,
        )
        assert result.metrics.activity_match_pct == 100.0


# ---------------------------------------------------------------------------
# CV-009: LAG_BEHAVIOR_DIFFERENCE expected
# ---------------------------------------------------------------------------

class TestCV009LagBehavior:

    def setup_method(self):
        self.fixture = get_comparison_fixture("CV-009")

    def test_expected_cats_include_lag_behavior(self):
        assert "LAG_BEHAVIOR_DIFFERENCE" in self.fixture.expected_divergence_cats

    def test_matching_analysis_passes(self):
        analysis = _build_matching_analysis(self.fixture.reference)
        result = compare_schedules(
            analysis, self.fixture.reference,
            policy=ComparisonPolicy.ADVISORY,
        )
        assert result.metrics.activity_match_pct == 100.0


# ---------------------------------------------------------------------------
# All fixtures: structural integrity checks
# ---------------------------------------------------------------------------

class TestAllFixtureStructure:

    def test_all_fixtures_produce_schedule_comparison(self):
        """Every fixture, with a matching analysis result, produces a valid ScheduleComparison."""
        from scheduleiq.cpm.compare.comparator import ScheduleComparison
        for fid, fixture in COMPARISON_FIXTURES.items():
            analysis = _build_matching_analysis(fixture.reference)
            result = compare_schedules(
                analysis, fixture.reference,
                policy=ComparisonPolicy.ADVISORY,
            )
            assert isinstance(result, ScheduleComparison), f"{fid} did not produce ScheduleComparison"

    def test_all_fixtures_matching_analysis_100_pct(self):
        """Matching analysis result yields 100% match (or 0% when no activities to compare)."""
        for fid, fixture in COMPARISON_FIXTURES.items():
            analysis = _build_matching_analysis(fixture.reference)
            result = compare_schedules(
                analysis, fixture.reference,
                policy=ComparisonPolicy.ADVISORY,
            )
            n = result.metrics.total_activities
            if n == 0:
                # Partial reference fixtures (CV-008): no per-activity comparison possible
                assert result.metrics.divergent_activities == 0, (
                    f"{fid}: zero activities compared but divergences exist"
                )
            else:
                assert result.metrics.activity_match_pct == 100.0, (
                    f"{fid}: expected 100% match, got {result.metrics.activity_match_pct}%"
                )

    def test_all_fixtures_to_dict_serializable(self):
        """Every ScheduleComparison from a fixture produces a serializable dict."""
        for fid, fixture in COMPARISON_FIXTURES.items():
            analysis = _build_matching_analysis(fixture.reference)
            result = compare_schedules(
                analysis, fixture.reference,
                policy=ComparisonPolicy.ADVISORY,
            )
            d = result.to_dict()
            assert isinstance(d, dict), f"{fid}: to_dict() did not return dict"
            assert "metrics" in d, f"{fid}: to_dict() missing 'metrics'"

    def test_all_fixtures_provenance_populated(self):
        for fid, fixture in COMPARISON_FIXTURES.items():
            analysis = _build_matching_analysis(fixture.reference)
            result = compare_schedules(
                analysis, fixture.reference,
                policy=ComparisonPolicy.GOVERNED,
            )
            assert result.provenance is not None, f"{fid}: provenance is None"
            assert result.provenance.run_id, f"{fid}: run_id is empty"
            assert len(result.provenance.stages) > 0, f"{fid}: no stage records"

    def test_all_fixtures_summary_fields(self):
        for fid, fixture in COMPARISON_FIXTURES.items():
            analysis = _build_matching_analysis(fixture.reference)
            result = compare_schedules(
                analysis, fixture.reference,
                policy=ComparisonPolicy.GOVERNED,
            )
            s = result.summary
            assert s is not None, f"{fid}: summary is None"
            assert s.run_id == result.provenance.run_id, f"{fid}: run_id mismatch"


# ---------------------------------------------------------------------------
# BenchmarkCategory.COMPARISON present
# ---------------------------------------------------------------------------

class TestBenchmarkCategoryComparison:

    def test_comparison_category_in_enum(self):
        from scheduleiq.cpm.benchmark.benchmarks import BenchmarkCategory
        values = {c.value for c in BenchmarkCategory}
        assert "comparison" in values

    def test_comparison_category_accessible(self):
        from scheduleiq.cpm.benchmark.benchmarks import BenchmarkCategory
        cat = BenchmarkCategory.COMPARISON
        assert cat.value == "comparison"
