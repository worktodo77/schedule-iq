"""
Tests for INFRA-018: Phase 7 Controlled Synthetic Benchmark Fixtures.

Covers test categories:
  16. Benchmark provenance (fixture-level)
  17. Fixture completeness and taxonomy
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    BenchmarkCategory,
    BenchmarkDefinition,
    BenchmarkMetadata,
    BenchmarkSuite,
    ValidationSeverity,
    BENCHMARK_FRAMEWORK_VERSION,
)
from scheduleiq.cpm.benchmark.fixtures import (  # noqa: E402
    PHASE7_SUITE,
    build_phase7_suite,
    BM_001, BM_002, BM_003, BM_004, BM_005,
    BM_006, BM_007, BM_008, BM_009, BM_010,
    BM_011, BM_012,
)


_ALL_BMS = [BM_001, BM_002, BM_003, BM_004, BM_005,
            BM_006, BM_007, BM_008, BM_009, BM_010,
            BM_011, BM_012]


# ---------------------------------------------------------------------------
# Category 17: Fixture completeness and taxonomy
# ---------------------------------------------------------------------------

class TestFixtureCompleteness:
    def test_suite_has_exactly_12_benchmarks(self):
        assert len(PHASE7_SUITE.benchmarks) == 12

    def test_suite_ids_are_sequential(self):
        ids = PHASE7_SUITE.benchmark_ids()
        for i, bm_id in enumerate(ids, 1):
            assert bm_id == f"BM-{i:03d}", f"Expected BM-{i:03d}, got {bm_id}"

    def test_build_phase7_suite_returns_suite(self):
        suite = build_phase7_suite()
        assert isinstance(suite, BenchmarkSuite)

    def test_build_phase7_suite_same_ids_as_phase7_suite(self):
        suite = build_phase7_suite()
        assert suite.benchmark_ids() == PHASE7_SUITE.benchmark_ids()

    def test_all_bm_objects_are_benchmark_definitions(self):
        for bm in _ALL_BMS:
            assert isinstance(bm, BenchmarkDefinition)

    def test_suite_get_each_by_id(self):
        for i in range(1, 13):
            bm_id = f"BM-{i:03d}"
            bm = PHASE7_SUITE.get(bm_id)
            assert bm is not None, f"{bm_id} not found in suite"
            assert bm.metadata.benchmark_id == bm_id


class TestFixtureCategoryTaxonomy:
    """Key BenchmarkCategory values are represented in the suite."""

    def _get_categories(self):
        return {
            PHASE7_SUITE.get(bm_id).metadata.category
            for bm_id in PHASE7_SUITE.benchmark_ids()
        }

    def test_simple_fs_category_present(self):
        assert BenchmarkCategory.SIMPLE_FS in self._get_categories()

    def test_lag_heavy_category_present(self):
        assert BenchmarkCategory.LAG_HEAVY in self._get_categories()

    def test_ss_ff_sf_category_present(self):
        assert BenchmarkCategory.SS_FF_SF in self._get_categories()

    def test_branching_category_present(self):
        assert BenchmarkCategory.BRANCHING in self._get_categories()

    def test_edge_case_category_present(self):
        assert BenchmarkCategory.EDGE_CASE in self._get_categories()

    def test_convention_divergence_category_present(self):
        assert BenchmarkCategory.CONVENTION_DIVERGENCE in self._get_categories()

    def test_invalid_network_category_present(self):
        assert BenchmarkCategory.INVALID_NETWORK in self._get_categories()

    def test_tied_longest_path_category_present(self):
        assert BenchmarkCategory.TIED_LONGEST_PATH in self._get_categories()


# ---------------------------------------------------------------------------
# Category 16: Benchmark provenance — fixture-level
# ---------------------------------------------------------------------------

class TestFixtureProvenance:
    def test_all_source_synthetic(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.source == "synthetic", (
                f"{bm_id}: source must be 'synthetic'"
            )

    def test_no_proprietary_data(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.source != "xer", f"{bm_id}: no XER source allowed"
            assert "proprietary" not in bm.metadata.description.lower()

    def test_all_have_version(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.benchmark_version, f"{bm_id}: benchmark_version empty"

    def test_all_versions_contain_phase7(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert "phase7" in bm.metadata.benchmark_version, (
                f"{bm_id}: version should contain 'phase7'"
            )

    def test_all_have_non_empty_description(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.description.strip(), f"{bm_id}: description empty"

    def test_all_have_benchmark_category(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert isinstance(bm.metadata.category, BenchmarkCategory)

    def test_all_baseline_captured_is_bool(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert isinstance(bm.expectations.baseline_captured, bool), (
                f"{bm_id}: baseline_captured must be bool"
            )

    def test_all_have_project_start(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.project_start, f"{bm_id}: project_start empty"

    def test_all_have_activities(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert len(bm.activities) > 0, f"{bm_id}: must have activities"


# ---------------------------------------------------------------------------
# Specific fixture content checks
# ---------------------------------------------------------------------------

class TestSpecificFixtures:
    def test_bm001_three_activities(self):
        assert len(BM_001.activities) == 3

    def test_bm001_two_relationships(self):
        assert len(BM_001.relationships) == 2

    def test_bm001_inclusive_day_convention(self):
        assert BM_001.convention == "inclusive_day"

    def test_bm011_p6_compatibility_convention(self):
        assert BM_011.convention == "p6_compatibility"

    def test_bm012_is_invalid_network(self):
        assert BM_012.expectations.is_valid is False

    def test_bm012_invalid_network_category(self):
        assert BM_012.metadata.category == BenchmarkCategory.INVALID_NETWORK

    def test_bm004_tied_paths_flag(self):
        assert BM_004.expectations.tied_paths is True

    def test_bm004_has_divergence_flags(self):
        assert len(BM_004.expectations.divergence_flags) > 0

    def test_bm010_has_milestone_activity(self):
        act_ids = {a["act_id"] for a in BM_010.activities}
        assert "M" in act_ids

    def test_bm010_milestone_has_zero_duration(self):
        milestone = next(a for a in BM_010.activities if a["act_id"] == "M")
        assert milestone["original_duration"] == 0

    def test_bm005_has_positive_lag(self):
        lags = [r.get("lag", 0) for r in BM_005.relationships]
        assert any(lag > 0 for lag in lags)

    def test_bm006_has_negative_lag(self):
        lags = [r.get("lag", 0) for r in BM_006.relationships]
        assert any(lag < 0 for lag in lags)

    def test_bm007_has_ss_relationship(self):
        rel_types = {r["rel_type"] for r in BM_007.relationships}
        assert "SS" in rel_types

    def test_bm008_has_ff_relationship(self):
        rel_types = {r["rel_type"] for r in BM_008.relationships}
        assert "FF" in rel_types

    def test_bm009_has_sf_relationship(self):
        rel_types = {r["rel_type"] for r in BM_009.relationships}
        assert "SF" in rel_types

    def test_all_activity_ids_unique_within_fixture(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            ids = [a["act_id"] for a in bm.activities]
            assert len(ids) == len(set(ids)), f"{bm_id}: duplicate activity IDs"
