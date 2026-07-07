"""
V1-G: Tests for comparison_validation/fixtures.py.

Covers:
  - ReferenceScheduledActivity model and to_dict/from_dict round-trip
  - ReferenceSchedule model, add_activity, to_dict/from_dict round-trip
  - ComparisonFixture model and to_dict
  - All 10 synthetic fixtures CV-001 through CV-010 present and structurally valid
  - get_comparison_fixture() lookup
  - COMPARISON_FIXTURES dict completeness
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date

from scheduleiq.cpm.compare.fixtures import (  # noqa: E402
    COMPARISON_FIXTURES,
    ComparisonFixture,
    ReferenceSchedule,
    ReferenceScheduledActivity,
    get_comparison_fixture,
)
from scheduleiq.cpm.compare.divergences import DivergenceCategory  # noqa: E402


# ---------------------------------------------------------------------------
# ReferenceScheduledActivity
# ---------------------------------------------------------------------------

class TestReferenceScheduledActivity:

    def test_minimal_construction(self):
        ra = ReferenceScheduledActivity(act_id="A100")
        assert ra.act_id == "A100"
        assert ra.early_start is None
        assert ra.total_float is None

    def test_full_construction(self):
        ra = ReferenceScheduledActivity(
            act_id="A100",
            early_start=date(2024, 1, 2),
            early_finish=date(2024, 1, 12),
            late_start=date(2024, 1, 2),
            late_finish=date(2024, 1, 12),
            total_float=0,
            free_float=0,
            is_critical=True,
            original_duration=10,
        )
        assert ra.early_finish == date(2024, 1, 12)
        assert ra.is_critical is True

    def test_to_dict_keys(self):
        ra = ReferenceScheduledActivity(act_id="A100", total_float=5)
        d = ra.to_dict()
        for k in ("act_id", "early_start", "early_finish", "late_start", "late_finish",
                   "total_float", "free_float", "is_critical", "original_duration", "notes"):
            assert k in d

    def test_to_dict_date_serialization(self):
        ra = ReferenceScheduledActivity(
            act_id="A100",
            early_start=date(2024, 3, 15),
        )
        d = ra.to_dict()
        assert d["early_start"] == "2024-03-15"

    def test_from_dict_round_trip(self):
        ra = ReferenceScheduledActivity(
            act_id="A100",
            early_start=date(2024, 1, 2),
            early_finish=date(2024, 1, 12),
            total_float=3,
            is_critical=False,
        )
        ra2 = ReferenceScheduledActivity.from_dict(ra.to_dict())
        assert ra2.act_id == ra.act_id
        assert ra2.early_start == ra.early_start
        assert ra2.total_float == ra.total_float
        assert ra2.is_critical == ra.is_critical


# ---------------------------------------------------------------------------
# ReferenceSchedule
# ---------------------------------------------------------------------------

class TestReferenceSchedule:

    def _make_ref(self) -> ReferenceSchedule:
        ref = ReferenceSchedule(
            schedule_id="REF-001",
            description="Test reference",
            project_finish=date(2024, 6, 30),
            source="synthetic",
        )
        ref.add_activity(ReferenceScheduledActivity(
            act_id="A100",
            early_finish=date(2024, 6, 30),
            total_float=0,
            is_critical=True,
        ))
        return ref

    def test_add_activity(self):
        ref = self._make_ref()
        assert "A100" in ref.activities

    def test_to_dict_keys(self):
        d = self._make_ref().to_dict()
        for k in ("schedule_id", "description", "activities", "project_finish",
                   "source", "tool", "lag_strategy_assumed"):
            assert k in d

    def test_to_dict_activities_nested(self):
        d = self._make_ref().to_dict()
        assert "A100" in d["activities"]

    def test_from_dict_round_trip(self):
        ref = self._make_ref()
        ref.critical_path_activity_ids = ["A100"]
        ref2 = ReferenceSchedule.from_dict(ref.to_dict())
        assert ref2.schedule_id == ref.schedule_id
        assert ref2.project_finish == ref.project_finish
        assert "A100" in ref2.activities
        assert ref2.critical_path_activity_ids == ["A100"]

    def test_source_default(self):
        ref = ReferenceSchedule(schedule_id="X", description="y")
        assert ref.source == "synthetic"


# ---------------------------------------------------------------------------
# ComparisonFixture model
# ---------------------------------------------------------------------------

class TestComparisonFixture:

    def test_to_dict_keys(self):
        ref = ReferenceSchedule(schedule_id="CV-001", description="test")
        f = ComparisonFixture(
            fixture_id="CV-001",
            description="Test fixture",
            reference=ref,
            expected_divergence_cats=["FLOAT_METHOD_DIFFERENCE"],
            expected_match_pct_min=80.0,
        )
        d = f.to_dict()
        for k in ("fixture_id", "description", "reference", "expected_divergence_cats",
                   "expected_match_pct_min", "expected_cp_agreement"):
            assert k in d


# ---------------------------------------------------------------------------
# Synthetic fixtures CV-001 through CV-010
# ---------------------------------------------------------------------------

class TestSyntheticFixtures:

    EXPECTED_IDS = [f"CV-{i:03d}" for i in range(1, 11)]

    def test_all_fixtures_present(self):
        for fid in self.EXPECTED_IDS:
            assert fid in COMPARISON_FIXTURES, f"Missing fixture {fid}"

    def test_get_comparison_fixture_returns_correct(self):
        for fid in self.EXPECTED_IDS:
            f = get_comparison_fixture(fid)
            assert f.fixture_id == fid

    def test_get_comparison_fixture_raises_for_unknown(self):
        with pytest.raises(KeyError):
            get_comparison_fixture("CV-999")

    def test_all_fixtures_have_activities(self):
        # CV-008 is a partial-reference fixture (project-finish only, no per-activity data)
        PARTIAL_FIXTURES = {"CV-008"}
        for fid, f in COMPARISON_FIXTURES.items():
            if fid in PARTIAL_FIXTURES:
                continue  # Partial reference — no activities by design
            assert len(f.reference.activities) > 0, f"{fid} has no activities"

    def test_all_fixtures_have_description(self):
        for fid, f in COMPARISON_FIXTURES.items():
            assert f.description, f"{fid} has no description"

    def test_all_fixtures_source_is_synthetic(self):
        for fid, f in COMPARISON_FIXTURES.items():
            assert f.source in ("synthetic", "analyst_reviewed"), f"{fid} bad source"

    def test_cv001_no_divergences_expected(self):
        f = get_comparison_fixture("CV-001")
        assert f.expected_match_pct_min == 100.0

    def test_cv003_expects_float_method_difference(self):
        f = get_comparison_fixture("CV-003")
        assert "FLOAT_METHOD_DIFFERENCE" in f.expected_divergence_cats

    def test_cv007_expects_p6_emulation_difference(self):
        f = get_comparison_fixture("CV-007")
        assert "P6_EMULATION_DIFFERENCE" in f.expected_divergence_cats

    def test_cv009_expects_lag_behavior_difference(self):
        f = get_comparison_fixture("CV-009")
        assert "LAG_BEHAVIOR_DIFFERENCE" in f.expected_divergence_cats

    def test_all_expected_cats_are_valid_divergence_categories(self):
        valid_cats = {c.value for c in DivergenceCategory}
        for fid, f in COMPARISON_FIXTURES.items():
            for cat in f.expected_divergence_cats:
                assert cat in valid_cats, f"{fid} has invalid cat {cat!r}"

    def test_all_fixtures_have_valid_match_pct(self):
        for fid, f in COMPARISON_FIXTURES.items():
            assert 0.0 <= f.expected_match_pct_min <= 100.0, f"{fid} invalid match_pct"

    def test_all_fixtures_have_at_least_one_activity_with_act_id(self):
        for fid, f in COMPARISON_FIXTURES.items():
            for act_id, ra in f.reference.activities.items():
                assert ra.act_id == act_id, f"{fid}: act_id mismatch {ra.act_id!r} vs {act_id!r}"
