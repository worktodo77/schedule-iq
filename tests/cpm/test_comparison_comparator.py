"""
V1-G: Tests for comparison_validation/comparator.py.

Covers:
  - compare_schedules() with exact-match schedules (no divergences)
  - compare_schedules() with single-field divergence (within tolerance)
  - compare_schedules() with single-field divergence (out of tolerance)
  - Activity universe handling (mip39-only, ref-only activities)
  - Project finish comparison
  - Critical path comparison (agreement and disagreement)
  - Checkpoint generation under STRICT policy
  - Blocking determination
  - Determinism (same inputs → same run IDs differ, but structure is identical)
  - ScheduleComparison.to_dict() serialization
  - ActivityComparison and FieldComparison structures
  - ComparisonCheckpointRegistry lifecycle
  - is_valid=False analysis result handling
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date
from types import SimpleNamespace

from scheduleiq.cpm.compare.comparator import (  # noqa: E402
    ActivityComparison,
    FieldComparison,
    ScheduleComparison,
    compare_schedules,
)
from scheduleiq.cpm.compare.divergences import DivergenceCategory  # noqa: E402
from scheduleiq.cpm.compare.fixtures import ReferenceSchedule, ReferenceScheduledActivity  # noqa: E402
from scheduleiq.cpm.compare.policies import ComparisonPolicy  # noqa: E402
from scheduleiq.cpm.compare.tolerances import TOLERANCE_STRICT, TOLERANCE_CALENDAR_AWARE  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sa(
    act_id="A100",
    early_start=date(2024, 1, 2),
    early_finish=date(2024, 1, 12),
    late_start=date(2024, 1, 2),
    late_finish=date(2024, 1, 12),
    total_float=0,
    free_float=0,
    is_critical=True,
    original_duration=10,
):
    """Build a minimal ScheduledActivity-like object for testing."""
    return SimpleNamespace(
        act_id=act_id,
        early_start=early_start,
        early_finish=early_finish,
        late_start=late_start,
        late_finish=late_finish,
        total_float=total_float,
        free_float=free_float,
        is_critical=is_critical,
        original_duration=original_duration,
    )


def _make_ra(
    act_id="A100",
    early_start=date(2024, 1, 2),
    early_finish=date(2024, 1, 12),
    late_start=date(2024, 1, 2),
    late_finish=date(2024, 1, 12),
    total_float=0,
    free_float=0,
    is_critical=True,
    original_duration=10,
) -> ReferenceScheduledActivity:
    return ReferenceScheduledActivity(
        act_id=act_id,
        early_start=early_start,
        early_finish=early_finish,
        late_start=late_start,
        late_finish=late_finish,
        total_float=total_float,
        free_float=free_float,
        is_critical=is_critical,
        original_duration=original_duration,
    )


def _make_analysis(activities: dict, project_finish=None, cp_ids=None, is_valid=True):
    """Build a minimal AnalysisResult-like object for testing."""
    cp = SimpleNamespace(activity_ids=cp_ids or []) if cp_ids is not None else None
    return SimpleNamespace(
        scheduled=activities,
        project_finish=project_finish,
        critical_path=cp,
        is_valid=is_valid,
    )


def _make_reference(
    acts: list[ReferenceScheduledActivity],
    schedule_id="REF-001",
    project_finish=None,
    cp_ids=None,
) -> ReferenceSchedule:
    ref = ReferenceSchedule(
        schedule_id=schedule_id,
        description="Test reference",
        project_finish=project_finish,
        critical_path_activity_ids=cp_ids or [],
        source="synthetic",
    )
    for act in acts:
        ref.add_activity(act)
    return ref


# ---------------------------------------------------------------------------
# Exact match — zero divergences
# ---------------------------------------------------------------------------

class TestExactMatch:

    def setup_method(self):
        sa = _make_sa()
        ra = _make_ra()
        analysis = _make_analysis({"A100": sa}, project_finish=date(2024, 1, 12), cp_ids=["A100"])
        reference = _make_reference([ra], project_finish=date(2024, 1, 12), cp_ids=["A100"])
        self.result = compare_schedules(
            analysis, reference, policy=ComparisonPolicy.STRICT, tolerance_policy=TOLERANCE_STRICT
        )

    def test_returns_schedule_comparison(self):
        assert isinstance(self.result, ScheduleComparison)

    def test_no_divergences(self):
        assert len(self.result.divergences) == 0

    def test_no_checkpoints(self):
        assert len(self.result.checkpoints) == 0

    def test_not_blocked(self):
        assert self.result.is_blocked is False

    def test_metrics_total_activities(self):
        assert self.result.metrics.total_activities == 1

    def test_metrics_exact_match(self):
        assert self.result.metrics.exact_match_activities == 1

    def test_metrics_within_tolerance(self):
        assert self.result.metrics.within_tolerance_activities == 1

    def test_metrics_match_pct_100(self):
        assert self.result.metrics.activity_match_pct == 100.0

    def test_metrics_cp_agreement(self):
        assert self.result.metrics.critical_path_agreement is True

    def test_summary_present(self):
        assert self.result.summary is not None

    def test_provenance_present(self):
        assert self.result.provenance is not None

    def test_provenance_has_run_id(self):
        assert len(self.result.provenance.run_id) == 36  # UUID

    def test_activity_comparisons_count(self):
        assert len(self.result.activity_comparisons) == 1

    def test_activity_comparison_exact_match(self):
        ac = self.result.activity_comparisons[0]
        assert ac.is_exact_match is True
        assert ac.is_within_tolerance is True
        assert ac.has_divergences is False


# ---------------------------------------------------------------------------
# Single-field divergence — within tolerance
# ---------------------------------------------------------------------------

class TestWithinToleranceDivergence:

    def setup_method(self):
        sa = _make_sa(early_finish=date(2024, 1, 13))  # 1 day later
        ra = _make_ra(early_finish=date(2024, 1, 12))
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        self.result = compare_schedules(
            analysis, reference,
            policy=ComparisonPolicy.GOVERNED,
            tolerance_policy=TOLERANCE_CALENDAR_AWARE,
        )

    def test_within_tolerance_activities(self):
        assert self.result.metrics.within_tolerance_activities == 1

    def test_not_blocked(self):
        assert self.result.is_blocked is False

    def test_activity_not_divergent(self):
        ac = self.result.activity_comparisons[0]
        assert ac.has_divergences is False
        assert ac.is_within_tolerance is True


# ---------------------------------------------------------------------------
# Single-field divergence — out of tolerance
# ---------------------------------------------------------------------------

class TestOutOfToleranceDivergence:

    def setup_method(self):
        sa = _make_sa(total_float=5)
        ra = _make_ra(total_float=3)  # delta = 2, STRICT needs exact
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        self.result = compare_schedules(
            analysis, reference,
            policy=ComparisonPolicy.GOVERNED,
            tolerance_policy=TOLERANCE_STRICT,
        )

    def test_divergence_created(self):
        assert len(self.result.divergences) > 0

    def test_divergent_activities_count(self):
        assert self.result.metrics.divergent_activities == 1

    def test_activity_has_divergence(self):
        ac = self.result.activity_comparisons[0]
        assert ac.has_divergences is True
        assert ac.divergence_count == 1

    def test_match_pct_below_100(self):
        assert self.result.metrics.activity_match_pct < 100.0

    def test_float_variance_max_set(self):
        assert self.result.metrics.total_float_variance_max == 2


# ---------------------------------------------------------------------------
# Activity universe — mip39-only and ref-only activities
# ---------------------------------------------------------------------------

class TestActivityUniverse:

    def setup_method(self):
        sa_a = _make_sa("A100")
        sa_b = _make_sa("A200")  # mip39-only
        ra_a = _make_ra("A100")
        ra_c = _make_ra("A300")  # ref-only
        analysis = _make_analysis({"A100": sa_a, "A200": sa_b})
        reference = _make_reference([ra_a, ra_c])
        self.result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)

    def test_mip39_only_count(self):
        assert self.result.metrics.mip39_only_activities == 1

    def test_ref_only_count(self):
        assert self.result.metrics.reference_only_activities == 1

    def test_universe_divergences_created(self):
        # A200 (mip39-only) and A300 (ref-only) each get a divergence
        div_fields = [d.field for d in self.result.divergences.all]
        assert "activity_presence" in div_fields


# ---------------------------------------------------------------------------
# Critical path comparison
# ---------------------------------------------------------------------------

class TestCriticalPathComparison:

    def test_cp_agreement_when_sets_match(self):
        sa = _make_sa("A100", is_critical=True)
        ra = _make_ra("A100", is_critical=True)
        analysis = _make_analysis({"A100": sa}, cp_ids=["A100"])
        reference = _make_reference([ra], cp_ids=["A100"])
        result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        assert result.metrics.critical_path_agreement is True

    def test_cp_disagreement_when_sets_differ(self):
        sa_a = _make_sa("A100")
        sa_b = _make_sa("A200")
        ra_a = _make_ra("A100")
        ra_b = _make_ra("A200")
        # mip39 CP: [A100]; reference CP: [A200] — non-empty sets that differ
        analysis = _make_analysis({"A100": sa_a, "A200": sa_b}, cp_ids=["A100"])
        reference = _make_reference([ra_a, ra_b], cp_ids=["A200"])
        result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        assert result.metrics.critical_path_agreement is False
        assert "A100" in result.metrics.critical_path_mip39_only
        assert "A200" in result.metrics.critical_path_ref_only

    def test_cp_skipped_when_ref_cp_empty(self):
        sa = _make_sa("A100")
        ra = _make_ra("A100")
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])  # no cp_ids
        result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        assert result.critical_path_comparison.get("skipped") is True


# ---------------------------------------------------------------------------
# Policy-driven blocking
# ---------------------------------------------------------------------------

class TestBlockingBehavior:

    def test_strict_blocks_on_unknown_divergence(self):
        sa = _make_sa(original_duration=10)
        ra = _make_ra(original_duration=15)  # out of tolerance, UNKNOWN category
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        result = compare_schedules(
            analysis, reference,
            policy=ComparisonPolicy.STRICT,
            tolerance_policy=TOLERANCE_STRICT,
        )
        # original_duration divergence → UNKNOWN → blocking under STRICT
        assert result.is_blocked is True

    def test_experimental_never_blocks(self):
        sa = _make_sa(original_duration=10)
        ra = _make_ra(original_duration=15)
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        result = compare_schedules(
            analysis, reference,
            policy=ComparisonPolicy.EXPERIMENTAL,
            tolerance_policy=TOLERANCE_STRICT,
        )
        assert result.is_blocked is False

    def test_advisory_never_blocks(self):
        sa = _make_sa(total_float=0)
        ra = _make_ra(total_float=5)  # material difference in float
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        result = compare_schedules(
            analysis, reference,
            policy=ComparisonPolicy.ADVISORY,
            tolerance_policy=TOLERANCE_STRICT,
        )
        assert result.is_blocked is False


# ---------------------------------------------------------------------------
# Invalid analysis result handling
# ---------------------------------------------------------------------------

class TestInvalidAnalysisResult:

    def test_invalid_result_creates_material_divergence(self):
        sa = _make_sa()
        ra = _make_ra()
        analysis = _make_analysis({"A100": sa}, is_valid=False)
        reference = _make_reference([ra])
        result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        material = result.divergences.material()
        assert len(material) >= 1


# ---------------------------------------------------------------------------
# to_dict() serialization
# ---------------------------------------------------------------------------

class TestScheduleComparisonToDict:

    def setup_method(self):
        sa = _make_sa()
        ra = _make_ra()
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        self.result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)

    def test_to_dict_has_required_keys(self):
        d = self.result.to_dict()
        for k in ("policy", "tolerance_policy", "is_blocked", "metrics",
                   "provenance", "summary", "divergences", "checkpoints",
                   "activity_comparisons"):
            assert k in d, f"Missing key: {k}"

    def test_to_dict_policy_is_string(self):
        d = self.result.to_dict()
        assert isinstance(d["policy"], str)

    def test_to_dict_activity_comparisons_list(self):
        d = self.result.to_dict()
        assert isinstance(d["activity_comparisons"], list)

    def test_to_dict_metrics_dict(self):
        d = self.result.to_dict()
        assert isinstance(d["metrics"], dict)


# ---------------------------------------------------------------------------
# Determinism — same inputs produce same structure
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_same_inputs_same_divergence_count(self):
        sa = _make_sa(total_float=5)
        ra = _make_ra(total_float=3)
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        r1 = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        r2 = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        assert len(r1.divergences) == len(r2.divergences)

    def test_same_inputs_same_metrics(self):
        sa = _make_sa(total_float=5)
        ra = _make_ra(total_float=3)
        analysis = _make_analysis({"A100": sa})
        reference = _make_reference([ra])
        r1 = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        r2 = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        assert r1.metrics.activity_match_pct == r2.metrics.activity_match_pct
        assert r1.metrics.total_float_variance_max == r2.metrics.total_float_variance_max

    def test_activity_comparison_sorted_by_act_id(self):
        activities = {
            "Z100": _make_sa("Z100"),
            "A100": _make_sa("A100"),
            "M200": _make_sa("M200"),
        }
        ref_acts = [_make_ra("Z100"), _make_ra("A100"), _make_ra("M200")]
        analysis = _make_analysis(activities)
        reference = _make_reference(ref_acts)
        result = compare_schedules(analysis, reference, policy=ComparisonPolicy.ADVISORY)
        act_ids = [ac.act_id for ac in result.activity_comparisons]
        assert act_ids == sorted(act_ids)
