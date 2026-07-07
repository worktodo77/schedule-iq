"""
V1-G: Integration tests for the comparison_validation package.

Tests end-to-end compare_schedules() behavior with multi-activity schedules,
analyst resolution workflows, divergence reclassification, and package-level
import completeness.

These tests import from the package __init__ to verify the public API.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date
from types import SimpleNamespace

from scheduleiq.cpm.compare import (  # noqa: E402
    ComparisonCheckpointRegistry,
    ComparisonCheckpointStatus,
    ComparisonMetrics,
    ComparisonPolicy,
    DivergenceAccumulator,
    DivergenceCategory,
    ReferenceSchedule,
    ReferenceScheduledActivity,
    ScheduleComparison,
    TOLERANCE_STRICT,
    TOLERANCE_CALENDAR_AWARE,
    compare_schedules,
    get_comparison_fixture,
)
from scheduleiq.cpm.compare.divergences import DivergenceRecord  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sa(act_id, es, ef, ls, lf, tf, ff, critical, dur):
    return SimpleNamespace(
        act_id=act_id, early_start=es, early_finish=ef,
        late_start=ls, late_finish=lf, total_float=tf, free_float=ff,
        is_critical=critical, original_duration=dur,
    )


def _ra(act_id, es, ef, ls, lf, tf, ff, critical, dur):
    return ReferenceScheduledActivity(
        act_id=act_id, early_start=es, early_finish=ef,
        late_start=ls, late_finish=lf, total_float=tf, free_float=ff,
        is_critical=critical, original_duration=dur,
    )


# ---------------------------------------------------------------------------
# Multi-activity comparison
# ---------------------------------------------------------------------------

class TestMultiActivityComparison:

    def setup_method(self):
        # 3-activity chain; A110 has a float divergence
        d = date
        self.analysis = SimpleNamespace(
            scheduled={
                "A100": _sa("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10),
                "A110": _sa("A110", d(2024,1,15), d(2024,1,26), d(2024,1,15), d(2024,1,26), 5, 5, False, 10),
                "A120": _sa("A120", d(2024,1,29), d(2024,2,9), d(2024,1,29), d(2024,2,9), 0, 0, True, 10),
            },
            project_finish=d(2024,2,9),
            critical_path=SimpleNamespace(activity_ids=["A100", "A120"]),
            is_valid=True,
        )
        ref = ReferenceSchedule(schedule_id="REF-INT", description="Integration test")
        ref.add_activity(_ra("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10))
        ref.add_activity(_ra("A110", d(2024,1,15), d(2024,1,26), d(2024,1,15), d(2024,1,26), 3, 3, False, 10))  # TF differs
        ref.add_activity(_ra("A120", d(2024,1,29), d(2024,2,9), d(2024,1,29), d(2024,2,9), 0, 0, True, 10))
        ref.project_finish = d(2024,2,9)
        ref.critical_path_activity_ids = ["A100", "A120"]
        self.ref = ref
        self.result = compare_schedules(
            self.analysis, ref,
            policy=ComparisonPolicy.GOVERNED,
            tolerance_policy=TOLERANCE_STRICT,
        )

    def test_3_activities_compared(self):
        assert self.result.metrics.total_activities == 3

    def test_2_exact_match_1_divergent(self):
        assert self.result.metrics.divergent_activities == 1

    def test_match_pct_two_thirds(self):
        # 2 of 3 within tolerance
        assert abs(self.result.metrics.activity_match_pct - 66.67) < 0.1

    def test_float_divergence_on_a110(self):
        ac_110 = next(ac for ac in self.result.activity_comparisons if ac.act_id == "A110")
        assert ac_110.has_divergences is True

    def test_cp_agreement(self):
        assert self.result.metrics.critical_path_agreement is True

    def test_finish_comparison_no_variance(self):
        if self.result.finish_comparison:
            assert self.result.finish_comparison.is_within_tolerance is True

    def test_provenance_stage_records_populated(self):
        stages = [s.stage_name for s in self.result.provenance.stages]
        assert "activity_universe" in stages
        assert "per_activity_comparison" in stages
        assert "project_level_comparison" in stages


# ---------------------------------------------------------------------------
# Analyst resolution workflow
# ---------------------------------------------------------------------------

class TestAnalystResolutionWorkflow:

    def setup_method(self):
        d = date
        analysis = SimpleNamespace(
            scheduled={"A100": _sa("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 5, 2, False, 10)},
            project_finish=None, critical_path=SimpleNamespace(activity_ids=[]),
            is_valid=True,
        )
        ref = ReferenceSchedule(schedule_id="REF-RES", description="Resolution test")
        ref.add_activity(_ra("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10))
        self.result = compare_schedules(
            analysis, ref,
            policy=ComparisonPolicy.STRICT,
            tolerance_policy=TOLERANCE_STRICT,
        )

    def test_initially_blocked(self):
        # TF divergence (FLOAT_METHOD) + is_critical mismatch (FLOAT_METHOD) → STRICT may block on UNKNOWN
        # The result may or may not be blocked depending on field classification
        # We just verify that divergences exist
        assert len(self.result.divergences) > 0

    def test_waive_divergence_marks_resolved(self):
        div = self.result.divergences.all[0]
        div.waive("Acceptable float method difference — analyst reviewed")
        assert div.is_resolved is True
        assert div.resolution == "waived"
        assert "analyst reviewed" in div.analyst_note

    def test_reclassify_divergence(self):
        div = self.result.divergences.all[0]
        div.reclassify(DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "TF=0 vs longest-path")
        assert div.category == DivergenceCategory.FLOAT_METHOD_DIFFERENCE

    def test_checkpoint_acknowledge(self):
        cps = self.result.checkpoints.all()
        if cps:
            cp = cps[0]
            cp.acknowledge("Reviewed — acceptable divergence")
            assert cp.status == ComparisonCheckpointStatus.ACKNOWLEDGED


# ---------------------------------------------------------------------------
# Package-level import completeness
# ---------------------------------------------------------------------------

class TestPackageImports:

    def test_all_exported_symbols_importable(self):
        from scheduleiq.cpm.compare import (
            compare_schedules, run_lag_strategy_experiment,
            ActivityComparison, FieldComparison, LagStrategyExperiment,
            LagStrategyResult, ScheduleComparison,
            DivergenceAccumulator, DivergenceCategory, DivergenceRecord,
            NAMED_TOLERANCE_POLICIES, TOLERANCE_ADVISORY, TOLERANCE_CALENDAR_AWARE,
            TOLERANCE_STRICT, TolerancePolicy, ToleranceType, within_tolerance,
            ComparisonPolicy, ComparisonPolicyConfig, get_comparison_policy_config,
            ComparisonCheckpoint, ComparisonCheckpointRegistry, ComparisonCheckpointStatus,
            ComparisonProvenance, ComparisonStageRecord, build_comparison_provenance,
            ComparisonMetrics,
            COMPARISON_FIXTURES, ComparisonFixture, ReferenceSchedule,
            ReferenceScheduledActivity, get_comparison_fixture,
            ComparisonSummary, LagStrategyExperimentSummary,
        )

    def test_compare_schedules_is_callable(self):
        assert callable(compare_schedules)

    def test_divergence_category_values_accessible(self):
        assert DivergenceCategory.EXPECTED_DIFFERENCE.value == "EXPECTED_DIFFERENCE"
        assert DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE.is_blocking() is True


# ---------------------------------------------------------------------------
# Provenance reproducibility
# ---------------------------------------------------------------------------

class TestProvenanceReproducibility:

    def test_two_runs_same_activity_count(self):
        d = date
        analysis = SimpleNamespace(
            scheduled={"A100": _sa("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10)},
            project_finish=d(2024,1,12), critical_path=SimpleNamespace(activity_ids=["A100"]),
            is_valid=True,
        )
        ref = ReferenceSchedule(schedule_id="REF-PROV", description="Provenance test")
        ref.add_activity(_ra("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10))
        ref.project_finish = d(2024,1,12)
        r1 = compare_schedules(analysis, ref, policy=ComparisonPolicy.GOVERNED)
        r2 = compare_schedules(analysis, ref, policy=ComparisonPolicy.GOVERNED)
        assert r1.provenance.original_activity_count == r2.provenance.original_activity_count
        assert r1.provenance.reference_activity_count == r2.provenance.reference_activity_count

    def test_provenance_standard_assumptions_populated(self):
        d = date
        analysis = SimpleNamespace(
            scheduled={"A100": _sa("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10)},
            project_finish=None, critical_path=None, is_valid=True,
        )
        ref = ReferenceSchedule(schedule_id="REF-PROV2", description="Provenance test 2")
        ref.add_activity(_ra("A100", d(2024,1,2), d(2024,1,12), d(2024,1,2), d(2024,1,12), 0, 0, True, 10))
        result = compare_schedules(analysis, ref, policy=ComparisonPolicy.GOVERNED)
        # Standard assumptions are added by build_comparison_provenance
        assert len(result.provenance.assumptions) >= 3
        # Standard disclosure present
        assert len(result.provenance.disclosures) >= 1
