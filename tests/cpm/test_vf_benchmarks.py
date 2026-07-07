"""
Tests for INFRA-015: Phase 7 Benchmark Definition Structures.

Covers test categories:
  1. Benchmark serialization
  16. Benchmark provenance
  18. Backward compatibility tests
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark import (  # noqa: E402
    BENCHMARK_FRAMEWORK_VERSION,
    BenchmarkCategory,
    BenchmarkDefinition,
    BenchmarkExpectations,
    BenchmarkMetadata,
    BenchmarkSuite,
    ExpectedActivityResult,
    ValidationSeverity,
)
from scheduleiq.cpm.benchmark.fixtures import (  # noqa: E402
    PHASE7_SUITE,
    BM_001, BM_002, BM_003, BM_004, BM_005,
    BM_006, BM_007, BM_008, BM_009, BM_010,
    BM_011, BM_012,
)


# ---------------------------------------------------------------------------
# ValidationSeverity
# ---------------------------------------------------------------------------

class TestValidationSeverity:
    def test_members_exist(self):
        assert ValidationSeverity.INFORMATIONAL
        assert ValidationSeverity.WARNING
        assert ValidationSeverity.ANALYTICAL
        assert ValidationSeverity.CRITICAL

    def test_is_at_least_equal(self):
        assert ValidationSeverity.ANALYTICAL.is_at_least(ValidationSeverity.ANALYTICAL)

    def test_is_at_least_higher(self):
        assert ValidationSeverity.CRITICAL.is_at_least(ValidationSeverity.INFORMATIONAL)

    def test_is_at_least_lower_false(self):
        assert not ValidationSeverity.INFORMATIONAL.is_at_least(ValidationSeverity.WARNING)

    def test_ordering_informational_lowest(self):
        for s in [ValidationSeverity.WARNING, ValidationSeverity.ANALYTICAL, ValidationSeverity.CRITICAL]:
            assert s.is_at_least(ValidationSeverity.INFORMATIONAL)

    def test_ordering_critical_highest(self):
        for s in [ValidationSeverity.INFORMATIONAL, ValidationSeverity.WARNING, ValidationSeverity.ANALYTICAL]:
            assert not s.is_at_least(ValidationSeverity.CRITICAL)


# ---------------------------------------------------------------------------
# BenchmarkMetadata serialization
# ---------------------------------------------------------------------------

class TestBenchmarkMetadataSerialization:
    def setup_method(self):
        self.meta = BenchmarkMetadata(
            benchmark_id="BM-TEST",
            benchmark_version="1.0",
            description="Test benchmark",
            category=BenchmarkCategory.SIMPLE_FS,
            source="synthetic",
            assumptions=["A1", "A2"],
            tags=["t1"],
        )

    def test_to_dict_returns_dict(self):
        d = self.meta.to_dict()
        assert isinstance(d, dict)

    def test_benchmark_id_in_dict(self):
        assert self.meta.to_dict()["benchmark_id"] == "BM-TEST"

    def test_version_in_dict(self):
        assert self.meta.to_dict()["benchmark_version"] == "1.0"

    def test_category_as_string(self):
        assert self.meta.to_dict()["category"] == "simple_fs"

    def test_source_in_dict(self):
        assert self.meta.to_dict()["source"] == "synthetic"

    def test_assumptions_list(self):
        assert self.meta.to_dict()["assumptions"] == ["A1", "A2"]

    def test_tags_list(self):
        assert self.meta.to_dict()["tags"] == ["t1"]


# ---------------------------------------------------------------------------
# ExpectedActivityResult serialization
# ---------------------------------------------------------------------------

class TestExpectedActivityResultSerialization:
    def setup_method(self):
        self.exp = ExpectedActivityResult(
            activity_id="A100",
            early_start="2026-01-05",
            early_finish="2026-01-07",
            late_start="2026-01-05",
            late_finish="2026-01-07",
            total_float=0,
            free_float=0,
            is_critical=True,
        )

    def test_to_dict_all_fields(self):
        d = self.exp.to_dict()
        assert d["activity_id"] == "A100"
        assert d["early_start"] == "2026-01-05"
        assert d["early_finish"] == "2026-01-07"
        assert d["total_float"] == 0
        assert d["is_critical"] is True

    def test_serialization_roundtrip_keys(self):
        keys = set(self.exp.to_dict())
        expected_keys = {
            "activity_id", "early_start", "early_finish",
            "late_start", "late_finish", "total_float", "free_float", "is_critical",
        }
        assert keys == expected_keys


# ---------------------------------------------------------------------------
# BenchmarkExpectations serialization
# ---------------------------------------------------------------------------

class TestBenchmarkExpectationsSerialization:
    def setup_method(self):
        self.exp_act = ExpectedActivityResult(
            "A", "2026-01-05", "2026-01-07", "2026-01-05", "2026-01-07", 0, 0, True,
        )
        self.expectations = BenchmarkExpectations(
            is_valid=True,
            project_finish="2026-01-07",
            project_duration=3,
            critical_path_activity_ids=["A"],
            activities={"A": self.exp_act},
            warning_codes_present=["ENG-001"],
            divergence_flags=["CP-002"],
            tied_paths=True,
            convention="inclusive_day",
            baseline_captured=False,
        )

    def test_to_dict_is_valid(self):
        assert self.expectations.to_dict()["is_valid"] is True

    def test_to_dict_project_finish(self):
        assert self.expectations.to_dict()["project_finish"] == "2026-01-07"

    def test_to_dict_critical_path_ids(self):
        assert self.expectations.to_dict()["critical_path_activity_ids"] == ["A"]

    def test_to_dict_activities_nested(self):
        d = self.expectations.to_dict()["activities"]
        assert "A" in d
        assert d["A"]["total_float"] == 0

    def test_to_dict_baseline_captured(self):
        assert self.expectations.to_dict()["baseline_captured"] is False

    def test_to_dict_tied_paths(self):
        assert self.expectations.to_dict()["tied_paths"] is True


# ---------------------------------------------------------------------------
# BenchmarkDefinition serialization
# ---------------------------------------------------------------------------

class TestBenchmarkDefinitionSerialization:
    def test_bm001_to_dict_complete(self):
        d = BM_001.to_dict()
        assert d["metadata"]["benchmark_id"] == "BM-001"
        assert d["project_start"] == "2026-01-05"
        assert len(d["activities"]) == 3
        assert len(d["relationships"]) == 2
        assert d["convention"] == "inclusive_day"

    def test_bm001_activities_have_act_id(self):
        acts = BM_001.to_dict()["activities"]
        ids = [a["act_id"] for a in acts]
        assert set(ids) == {"A", "B", "C"}

    def test_bm001_relationships_structure(self):
        rels = BM_001.to_dict()["relationships"]
        for r in rels:
            assert "pred_id" in r
            assert "succ_id" in r
            assert "rel_type" in r

    def test_bm001_expectations_nested(self):
        exp = BM_001.to_dict()["expectations"]
        assert exp["is_valid"] is True
        assert exp["project_finish"] == "2026-01-13"
        assert "A" in exp["activities"]


# ---------------------------------------------------------------------------
# BenchmarkSuite serialization
# ---------------------------------------------------------------------------

class TestBenchmarkSuiteSerialization:
    def test_phase7_suite_id(self):
        assert PHASE7_SUITE.suite_id == "SUITE-P7-001"

    def test_suite_has_12_benchmarks(self):
        assert len(PHASE7_SUITE.benchmarks) == 12

    def test_suite_to_dict_complete(self):
        d = PHASE7_SUITE.to_dict()
        assert d["suite_id"] == "SUITE-P7-001"
        assert "benchmarks" in d
        assert "benchmark_ids" in d

    def test_suite_framework_version(self):
        assert PHASE7_SUITE.framework_version == BENCHMARK_FRAMEWORK_VERSION

    def test_suite_get_existing(self):
        bm = PHASE7_SUITE.get("BM-001")
        assert bm is not None
        assert bm.metadata.benchmark_id == "BM-001"

    def test_suite_get_missing_returns_none(self):
        assert PHASE7_SUITE.get("BM-NONEXISTENT") is None

    def test_suite_benchmark_ids_ordered(self):
        ids = PHASE7_SUITE.benchmark_ids()
        assert ids == ["BM-001", "BM-002", "BM-003", "BM-004", "BM-005",
                       "BM-006", "BM-007", "BM-008", "BM-009", "BM-010",
                       "BM-011", "BM-012"]

    def test_suite_add_and_retrieve(self):
        suite = BenchmarkSuite(
            suite_id="TEST", suite_version="1.0", description="test",
        )
        meta = BenchmarkMetadata(
            benchmark_id="BM-X", benchmark_version="1.0",
            description="X", category=BenchmarkCategory.EDGE_CASE,
        )
        bm = BenchmarkDefinition(
            metadata=meta, activities=[], relationships=[],
            project_start="2026-01-05",
        )
        suite.add(bm)
        assert suite.get("BM-X") is bm


# ---------------------------------------------------------------------------
# Benchmark framework version
# ---------------------------------------------------------------------------

class TestBenchmarkFrameworkVersion:
    def test_version_string_exists(self):
        assert BENCHMARK_FRAMEWORK_VERSION
        assert isinstance(BENCHMARK_FRAMEWORK_VERSION, str)

    def test_version_contains_phase7(self):
        assert "phase7" in BENCHMARK_FRAMEWORK_VERSION

    def test_suite_records_framework_version(self):
        d = PHASE7_SUITE.to_dict()
        assert d["framework_version"] == BENCHMARK_FRAMEWORK_VERSION


# ---------------------------------------------------------------------------
# Benchmark provenance fields
# ---------------------------------------------------------------------------

class TestBenchmarkProvenance:
    def test_all_benchmarks_synthetic_source(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.source == "synthetic", (
                f"{bm_id}: source must be 'synthetic' (no proprietary data)"
            )

    def test_all_benchmarks_have_version(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.benchmark_version, f"{bm_id}: benchmark_version must be set"

    def test_all_benchmarks_have_description(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert bm.metadata.description, f"{bm_id}: description must be set"

    def test_all_benchmarks_have_category(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert isinstance(bm.metadata.category, BenchmarkCategory), (
                f"{bm_id}: category must be a BenchmarkCategory"
            )

    def test_baseline_captured_flag_documented(self):
        for bm_id in PHASE7_SUITE.benchmark_ids():
            bm = PHASE7_SUITE.get(bm_id)
            assert isinstance(bm.expectations.baseline_captured, bool), (
                f"{bm_id}: baseline_captured must be bool"
            )


# ---------------------------------------------------------------------------
# Backward compatibility: AnalysisContext accepts new fields
# ---------------------------------------------------------------------------

class TestContextBackwardCompatibility:
    def test_context_has_benchmark_fields(self):
        from scheduleiq.cpm.context import AnalysisContext
        ctx = AnalysisContext()
        assert ctx.benchmark_id is None
        assert ctx.benchmark_version is None
        assert ctx.validation_provenance is None

    def test_context_to_dict_includes_benchmark_fields(self):
        from scheduleiq.cpm.context import AnalysisContext
        ctx = AnalysisContext()
        ctx.benchmark_id = "BM-001"
        ctx.benchmark_version = "1.0-phase7"
        d = ctx.to_dict()
        assert d["benchmark_id"] == "BM-001"
        assert d["benchmark_version"] == "1.0-phase7"
        assert d["validation_provenance"] is None

    def test_existing_context_fields_unchanged(self):
        from scheduleiq.cpm.context import AnalysisContext
        ctx = AnalysisContext(calendar_name="test_cal")
        d = ctx.to_dict()
        assert d["calendar_name"] == "test_cal"
        assert "engine_version" in d
        assert "ef_convention" in d
        assert "import_provenance" in d
